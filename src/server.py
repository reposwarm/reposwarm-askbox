"""RepoSwarm Askbox HTTP server — persistent container that serves architecture questions."""

import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.agent import clone_arch_hub, get_adapter, SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Config from env
# ---------------------------------------------------------------------------
ARCH_HUB_URL = os.environ.get("ARCH_HUB_URL", "")
ARCH_HUB_BRANCH = os.environ.get("ARCH_HUB_BRANCH", "main")
ARCH_HUB_PATH = os.environ.get("ARCH_HUB_PATH", "/tmp/arch-hub")
DEFAULT_ADAPTER = os.environ.get("ASKBOX_ADAPTER", "claude-agent-sdk")
DEFAULT_MODEL = os.environ.get("MODEL_ID")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/output")
PORT = int(os.environ.get("ASKBOX_PORT", "8082"))


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class AskStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class AskRequest(BaseModel):
    question: str
    adapter: str | None = None
    model: str | None = None
    repos: list[str] | None = Field(None, description="Filter to specific repos (not yet implemented)")


class AskJob(BaseModel):
    id: str
    question: str
    status: AskStatus
    adapter: str
    answer: str | None = None
    error: str | None = None
    created_at: float
    started_at: float | None = None
    completed_at: float | None = None
    tool_calls: int = 0


class AskResponse(BaseModel):
    id: str
    status: AskStatus


class HealthResponse(BaseModel):
    status: str
    arch_hub_ready: bool
    arch_hub_path: str
    arch_hub_repos: int
    jobs_total: int
    jobs_running: int
    uptime_seconds: float


# ---------------------------------------------------------------------------
# In-memory job store
# ---------------------------------------------------------------------------
jobs: dict[str, AskJob] = {}
start_time: float = 0
arch_hub_ready: bool = False
arch_hub_repo_count: int = 0
# Serialize question execution — one at a time
question_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Lifespan: clone arch-hub on startup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global arch_hub_ready, arch_hub_repo_count, start_time
    start_time = time.time()

    if ARCH_HUB_URL:
        try:
            print(f"[askbox] Cloning arch-hub from {ARCH_HUB_URL}...", flush=True)
            clone_arch_hub(ARCH_HUB_URL, ARCH_HUB_PATH, ARCH_HUB_BRANCH)
            # Count .arch.md files
            arch_hub_repo_count = len(list(Path(ARCH_HUB_PATH).rglob("*.arch.md")))
            arch_hub_ready = True
            print(f"[askbox] Arch-hub ready: {arch_hub_repo_count} repos indexed", flush=True)
        except Exception as e:
            print(f"[askbox] WARNING: Failed to clone arch-hub: {e}", flush=True)
            print("[askbox] Server starting anyway — set ARCH_HUB_URL or POST to /arch-hub/refresh", flush=True)
    else:
        print("[askbox] No ARCH_HUB_URL set — start without arch-hub, POST to /arch-hub/refresh later", flush=True)

    # Auto-detect existing arch files at ARCH_HUB_PATH (e.g. volume-mounted)
    if not arch_hub_ready:
        existing = list(Path(ARCH_HUB_PATH).rglob("*.arch.md"))
        if existing:
            arch_hub_repo_count = len(existing)
            arch_hub_ready = True
            print(f"[askbox] Auto-detected {arch_hub_repo_count} repos at {ARCH_HUB_PATH}", flush=True)

    yield  # Server runs

    print("[askbox] Shutting down", flush=True)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="RepoSwarm Askbox",
    description="Query architecture docs with AI",
    version="0.2.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health():
    running = sum(1 for j in jobs.values() if j.status == AskStatus.running)
    return HealthResponse(
        status="healthy",
        arch_hub_ready=arch_hub_ready,
        arch_hub_path=ARCH_HUB_PATH,
        arch_hub_repos=arch_hub_repo_count,
        jobs_total=len(jobs),
        jobs_running=running,
        uptime_seconds=round(time.time() - start_time, 1),
    )


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    if not arch_hub_ready:
        raise HTTPException(status_code=503, detail="Arch-hub not loaded. Set ARCH_HUB_URL or POST /arch-hub/refresh")

    job_id = str(uuid.uuid4())[:8]
    adapter_name = req.adapter or DEFAULT_ADAPTER
    job = AskJob(
        id=job_id,
        question=req.question,
        status=AskStatus.queued,
        adapter=adapter_name,
        created_at=time.time(),
    )
    jobs[job_id] = job

    # Run in background
    asyncio.create_task(_run_job(job, req.model))

    return AskResponse(id=job_id, status=AskStatus.queued)


@app.get("/ask/{job_id}", response_model=AskJob)
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return jobs[job_id]


@app.get("/ask", response_model=list[AskJob])
async def list_jobs(limit: int = 20, status: AskStatus | None = None):
    result = sorted(jobs.values(), key=lambda j: j.created_at, reverse=True)
    if status:
        result = [j for j in result if j.status == status]
    return result[:limit]


@app.post("/arch-hub/refresh")
async def refresh_arch_hub(url: str | None = None, branch: str | None = None):
    """Re-clone or update the arch-hub."""
    global arch_hub_ready, arch_hub_repo_count, ARCH_HUB_URL

    hub_url = url or ARCH_HUB_URL
    hub_branch = branch or ARCH_HUB_BRANCH

    if not hub_url:
        raise HTTPException(status_code=400, detail="No arch-hub URL provided (pass ?url= or set ARCH_HUB_URL)")

    try:
        ARCH_HUB_URL = hub_url
        clone_arch_hub(hub_url, ARCH_HUB_PATH, hub_branch)
        arch_hub_repo_count = len(list(Path(ARCH_HUB_PATH).rglob("*.arch.md")))
        arch_hub_ready = True
        return {"status": "refreshed", "repos": arch_hub_repo_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh: {e}")


# ---------------------------------------------------------------------------
# Background job runner
# ---------------------------------------------------------------------------
async def _run_job(job: AskJob, model_override: str | None = None):
    """Execute a question job. Serialized via lock (one at a time)."""
    async with question_lock:
        job.status = AskStatus.running
        job.started_at = time.time()

        try:
            model = model_override or DEFAULT_MODEL
            adapter = get_adapter(job.adapter, model)

            def on_status(msg: str):
                if "Tool:" in msg:
                    job.tool_calls += 1

            answer = await adapter.ask(
                question=job.question,
                arch_hub_path=ARCH_HUB_PATH,
                system_prompt=SYSTEM_PROMPT,
                on_status=on_status,
            )

            job.answer = answer
            job.status = AskStatus.completed
            job.completed_at = time.time()

            # Write to output dir
            output_path = Path(OUTPUT_DIR)
            output_path.mkdir(parents=True, exist_ok=True)
            (output_path / f"{job.id}.md").write_text(answer, encoding="utf-8")

            elapsed = round(job.completed_at - job.started_at, 1)
            print(f"[askbox] Job {job.id} completed: {len(answer)} chars, {job.tool_calls} tool calls, {elapsed}s", flush=True)

        except Exception as e:
            job.status = AskStatus.failed
            job.error = str(e)
            job.completed_at = time.time()
            print(f"[askbox] Job {job.id} failed: {e}", flush=True)


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------
def main():
    import uvicorn
    print(f"[askbox] Starting server on port {PORT}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")


if __name__ == "__main__":
    main()
