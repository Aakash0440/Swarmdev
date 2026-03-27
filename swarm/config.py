"""
SwarmConfig — central settings for the enterprise swarm.
Supports Python, React/JS/TS, Full-Stack, ML/AI projects.
"""
from dataclasses import dataclass, field
from typing import Optional


# ── Language / stack detection keywords ──────────────────────────────────────
STACK_KEYWORDS = {
    "react":      ["react", "jsx", "tsx", "next", "vite", "tailwind", "frontend", "ui", "component"],
    "fullstack":  ["fullstack", "full stack", "full-stack", "fastapi", "express", "api", "backend", "database"],
    "ml":         ["machine learning", "ml", "ai", "model", "train", "pytorch", "tensorflow", "sklearn", "neural"],
    "python":     ["python", "cli", "script", "automation", "django", "flask", "fastapi"],
    "mobile":     ["react native", "expo", "mobile", "ios", "android"],
}

# ── Agent role definitions ────────────────────────────────────────────────────
AGENT_ROLES = {
    # Universal
    "architect":       "System design, high-level structure, technology decisions",
    "tech_lead":       "Code review, quality gates, integration oversight",
    "devops":          "CI/CD, Docker, deployment, environment config",
    "qa_engineer":     "Testing strategy, test writing, bug triage",
    "security":        "Security audit, auth flows, vulnerability scanning",
    "documenter":      "README, API docs, inline comments, user guides",

    # Frontend / React
    "frontend_dev":    "React components, hooks, state management, UI logic",
    "ui_designer":     "Tailwind styling, layout, accessibility, design tokens",
    "react_native_dev":"React Native / Expo mobile screens",

    # Backend / Python
    "backend_dev":     "FastAPI/Django/Flask routes, business logic, middleware",
    "db_engineer":     "Database schema, migrations, ORM models, queries",
    "api_integrator":  "Third-party APIs, webhooks, auth integrations",

    # ML / AI
    "ml_engineer":     "Model architecture, training loops, evaluation metrics",
    "data_engineer":   "Data pipelines, feature engineering, ETL",
    "mlops":           "Model serving, experiment tracking, deployment",
}

# ── Skill → roles mapping (which roles can work on which skill areas) ─────────
SKILL_ROLES = {
    "scaffolding":     ["architect", "devops"],
    "components":      ["frontend_dev", "ui_designer"],
    "routing":         ["frontend_dev", "backend_dev"],
    "state":           ["frontend_dev", "tech_lead"],
    "styling":         ["ui_designer", "frontend_dev"],
    "api":             ["backend_dev", "api_integrator"],
    "database":        ["db_engineer", "backend_dev"],
    "auth":            ["security", "backend_dev"],
    "testing":         ["qa_engineer", "tech_lead"],
    "ml_model":        ["ml_engineer", "data_engineer"],
    "deployment":      ["devops", "mlops"],
    "docs":            ["documenter", "tech_lead"],
    "mobile":          ["react_native_dev", "frontend_dev"],
}


@dataclass
class SwarmConfig:
    # ── LLM backend ──
    llm_provider: str = "dual"          # dual | groq | gemini | openai | ollama
    model_name: str = "llama-3.3-70b-versatile"
    api_key: Optional[str] = None       # used for single-provider modes

    # ── Dual-provider keys (used when llm_provider == "dual") ──
    groq_api_key:   Optional[str] = None   # overrides env GROQ_API_KEY
    gemini_api_key: Optional[str] = None   # overrides env GOOGLE_API_KEY

    # ── Model names per provider (dual mode) ──
    groq_model:   str = "llama-3.3-70b-versatile"
    gemini_model: str = "gemini-2.0-flash"

    temperature: float = 0.3
    max_tokens: int = 4096

    # ── Swarm scale ──
    total_agents: int = 1000
    agents_per_task: int = 10           # parallel agents per task node
    max_concurrent_tasks: int = 12      # concurrent task nodes running

    # ── Quality gates ──
    min_confidence: float = 0.75        # agent won't submit below this
    max_retries: int = 3                # retries per task before escalation
    verification_enabled: bool = True   # run verifier after each task

    # ── Memory / stigmergy ──
    use_chroma: bool = True             # ChromaDB for long-term memory
    chroma_path: str = "./chroma_db"
    pheromone_decay: float = 0.05       # how fast old signals fade

    # ── Output ──
    output_dir: str = "./output"
    log_level: str = "INFO"

    # ── Runtime (set automatically) ──
    detected_stack: str = "python"      # auto-detected from task description
    project_name: str = "swarm_project"
    extra_roles: list = field(default_factory=list)


def detect_stack(description: str) -> str:
    """Detect the project stack from the task description."""
    desc_lower = description.lower()
    scores = {stack: 0 for stack in STACK_KEYWORDS}
    for stack, keywords in STACK_KEYWORDS.items():
        for kw in keywords:
            if kw in desc_lower:
                scores[stack] += 1
    # fullstack wins if both react + backend signals present
    if scores["react"] >= 1 and scores["fullstack"] >= 1:
        return "fullstack"
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "python"


def get_roles_for_stack(stack: str) -> list[str]:
    """Return the default agent roles for a given stack."""
    base = ["architect", "tech_lead", "qa_engineer", "documenter", "devops"]
    extras = {
        "react":      ["frontend_dev", "ui_designer", "api_integrator"],
        "fullstack":  ["frontend_dev", "ui_designer", "backend_dev", "db_engineer", "security"],
        "ml":         ["ml_engineer", "data_engineer", "mlops", "backend_dev"],
        "python":     ["backend_dev", "db_engineer", "api_integrator"],
        "mobile":     ["react_native_dev", "frontend_dev", "backend_dev"],
    }
    return base + extras.get(stack, extras["python"])
