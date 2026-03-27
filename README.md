# SwarmDev v3

1,000-agent swarm intelligence for code generation.
Supports React, Full-Stack, ML/AI, and Python projects.

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env with your keys
```

---

## Running

### Web UI (recommended)
```bash
python server.py
```
Open http://localhost:8000

### CLI
```bash
python cli.py
```

### Direct
```bash
python main.py "build a React cat food store"
python main.py --demo react
python main.py --demo fullstack
python main.py --demo ml
```

---

## Folder structure

```
swarmdev_v3/
├── server.py     ← FastAPI server + web UI backend
├── cli.py        ← Interactive terminal CLI
├── ui.html       ← Web frontend (auto-served at localhost:8000)
├── main.py       ← Direct entry point
├── .env.example
├── swarm/        ← Core engine (agents, executor, scaffolder…)
└── tests/
```

---

## Token saving (free tier)

In `.env`:
```
GROQ_MODEL=llama-3.1-8b-instant
```

In `swarm/llm_router.py`:
```python
MAX_RETRIES = 2
max_tokens: int = 2000
```
