---
phase: "02"
plan: "01"
subsystem: persistence
tags: [sqlalchemy, sqlite, orm, database]
dependency_graph:
  requires: []
  provides: [backend/database.py, sqlalchemy-dependency]
  affects: [backend/api.py]
tech_stack:
  added: [sqlalchemy>=2.0]
  patterns: [DeclarativeBase, sessionmaker, WAL-mode, contextmanager-session, select()-2.0-style]
key_files:
  created: [backend/database.py]
  modified: [requirements.txt]
decisions:
  - "Use Text columns for all cost fields (triage/classify/analyze/total_cost_usd) — avoids SQLite float precision artifacts"
  - "turbine_meta stored as JSON string in Text column — portable across SQLite versions, explicit json.dumps/loads"
  - "DATA_DIR/JOBS_DIR created at module import time — before engine creation (prevents OperationalError on first startup)"
  - "WAL mode + check_same_thread=False — enables concurrent reads from status endpoint while pipeline writes progress"
  - "list_jobs_last_30_days uses Python-side datetime comparison — bypasses SQLite ISO string comparison ambiguity"
metrics:
  duration: "~2 min"
  completed: "2026-03-06"
  tasks_completed: 2
  files_created: 1
  files_modified: 1
---

# Phase 2 Plan 01: Database Layer Summary

SQLAlchemy 2.0 sync ORM persistence layer — `backend/database.py` with engine, WAL mode, Job model, session factory, and 6 CRUD helpers replacing the in-memory `_jobs` dict and `state.json` filesystem approach.

---

## What Was Built

`backend/database.py` — the complete persistence foundation for Phase 2. This module owns the SQLAlchemy engine, session factory, `Job` ORM model, and all CRUD helpers. `api.py` (Plan 02-02) will import from this module exclusively.

Key design decisions followed exactly from `02-RESEARCH.md` and `02-CONTEXT.md`:

- **Engine**: `sqlite:///DATA_DIR/bdda.db` with `check_same_thread=False` (mandatory for FastAPI thread pool)
- **WAL mode**: Enabled via `@event.listens_for(engine, "connect")` — `PRAGMA journal_mode=WAL` + `PRAGMA synchronous=NORMAL`
- **Session factory**: `SessionLocal` via `sessionmaker(bind=engine, autocommit=False, autoflush=False)` + `get_db()` context manager (no auto-commit)
- **Job model**: `class Base(DeclarativeBase): pass` + `class Job(Base)` — SQLAlchemy 2.0 style, not legacy `declarative_base()`
- **All cost fields**: Stored as `Text` (string) to avoid SQLite float precision issues
- **turbine_meta**: Stored as JSON string in `Text` column — explicit `json.dumps`/`json.loads` in helpers
- **CRUD helpers**: `get_job`, `save_new_job`, `update_job`, `set_stage`, `list_jobs_last_30_days` — all using `select()` + `session.scalars()` (2.0 style)
- **DATA_DIR setup**: `mkdir(parents=True, exist_ok=True)` runs at import time, before engine creation (prevents `OperationalError` on first startup)
- **30-day filter**: Python-side `datetime.now(timezone.utc) - timedelta(days=30)` comparison — bypasses SQLite ISO string comparison ambiguity

---

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Create backend/database.py — engine, WAL, Job model, CRUD helpers | f2fb809 | backend/database.py (228 lines) |
| 2 | Add sqlalchemy>=2.0 to requirements.txt | 5b57e33 | requirements.txt |

---

## Verification Results

All plan verification checks passed:

1. `python3 -c "... import database; database.init_db(); print('database.py imports OK')"` — PASSED
2. `grep "sqlalchemy" requirements.txt` — returns `sqlalchemy>=2.0` — PASSED
3. `python3 -c "import sqlalchemy; print(sqlalchemy.__version__)"` — returns `2.0.48` — PASSED
4. Full CRUD round-trip (save_new_job → get_job → set_stage → get_job → update_job with cost → get_job) — All assertions PASSED

---

## Deviations from Plan

None — plan executed exactly as written. The `backend/database.py` implements all specified patterns from `02-RESEARCH.md` Pattern 1 + Pattern 3 + complete code example. No architectural decisions were required beyond what was specified.

---

## Must-Have Verification

| Truth | Status |
|-------|--------|
| backend/database.py exists and imports without error | PASSED |
| Job model defines all required columns | PASSED — id, job_id, stage, turbine_meta_json, pdf_path, all cost fields, all timestamps |
| get_db() context manager yields a session and closes reliably | PASSED |
| get_job(), save_new_job(), update_job(), set_stage() are callable | PASSED — all tested in verification |
| DATA_DIR and JOBS_DIR created at import time | PASSED |
| sqlalchemy>=2.0 in requirements.txt | PASSED |

| Artifact | Status |
|----------|--------|
| backend/database.py — 228 lines (min: 120) | PASSED |
| requirements.txt contains sqlalchemy>=2.0 | PASSED |

| Key Link | Status |
|----------|--------|
| sqlite:///DATA_DIR/bdda.db via create_engine with check_same_thread=False | PASSED |
| PRAGMA journal_mode=WAL via event.listens_for engine connect | PASSED |

---

## Self-Check: PASSED

Files verified:
- `backend/database.py` — EXISTS (228 lines)
- `requirements.txt` — MODIFIED (contains `sqlalchemy>=2.0`)

Commits verified:
- `f2fb809` — feat(02-01): create backend/database.py
- `5b57e33` — chore(02-01): add sqlalchemy>=2.0 to requirements.txt
