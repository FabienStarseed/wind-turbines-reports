---
phase: 03-auth
plan: "03"
subsystem: auth
tags: [jwt, fastapi, oauth2, bcrypt, sqlite, cors]

# Dependency graph
requires:
  - phase: 03-auth/03-01
    provides: database.py with User model, get_user_by_username, create_user, _seed_admin_user, save_new_job with owner_id, list_jobs_last_30_days with owner_id filter
  - phase: 03-auth/03-02
    provides: auth.py with get_current_user, create_token, verify_password, hash_password, OAuth2PasswordBearer
provides:
  - POST /api/auth/token login endpoint using OAuth2PasswordRequestForm
  - POST /api/admin/create-user protected by X-Admin-Secret header
  - GET /login route serving login.html (404 fallback until Plan 04 creates file)
  - JWT protection on POST /api/upload, GET /api/status/{job_id}, GET /api/download/{job_id}, GET /api/jobs, DELETE /api/jobs/{job_id}
  - Ownership enforcement (403 for non-admin accessing another user's job)
  - Silent refresh middleware setting X-New-Token response header
  - CORS expose_headers updated to include X-New-Token
  - lifespan() calling init_db -> migrate_schema -> _seed_admin_user -> _mark_interrupted_jobs_failed
affects:
  - 03-auth/03-04 (login.html — GET /login route registered here)
  - 04-ui (frontend JS needs X-New-Token header handling, Bearer token in requests)
  - 05-deploy (ADMIN_SECRET env var required)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "OAuth2PasswordRequestForm for login (x-www-form-urlencoded, not JSON)"
    - "get_current_user FastAPI dependency injected per-endpoint via Depends()"
    - "Silent token refresh via request.state.new_token + HTTP middleware header injection"
    - "X-Admin-Secret header (not JWT) for admin-only create-user endpoint"
    - "Ownership check pattern: if not current_user['is_admin'] and owner_id != user_id: 403"

key-files:
  created: []
  modified:
    - backend/api.py

key-decisions:
  - "GET /login registered before static mount — static mount remains last route registration"
  - "ADMIN_SECRET read at module level (not per-request) for consistent guard behavior"
  - "lifespan order: init_db -> migrate_schema -> _seed_admin_user -> _mark_interrupted_jobs_failed (migrate before seed to ensure owner_id column exists)"
  - "DELETE /api/jobs/{job_id}: ownership check before directory deletion to avoid removing files for unauthorized requests"
  - "Public endpoints kept: /api/estimate, /api/health, /api/debug/ai (no auth required)"

patterns-established:
  - "Ownership enforcement pattern: admin exempt, inspector must own job (check current_user['is_admin'] first)"
  - "Silent refresh via middleware: request.state.new_token set by get_current_user, read by attach_new_token_header"

requirements-completed: [AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05]

# Metrics
duration: 3min
completed: 2026-03-06
---

# Phase 3 Plan 03: Auth Integration Summary

**All 5 AUTH endpoints wired into FastAPI: JWT login, admin create-user, 5 protected endpoints with ownership enforcement, silent-refresh middleware, and GET /login route**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-06T12:07:00Z
- **Completed:** 2026-03-06T12:09:30Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- Wired auth.py and database.py into api.py — all 5 AUTH requirements satisfied in the live API
- 14 isolated changes applied sequentially: imports, ADMIN_SECRET, lifespan, middleware, CORS, 8 endpoint changes, GET /login
- Both verify scripts pass: module loads OK, all expected routes present, static mount last

## Task Commits

Each task was committed atomically:

1. **Tasks 1+2: Add imports, middleware, CORS update, lifespan changes, new endpoints, protect existing endpoints** - `d7463fe` (feat)

**Plan metadata:** _(pending final docs commit)_

## Files Created/Modified
- `backend/api.py` - Auth-protected FastAPI app: all 14 changes applied (imports, middleware, CORS, lifespan, 2 new endpoints, 5 protected endpoints, GET /login)

## Decisions Made
- GET /login registered before static mount — the static `app.mount("/")` must remain the absolute last route registration or it swallows all other routes
- ADMIN_SECRET at module level ensures consistent guard behavior (value resolved once at startup)
- lifespan call order: init_db then migrate_schema (owner_id column must exist) then _seed_admin_user (needs owner_id column for correct seeding) then _mark_interrupted_jobs_failed
- DELETE ownership check placed before directory deletion — prevents removing files for jobs the requesting user doesn't own

## Deviations from Plan

None - plan executed exactly as written. All 14 changes applied in order.

## Issues Encountered

None.

## User Setup Required

New environment variable required:

| Var | Required | Description |
|-----|----------|-------------|
| `ADMIN_SECRET` | Yes | Header value to authorize `POST /api/admin/create-user` |

Already documented in 03-CONTEXT.md. No additional setup needed.

## Next Phase Readiness
- All 5 AUTH requirements (AUTH-01 through AUTH-05) are satisfied in backend/api.py
- GET /login route registered and ready — Plan 04 creates the login.html file
- Frontend needs to: send `Authorization: Bearer <token>` on protected requests, handle 401 by redirecting to /login, check X-New-Token response header to silently update stored token

---
*Phase: 03-auth*
*Completed: 2026-03-06*
