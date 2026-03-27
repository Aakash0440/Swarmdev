"""
Agents — the individual workers of the swarm.
Each agent has a role, skill set, and LLM brain.
Language-aware: generates Python, JS/JSX/TS, SQL, YAML correctly.
"""
import asyncio
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from .config import AGENT_ROLES

logger = logging.getLogger(__name__)


class AgentState(Enum):
    IDLE    = "idle"
    WORKING = "working"
    DONE    = "done"
    FAILED  = "failed"
    RESTING = "resting"


# ── Code-generation system prompts per language/role ─────────────────────────
ROLE_SYSTEM_PROMPTS: dict[str, str] = {
    "frontend_dev": """You are a senior React developer. Write modern React 18 code using:
- Functional components with hooks
- React Router v6 for navigation
- Tailwind CSS for styling
- Axios for API calls
- Proper error boundaries and loading states
Output ONLY the file content. No explanations.""",

    "ui_designer": """You are a UI/UX engineer specialising in Tailwind CSS and accessible design.
Create beautiful, responsive React components. Use Tailwind utility classes.
Ensure WCAG 2.1 AA accessibility. Output ONLY the JSX file content.""",

    "backend_dev": """You are a senior backend engineer. Write clean Python using FastAPI.
- Use Pydantic models for request/response validation
- Proper HTTP status codes and error handling
- Dependency injection for database sessions
- Async route handlers
Output ONLY the Python file content.""",

    "db_engineer": """You are a database engineer. Write SQLAlchemy 2.0 ORM models and Alembic migrations.
- Proper relationships (ForeignKey, relationship())
- Indexes on frequently-queried columns
- Soft-delete patterns where appropriate
Output ONLY the Python file content.""",

    "ml_engineer": """You are a senior ML engineer. Write production-quality PyTorch/sklearn code.
- Proper train/val/test splits
- Logging with MLflow
- Model checkpointing
- Clear docstrings
Output ONLY the Python file content.""",

    "data_engineer": """You are a data engineer. Write efficient pandas/numpy data pipelines.
- Handle missing values and outliers
- Type validation
- Efficient vectorised operations
Output ONLY the Python file content.""",

    "qa_engineer": """You are a QA engineer. Write comprehensive tests using pytest (Python) or vitest (JS/TS).
- Unit tests for each function
- Integration tests for API routes
- Edge cases and error paths
- Minimum 80% coverage
Output ONLY the test file content.""",

    "devops": """You are a DevOps engineer. Write Docker, docker-compose, GitHub Actions, or Makefile configs.
- Multi-stage Docker builds
- Environment variable handling
- Health checks
Output ONLY the config file content.""",

    "security": """You are a security engineer. Implement authentication and authorisation.
- JWT tokens (python-jose)
- Password hashing (passlib/bcrypt)
- RBAC patterns
- Input validation
Output ONLY the Python file content.""",

    "documenter": """You are a technical writer. Write clear, professional documentation.
- Concise README with setup steps
- API endpoint documentation
- Code examples
- Troubleshooting section
Output ONLY the markdown content.""",

    "react_native_dev": """You are a React Native / Expo developer.
Write cross-platform mobile screens using Expo SDK and React Navigation.
Output ONLY the file content.""",

    "architect": """You are a software architect. Design clean system structures.
Write configuration files, entry points, and architectural scaffolding.
Output ONLY the file content.""",

    "api_integrator": """You are an API integration specialist. Write clean service layers for external APIs.
Use httpx/aiohttp for async HTTP. Proper retry logic and error handling.
Output ONLY the Python file content.""",

    "mlops": """You are an MLOps engineer. Write model serving, experiment tracking, and deployment configs.
Use FastAPI for serving, MLflow for tracking, Docker for containerisation.
Output ONLY the file content.""",

    "tech_lead": """You are a tech lead. Review and refine implementation code.
Write clean, idiomatic code following the project's existing patterns.
Output ONLY the file content.""",
}

# ── File extension per skill/stack ────────────────────────────────────────────
SKILL_EXTENSION: dict[str, str] = {
    "components": ".jsx",
    "routing":    ".jsx",
    "state":      ".js",
    "styling":    ".css",
    "mobile":     ".jsx",
    "api":        ".py",
    "database":   ".py",
    "auth":       ".py",
    "ml_model":   ".py",
    "deployment": ".yml",
    "docs":       ".md",
    "testing":    ".py",   # overridden for JS stacks below
    "scaffolding": ".py",
}


@dataclass
class Agent:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    role: str = "backend_dev"
    stack: str = "python"
    specialisation: str = ""
    state: AgentState = AgentState.IDLE
    tasks_completed: int = 0
    confidence: float = 1.0
    energy: float = 1.0
    _llm = None           # injected by executor
    _memory = None        # injected by executor

    # ── LLM injection ─────────────────────────────────────────────────────────
    def inject(self, llm, memory):
        self._llm = llm
        self._memory = memory

    # ── Core work loop ────────────────────────────────────────────────────────
    async def work(self, task, output_dir: str) -> dict:
        self.state = AgentState.WORKING
        start = time.time()
        logger.info(f"Agent {self.id} ({self.role}) → task '{task.name}'")

        try:
            result = await self._execute_task(task, output_dir)
            self.tasks_completed += 1
            self.state = AgentState.DONE
            elapsed = time.time() - start
            logger.info(f"Agent {self.id} ✓ '{task.name}' in {elapsed:.1f}s")
            return result
        except Exception as e:
            self.state = AgentState.FAILED
            logger.error(f"Agent {self.id} ✗ '{task.name}': {e}")
            return {"success": False, "error": str(e)}

    async def _execute_task(self, task, output_dir: str) -> dict:
        # 1. Gather context from memory
        context = await self._gather_context(task)

        # 2. Generate code / content
        content = await self._generate(task, context)

        # 3. Determine output file path
        file_path = self._resolve_output_path(task, output_dir)

        # 4. Write file
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        Path(file_path).write_text(content, encoding="utf-8")

        # 5. Deposit result in memory
        await self._memory.deposit(
            key=f"task:{task.id}:result",
            value={"file": file_path, "content": content[:500]},
            strength=self.confidence,
            agent_id=self.id,
        )

        task.output_files.append(file_path)
        return {"success": True, "file": file_path, "agent": self.id}

    # ── Code generation ───────────────────────────────────────────────────────
    async def _generate(self, task, context: str) -> str:
        system = ROLE_SYSTEM_PROMPTS.get(self.role, ROLE_SYSTEM_PROMPTS["backend_dev"])
        prompt = self._build_prompt(task, context)
        # Pass skill so LLMRouter can route Groq vs Gemini optimally
        if hasattr(self._llm, "complete") and "skill" in self._llm.complete.__code__.co_varnames:
            content = await self._llm.complete(prompt, system, skill=task.skill)
        else:
            content = await self._llm.complete(prompt, system)

        # Strip accidental markdown fences
        for fence in ("```jsx", "```tsx", "```js", "```ts", "```python", "```py",
                       "```css", "```yaml", "```markdown", "```md", "```"):
            content = content.replace(fence, "")
        return content.strip()

    def _build_prompt(self, task, context: str) -> str:
        ext = self._get_extension(task.skill)
        lang_hint = {
            ".jsx": "React JSX (ES modules, no require())",
            ".tsx": "TypeScript React (strict mode)",
            ".js":  "ES2022 JavaScript (ES modules)",
            ".py":  "Python 3.11+",
            ".css": "CSS / Tailwind",
            ".yml": "YAML",
            ".md":  "Markdown",
        }.get(ext, "the appropriate language")

        return f"""Task: {task.name}
Description: {task.description}
Stack: {self.stack}
Output language: {lang_hint}
Your role: {AGENT_ROLES.get(self.role, self.role)}

{f'Relevant context from other agents:{chr(10)}{context}' if context else ''}

Write production-quality code for this task. Be complete and specific.
Include all imports. Handle errors. Follow best practices for {lang_hint}."""

    # ── Path resolution ───────────────────────────────────────────────────────
    def _resolve_output_path(self, task, output_dir: str) -> str:
        ext = self._get_extension(task.skill)
        safe_name = task.name.lower().replace(" ", "_").replace("/", "_")

        if self.stack in ("react", "fullstack") and ext in (".jsx", ".tsx", ".js", ".css"):
            sub = "frontend/src"
            if task.skill == "components":
                sub += "/components"
            elif task.skill == "routing":
                sub += "/pages"
            elif task.skill == "state":
                sub += "/store"
            elif task.skill == "styling":
                sub += "/styles"
            path = os.path.join(output_dir, sub, f"{safe_name}{ext}")
        elif self.stack == "fullstack" and task.skill in ("api", "database", "auth"):
            path = os.path.join(output_dir, "backend", "api", f"{safe_name}{ext}")
        elif self.stack == "ml":
            if task.skill == "ml_model":
                path = os.path.join(output_dir, "src", "models", f"{safe_name}{ext}")
            elif task.skill == "testing":
                path = os.path.join(output_dir, "tests", f"test_{safe_name}{ext}")
            else:
                path = os.path.join(output_dir, "src", f"{safe_name}{ext}")
        elif task.skill == "testing":
            path = os.path.join(output_dir, "tests", f"test_{safe_name}{ext}")
        elif task.skill == "docs":
            path = os.path.join(output_dir, f"{safe_name}.md")
        elif task.skill == "deployment":
            path = os.path.join(output_dir, f"{safe_name}.yml")
        else:
            path = os.path.join(output_dir, "src", f"{safe_name}{ext}")

        return path

    def _get_extension(self, skill: str) -> str:
        if self.stack in ("react", "fullstack", "mobile"):
            overrides = {"testing": ".jsx", "components": ".jsx", "routing": ".jsx", "state": ".js"}
            if skill in overrides:
                return overrides[skill]
        return SKILL_EXTENSION.get(skill, ".py")

    # ── Memory helpers ────────────────────────────────────────────────────────
    async def _gather_context(self, task) -> str:
        if not self._memory:
            return ""
        results = await self._memory.search(task.description, n=3)
        snippets = []
        for r in results:
            v = r.get("value", "")
            if isinstance(v, dict):
                snippets.append(f"- {v.get('file', '')}: {str(v.get('content', ''))[:200]}")
            elif isinstance(v, str):
                snippets.append(f"- {v[:200]}")
        return "\n".join(snippets)


# ── Agent Pool ────────────────────────────────────────────────────────────────
class AgentPool:
    """Manages a pool of N agents across all roles for a given stack."""

    def __init__(self, total: int, stack: str, llm, memory):
        self.total = total
        self.stack = stack
        self.llm = llm
        self.memory = memory
        self.agents: list[Agent] = []
        self._build_pool()

    def _build_pool(self):
        from .config import get_roles_for_stack
        roles = get_roles_for_stack(self.stack)
        agents_per_role = max(1, self.total // len(roles))
        for role in roles:
            for _ in range(agents_per_role):
                a = Agent(role=role, stack=self.stack)
                a.inject(self.llm, self.memory)
                self.agents.append(a)
        logger.info(f"Agent pool: {len(self.agents)} agents across {len(roles)} roles (stack={self.stack})")

    def get_agents_for_task(self, task, n: int = 10) -> list[Agent]:
        """Return the best N agents for a task based on role match."""
        from .config import SKILL_ROLES
        preferred_roles = SKILL_ROLES.get(task.skill, [task.role])
        matched = [a for a in self.agents if a.role in preferred_roles and a.state == AgentState.IDLE]
        unmatched = [a for a in self.agents if a.role not in preferred_roles and a.state == AgentState.IDLE]
        pool = matched[:n] or unmatched[:n] or self.agents[:n]
        return pool[:n]

    def idle_count(self) -> int:
        return sum(1 for a in self.agents if a.state == AgentState.IDLE)

    def stats(self) -> dict:
        from collections import Counter
        return {
            "total": len(self.agents),
            "by_state": dict(Counter(a.state.value for a in self.agents)),
            "tasks_completed": sum(a.tasks_completed for a in self.agents),
        }
