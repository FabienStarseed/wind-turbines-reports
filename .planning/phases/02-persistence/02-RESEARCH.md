# Phase 2: Persistence - Research

**Researched:** 2026-03-05
**Domain:** SQLAlchemy 2.0 (sync) + SQLite + Render Persistent Disk
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Job History Behaviour**
- Retention window: Show jobs from the last 30 days only. Jobs older than 30 days are not shown in history (but their records stay in SQLite — just filtered from the UI query).
- Interrupted jobs: If a job was in-progress (stage = "triaging", "classifying", "analyzing") when Render restarted, mark it as stage = "failed" with `stage_message = "Job interrupted by server restart"` on startup. Do not silently drop them.
- Manual delete: Users can delete a job from history. Deleting removes the SQLite row AND all files in `/data/jobs/{job_id}/`. This is the same as the "files expired" cleanup flow.
- Scale: ~50 jobs/month expected. No pagination required in Phase 2. Simple list is fine.

**File Storage Layout & Cleanup**
- Raw uploaded images: Deleted immediately after the triage stage completes. Do not keep originals — they are 15-30MB each (DJI P1) and would exhaust disk quickly.
- Intermediate AI outputs (triage.json, classify.json, analyze.json): Kept permanently alongside the PDF. User can delete via the manual delete button.
- PDF report: Kept permanently, re-downloadable at any time via `/api/download/{job_id}`.
- Files expired state: If a job's files are deleted (manual delete), the job row is also deleted from SQLite. It disappears from history. If files are missing but the row exists (edge case), show status as `"files_expired"`.

**Storage layout:**
```
/data/
├── bdda.db
└── jobs/
    └── {job_id}/
        ├── triage.json
        ├── classify.json
        ├── analyze.json
        ├── report.pdf
        └── errors.json        # if any
        # NOTE: uploaded images deleted after triage completes
```

**Render Persistent Disk**
- Disk size: 1GB ($0.25/month). Upgrade later — Render allows online resize.
- Mount path: `/data`. SQLite at `/data/bdda.db`, jobs at `/data/jobs/`.
- Disk full behaviour: Refuse new jobs with HTTP 507 with message: "Server storage full — please contact the administrator." Do NOT auto-delete old jobs silently.
- Local dev fallback: When `DATA_DIR` env var is not set, use `./data/` relative to backend directory.
- DATA_DIR env var: `DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))`.

**SQLAlchemy**
- SQLAlchemy sync + SQLite (no async driver).
- The `_jobs: Dict[str, dict]` global in `api.py` is removed entirely and replaced with SQLAlchemy calls.
- No data migration script — clean break from in-memory state.

**render.yaml disk config (verbatim):**
```yaml
services:
  - type: web
    name: bdda
    disk:
      name: bdda-data
      mountPath: /data
      sizeGB: 1
```

### Claude's Discretion
- CONTEXT.md has no explicit "Claude's Discretion" section for Phase 2.

### Deferred Ideas (OUT OF SCOPE)
- Automatic cleanup of jobs older than 30 days from disk
- External storage (S3, R2, Cloudflare)
- Disk usage dashboard (deferred to Phase 5 UI)
- Email notifications on job complete
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PERS-01 | Job state stored in SQLite (survives Render restarts) | SQLAlchemy 2.0 sync ORM with DeclarativeBase, sessionmaker, and lifespan startup confirmed. WAL mode + check_same_thread=False pattern documented. |
| PERS-02 | Uploaded images and PDFs stored on Render Persistent Disk | Render disk YAML config confirmed (name/mountPath/sizeGB). DATA_DIR env var pattern for local fallback documented. Image deletion after triage documented. |
| PERS-03 | Job history visible across sessions (no more lost jobs on restart) | DB query pattern for 30-day filter documented. Startup scan for interrupted jobs documented. /api/jobs endpoint replaces filesystem glob. |
| PERS-04 | render.yaml updated with persistent disk config | Exact YAML fields confirmed from Render blueprint spec. CRITICAL: disk requires paid instance (Starter = $7/month minimum). Free tier cannot use persistent disk. |
</phase_requirements>

---

## Summary

Phase 2 replaces the current in-memory `_jobs` dict and filesystem-based `state.json` with SQLAlchemy 2.0 sync ORM backed by a SQLite database at `/data/bdda.db`. All job state flows through SQLAlchemy instead of `json.load`/`json.dump`. File storage moves from the project's `jobs/` directory to `/data/jobs/` on the Render Persistent Disk.

The SQLAlchemy setup is straightforward: one `Job` model, a module-level `engine` and `SessionLocal` sessionmaker, a `get_db()` context manager for session lifecycle, and a `lifespan` startup event that creates tables and scans for interrupted jobs. The `turbine_meta` dict stored in `state.json` today becomes a `JSON` column in SQLite. The background pipeline (`run_pipeline`) is synchronous and uses its own session created directly with `SessionLocal()`.

**Critical operational finding:** Render Persistent Disk requires a paid web service instance (minimum Starter tier, $7/month). The free tier has an ephemeral filesystem — data is wiped on every restart/redeploy. The CONTEXT.md decision to "stay on free tier" and the decision to "add persistent disk" are mutually exclusive. The planner must surface this to the user before implementation.

**Primary recommendation:** Implement SQLAlchemy 2.0 sync ORM with a single `Job` table, WAL mode for safe concurrent reads/writes from background threads, and the `lifespan` pattern for startup initialization. Add disk as specified in CONTEXT.md, but flag the paid tier requirement clearly.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | >=2.0 | ORM, session management, DDL | Industry-standard Python ORM; 2.0 API is stable and typed; sync mode fits project's sync pipeline |
| sqlite3 (stdlib) | built-in | SQLite DBAPI driver | No install needed; SQLAlchemy uses it automatically via `sqlite:///` URL |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| shutil (stdlib) | built-in | Disk usage check, recursive delete | `shutil.disk_usage()` for 507 guard; `shutil.rmtree()` for job directory delete |
| contextlib (stdlib) | built-in | `asynccontextmanager` for lifespan | FastAPI lifespan startup event |
| pathlib (stdlib) | built-in | Path manipulation | Already used throughout backend |

**SQLAlchemy is not yet in requirements.txt. It must be added.**

### Installation
```bash
# Add to requirements.txt:
sqlalchemy>=2.0
```

SQLAlchemy 2.0 is pure Python, no system dependencies. sqlite3 is Python stdlib.

---

## Architecture Patterns

### Recommended Project Structure

The persistence layer lives entirely in a new `backend/database.py` module. The `api.py` imports from it.

```
backend/
├── api.py           # FastAPI app — imports from database.py, removes _jobs dict
├── database.py      # NEW: engine, SessionLocal, Base, Job model, helpers
├── ingest.py        # Unchanged
├── triage.py        # Unchanged
├── classify.py      # Unchanged
├── analyze.py       # Unchanged
└── report.py        # Unchanged
```

### Pattern 1: database.py — Engine, Model, Session Factory

**What:** Central module that owns the SQLAlchemy engine, ORM model, and session factory.
**When to use:** All DB access in `api.py` and `run_pipeline` imports from here.

```python
# backend/database.py
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine, event, func, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# ── DATA_DIR ──────────────────────────────────────────────────────────────────

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR = DATA_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "bdda.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

# ── ENGINE ────────────────────────────────────────────────────────────────────

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required: FastAPI uses multiple threads
)

# Enable WAL mode: readers don't block writers; background pipeline can write
# while API reads status concurrently.
@event.listens_for(engine, "connect")
def set_sqlite_pragmas(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

# ── SESSION FACTORY ───────────────────────────────────────────────────────────

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager that yields a session and closes it on exit."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

# ── BASE + MODEL ──────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    job_id     = Column(String(8), unique=True, nullable=False, index=True)
    stage      = Column(String(32), nullable=False, default="queued")
    stage_message = Column(Text, default="")
    # turbine_meta stored as JSON string; SQLite has no native JSON type —
    # use Text and json.dumps/loads in helpers (see Pattern 3 below)
    turbine_meta_json = Column(Text, default="{}")
    image_count       = Column(Integer, default=0)
    total_images      = Column(Integer, nullable=True)
    flagged_images    = Column(Integer, nullable=True)
    critical_findings = Column(Integer, nullable=True)
    pdf_path          = Column(Text, nullable=True)
    triage_cost_usd   = Column(Text, nullable=True)    # stored as string float
    classify_cost_usd = Column(Text, nullable=True)
    analyze_cost_usd  = Column(Text, nullable=True)
    total_cost_usd    = Column(Text, nullable=True)
    image_cap_warning = Column(Text, nullable=True)
    error_traceback   = Column(Text, nullable=True)
    created_at        = Column(DateTime(timezone=True), server_default=func.now())
    updated_at        = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at      = Column(DateTime(timezone=True), nullable=True)
    failed_at         = Column(DateTime(timezone=True), nullable=True)


def init_db():
    """Create tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
```

Source: SQLAlchemy 2.0 docs (https://docs.sqlalchemy.org/en/20/orm/quickstart.html), FastAPI SQLite docs (https://fastapi.tiangolo.com/tutorial/sql-databases/)

### Pattern 2: FastAPI Lifespan — Startup Init + Interrupted Job Recovery

**What:** Replace deprecated `@app.on_event("startup")` with `lifespan` context manager. On startup: create DB tables, scan for interrupted jobs, mark them failed.
**When to use:** FastAPI 0.93+ (already on 0.115.5 per requirements.txt).

```python
# backend/api.py (startup section)
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import select, update
from database import get_db, init_db, Job, JOBS_DIR

INTERRUPTED_STAGES = {"triaging", "classifying", "analyzing", "ingesting", "generating_report", "queued"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    init_db()
    _mark_interrupted_jobs_failed()
    yield
    # --- Shutdown --- (nothing needed)

def _mark_interrupted_jobs_failed():
    """Mark in-progress jobs as failed — they were interrupted by restart."""
    with get_db() as session:
        stmt = (
            update(Job)
            .where(Job.stage.in_(INTERRUPTED_STAGES))
            .values(
                stage="failed",
                stage_message="Job interrupted by server restart",
            )
        )
        session.execute(stmt)
        session.commit()

app = FastAPI(
    title="BDDA — Blade Defect Detection Agent",
    lifespan=lifespan,
)
```

Source: FastAPI lifespan docs (https://fastapi.tiangolo.com/advanced/events/)

### Pattern 3: CRUD Helpers — Replacing _jobs Dict

**What:** Drop-in replacements for `get_job`, `save_job`, `update_job`, `set_stage` that talk to SQLite instead of an in-memory dict.

```python
# backend/database.py (continued)
import json
from datetime import datetime, timezone

def _job_to_dict(job: Job) -> dict:
    """Convert Job ORM row to the dict shape the rest of api.py expects."""
    d = {
        "job_id": job.job_id,
        "stage": job.stage,
        "stage_message": job.stage_message,
        "image_count": job.image_count,
        "total_images": job.total_images,
        "flagged_images": job.flagged_images,
        "critical_findings": job.critical_findings,
        "pdf_path": job.pdf_path,
        "triage_cost_usd": job.triage_cost_usd,
        "classify_cost_usd": job.classify_cost_usd,
        "analyze_cost_usd": job.analyze_cost_usd,
        "total_cost_usd": job.total_cost_usd,
        "image_cap_warning": job.image_cap_warning,
        "error_traceback": job.error_traceback,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "failed_at": job.failed_at.isoformat() if job.failed_at else None,
        "turbine_meta": json.loads(job.turbine_meta_json or "{}"),
    }
    return d


def get_job(job_id: str) -> Optional[dict]:
    with get_db() as session:
        job = session.scalars(select(Job).where(Job.job_id == job_id)).first()
        if job is None:
            return None
        return _job_to_dict(job)


def save_job(job_id: str, state: dict):
    """Insert or update a job row."""
    with get_db() as session:
        job = session.scalars(select(Job).where(Job.job_id == job_id)).first()
        if job is None:
            job = Job(job_id=job_id)
            session.add(job)
        _apply_state_to_job(job, state)
        session.commit()


def update_job(job_id: str, **kwargs):
    with get_db() as session:
        job = session.scalars(select(Job).where(Job.job_id == job_id)).first()
        if job is None:
            return
        for key, value in kwargs.items():
            _set_job_attr(job, key, value)
        session.commit()


def set_stage(job_id: str, stage: str, message: str = ""):
    update_job(job_id, stage=stage, stage_message=message)
```

### Pattern 4: /api/jobs — 30-Day Filter, No Filesystem Glob

**What:** Replace the current `JOBS_DIR.glob("*/state.json")` scan with a DB query filtered by `created_at`.

```python
# backend/api.py
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from database import get_db, Job, _job_to_dict

@app.get("/api/jobs")
async def list_jobs():
    """List jobs created in the last 30 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    with get_db() as session:
        stmt = (
            select(Job)
            .where(Job.created_at >= cutoff)
            .order_by(Job.created_at.desc())
        )
        jobs = session.scalars(stmt).all()
    return [
        {
            "job_id": j.job_id,
            "turbine_id": json.loads(j.turbine_meta_json or "{}").get("turbine_id"),
            "stage": j.stage,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j in jobs
    ]
```

### Pattern 5: Disk Space Guard — HTTP 507

**What:** Check available disk space before accepting an upload. Return 507 if < 100MB free.

```python
# backend/api.py (inside upload endpoint, before extract_upload)
import shutil
from fastapi import HTTPException
from database import DATA_DIR

def check_disk_space():
    usage = shutil.disk_usage(DATA_DIR)
    free_mb = usage.free / (1024 * 1024)
    if free_mb < 100:
        raise HTTPException(
            status_code=507,
            detail="Server storage full — please contact the administrator.",
        )
```

Source: Python stdlib `shutil.disk_usage` — stable across Python 3.3+

### Pattern 6: Image Deletion After Triage

**What:** After `save_triage_results()` succeeds in `run_pipeline`, delete the `images/` subdirectory.

```python
# backend/api.py (inside run_pipeline, after save_triage_results)
import shutil

# After save_triage_results(summary, triage_path)
images_dir = job_dir / "images"
if images_dir.exists():
    shutil.rmtree(images_dir)
```

### Pattern 7: Job Directory Migration — JOBS_DIR moves to DATA_DIR

**What:** The current `JOBS_DIR = BASE_DIR / "jobs"` moves to `DATA_DIR / "jobs"` (inside the persistent disk mount). All job file I/O uses the new path.

```python
# api.py — replace the old PATHS section:
from database import DATA_DIR, JOBS_DIR  # both defined in database.py
```

### Pattern 8: Download Endpoint — PDF Path from DB

**What:** `pdf_path` is stored in the DB. The download endpoint reads it from there. The path will be something like `/data/jobs/{job_id}/report_{turbine_id}.pdf`.

```python
@app.get("/api/download/{job_id}")
async def download_report(job_id: str):
    state = get_job(job_id)  # now reads from SQLite
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")
    if state.get("stage") != "complete":
        raise HTTPException(status_code=400, detail="Report not ready yet")
    pdf_path = Path(state["pdf_path"])
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")
    ...
```

### Pattern 9: DELETE Endpoint — Remove DB Row + Directory

**What:** Delete both the SQLite row and the job directory recursively.

```python
@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    # Remove files
    job_dir = JOBS_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
    # Remove DB row
    with get_db() as session:
        job = session.scalars(select(Job).where(Job.job_id == job_id)).first()
        if job:
            session.delete(job)
            session.commit()
    return {"deleted": job_id}
```

### Anti-Patterns to Avoid

- **Sharing a session across threads:** The background pipeline (`run_pipeline`) runs in a thread pool. Never pass a session from the upload endpoint into the background task — each thread must create its own session via `SessionLocal()` or `get_db()`.
- **Using `@app.on_event("startup")`:** Deprecated since FastAPI 0.93. Use `lifespan` parameter instead. Using both simultaneously is not supported.
- **Using SQLAlchemy 1.x `Query` API:** The `session.query(Job)` pattern is legacy. Use `select(Job)` with `session.scalars()` in 2.0 style.
- **Storing floats in Float columns for costs:** SQLite has known floating-point precision issues. Store cost values as `Text` (string representation) or `Numeric` to avoid rounding artifacts. The current state.json stores them as floats already — keep as `Text` to match existing behaviour.
- **Not using WAL mode:** Default SQLite journal mode blocks all reads during a write. The background pipeline writes progress updates while the status endpoint is polling — WAL mode prevents write-blocked reads.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DB table creation | Custom `CREATE TABLE` SQL | `Base.metadata.create_all(engine)` | Handles column changes, idempotent |
| Session lifecycle | Manual open/close everywhere | `get_db()` context manager | Guarantees close on error |
| WAL mode setup | Manual PRAGMA in each query | `@event.listens_for(engine, "connect")` | Runs for every new connection automatically |
| Concurrent write safety | Write queues, locks, retries | WAL mode pragma | SQLite WAL natively handles concurrent readers + one writer |
| Startup table migration | Custom migration SQL | `Base.metadata.create_all()` (Phase 2 only) | Idempotent; Phase 2 is clean-break, no migration needed |

**Key insight:** SQLite with WAL mode handles the concurrency pattern here (one background writer + one API reader) without any additional coordination. The `check_same_thread=False` flag combined with WAL mode is the correct, well-documented approach for this workload.

---

## Common Pitfalls

### Pitfall 1: Render Disk Requires Paid Instance (CRITICAL)

**What goes wrong:** Deploy with `disk:` block in render.yaml on a free tier instance. Render rejects the config or silently ignores the disk. Data is still ephemeral.
**Why it happens:** Render Persistent Disks are only available on paid web service instances (minimum Starter tier = $7/month). The CONTEXT.md says "stay on free tier for now" AND "add persistent disk" — these are mutually exclusive.
**How to avoid:** Upgrade the web service to at least the Starter tier ($7/month) before or at the same time as adding the disk block. The disk itself costs $0.25/GB/month ($0.25 for 1GB).
**Warning signs:** If the app deploys fine but jobs disappear on restart, the disk attachment failed silently or the free tier is still active.

### Pitfall 2: check_same_thread Must Be False

**What goes wrong:** `OperationalError: SQLite objects created in a thread can only be used in that same thread.`
**Why it happens:** FastAPI's thread pool runs background tasks in different threads from the main event loop. SQLite's default `check_same_thread=True` blocks this.
**How to avoid:** Always pass `connect_args={"check_same_thread": False}` to `create_engine`. This is safe because SQLAlchemy's connection pool manages thread safety at a higher level.

### Pitfall 3: SQLite Default Journal Mode Blocks Status Polling

**What goes wrong:** `run_pipeline` is writing status updates while the frontend polls `/api/status/{job_id}`. Under default journal mode, reads block during writes, causing status endpoint to time out.
**Why it happens:** SQLite's default rollback journal acquires an exclusive write lock that blocks all readers.
**How to avoid:** Enable WAL mode in the engine connection event. WAL allows one concurrent writer and unlimited readers.

### Pitfall 4: session.close() vs session.commit() — Don't Confuse Them

**What goes wrong:** Closing the session without committing means changes are rolled back silently.
**Why it happens:** The `get_db()` context manager only closes the session in the `finally` block — it does NOT auto-commit. Each write operation must call `session.commit()` explicitly.
**How to avoid:** Always call `session.commit()` after any INSERT/UPDATE/DELETE within the context manager.

### Pitfall 5: turbine_meta as JSON in Text Column

**What goes wrong:** SQLAlchemy's `JSON` type works with PostgreSQL natively, but its behaviour on SQLite varies by version. SQLite < 3.37.2 does not have native JSON column support.
**Why it happens:** Render's Python 3.11 runtime uses a newer SQLite (likely 3.39+), but it's version-dependent. Using `JSON` type may serialize/deserialize correctly, but mutation tracking does not work (you must reassign the whole dict, not modify in-place).
**How to avoid:** Store `turbine_meta` as `Text` with explicit `json.dumps()` / `json.loads()` in the helper functions. This is explicit, portable, and matches what the current `state.json` approach already does.

### Pitfall 6: DATA_DIR Must Exist Before DB Init

**What goes wrong:** `sqlite:////data/bdda.db` fails to open because `/data` doesn't exist locally.
**Why it happens:** On local dev with `DATA_DIR=./data`, the directory may not exist yet.
**How to avoid:** Call `DATA_DIR.mkdir(parents=True, exist_ok=True)` in `database.py` at module import time, before the engine is created.

### Pitfall 7: Render Disk Zero-Downtime Deploy Is Blocked

**What goes wrong:** Render's zero-downtime deploys (blue-green) are incompatible with persistent disks. Each disk can only be attached to one instance at a time.
**Why it happens:** Render documentation explicitly states persistent disks prevent zero-downtime deploys.
**How to avoid:** Accept this limitation. For Phase 2 (internal tool, small team), a brief redeploy downtime is acceptable. Note it in the deploy runbook.

---

## Code Examples

### Complete database.py Module

```python
# backend/database.py
"""
database.py — SQLAlchemy 2.0 sync session, Job model, and CRUD helpers.
Replaces the in-memory _jobs dict and state.json filesystem pattern.
"""
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine, event, func, select, update
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# ── DATA_DIR ──────────────────────────────────────────────────────────────────

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR = DATA_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "bdda.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

# ── ENGINE ────────────────────────────────────────────────────────────────────

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

@event.listens_for(engine, "connect")
def set_sqlite_pragmas(dbapi_connection, connection_record):
    """Enable WAL mode so reads don't block background pipeline writes."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

@contextmanager
def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

# ── MODEL ─────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    job_id            = Column(String(8), unique=True, nullable=False, index=True)
    stage             = Column(String(32), nullable=False, default="queued")
    stage_message     = Column(Text, default="")
    turbine_meta_json = Column(Text, default="{}")
    image_count       = Column(Integer, default=0)
    total_images      = Column(Integer, nullable=True)
    flagged_images    = Column(Integer, nullable=True)
    critical_findings = Column(Integer, nullable=True)
    pdf_path          = Column(Text, nullable=True)
    triage_cost_usd   = Column(Text, nullable=True)
    classify_cost_usd = Column(Text, nullable=True)
    analyze_cost_usd  = Column(Text, nullable=True)
    total_cost_usd    = Column(Text, nullable=True)
    image_cap_warning = Column(Text, nullable=True)
    error_traceback   = Column(Text, nullable=True)
    created_at        = Column(DateTime(timezone=True), server_default=func.now())
    updated_at        = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at      = Column(DateTime(timezone=True), nullable=True)
    failed_at         = Column(DateTime(timezone=True), nullable=True)


def init_db():
    Base.metadata.create_all(bind=engine)


# ── CRUD HELPERS ──────────────────────────────────────────────────────────────

def _job_to_dict(job: Job) -> dict:
    return {
        "job_id": job.job_id,
        "stage": job.stage,
        "stage_message": job.stage_message,
        "turbine_meta": json.loads(job.turbine_meta_json or "{}"),
        "image_count": job.image_count,
        "total_images": job.total_images,
        "flagged_images": job.flagged_images,
        "critical_findings": job.critical_findings,
        "pdf_path": job.pdf_path,
        "triage_cost_usd": float(job.triage_cost_usd) if job.triage_cost_usd else None,
        "classify_cost_usd": float(job.classify_cost_usd) if job.classify_cost_usd else None,
        "analyze_cost_usd": float(job.analyze_cost_usd) if job.analyze_cost_usd else None,
        "total_cost_usd": float(job.total_cost_usd) if job.total_cost_usd else None,
        "image_cap_warning": job.image_cap_warning,
        "error_traceback": job.error_traceback,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "failed_at": job.failed_at.isoformat() if job.failed_at else None,
    }


def get_job(job_id: str) -> Optional[dict]:
    with get_db() as session:
        job = session.scalars(select(Job).where(Job.job_id == job_id)).first()
        return _job_to_dict(job) if job else None


def save_new_job(state: dict):
    """Insert a new Job row from the initial state dict."""
    with get_db() as session:
        job = Job(
            job_id=state["job_id"],
            stage=state.get("stage", "queued"),
            stage_message=state.get("stage_message", ""),
            turbine_meta_json=json.dumps(state.get("turbine_meta", {})),
            image_count=state.get("image_count", 0),
        )
        session.add(job)
        session.commit()


def update_job(job_id: str, **kwargs):
    """Update specific fields on a job row."""
    COLUMN_MAP = {
        "stage": "stage",
        "stage_message": "stage_message",
        "total_images": "total_images",
        "flagged_images": "flagged_images",
        "critical_findings": "critical_findings",
        "pdf_path": "pdf_path",
        "triage_cost_usd": "triage_cost_usd",
        "classify_cost_usd": "classify_cost_usd",
        "analyze_cost_usd": "analyze_cost_usd",
        "total_cost_usd": "total_cost_usd",
        "image_cap_warning": "image_cap_warning",
        "error_traceback": "error_traceback",
        "completed_at": "completed_at",
        "failed_at": "failed_at",
    }
    values = {}
    for key, value in kwargs.items():
        if key in COLUMN_MAP:
            # Store cost floats as strings
            if key.endswith("_usd") and value is not None:
                value = str(value)
            values[COLUMN_MAP[key]] = value
    if not values:
        return
    with get_db() as session:
        session.execute(
            update(Job).where(Job.job_id == job_id).values(**values)
        )
        session.commit()


def set_stage(job_id: str, stage: str, message: str = ""):
    update_job(job_id, stage=stage, stage_message=message)
```

Source: SQLAlchemy 2.0 docs — https://docs.sqlalchemy.org/en/20/orm/quickstart.html

### render.yaml With Disk

```yaml
# render.yaml
services:
  - type: web
    name: bdda
    runtime: python
    rootDir: .
    buildCommand: pip install -r requirements.txt
    startCommand: cd backend && uvicorn api:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /api/health
    disk:
      name: bdda-data
      mountPath: /data
      sizeGB: 1
    envVars:
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: COST_LIMIT_USD
        sync: false
```

Note: `GOOGLE_API_KEY` and `KIMI_API_KEY` removed (Phase 1 completed). `DATA_DIR` env var does NOT need to be in render.yaml — the default in `database.py` is `/data`, which matches the mountPath.

Source: Render Blueprint YAML Reference — https://render.com/docs/blueprint-spec

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` | `lifespan` context manager | FastAPI 0.93 (2023) | `on_event` is deprecated; use `lifespan` parameter |
| `session.query(Model)` | `select(Model)` + `session.scalars()` | SQLAlchemy 2.0 (2023) | Old Query API is legacy; 2.0 style is typed and explicit |
| `DeclarativeBase` via `declarative_base()` | `class Base(DeclarativeBase): pass` | SQLAlchemy 2.0 | New class-based syntax required for Mapped type annotations |
| `from sqlalchemy.ext.declarative import declarative_base` | `from sqlalchemy.orm import DeclarativeBase` | SQLAlchemy 2.0 | Import path changed |

**Deprecated/outdated:**
- `@app.on_event("startup")`: Replaced by `lifespan` parameter. Works in FastAPI 0.115.5 but emits deprecation warning.
- `session.query(Job).filter(...)`: Legacy 1.x Query API. Replace with `select(Job).where(...)`.
- `declarative_base()` from `sqlalchemy.ext.declarative`: Use `DeclarativeBase` class from `sqlalchemy.orm` instead.

---

## Open Questions

1. **Render free tier vs paid tier conflict**
   - What we know: Render Persistent Disk requires a paid instance (min $7/month Starter). Free tier has ephemeral filesystem.
   - What's unclear: The CONTEXT.md says "stay on free tier for now" AND wants a persistent disk. These are mutually exclusive.
   - Recommendation: The planner must flag this to the user before starting implementation. The correct sequence is: upgrade to Starter tier ($7/month), then add the disk ($0.25/month for 1GB). Total: ~$7.25/month.

2. **Session per background task call**
   - What we know: `run_pipeline` runs in FastAPI's thread pool. Each call to `update_job()` or `set_stage()` inside the pipeline creates and closes its own session via `get_db()`.
   - What's unclear: Whether many short-lived sessions in a single pipeline run (10-15 DB writes per job) causes any overhead concern.
   - Recommendation: At ~50 jobs/month and SQLite's sub-millisecond local I/O, this is not a real concern. The pattern is correct.

3. **`created_at` timezone awareness in SQLite**
   - What we know: SQLite stores datetime as text strings. SQLAlchemy's `DateTime(timezone=True)` serialises to ISO 8601 strings. The 30-day filter compares Python-side `datetime.now(timezone.utc)` against stored strings.
   - What's unclear: Whether SQLite's `>=` comparison on ISO 8601 strings is reliable for the 30-day filter.
   - Recommendation: Store `created_at` with `server_default=func.now()` and do the comparison in Python (load all jobs from last 30 days by filtering `job.created_at >= cutoff` in SQLAlchemy's ORM layer, not raw SQL). This bypasses SQLite's string comparison ambiguity.

---

## Sources

### Primary (HIGH confidence)
- SQLAlchemy 2.0 ORM Quickstart — https://docs.sqlalchemy.org/en/20/orm/quickstart.html
- SQLAlchemy 2.0 Session Basics — https://docs.sqlalchemy.org/en/20/orm/session_basics.html
- SQLAlchemy SQLite Dialect — https://docs.sqlalchemy.org/en/20/dialects/sqlite.html
- FastAPI SQL Databases Tutorial — https://fastapi.tiangolo.com/tutorial/sql-databases/
- FastAPI Lifespan Events — https://fastapi.tiangolo.com/advanced/events/
- Render Persistent Disks Docs — https://render.com/docs/disks
- Render Blueprint YAML Reference — https://render.com/docs/blueprint-spec
- Render Free Tier Docs — https://render.com/docs/free
- Render Pricing — https://render.com/pricing

### Secondary (MEDIUM confidence)
- SQLite WAL mode overview — https://sqlite.org/wal.html (verified against SQLAlchemy event listener pattern)
- WAL mode enabling via SQLAlchemy event — https://til.simonwillison.net/sqlite/enabling-wal-mode (matches SQLAlchemy docs)

### Tertiary (LOW confidence)
- None. All critical findings verified against official docs.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — SQLAlchemy 2.0 sync + SQLite stdlib is stable, well-documented, officially supported
- Architecture: HIGH — Patterns taken directly from FastAPI and SQLAlchemy official docs
- Pitfalls: HIGH — Render disk/free-tier conflict verified from official Render docs; WAL/threading patterns from SQLAlchemy + SQLite official docs
- Render disk config: HIGH — Verified from Render blueprint spec and pricing page

**Research date:** 2026-03-05
**Valid until:** 2026-06-05 (SQLAlchemy 2.0 and Render docs are stable; Render pricing may change)
