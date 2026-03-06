---
phase: 03-auth
plan: "04"
subsystem: auth
tags: [jwt, html, login, oauth2, localstorage, render, env-vars]

# Dependency graph
requires:
  - phase: 03-auth/03-03
    provides: GET /login route in api.py, POST /api/auth/token endpoint, auth middleware
  - phase: 03-auth/03-02
    provides: PyJWT and pwdlib already in requirements.txt
provides:
  - "frontend/login.html — functional login page with URLSearchParams OAuth2 form submission"
  - "localStorage['bdda_token'] JWT storage pattern"
  - "X-New-Token header check on login response"
  - "render.yaml with SECRET_KEY, ADMIN_SECRET, ADMIN_USERNAME, ADMIN_PASSWORD env vars"
affects: [05-ui, any phase adding authenticated frontend pages]

# Tech tracking
tech-stack:
  added: []  # requirements.txt already had PyJWT and pwdlib from 03-02
  patterns:
    - "OAuth2 x-www-form-urlencoded login via URLSearchParams (not JSON)"
    - "JWT stored in localStorage under key 'bdda_token'"
    - "Silent token refresh via X-New-Token response header"
    - "?next= redirect param for post-login navigation"
    - "Render sync:false for secrets (never stored in repo)"

key-files:
  created:
    - frontend/login.html
  modified:
    - render.yaml

key-decisions:
  - "Login form uses URLSearchParams (not JSON) to satisfy FastAPI OAuth2PasswordRequestForm x-www-form-urlencoded requirement"
  - "Already-logged-in users are redirected immediately on page load (prevents double-login loop)"
  - "X-New-Token header checked on login response to support token refresh from first interaction"
  - "ADMIN_USERNAME committed as value:admin (non-secret default); all passwords/secrets use sync:false"

patterns-established:
  - "URLSearchParams pattern: new URLSearchParams(new FormData(form)) for OAuth2 endpoints"
  - "bdda_token: all frontend pages store/read JWT under this localStorage key"
  - "Render secrets: sync:false means Render prompts for value in Dashboard — never in repo"

requirements-completed: [AUTH-01, AUTH-02]

# Metrics
duration: 10min
completed: 2026-03-06
---

# Phase 3 Plan 04: Login Page + Auth Env Vars Summary

**Self-contained HTML login page submitting to POST /api/auth/token via URLSearchParams OAuth2 format, with JWT localStorage storage, X-New-Token refresh header support, and four auth env vars added to render.yaml**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-03-06T00:00:00Z
- **Completed:** 2026-03-06T00:10:00Z
- **Tasks:** 2
- **Files modified:** 2 (login.html created, render.yaml updated)

## Accomplishments

- Created `frontend/login.html` — functional unstyled login page (Phase 5 redesigns with Tailwind)
- Form submits as `application/x-www-form-urlencoded` via `URLSearchParams` — required by FastAPI `OAuth2PasswordRequestForm`
- On success: stores JWT in `localStorage['bdda_token']`, redirects to `?next=` param or `/`
- On failure: shows "Invalid credentials" inline without page reload
- If already logged in: immediately redirects (no double-login loop)
- Checks `X-New-Token` response header and updates stored token if present
- Added 4 auth env vars to `render.yaml`: `SECRET_KEY`, `ADMIN_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`
- Verified `GET /login` route exists in `api.py` (added in Plan 03-03) — no changes needed
- `requirements.txt` already had `PyJWT==2.11.0` and `pwdlib[bcrypt]==0.3.0` (added in Plan 03-02) — no changes needed

## Task Commits

Each task was committed atomically (both tasks committed together since they form one logical change):

1. **Task 1: Create frontend/login.html** + **Task 2: Update render.yaml + verify** - `a31645f` (feat)

**Plan metadata:** Committed with SUMMARY.md and STATE.md below.

## Files Created/Modified

- `frontend/login.html` — Self-contained login page with OAuth2 form, JWT storage, redirect logic, X-New-Token header check
- `render.yaml` — Added SECRET_KEY (sync:false), ADMIN_SECRET (sync:false), ADMIN_USERNAME (value:admin), ADMIN_PASSWORD (sync:false)

## Decisions Made

- Used `URLSearchParams(new FormData(form))` pattern — required by FastAPI `OAuth2PasswordRequestForm` which expects `application/x-www-form-urlencoded`, not JSON
- `ADMIN_USERNAME` committed with `value: admin` (safe default, not a secret); all actual secrets use `sync: false`
- `X-New-Token` header is checked even on the initial login response to cover edge cases (server-issued refresh on first login)
- Already-logged-in redirect uses `window.location.href` in an IIFE — runs before DOM is painted

## Deviations from Plan

None — plan executed exactly as written.

- `requirements.txt` already had auth packages from Plan 03-02 (as expected per instructions)
- `GET /login` route already existed in `api.py` from Plan 03-03 (as expected per instructions — verification only, no code changes)
- Smoke test confirmed login page served and auth endpoint functional

## Issues Encountered

None.

## User Setup Required

**External services require manual configuration before deploying to Render:**

Set these values in **Render Dashboard -> Service -> Environment**:

| Variable | How to generate | Required |
|---|---|---|
| `SECRET_KEY` | `openssl rand -hex 32` | Yes — JWT signing key |
| `ADMIN_SECRET` | `openssl rand -hex 16` | Yes — protects /api/admin/create-user |
| `ADMIN_PASSWORD` | Choose strong password | Yes — admin login password |
| `ADMIN_USERNAME` | Override if desired (default: `admin`) | No |

If `ADMIN_PASSWORD` is not set before first deploy, the server seeds admin with password `changeme` and logs a warning.

## Next Phase Readiness

- Phase 3 auth is now complete: JWT endpoints, auth middleware, ownership enforcement, login page all in place
- Phase 4 (gaps/fixes) already completed (Plan 02-gaps)
- Phase 5 (UI) can now redesign `frontend/login.html` with Tailwind + Alpine.js
- All 5 Phase 3 success criteria are met:
  1. POST /api/auth/token returns JWT for valid credentials
  2. POST /api/upload returns 401 without valid token
  3. GET /api/jobs returns only jobs belonging to authenticated inspector
  4. POST /api/admin/create-user creates new inspector (protected by ADMIN_SECRET header)
  5. Login page at /login redirects to dashboard on success

## Self-Check: PASSED

- FOUND: `frontend/login.html` (created)
- FOUND: `render.yaml` (modified with 4 auth env vars)
- FOUND: `.planning/phases/03-auth/03-04-SUMMARY.md` (this file)
- FOUND: commit `a31645f` (feat(03-04): login page + auth env vars in render.yaml)
- VERIFIED: URLSearchParams (4 matches), bdda_token (3 matches), /api/auth/token (1 match) in login.html
- VERIFIED: PyJWT and pwdlib in requirements.txt; python-jose and passlib absent
- VERIFIED: SECRET_KEY, ADMIN_SECRET, ADMIN_USERNAME, ADMIN_PASSWORD in render.yaml
- VERIFIED: GET /login route (login_page function) in api.py
- SMOKE TEST: Login page served OK; Auth endpoint returns access_token OK

---
*Phase: 03-auth*
*Completed: 2026-03-06*
