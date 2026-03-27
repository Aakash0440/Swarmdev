"""
SwarmDev API Server — FastAPI backend for the web UI and CLI.
Run: python server.py
"""
import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("swarmdev.server")

app = FastAPI(title="SwarmDev API", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory job store ───────────────────────────────────────────────────────
JOBS: dict[str, dict] = {}
HISTORY_FILE = Path("./swarmdev_history.json")

DEMO_DESCRIPTIONS = {
    "collab_editor": "Build a Real-Time Distributed Collaborative Code Editor. Features: WebSocket-based real-time sync, operational transformation for conflict resolution, Monaco editor integration, JWT auth, room/session management, Redis pub/sub.",
    "ecommerce":     "Build a full E-Commerce platform with product listings, cart, checkout, Stripe payments, admin dashboard, inventory management, and order tracking.",
    "ml_pipeline":   "Build a Machine Learning training pipeline with data ingestion, preprocessing, PyTorch model training, MLflow experiment tracking, and model serving via FastAPI.",
    "rest_api":      "Build a production REST API with JWT authentication, RBAC, PostgreSQL database, Alembic migrations, rate limiting, and OpenAPI documentation.",
}


# ── Persistence helpers ───────────────────────────────────────────────────────

def _load_history():
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            JOBS.update(data)
            logger.info(f"Loaded {len(data)} jobs from history")
        except Exception as e:
            logger.warning(f"Could not load history: {e}")


def _save_history():
    try:
        HISTORY_FILE.write_text(json.dumps(JOBS, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not save history: {e}")


def _append_log(job_id: str, level: str, msg: str):
    if job_id in JOBS:
        JOBS[job_id]["logs"].append({
            "ts":    datetime.utcnow().isoformat(),
            "level": level,
            "msg":   msg,
        })


# ── Schemas ───────────────────────────────────────────────────────────────────

class JobRequest(BaseModel):
    project_name: str
    description:  str
    stack:        str = "fullstack"


class JobResponse(BaseModel):
    id:           str
    project_name: str
    description:  str
    stack:        str
    status:       str
    created_at:   str


# ── Background runner ─────────────────────────────────────────────────────────

async def _run_swarm(job_id: str):
    job = JOBS[job_id]
    job["status"] = "running"
    job["started_at"] = datetime.utcnow().isoformat()
    _append_log(job_id, "info", f"Starting swarm for '{job['project_name']}'…")
    _save_history()

    try:
        # Add swarmdev_v3 directory to path
        swarm_dir = Path(os.getenv("SWARMDEV_PATH", "./")).resolve()
        if str(swarm_dir) not in sys.path:
            sys.path.insert(0, str(swarm_dir))

        from swarm.config import SwarmConfig
        from swarm.executor import SwarmExecutor

        cfg = SwarmConfig(
            groq_api_key=os.getenv("GROQ_API_KEY"),
            gemini_api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"),
            groq_model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            llm_provider="dual",
            output_dir=os.getenv("OUTPUT_DIR", "./output"),
            stack=job["stack"],
            max_agents=1000,
        )

        # Patch logger to forward to job logs
        class JobLogHandler(logging.Handler):
            def emit(self, record):
                lvl = record.levelname.lower()
                if lvl not in ("info", "warning", "error"):
                    lvl = "info"
                _append_log(job_id, lvl, self.format(record))

        handler = JobLogHandler()
        handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        root = logging.getLogger("swarm")
        root.addHandler(handler)

        executor = SwarmExecutor(cfg)
        result = await executor.run(job["description"], job["project_name"])

        root.removeHandler(handler)

        job["status"]          = "done"
        job["files_generated"] = result.get("files", [])
        job["tokens_used"]     = result.get("tokens_used", 0)
        job["task_status"]     = result.get("task_status", {})
        job["elapsed_seconds"] = result.get("elapsed", 0)
        _append_log(job_id, "info", f"✓ Done — {len(job['files_generated'])} files generated")

    except Exception as e:
        logger.exception(f"Job {job_id} failed")
        job["status"] = "failed"
        job["error"]  = str(e)
        _append_log(job_id, "error", f"✗ Failed: {e}")

    finally:
        job["finished_at"] = datetime.utcnow().isoformat()
        _save_history()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "jobs": len(JOBS)}


@app.post("/jobs", response_model=JobResponse, status_code=201)
async def create_job(req: JobRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    job = {
        "id":              job_id,
        "project_name":    req.project_name,
        "description":     req.description,
        "stack":           req.stack,
        "status":          "queued",
        "created_at":      datetime.utcnow().isoformat(),
        "started_at":      None,
        "finished_at":     None,
        "logs":            [],
        "files_generated": [],
        "tokens_used":     0,
        "task_status":     {},
        "elapsed_seconds": 0,
        "error":           None,
    }
    JOBS[job_id] = job
    _save_history()
    background_tasks.add_task(_run_swarm, job_id)
    logger.info(f"Job queued: {job_id[:8]} — {req.project_name}")
    return job


@app.post("/jobs/demo/{demo_name}", response_model=JobResponse, status_code=201)
async def create_demo_job(demo_name: str, background_tasks: BackgroundTasks):
    if demo_name not in DEMO_DESCRIPTIONS:
        raise HTTPException(404, f"Demo '{demo_name}' not found. Available: {list(DEMO_DESCRIPTIONS)}")
    req = JobRequest(
        project_name=demo_name,
        description=DEMO_DESCRIPTIONS[demo_name],
        stack="fullstack",
    )
    return await create_job(req, background_tasks)


@app.get("/jobs")
def list_jobs():
    return sorted(JOBS.values(), key=lambda j: j["created_at"], reverse=True)


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    # Support partial ID
    matches = [j for jid, j in JOBS.items() if jid.startswith(job_id)]
    if not matches:
        raise HTTPException(404, "Job not found")
    return matches[0]


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    matches = [jid for jid in JOBS if jid.startswith(job_id)]
    if not matches:
        raise HTTPException(404, "Job not found")
    del JOBS[matches[0]]
    _save_history()
    return {"deleted": matches[0]}


@app.get("/jobs/{job_id}/logs/stream")
async def stream_logs(job_id: str):
    """SSE endpoint — streams new log lines as they arrive."""
    matches = [jid for jid in JOBS if jid.startswith(job_id)]
    if not matches:
        raise HTTPException(404, "Job not found")
    full_id = matches[0]

    async def generator():
        seen = 0
        while True:
            job = JOBS.get(full_id, {})
            logs = job.get("logs", [])
            for entry in logs[seen:]:
                data = json.dumps(entry)
                yield f"data: {data}\n\n"
                seen += 1
            if job.get("status") in ("done", "failed", "cancelled"):
                yield "data: {\"__done__\": true}\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(generator(), media_type="text/event-stream")


@app.get("/files")
def list_output_files():
    output_dir = Path(os.getenv("OUTPUT_DIR", "./output"))
    if not output_dir.exists():
        return []
    files = []
    for f in output_dir.rglob("*"):
        if f.is_file():
            files.append({
                "path":     str(f),
                "size":     f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
    return files


@app.get("/files/content")
def get_file_content(path: str):
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "File not found")
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        return {"path": str(p), "content": content, "size": p.stat().st_size}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Web UI ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def web_ui():
    html_path = Path(__file__).parent / "ui.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>SwarmDev API</h1><p>Place ui.html next to server.py for the web UI.</p>")


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    from dotenv import load_dotenv
    load_dotenv()
    _load_history()
    logger.info("SwarmDev API server started")


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
