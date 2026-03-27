"""
TaskGraph — decomposes a high-level project description into a DAG of tasks.
Uses LLM to produce stack-aware task breakdowns (React, FastAPI, ML, etc.).
"""
import json
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    DONE      = "done"
    FAILED    = "failed"
    SKIPPED   = "skipped"


class TaskPriority(Enum):
    CRITICAL = 1
    HIGH     = 2
    NORMAL   = 3
    LOW      = 4


@dataclass
class Task:
    id: str
    name: str
    description: str
    skill: str                          # e.g. "components", "api", "ml_model"
    role: str                           # preferred agent role
    priority: TaskPriority = TaskPriority.NORMAL
    dependencies: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    assigned_agents: list[str] = field(default_factory=list)
    output_files: list[str] = field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    retries: int = 0

    def is_ready(self, completed_ids: set[str]) -> bool:
        return all(dep in completed_ids for dep in self.dependencies)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "skill": self.skill,
            "role": self.role,
            "priority": self.priority.value,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "output_files": self.output_files,
        }


class TaskGraph:
    """
    Decomposes a project description into an ordered DAG of tasks.
    Nodes are Tasks; edges are dependency relationships.
    """

    DECOMPOSE_SYSTEM = """You are a senior software architect decomposing a project into an ordered task graph.
Return ONLY a JSON array of task objects. No markdown, no explanation.

Each task object must have exactly these fields:
{
  "name": "short task name",
  "description": "detailed description of what to implement",
  "skill": "one of: scaffolding|components|routing|state|styling|api|database|auth|testing|ml_model|deployment|docs|mobile",
  "role": "one of: architect|frontend_dev|ui_designer|backend_dev|db_engineer|ml_engineer|data_engineer|qa_engineer|devops|security|documenter|api_integrator",
  "priority": 1-4,
  "dependencies": ["name of task this depends on", ...]
}

Rules:
- 8-15 tasks total
- Dependencies must use exact task names from the same list
- Order from foundational → feature → integration → testing → docs
- Be specific: name the files, components, routes, models to create"""

    def __init__(self, llm_client, stack: str = "python"):
        self.llm = llm_client
        self.stack = stack
        self.tasks: dict[str, Task] = {}

    # ── Build graph from description ──────────────────────────────────────────
    async def build(self, description: str, project_name: str) -> list[Task]:
        prompt = self._build_prompt(description, project_name)
        logger.info("Decomposing project into task graph…")
        try:
            raw = await self.llm.complete(prompt, self.DECOMPOSE_SYSTEM)
            raw = raw.strip().replace("```json", "").replace("```", "").strip()
            task_defs = json.loads(raw)
        except Exception as e:
            logger.error(f"Task decomposition failed: {e}. Using fallback.")
            task_defs = self._fallback_tasks(description)

        tasks = self._build_tasks(task_defs)
        logger.info(f"Task graph built: {len(tasks)} tasks")
        return tasks

    def _build_prompt(self, description: str, project_name: str) -> str:
        stack_hints = {
            "react": "React 18 + Vite + Tailwind CSS + React Router v6. No backend needed.",
            "fullstack": "React 18 frontend + FastAPI backend + SQLAlchemy ORM + PostgreSQL/SQLite.",
            "ml": "PyTorch / scikit-learn model + FastAPI serving endpoint + MLflow tracking.",
            "python": "Python 3.11+ CLI/library/backend with pytest tests.",
            "mobile": "React Native + Expo. Cross-platform iOS/Android.",
        }
        hint = stack_hints.get(self.stack, stack_hints["python"])
        return f"""Project: {project_name}
Stack: {hint}
Description: {description}

Decompose this into 8-15 specific implementation tasks."""

    def _build_tasks(self, task_defs: list[dict]) -> list[Task]:
        name_to_id: dict[str, str] = {}
        tasks = []
        for td in task_defs:
            tid = str(uuid.uuid4())[:8]
            name_to_id[td["name"]] = tid
            t = Task(
                id=tid,
                name=td.get("name", f"task_{tid}"),
                description=td.get("description", ""),
                skill=td.get("skill", "api"),
                role=td.get("role", "backend_dev"),
                priority=TaskPriority(td.get("priority", 3)),
                dependencies=[],   # resolved below
            )
            self.tasks[tid] = t
            tasks.append(t)

        # Resolve dependency names → IDs
        for td, task in zip(task_defs, tasks):
            for dep_name in td.get("dependencies", []):
                dep_id = name_to_id.get(dep_name)
                if dep_id and dep_id != task.id:
                    task.dependencies.append(dep_id)

        return tasks

    # ── Ready / completed helpers ─────────────────────────────────────────────
    def ready_tasks(self, completed_ids: set[str]) -> list[Task]:
        return [
            t for t in self.tasks.values()
            if t.status == TaskStatus.PENDING
            and t.id not in completed_ids
            and t.is_ready(completed_ids)
        ]

    def all_done(self) -> bool:
        return all(
            t.status in (TaskStatus.DONE, TaskStatus.SKIPPED, TaskStatus.FAILED)
            for t in self.tasks.values()
        )

    def summary(self) -> dict:
        counts = {s.value: 0 for s in TaskStatus}
        for t in self.tasks.values():
            counts[t.status.value] += 1
        return counts

    # ── Fallback task list ────────────────────────────────────────────────────
    def _fallback_tasks(self, description: str) -> list[dict]:
        base = [
            {"name": "Project setup", "description": f"Scaffold the project structure for: {description}",
             "skill": "scaffolding", "role": "architect", "priority": 1, "dependencies": []},
            {"name": "Core implementation", "description": f"Implement core logic for: {description}",
             "skill": "api", "role": "backend_dev", "priority": 2, "dependencies": ["Project setup"]},
            {"name": "Tests", "description": "Write unit and integration tests",
             "skill": "testing", "role": "qa_engineer", "priority": 3, "dependencies": ["Core implementation"]},
            {"name": "Documentation", "description": "Write README and inline docs",
             "skill": "docs", "role": "documenter", "priority": 4, "dependencies": ["Core implementation"]},
        ]
        if self.stack in ("react", "fullstack", "mobile"):
            base.insert(1, {
                "name": "UI components", "description": "Build main React components",
                "skill": "components", "role": "frontend_dev", "priority": 2, "dependencies": ["Project setup"]
            })
        return base
