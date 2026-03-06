---
phase: 03-auth
plan: "01"
subsystem: database
tags: [sqlalchemy, sqlite, user-model, schema-migration, crud]

# Dependency graph
requires:
  - phase: 02-persistence
    provides: SQLAlchemy engine, Job model, get_db() context manager, existing database.py pattern
provides:
  - User ORM model with id/username/hashed_password/is_admin/created_at fields
  - migrate_schema() using PRAGMA table_info check (SQLite 3.27.2 compat)
  - _seed_admin_user() with lazy auth import (avoids circular dependency)
  - get_user_by_username() returning dict or None
  - create_user() raising ValueError on duplicate username
  - owner_id column on Job model (nullable String(36))
  - save_new_job() accepting optional owner_id parameter
  - list_jobs_last_30_days() accepting optional owner_id filter
  - _job_to_dict() including owner_id in returned dict
affects:
  - 03-02 (auth.py JWT implementation — needs get_user_by_username, User model)
  - 03-03 (api.py auth integration — needs save_new_job owner_id, list_jobs_last_30_days filter)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Lazy import inside function body to break circular dependency: `from auth import hash_password` inside _seed_admin_user()"
    - "PRAGMA table_info(jobs) check before ALTER TABLE — avoids SQLite 3.37.0+ IF NOT EXISTS syntax"
    - "owner_id on Job is nullable VARCHAR(36) — legacy jobs have NULL, admin sees all, inspectors see only theirs"
    - "User.id uses String(36) UUID stored as plain text — explicit and portable for SQLite"

key-files:
  created: []
  modified:
    - backend/database.py

key-decisions:
  - "owner_id on Job model declared as String(36) not ForeignKey — SQLite FK enforcement is opt-in and migrate_schema uses raw ALTER TABLE which still sets the REFERENCES constraint for documentation purposes"
  - "User.id stored as String(36) UUID text rather than binary — portable and readable in SQLite browser tools"
  - "_seed_admin_user lazy imports auth.hash_password inside function body to avoid circular import at module level"
  - "migrate_schema uses PRAGMA table_info(jobs) pre-check because Render SQLite 3.27.2 lacks ADD COLUMN IF NOT EXISTS (requires 3.37.0+)"

patterns-established:
  - "Pattern: All new CRUD helpers follow SQLAlchemy 2.0 select() + session.scalars() style — no legacy session.query()"
  - "Pattern: _seed_* functions called from lifespan() in api.py, never at module import time"

requirements-completed: [AUTH-05]

# Metrics
duration: 8min
completed: 2026-03-06
---

# Phase 3 Plan 01: User model + schema migration Summary

**User ORM model with PRAGMA-based owner_id migration, admin auto-seeding, and CRUD helpers for username-based auth lookup**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-06T11:56:04Z
- **Completed:** 2026-03-06T12:04:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Added User ORM model with all 5 locked fields (id UUID, username unique, hashed_password, is_admin, created_at)
- Added migrate_schema() with PRAGMA table_info check for SQLite 3.27.2 compatibility on Render
- Added _seed_admin_user() with lazy auth import pattern to break circular dependency
- Added get_user_by_username() and create_user() CRUD helpers for auth.py (Plan 02)
- Updated Job model and all job CRUD functions to support owner_id for inspector visibility filtering

## Task Commits

Each task was committed atomically:

1. **Task 1: Add User model and migrate_schema() to database.py** - `cf9c904` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified
- `/Users/fabien/Desktop/CLAUDE/applications/drone/bdda/.claude/worktrees/frosty-banach/backend/database.py` - Added User model, migrate_schema(), _seed_admin_user(), get_user_by_username(), create_user(), updated save_new_job() + list_jobs_last_30_days() + _job_to_dict()

## Decisions Made
- Used String(36) for User.id (UUID as plain text) rather than a native UUID type — explicit and portable for SQLite-only project
- Placed owner_id on Job as a declared ORM column (nullable) so SQLAlchemy knows about it; migrate_schema() handles ALTER TABLE for existing DBs without `IF NOT EXISTS`
- Lazy import of `from auth import hash_password` inside `_seed_admin_user()` body to prevent circular import that would occur at module level

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The `python` command was not in PATH on this machine (macOS convention); used `python3` for verification — this is a local dev environment detail, not a code issue.

## User Setup Required

None - no external service configuration required. Environment variables `ADMIN_USERNAME` and `ADMIN_PASSWORD` are consumed at runtime by `_seed_admin_user()` which is called from api.py lifespan (added in Plan 03-03).

## Next Phase Readiness
- Plan 03-02 (auth.py): `get_user_by_username()` and `create_user()` are ready; User model is importable
- Plan 03-03 (api.py integration): `save_new_job(owner_id=...)` and `list_jobs_last_30_days(owner_id=...)` are ready; `_seed_admin_user()` and `migrate_schema()` are ready to be called from lifespan()
- No blockers

---
*Phase: 03-auth*
*Completed: 2026-03-06*
