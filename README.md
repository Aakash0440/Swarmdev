# SwarmDev v3

> Simulate an enterprise development team — 1,000 AI agents building full projects in parallel from a single description.

---

## What it does

You write one sentence. SwarmDev spins up 1,000 specialist agents that coordinate like an ant colony — leaving signals in shared memory, building on each other's output — and delivers a complete, verified codebase.

```bash
python main.py "build a full-stack job board with React, FastAPI, and JWT auth"
```

That's it. The swarm handles everything else.

---

## How it works

```
Your description
      │
      ▼
Stack detection          ← React? Full-stack? ML? Python?
      │
      ▼
Project scaffolding      ← Writes correct boilerplate first (39 files for full-stack)
      │
      ▼
LLM task decomposition   ← Breaks project into 8–15 tasks with a dependency graph
      │
      ▼
Swarm execution          ← 10–12 specialist agents per task, running in parallel
      │
      ├── Architect · Frontend dev · UI designer
      ├── Backend dev · DB engineer · Security
      ├── ML engineer · DevOps · QA engineer
      │
      ▼
Verification             ← pytest + mypy + flake8 (Python) · eslint (JS/JSX)
      │
      ▼
Stigmergy memory         ← Agents deposit results; later agents build on them
      │
      ▼
Complete project on disk
```

---

## Supported stacks

| Stack | What gets built |
|-------|----------------|
| `react` | React 18 + Vite + Tailwind CSS + React Router |
| `fullstack` | React frontend + FastAPI backend + SQLAlchemy + JWT auth |
| `ml` | PyTorch / sklearn + MLflow tracking + FastAPI serving |
| `python` | FastAPI / CLI + SQLAlchemy + pytest |

---

## Setup

**1. Clone and install**
```bash
git clone https://github.com/your-username/swarmdev
cd swarmdev
pip install -r requirements.txt
```

**2. Add your API keys**
```bash
cp .env.example .env
```

Edit `.env`:
```env
GROQ_API_KEY=your_key_here        # free at console.groq.com
GOOGLE_API_KEY=your_key_here      # free at aistudio.google.com
GROQ_MODEL=llama-3.1-8b-instant   # recommended for free tier
```

**3. Run**
```bash
python server.py        # web UI at http://localhost:8000
# or
python cli.py           # interactive terminal
# or
python main.py "your project description"
```

---

## Running modes

### Web UI — recommended
```bash
python server.py
```
Open **http://localhost:8000** — submit tasks, watch live logs, browse generated files, view job history.

### CLI
```bash
python cli.py
```
Rich terminal interface with progress bars, live log streaming, and job history.

### Direct
```bash
# Custom description
python main.py "build a React dashboard for IoT sensor monitoring"

# Built-in demos
python main.py --demo react        # cat food e-commerce store
python main.py --demo fullstack    # task manager with auth
python main.py --demo ml           # sentiment analyser
python main.py --demo python       # Hacker News CLI tool
```

---

## Project structure

```
swarmdev_v3/
├── server.py               ← FastAPI server + web UI backend
├── cli.py                  ← Interactive terminal CLI
├── ui.html                 ← Web frontend (served automatically)
├── main.py                 ← Direct CLI entry point
├── requirements.txt
├── .env.example
│
├── swarm/
│   ├── agents.py           ← 1,000 role-based agents with language-aware codegen
│   ├── config.py           ← Stack detection, role definitions, skill mappings
│   ├── executor.py         ← Async swarm orchestration loop
│   ├── llm_router.py       ← Groq + Gemini dual-provider router with cooldowns
│   ├── memory.py           ← ChromaDB stigmergy store
│   ├── scaffolder.py       ← Project skeleton generator (React, fullstack, ML, Python)
│   ├── task_graph.py       ← LLM-powered DAG decomposer
│   └── verifier.py         ← Multi-language code verification
│
└── tests/
    └── test_swarm.py       ← 33 tests, all passing
```

---

## Staying within free tier limits

Both Groq and Gemini have generous free tiers. To avoid rate limits on longer runs:

In `.env`:
```env
GROQ_MODEL=llama-3.1-8b-instant    # 10x higher TPM than 70b on free tier
```

In `swarm/llm_router.py`:
```python
MAX_RETRIES  = 2      # default 3 — reduces wasted retry tokens
max_tokens   = 2000   # default 4096 — most files don't need more
```

Typical token usage per run:

| Project type | Tokens |
|-------------|--------|
| Python CLI | ~80–120k |
| React app | ~150–200k |
| Full-stack | ~200–300k |
| ML pipeline | ~200–280k |

---

## Sample tasks

**Low tokens — good for first runs**
```
Build a URL shortener API with FastAPI and SQLite. Features: custom slugs,
redirect endpoint, click tracking, list and delete endpoints. Include pytest tests.
```

```
Build a React expense tracker with Vite and Tailwind. Features: add income/expense
entries, running balance, category filter, monthly bar chart with Recharts,
localStorage persistence.
```

**Medium**
```
Build a full-stack markdown notes app. React 18 + FastAPI + SQLite. Features:
JWT auth, create/edit notes with markdown preview, tags, pin, search, soft delete.
Include pytest tests and docker-compose.
```

**Ambitious**
```
Build a real-time chat app. React + FastAPI + WebSockets + SQLAlchemy. Features:
JWT auth, chat rooms, online presence, message history, emoji reactions, file uploads,
Redis pub/sub for multi-instance broadcasting. Include pytest tests and docker-compose.
```

---

## Tech stack

- **LLM** — Groq (llama-3.1-8b-instant / llama-3.3-70b-versatile) · Google Gemini
- **Memory** — ChromaDB vector store
- **Verification** — pytest · mypy · flake8 · eslint
- **Server** — FastAPI + uvicorn
- **CLI** — Click + Rich
- **Async** — Python asyncio throughout

---

## License

MIT