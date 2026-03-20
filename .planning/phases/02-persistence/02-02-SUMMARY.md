---
phase: 02-persistence
plan: "02"
subsystem: api
tags: [sqlalchemy, sqlite, lifespan, disk-guard, image-cleanup, job-history]
dependency_graph:
  requires: [02-01]
  provides: [sqlite-backed-api, lifespan-startup, disk-guard, image-cleanup-post-triage]
  affects: [backend/api.py]
tech_stack:
  added: []
  patterns: [lifespan context manager, SQLAlchemy session per request, 507 disk guard]
key_files:
  created: []
  modified:
    - backend/api.py
key_decisions:
  - "_jobs dict fully removed — clean break, no migration"
  - "lifespan replaces @app.on_event('startup') — FastAPI 0.93+ pattern"
  - "Images deleted via shutil.rmtree(images_dir) after save_triage_results()"
  - "507 returned when disk free < 100MB — checked on every upload"
  - "list_jobs_last_30_days() used for /api/jobs — no pagination needed at 50 jobs/month"
metrics:
  duration: "~15 minutes"
  completed: "2026-03-06"
  tasks_completed: 1
  tasks_total: 1
  files_modified: 1
---

# Phase 2 Plan 02: api.py SQLAlchemy Migration Summary

**One-liner:** Migrated `backend/api.py` from in-memory `_jobs` dict to SQLAlchemy-backed persistence — lifespan startup, SQLite endpoints, disk guard, image cleanup after triage, 30-day job history.

---

## What Was Built

### Removed
- Global `_jobs: Dict[str, dict]` dict — gone entirely
- `state.json` file-based state reads/writes — replaced by SQLAlchemy
- `@app.on_event("startup")` — deprecated FastAPI pattern

### Added / Changed

**Imports from database.py:**
```python
from database import (
    DATA_DIR, JOBS_DIR, init_db, get_db,
    save_new_job, update_job, set_stage, get_job,
    list_jobs_last_30_days, Job
)
```

**Lifespan context manager:**
- `init_db()` called on startup — creates tables if not exist
- `_mark_interrupted_jobs_failed()` scans for in-progress jobs and marks them `stage="failed"` with message "Job interrupted by server restart"

**Disk guard (`check_disk_space()`):**
- `shutil.disk_usage(DATA_DIR).free < 100MB` → raises HTTP 507 Insufficient Storage
- Called at start of every `/api/upload` request

**Image cleanup:**
- After `save_triage_results()` succeeds, `shutil.rmtree(images_dir)` deletes raw uploaded images
- Keeps triage.json, classify.json, analyze.json, report.pdf
- Frees 15-30MB per DJI P1 image (critical for 1GB disk budget)

**SQLite-backed endpoints:**
- `POST /api/upload` → `save_new_job()` + background task
- `GET /api/status/{job_id}` → `get_job()`
- `GET /api/jobs` → `list_jobs_last_30_days()` (30-day filter)
- `DELETE /api/jobs/{job_id}` → removes SQLite row + job directory
- `GET /api/health` → shows DATA_DIR, JOBS_DIR, ANTHROPIC_API_KEY status

**turbine_meta persistence:**
- Stored as `turbine_meta_json = json.dumps(turbine_meta)` in SQLite Text column
- Retrieved with `json.loads(job.turbine_meta_json)`

---

## Commits

| Task | Commit | Files |
|------|--------|-------|
| 1 — Full api.py migration | 8db14fd | backend/api.py |

---

## Self-Check: PASSED

- [x] `_jobs` dict removed — confirmed via grep
- [x] `from database import` present (line 28)
- [x] `lifespan` context manager defined (line 90)
- [x] `_mark_interrupted_jobs_failed()` defined (line 98)
- [x] `check_disk_space()` defined with 507 (lines 133-139)
- [x] `list_jobs_last_30_days()` used in `/api/jobs` (line 539)
- [x] Image cleanup after triage confirmed in run_pipeline
- [x] DELETE endpoint removes row + directory (line 546)
- [x] Commit 8db14fd present in git log
