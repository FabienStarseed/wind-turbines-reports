---
phase: 03-auth
plan: "02"
subsystem: auth
tags: [jwt, bcrypt, pyjwt, pwdlib, fastapi, oauth2]

# Dependency graph
requires:
  - phase: 03-01
    provides: User model (database.py) with get_user_by_username and create_user CRUD helpers
provides:
  - hash_password() — bcrypt hashing via pwdlib[bcrypt] with explicit BcryptHasher
  - verify_password() — bcrypt verification
  - create_token() — signed HS256 JWT with sub/user_id/is_admin/exp (8h lifetime)
  - decode_token() — JWT decode raising InvalidTokenError on failure
  - get_current_user() — async FastAPI dependency with silent refresh (<60 min remaining)
  - oauth2_scheme — OAuth2PasswordBearer pointed at /api/auth/token
affects: [03-03, 03-04]

# Tech tracking
tech-stack:
  added:
    - PyJWT==2.11.0 (JWT encode/decode — official FastAPI recommendation replacing python-jose)
    - pwdlib[bcrypt]==0.3.0 (password hashing — official FastAPI replacement for passlib)
  patterns:
    - PasswordHash((BcryptHasher(),)) — explicit bcrypt, NOT PasswordHash.recommended() which defaults to Argon2
    - Silent refresh via request.state.new_token — picked up by middleware in api.py
    - SECRET_KEY startup warning if missing or shorter than 32 chars

key-files:
  created:
    - backend/auth.py
  modified:
    - requirements.txt (added PyJWT and pwdlib[bcrypt])

key-decisions:
  - "Use PasswordHash((BcryptHasher(),)) explicitly — PasswordHash.recommended() defaults to Argon2, not bcrypt"
  - "PyJWT 2.11.0 chosen over python-jose (abandoned) per FastAPI official docs"
  - "pwdlib[bcrypt] chosen over passlib (abandoned, breaks with bcrypt 4.x+) per FastAPI official docs"
  - "Silent refresh: new token minted in get_current_user() and attached to request.state.new_token when <60 min remaining"
  - "SECRET_KEY warning logged at module load if missing or <32 chars"

patterns-established:
  - "Pattern: JWT round-trip — create_token() → decode_token() → user dict extraction"
  - "Pattern: Silent refresh via request.state, picked up by middleware writing X-New-Token header"
  - "Pattern: All auth logic in auth.py — api.py imports from auth.py, no circular deps"

requirements-completed: [AUTH-01, AUTH-02, AUTH-03]

# Metrics
duration: 2min
completed: 2026-03-06
---

# Phase 3 Plan 02: Auth.py Summary

**JWT utilities and bcrypt password hashing via PyJWT 2.11.0 + pwdlib[bcrypt] with silent token refresh via request.state**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-06T12:01:41Z
- **Completed:** 2026-03-06T12:03:58Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Created `backend/auth.py` with all 6 exports: `hash_password`, `verify_password`, `create_token`, `decode_token`, `get_current_user`, `oauth2_scheme`
- Used `PasswordHash((BcryptHasher(),))` explicitly — NOT `PasswordHash.recommended()` which defaults to Argon2
- JWT tokens include sub/user_id/is_admin/exp claims with 8-hour lifetime (per CONTEXT.md Area C)
- Silent refresh logic: when token has <60 minutes remaining, a new token is minted and stored on `request.state.new_token`
- `SECRET_KEY` startup warning if missing or shorter than 32 characters
- Added `PyJWT==2.11.0` and `pwdlib[bcrypt]==0.3.0` to `requirements.txt`

## Task Commits

Each task was committed atomically:

1. **Task 1: Create backend/auth.py** - `13752cf` (feat)

**Plan metadata:** (to be committed with this SUMMARY.md)

## Files Created/Modified

- `backend/auth.py` — Complete auth module: hash_password, verify_password, create_token, decode_token, get_current_user, oauth2_scheme
- `requirements.txt` — Added PyJWT==2.11.0 and pwdlib[bcrypt]==0.3.0 under Auth section

## Decisions Made

- `PasswordHash((BcryptHasher(),))` over `PasswordHash.recommended()`: CONTEXT.md Area A locks bcrypt as the hash algorithm. `recommended()` defaults to Argon2 (requires `pwdlib[argon2]` extra). Explicit BcryptHasher avoids the wrong default.
- `PyJWT` over `python-jose`: `python-jose` is abandoned (~3 years no release). Official FastAPI docs now recommend PyJWT.
- `pwdlib[bcrypt]` over `passlib`: `passlib` is abandoned and breaks with bcrypt 4.x+ and Python 3.13+. Official FastAPI docs recommend `pwdlib` as the successor.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added PyJWT and pwdlib[bcrypt] to requirements.txt**
- **Found during:** Task 1 (Create backend/auth.py)
- **Issue:** Packages not in `requirements.txt` — needed for verification script to run and for deploy correctness
- **Fix:** Added `PyJWT==2.11.0` and `pwdlib[bcrypt]==0.3.0` to `requirements.txt` under new `# Auth` section. Installed locally for testing via pip3.
- **Files modified:** requirements.txt
- **Verification:** pip install succeeded; verify script ran clean
- **Committed in:** `13752cf` (same task commit)

**Note on local Python version:** This machine has Python 3.9; only `pwdlib==0.2.1` was installable locally (0.3.0 requires Python 3.10+). The API is identical and tests passed. The production runtime (Python 3.12, per `runtime.txt`) will install `pwdlib[bcrypt]==0.3.0` as specified.

---

**Total deviations:** 1 auto-fixed (Rule 3 — blocking dependency)
**Impact on plan:** Required for correctness. No scope creep.

## Issues Encountered

None — verification script passed cleanly on all 3 assertions.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `backend/auth.py` is complete and importable
- `get_current_user` dependency ready for Plan 03-03 (protect api.py endpoints with `Depends(get_current_user)`)
- `hash_password` and `create_user` from `database.py` are ready for `_seed_admin_user()` in Plan 03-03
- `oauth2_scheme` ready for the login endpoint (`POST /api/auth/token`) in Plan 03-03
- No blockers for 03-03

---
*Phase: 03-auth*
*Completed: 2026-03-06*
