---
phase: 03-auth
verified: 2026-03-06T00:00:00Z
status: passed
score: 5/5 success criteria verified
re_verification: false
gaps: []
---

# Phase 3: Auth Verification Report

**Phase Goal:** Inspector login with JWT. All pipeline endpoints protected. Admin can create inspector accounts.
**Verified:** 2026-03-06
**Status:** PASS
**Re-verification:** No — initial verification

---

## Success Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|---------|
| 1 | POST /api/auth/token returns JWT for valid credentials | PASS | `api.py` line 371: `@app.post("/api/auth/token")`. Returns `{"access_token": token, "token_type": "bearer"}` after `verify_password()` check. |
| 2 | POST /api/upload returns 401 without valid token | PASS | `api.py` line 427: `current_user: dict = Depends(get_current_user)`. `get_current_user` raises HTTP 401 on missing/invalid token (`auth.py` line 104). |
| 3 | GET /api/jobs returns only jobs belonging to authenticated inspector | PASS | `api.py` lines 635-644: admin branch calls `list_jobs_last_30_days()` (no filter); inspector branch calls `list_jobs_last_30_days(owner_id=current_user["user_id"])`. `database.py` line 282: `stmt = stmt.where(Job.owner_id == owner_id)`. |
| 4 | POST /api/admin/create-user creates new inspector (protected by ADMIN_SECRET) | PASS | `api.py` line 392: `@app.post("/api/admin/create-user", status_code=201)`. Line 409: `if not ADMIN_SECRET or x_admin_secret != ADMIN_SECRET: raise HTTPException(status_code=403)`. |
| 5 | Login page at /login redirects to dashboard on success | PASS | `api.py` line 677: `@app.get("/login")` serves `frontend/login.html`. `login.html` line 79: `window.location.href = params.get('next') \|\| '/'` on successful token response. |

**Score: 5/5**

---

## Additional Checks

| Check | Status | Evidence |
|-------|--------|---------|
| User ORM model has id, username, hashed_password, is_admin, created_at | PASS | `database.py` lines 107-114: all five fields present. `id` is UUID String(36), `username` unique String(64), `hashed_password` Text, `is_admin` Boolean, `created_at` DateTime. |
| migrate_schema() uses PRAGMA table_info(jobs) — not IF NOT EXISTS | PASS | `database.py` line 131: `cursor.execute("PRAGMA table_info(jobs)")`. Line 134: `if "owner_id" not in existing_columns:` before ALTER TABLE. |
| _seed_admin_user() has lazy import of hash_password | PASS | `database.py` line 147: `from auth import hash_password  # imported here to avoid circular import at module level`. |
| auth.py uses PasswordHash((BcryptHasher(),)) — NOT PasswordHash.recommended() | PASS | `auth.py` line 40: `password_hash = PasswordHash((BcryptHasher(),))`. Comment on line 8 explicitly documents this constraint. |
| auth.py uses PyJWT (import jwt) — NOT python-jose | PASS | `auth.py` line 15: `import jwt`. Line 16: `from jwt.exceptions import InvalidTokenError`. |
| CORSMiddleware has expose_headers=["X-New-Token"] | PASS | `api.py` line 156: `expose_headers=["X-New-Token"],`. |
| Silent refresh middleware exists (attach_new_token_header) | PASS | `api.py` lines 138-147: `@app.middleware("http") async def attach_new_token_header(...)`. Reads `request.state.new_token` set by `get_current_user` and appends `X-New-Token` header. |
| lifespan() calls migrate_schema() and _seed_admin_user() | PASS | `api.py` lines 104-107: `init_db()` then `migrate_schema()` then `_seed_admin_user()` in startup order. |
| render.yaml has SECRET_KEY, ADMIN_SECRET, ADMIN_USERNAME, ADMIN_PASSWORD | PASS | `render.yaml` lines 28-34: all four env vars present. SECRET_KEY and ADMIN_SECRET have `sync: false`. ADMIN_USERNAME has `value: admin`. ADMIN_PASSWORD has `sync: false`. |
| requirements.txt has PyJWT==2.11.0 | PASS | `requirements.txt` line 28: `PyJWT==2.11.0`. |
| requirements.txt has pwdlib[bcrypt]==0.3.0 | PASS | `requirements.txt` line 29: `pwdlib[bcrypt]==0.3.0`. |
| Static file mount is the LAST route in api.py | PASS | `api.py` lines 686-689: `app.mount("/", StaticFiles(...))` appears after all `@app.get`/`@app.post` route definitions. |
| /api/estimate is public (no get_current_user) | PASS | `api.py` line 363: `@app.post("/api/estimate")` — no `Depends(get_current_user)` in signature. |
| /api/health is public (no get_current_user) | PASS | `api.py` line 666: `@app.get("/api/health")` — no `Depends(get_current_user)` in signature. |
| /api/debug/ai is public (no get_current_user) | PASS | `api.py` line 555: `@app.get("/api/debug/ai")` — no `Depends(get_current_user)` in signature. |

**Score: 15/15**

---

## Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|---------|
| AUTH-01 | Inspector can log in with username + password | PASS | `POST /api/auth/token` with `OAuth2PasswordRequestForm`; `login.html` submits URLSearchParams. |
| AUTH-02 | JWT token issued on login (8-hour session) | PASS | `auth.py` line 64: `timedelta(hours=TOKEN_EXPIRE_HOURS)` where `TOKEN_EXPIRE_HOURS = 8`. |
| AUTH-03 | All upload/status/download endpoints require valid token | PASS | `/api/upload`, `/api/status/{job_id}`, `/api/download/{job_id}`, `/api/jobs`, `DELETE /api/jobs/{job_id}` all have `Depends(get_current_user)`. |
| AUTH-04 | Admin can create new inspector accounts via protected endpoint | PASS | `POST /api/admin/create-user` protected by `X-Admin-Secret` header. |
| AUTH-05 | Each job linked to the inspector who created it | PASS | `database.py` line 100: `owner_id` column on Job. `api.py` line 492: `save_new_job(..., owner_id=current_user["user_id"])`. |

**Score: 5/5**

---

## Anti-Patterns

No blocking anti-patterns found. No TODO/FIXME/placeholder comments in auth-related files. No stub implementations. All handlers perform real work (DB queries, JWT operations, password verification).

---

## Human Verification Required

The following items cannot be verified programmatically:

### 1. Login redirect flow

**Test:** Open browser, navigate to `/login`, enter valid credentials, submit.
**Expected:** JWT stored in `localStorage` as `bdda_token`, browser redirects to `/`.
**Why human:** Requires live browser execution; localStorage writes and navigation cannot be verified by static analysis.

### 2. 401 returned to unauthenticated upload attempt

**Test:** Send `POST /api/upload` with no `Authorization` header.
**Expected:** HTTP 401 response with `{"detail": "Not authenticated"}`.
**Why human:** Requires running server; static analysis confirms wiring but not runtime behavior.

### 3. Silent token refresh on near-expiry

**Test:** Authenticate, set the token expiry to within 59 minutes, make any authenticated API call.
**Expected:** `X-New-Token` header present in response with a freshly minted JWT.
**Why human:** Requires manipulating JWT expiry in a live session.

---

## Summary

All 5 success criteria pass. All 15 additional checks pass. All 5 AUTH requirements are satisfied. No gaps found.

Key implementation points verified:
- `backend/auth.py` uses PyJWT + pwdlib[bcrypt] as specified, with correct `PasswordHash((BcryptHasher(),))` instantiation.
- `backend/database.py` has a complete `User` ORM model and `migrate_schema()` using `PRAGMA table_info` (SQLite 3.27 compatible).
- `backend/api.py` correctly orders routes: token endpoint first, static file mount last. All pipeline endpoints carry `Depends(get_current_user)`. Public endpoints (`/api/estimate`, `/api/health`, `/api/debug/ai`) have no auth guard as required.
- `render.yaml` declares all four new auth env vars.
- `requirements.txt` pins `PyJWT==2.11.0` and `pwdlib[bcrypt]==0.3.0`.

**Overall Verdict: PASS**

---

_Verified: 2026-03-06_
_Verifier: Claude (gsd-verifier)_
