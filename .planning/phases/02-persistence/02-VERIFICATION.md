---
phase: 02-persistence
verified: 2026-03-06T00:00:00Z
status: gaps_found
score: 14/16 must-haves verified
gaps:
  - truth: "On startup, any in-progress jobs are marked stage=failed with restart message"
    status: partial
    reason: "The _mark_interrupted_jobs_failed() function correctly sets stage='failed' in the DB, but /api/status only surfaces error/error_traceback fields for stage=='error', not stage=='failed'. A restarted job shows progress=0 (fallback) and error=None even though stage_message is set correctly."
    artifacts:
      - path: "backend/api.py"
        issue: "stage_progress dict and error-field logic at lines 430-454 do not handle stage='failed' — only stage='error'. Frontend receives stage='failed', progress=0, error=None instead of progress=-1, error=<message>."
    missing:
      - "Add 'failed': -1 to the stage_progress dict (line 438)"
      - "Extend the error-field logic at line 453: 'if stage in (\"error\", \"failed\")'"
  - truth: "REQUIREMENTS.md reflects completed PERS-01, PERS-02, PERS-03 status"
    status: failed
    reason: "REQUIREMENTS.md still shows PERS-01, PERS-02, PERS-03 as unchecked [ ] despite the implementation being complete. Only PERS-04 is marked [x]. This is a documentation gap."
    artifacts:
      - path: ".planning/REQUIREMENTS.md"
        issue: "Lines 36-38: PERS-01, PERS-02, PERS-03 marked [ ] (incomplete) but the code fully satisfies them."
    missing:
      - "Update PERS-01 to [x] with note '— Plans 02-01, 02-02'"
      - "Update PERS-02 to [x] with note '— Plan 02-02 (JOBS_DIR on /data)'"
      - "Update PERS-03 to [x] with note '— Plan 02-02 (lifespan, list_jobs_last_30_days)'"
human_verification:
  - test: "Deploy to Render Starter tier with disk config and restart the service"
    expected: "Jobs created before restart are still visible in /api/jobs and /api/status after restart"
    why_human: "Cannot verify Render Persistent Disk survival across restarts without live deployment"
  - test: "Upload images until disk is near-full (>900MB used on 1GB disk), then attempt upload"
    expected: "HTTP 507 returned before pipeline starts"
    why_human: "Requires live Render environment with nearly-full disk"
---

# Phase 2: Persistence Verification Report

**Phase Goal:** Job state and files survive Render restarts and redeployments using SQLite on a Persistent Disk.
**Verified:** 2026-03-06
**Status:** gaps_found — 14/16 must-haves verified
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | `backend/database.py` exists and imports without error | VERIFIED | File exists at 229 lines; all imports from sqlalchemy present |
| 2 | Job model defines all required columns | VERIFIED | id, job_id, stage, stage_message, turbine_meta_json, image_count, total_images, flagged_images, critical_findings, pdf_path, 4 cost Text fields, image_cap_warning, error_traceback, created_at, updated_at, completed_at, failed_at — all present (lines 79-102) |
| 3 | `get_db()` context manager yields a session and closes it reliably | VERIFIED | Lines 54-65: @contextmanager, yields SessionLocal(), closes in finally block |
| 4 | `get_job()`, `save_new_job()`, `update_job()`, `set_stage()` CRUD helpers are callable | VERIFIED | All 5 helpers present (lines 144-228), using select()+session.scalars() (2.0 style) |
| 5 | `DATA_DIR` and `JOBS_DIR` are created automatically at import time | VERIFIED | Lines 20-23: mkdir(parents=True, exist_ok=True) before engine creation |
| 6 | `sqlalchemy>=2.0` is present in requirements.txt | VERIFIED | Line 25 of requirements.txt under "# --- Database" section |
| 7 | SQLite engine uses `check_same_thread=False` | VERIFIED | Lines 32-35: create_engine with connect_args={"check_same_thread": False} |
| 8 | WAL mode enabled via engine connect event | VERIFIED | Lines 40-46: @event.listens_for(engine, "connect"), PRAGMA journal_mode=WAL + PRAGMA synchronous=NORMAL |
| 9 | `app` starts with lifespan context manager (not deprecated @app.on_event) | VERIFIED | Lines 89-95: @asynccontextmanager async def lifespan; line 119: lifespan=lifespan passed to FastAPI() |
| 10 | On startup, interrupted jobs are marked failed with restart message | PARTIAL | `_mark_interrupted_jobs_failed()` correctly sets stage="failed" in DB (line 105). But /api/status stage_progress dict and error-field logic (lines 430-454) only handle stage="error", not stage="failed". Frontend receives progress=0, error=None for restarted jobs. |
| 11 | `_jobs` in-memory dict fully removed | VERIFIED | grep for `_jobs:` returns no matches; only indirect references (list_jobs_last_30_days function name) |
| 12 | POST /api/upload stores job in SQLite, DELETE removes row + directory | VERIFIED | Line 401-407: save_new_job(); lines 544-555: delete_job removes directory + SQLite row |
| 13 | GET /api/jobs returns 30-day filtered results (no filesystem glob) | VERIFIED | Lines 538-541: list_jobs_last_30_days(); grep for JOBS_DIR.glob returns no matches |
| 14 | POST /api/upload returns HTTP 507 if free disk < 100MB | VERIFIED | Lines 133-141: check_disk_space() raises HTTPException(507); line 365: called first in upload handler |
| 15 | After triage stage, images/ subdirectory is deleted | VERIFIED | Lines 211-214: shutil.rmtree(images_dir) after save_triage_results() |
| 16 | render.yaml has persistent disk config matching DATA_DIR default | VERIFIED | Lines 18-21: disk block with name=bdda-data, mountPath=/data, sizeGB=1 |

**Score:** 14/16 truths verified (1 partial, 1 documentation gap)

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/database.py` | SQLAlchemy engine, Job ORM model, session factory, CRUD helpers (min 120 lines) | VERIFIED | 229 lines — exceeds minimum; all components present and substantive |
| `requirements.txt` | Contains `sqlalchemy>=2.0` | VERIFIED | Line 25: `sqlalchemy>=2.0` under Database section |
| `backend/api.py` | FastAPI app with SQLite-backed job management | VERIFIED | 581 lines; `from database import` at line 28; lifespan at line 119; all endpoints use database functions |
| `backend/api.py` | Contains `lifespan` context manager | VERIFIED | Defined at line 90, wired to FastAPI at line 119 |
| `render.yaml` | Render blueprint with persistent disk config containing `mountPath: /data` | VERIFIED | Line 20: `mountPath: /data`; line 21: `sizeGB: 1`; line 19: `name: bdda-data` |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `backend/api.py` | `backend/database.py` | `from database import DATA_DIR, JOBS_DIR, init_db, get_db, get_job, save_new_job, update_job, set_stage, list_jobs_last_30_days, Job` | WIRED | Line 28-32: import statement present; all imported names used in api.py |
| `run_pipeline` | `database.update_job` / `database.set_stage` | Direct calls replacing old _jobs dict pattern | WIRED | Lines 176, 183, 209, 240, 262, 287-294, 298-304: multiple update_job/set_stage calls throughout pipeline stages |
| `/api/upload` | `shutil.disk_usage(DATA_DIR)` | `check_disk_space()` guard before `extract_upload` | WIRED | Line 365: `check_disk_space()` is first statement in upload handler body, before extract_upload at line 374 |
| `render.yaml disk block` | `DATA_DIR default /data in database.py` | `mountPath: /data` matches `Path(os.environ.get("DATA_DIR", "/data"))` | WIRED | render.yaml line 20 `mountPath: /data` exactly matches database.py line 20 default |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| PERS-01 | 02-01, 02-02 | Job state stored in SQLite (survives Render restarts) | SATISFIED (code) / NOT UPDATED (doc) | database.py created; api.py fully migrated from _jobs dict; REQUIREMENTS.md still shows [ ] |
| PERS-02 | 02-02 | Uploaded images and PDFs stored on Render Persistent Disk | SATISFIED (code) / NOT UPDATED (doc) | JOBS_DIR = DATA_DIR/"jobs" imported from database.py; all files written to /data/jobs/{job_id}/; REQUIREMENTS.md still shows [ ] |
| PERS-03 | 02-02 | Job history visible across sessions (no more lost jobs on restart) | SATISFIED (code) / NOT UPDATED (doc) | list_jobs_last_30_days() reads from SQLite, not filesystem; lifespan calls init_db() on startup; REQUIREMENTS.md still shows [ ] |
| PERS-04 | 02-03 | render.yaml updated with persistent disk config | SATISFIED | render.yaml has disk block; REQUIREMENTS.md correctly shows [x] |

**REQUIREMENTS.md discrepancy:** PERS-01, PERS-02, PERS-03 are implemented in code but remain marked `[ ]` in `.planning/REQUIREMENTS.md`. The file was not updated after Plan 02-02 completed.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/api.py` | 105 vs 438 | `stage="failed"` set by restart recovery but stage_progress dict and error-field logic only handle `stage="error"` | Warning | Restarted jobs show `progress=0` and `error=None` instead of `progress=-1` and meaningful error message. Functional gap in status reporting for interrupted jobs. |
| `.planning/REQUIREMENTS.md` | 36-38 | PERS-01, PERS-02, PERS-03 marked `[ ]` after completion | Info | Documentation not updated — does not affect runtime behavior |

---

## Human Verification Required

### 1. Persistent Disk Survival Across Restarts

**Test:** Deploy to Render Starter tier with the render.yaml disk config. Create a job, let it complete. Manually restart the Render service (from the dashboard). Check /api/jobs after restart.
**Expected:** Completed jobs still appear with correct stage, PDF download still works.
**Why human:** Cannot verify Render Persistent Disk survival across cloud restarts from static analysis.

### 2. Disk Full Guard (507)

**Test:** Upload files until the 1GB disk is nearly full, then attempt a new upload.
**Expected:** HTTP 507 response with "Server storage full" message before any extraction occurs.
**Why human:** Requires a live Render environment with a nearly-full persistent disk.

### 3. Restart Recovery — Interrupted Job Status Display

**Test:** Start a pipeline job. Kill the Render service mid-pipeline (e.g., force redeploy during triaging). Check /api/status/{job_id} after restart.
**Expected:** The interrupted job should show as failed with a meaningful message. Currently the stage is set to "failed" in DB but the status endpoint only surfaces error fields for stage=="error".
**Why human:** Requires live deployment to observe, but this is also the gap noted in Gaps section above.

---

## Gaps Summary

Two gaps were found:

**Gap 1 (Warning — stage name inconsistency):** The lifespan startup recovery function `_mark_interrupted_jobs_failed()` sets `stage="failed"` for interrupted jobs. However, the `/api/status/{job_id}` endpoint's `stage_progress` dict does not include a `"failed"` key (so it falls back to `progress=0`) and the error/error_traceback fields are only populated when `stage == "error"`. A job that was interrupted by a restart will have its stage and message correctly stored in SQLite, but the status API response will show `progress=0` and `error=None` — making it appear as a queued job rather than a failed one. Fix: add `"failed": -1` to `stage_progress` and extend the error-field condition to include `stage == "failed"`.

**Gap 2 (Info — documentation not updated):** `.planning/REQUIREMENTS.md` still marks PERS-01, PERS-02, and PERS-03 as `[ ]` (incomplete). The implementation fully satisfies all three requirements. PERS-04 is correctly marked `[x]`. Fix: update the three checkboxes to `[x]` with plan references.

These gaps do not block the core phase goal (job state and files survive Render restarts). The SQLite persistence layer, file path migration, lifespan init, disk guard, and render.yaml are all correctly implemented. The stage name gap affects the UX of restart recovery display but not the data integrity itself.

---

_Verified: 2026-03-06_
_Verifier: Claude (gsd-verifier)_
