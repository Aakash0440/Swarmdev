"""
Executor — the async orchestration engine.
Runs the swarm loop: scaffold → decompose → dispatch agents → verify → repeat.
"""
import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Optional

from .agents import AgentPool, AgentState
from .config import SwarmConfig, detect_stack, get_roles_for_stack
from .llm_client import LLMClient
from .llm_router import LLMRouter
from .memory import StigmergyMemory
from .scaffolder import ProjectScaffolder
from .task_graph import TaskGraph, TaskStatus
from .verifier import Verifier

logger = logging.getLogger(__name__)


class SwarmExecutor:
    """
    Orchestrates 1000-agent swarm across a project task graph.

    Flow:
      1. Auto-detect stack from description
      2. Scaffold project skeleton
      3. LLM decomposes description → DAG of tasks
      4. Loop: assign ready tasks to agent groups → run in parallel
      5. Verify each task → retry or escalate on failure
      6. Deposit results in stigmergy memory
    """

    def __init__(self, config: Optional[SwarmConfig] = None):
        self.cfg = config or SwarmConfig()
        self._setup_logging()
        self.llm = self._build_llm_client()
        self.memory = StigmergyMemory(
            persist_path=self.cfg.chroma_path,
            decay_rate=self.cfg.pheromone_decay,
            use_chroma=self.cfg.use_chroma,
        )
        self.verifier = Verifier(min_score=self.cfg.min_confidence)
        self._pool: Optional[AgentPool] = None
        self._graph: Optional[TaskGraph] = None
        self._output_dir: str = ""
        self._start_time: float = 0

    # ── LLM factory ──────────────────────────────────────────────────────────
    def _build_llm_client(self):
        """Return an LLMRouter (dual) or plain LLMClient depending on config."""
        cfg = self.cfg
        if cfg.llm_provider == "dual":
            return LLMRouter(
                groq_key=cfg.groq_api_key,
                gemini_key=cfg.gemini_api_key,
                groq_model=cfg.groq_model,
                gemini_model=cfg.gemini_model,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
            )
        return LLMClient(
            provider=cfg.llm_provider,
            model=cfg.model_name,
            api_key=cfg.api_key,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )

    # ── Public API ────────────────────────────────────────────────────────────
    async def run(self, description: str, project_name: Optional[str] = None) -> dict:
        """
        Main entry point. Give it a project description; get a built project.

        Returns a summary dict with paths, stats, and status.
        """
        self._start_time = time.time()
        project_name = project_name or self._slugify(description)
        self.cfg.project_name = project_name

        # 1. Detect stack
        stack = detect_stack(description)
        self.cfg.detected_stack = stack
        logger.info(f"▶ SwarmDev | project='{project_name}' | stack={stack}")

        # 2. Set output directory
        self._output_dir = os.path.join(self.cfg.output_dir, project_name)
        Path(self._output_dir).mkdir(parents=True, exist_ok=True)

        # 3. Scaffold project skeleton
        logger.info("⚙  Scaffolding project skeleton…")
        scaffolder = ProjectScaffolder(self.cfg.output_dir, project_name, stack)
        scaffolded_files = scaffolder.scaffold()
        logger.info(f"   {len(scaffolded_files)} files scaffolded")

        # 4. Build agent pool
        self._pool = AgentPool(
            total=self.cfg.total_agents,
            stack=stack,
            llm=self.llm,
            memory=self.memory,
        )

        # 5. Decompose into task graph
        logger.info("🧠 Decomposing into task graph…")
        self._graph = TaskGraph(self.llm, stack=stack)
        tasks = await self._graph.build(description, project_name)
        logger.info(f"   {len(tasks)} tasks in graph")

        # 6. Execute swarm loop
        logger.info(f"🐝 Swarm loop starting ({self._pool.idle_count()} agents ready)…")
        await self._swarm_loop()

        # 7. Return summary
        elapsed = time.time() - self._start_time
        summary = self._build_summary(elapsed)
        self._print_summary(summary)
        return summary

    # ── Swarm loop ────────────────────────────────────────────────────────────
    async def _swarm_loop(self):
        completed_ids: set[str] = set()
        iteration = 0

        while not self._graph.all_done():
            iteration += 1
            ready = self._graph.ready_tasks(completed_ids)

            if not ready:
                # Nothing ready yet — check for true deadlock vs. cooldown stall
                pending = [t for t in self._graph.tasks.values() if t.status == TaskStatus.PENDING]
                if not pending:
                    break

                # If router has a cooldown active, wait for it to lift
                wait_secs = self._router_cooldown_remaining()
                if wait_secs > 0:
                    logger.info(
                        f"⏳ Both providers on cooldown — "
                        f"sleeping {wait_secs:.0f}s before retrying failed tasks…"
                    )
                    await asyncio.sleep(wait_secs + 1)
                    # Re-queue FAILED tasks as PENDING so they get retried
                    self._requeue_failed_tasks()
                else:
                    logger.warning(f"No ready tasks (iteration {iteration}), waiting…")
                    await asyncio.sleep(2)
                continue

            # Limit concurrent task groups
            batch = ready[:self.cfg.max_concurrent_tasks]
            logger.info(f"  Iteration {iteration}: {len(batch)} tasks ready, running in parallel")

            # Mark all as running before we dispatch
            for task in batch:
                task.status = TaskStatus.RUNNING

            # Dispatch each task to its agent group concurrently
            results = await asyncio.gather(
                *[self._run_task(task) for task in batch],
                return_exceptions=True,
            )

            for task, result in zip(batch, results):
                if isinstance(result, Exception):
                    task.status = TaskStatus.FAILED
                    task.error = str(result)
                    logger.error(f"Task '{task.name}' raised exception: {result}")
                elif result.get("success"):
                    task.status = TaskStatus.DONE
                    completed_ids.add(task.id)
                else:
                    task.status = TaskStatus.FAILED
                    task.error = result.get("error", "unknown")

            # Periodic memory decay
            if iteration % 5 == 0:
                await self.memory.decay()

    # ── Single task execution ─────────────────────────────────────────────────
    async def _run_task(self, task) -> dict:
        agents = self._pool.get_agents_for_task(task, n=self.cfg.agents_per_task)
        if not agents:
            return {"success": False, "error": "No agents available"}

        # Lead agent does the work; others review in parallel
        lead = agents[0]
        reviewers = agents[1:min(3, len(agents))]

        # Lead generates the implementation
        result = await lead.work(task, self._output_dir)
        if not result.get("success"):
            # Retry with a different agent
            for retry_agent in reviewers:
                result = await retry_agent.work(task, self._output_dir)
                if result.get("success"):
                    break

        if not result.get("success"):
            return result

        # Verification gate
        if self.cfg.verification_enabled and task.output_files:
            ver_result = await self.verifier.verify_task(task)
            logger.info(f"   verify '{task.name}': {ver_result}")

            if not ver_result.passed and task.retries < self.cfg.max_retries:
                task.retries += 1
                logger.info(f"   retrying '{task.name}' (attempt {task.retries})…")
                # Deposit failure context so next agent can fix it
                await self.memory.deposit(
                    key=f"task:{task.id}:issues",
                    value={"issues": ver_result.issues},
                    agent_id=lead.id,
                )
                task.status = TaskStatus.PENDING
                task.output_files.clear()
                return await self._run_task(task)

        return result

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _router_cooldown_remaining(self) -> float:
        """Return seconds until at least one LLM provider is available, or 0."""
        if not hasattr(self.llm, "stats"):
            return 0.0
        import time
        slots = []
        if hasattr(self.llm, "groq_slot") and self.llm.groq_slot:
            slots.append(self.llm.groq_slot)
        if hasattr(self.llm, "gemini_slot") and self.llm.gemini_slot:
            slots.append(self.llm.gemini_slot)
        if not slots or any(s.available for s in slots):
            return 0.0
        return min(s.cooldown_remaining for s in slots)

    def _requeue_failed_tasks(self):
        """Re-queue recently-failed tasks as PENDING so the loop retries them."""
        requeued = 0
        for task in self._graph.tasks.values():
            if task.status == TaskStatus.FAILED and task.retries < self.cfg.max_retries:
                task.status = TaskStatus.PENDING
                task.output_files.clear()
                requeued += 1
        if requeued:
            logger.info(f"↩️  Re-queued {requeued} failed tasks for retry after cooldown")

    def _build_summary(self, elapsed: float) -> dict:
        all_files = []
        for task in self._graph.tasks.values():
            all_files.extend(task.output_files)

        return {
            "project": self.cfg.project_name,
            "stack": self.cfg.detected_stack,
            "output_dir": self._output_dir,
            "elapsed_seconds": round(elapsed, 1),
            "tasks": self._graph.summary(),
            "agents": self._pool.stats(),
            "files_created": len(all_files),
            "file_list": all_files,
            "tokens_used": self.llm.total_tokens_used,
        }

    def _print_summary(self, s: dict):
        print("\n" + "═" * 60)
        print(f"  SwarmDev Complete — {s['project']} ({s['stack']})")
        print("═" * 60)
        print(f"  ⏱  Elapsed:      {s['elapsed_seconds']}s")
        print(f"  📁  Output:       {s['output_dir']}")
        print(f"  📄  Files:        {s['files_created']}")
        print(f"  🐝  Agents used:  {s['agents']['tasks_completed']} tasks completed")
        print(f"  🧮  Tokens used:  {s['tokens_used']:,}")
        print(f"  ✅  Task status:  {s['tasks']}")
        print("═" * 60)

    @staticmethod
    def _slugify(text: str) -> str:
        import re
        slug = re.sub(r"[^a-z0-9]+", "_", text.lower())[:40]
        return slug.strip("_") or "swarm_project"

    @staticmethod
    def _setup_logging():
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
