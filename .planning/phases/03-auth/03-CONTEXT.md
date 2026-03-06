# Phase 3: Auth — Context & Decisions

**Phase goal:** JWT login for inspectors, all pipeline endpoints protected, admin creates accounts.
**Date:** 2026-03-06
**Status:** Decisions locked ✅

---

## Area A — Inspector Account Setup

**Decision: Admin (Fabien) creates all accounts manually via protected endpoint.**

- There is exactly one admin: Fabien (the drone pilot / operator)
- Admin account is bootstrapped at startup via an `ADMIN_SECRET` env var — no UI needed, just a secret header or env-seeded user
- All inspector accounts are created by the admin via `POST /api/admin/create-user`
- No self-registration — inspectors are always invited/created by admin
- `POST /api/admin/create-user` is protected by a separate `ADMIN_SECRET` header (not JWT — admin operates via direct API call, not the inspector UI)
- Inspector credentials: `username` + `password` (bcrypt-hashed in DB)
- On first deploy, seed ONE admin user automatically if no users exist (username=`admin`, password from `ADMIN_PASSWORD` env var)

**Locked fields for User ORM:**
- `id` (UUID)
- `username` (unique)
- `hashed_password`
- `is_admin` (bool)
- `created_at`

---

## Area B — Job Visibility & Ownership

**Decision: Inspectors see only their own jobs. Admin (is_admin=True) sees all jobs.**

- `Job` table gets a `owner_id` FK → `User.id`
- `GET /api/jobs` returns:
  - If admin → all jobs (last 30 days)
  - If inspector → only jobs where `owner_id == current_user.id` (last 30 days)
- `POST /api/upload` assigns `owner_id = current_user.id` at job creation
- Existing jobs (created before auth existed) have `owner_id = NULL` → admin sees them, inspectors do not
- Job 30-day retention already implemented in Phase 2 — no change needed

**Ownership enforcement on all job endpoints:**
- `GET /api/status/{job_id}` — 403 if not owner (admin exempt)
- `GET /api/download/{job_id}` — 403 if not owner (admin exempt)
- `DELETE /api/jobs/{job_id}` — 403 if not owner (admin exempt)

---

## Area C — Token & Session Behaviour

**Decision: 8-hour JWT, silent refresh before expiry, no re-login required.**

- JWT lifetime: 8 hours (per AUTH-02)
- Refresh strategy: issue a new JWT whenever the current token has less than **1 hour remaining** — done transparently on any API call (returned in response header `X-New-Token`)
- Frontend checks for `X-New-Token` header on every response and updates its stored token if present
- No explicit refresh endpoint needed — refresh is opportunistic on normal API calls
- If token is already expired → 401 returned, frontend redirects to `/login`
- Token storage: `localStorage` (acceptable for internal inspector tool)
- Token payload: `{ "sub": username, "user_id": uuid, "is_admin": bool, "exp": unix_ts }`

---

## Area D — Login Page & Redirect Flow

**Decision: Login page at `/login`. After login → general welcome/dashboard screen (Phase 5 UI). Unauthenticated access → redirect to `/login`.**

- `/login` is a simple HTML page (self-contained, minimal — Phase 5 will polish it)
- On successful login → redirect to `/` (main dashboard / welcome screen)
- If unauthenticated user hits a protected page → frontend redirects to `/login?next=<original_url>`
- After login, redirect to `next` param if present, else `/`
- Phase 3 login page is functional but unstyled — Phase 5 redesigns it with Tailwind + Alpine.js

**Login page scope (Phase 3 only):**
- Username + password form
- Submit → `POST /api/auth/token`
- On success → store JWT, redirect
- On failure → show "Invalid credentials" inline (no flash/session needed)
- No "forgot password" — admin resets manually by recreating account

---

## Endpoint Summary (what gets added/modified)

### New endpoints
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/auth/token` | None | Login → returns JWT |
| POST | `/api/admin/create-user` | ADMIN_SECRET header | Create inspector account |
| GET | `/login` | None | Login HTML page |

### Modified endpoints (add JWT guard)
| Method | Path | Change |
|--------|------|--------|
| POST | `/api/upload` | Require JWT; assign `owner_id` |
| GET | `/api/status/{job_id}` | Require JWT; enforce ownership |
| GET | `/api/download/{job_id}` | Require JWT; enforce ownership |
| DELETE | `/api/jobs/{job_id}` | Require JWT; enforce ownership |
| GET | `/api/jobs` | Require JWT; filter by owner (admin sees all) |
| POST | `/api/estimate` | Keep public (no auth needed — cost check before login) |
| GET | `/api/health` | Keep public |
| GET | `/api/debug/ai` | Keep public (dev tool) |

---

## Database Changes

- New `User` table (SQLAlchemy model in `database.py`)
- `Job` table: add `owner_id` column (nullable FK → `User.id`)
- Startup: auto-seed admin user if no users exist (reads `ADMIN_USERNAME` + `ADMIN_PASSWORD` env vars; defaults `admin`/`changeme` with warning log)

---

## Environment Variables (new)

| Var | Required | Description |
|-----|----------|-------------|
| `SECRET_KEY` | Yes | JWT signing key (random 32-byte hex) |
| `ADMIN_SECRET` | Yes | Header value to authorize `create-user` endpoint |
| `ADMIN_USERNAME` | No | Seed admin username (default: `admin`) |
| `ADMIN_PASSWORD` | No | Seed admin password (default: `changeme` — warn if unchanged) |

---

## Out of Scope for Phase 3

- Styled login page → Phase 5
- Password reset flow → not needed (admin recreates account)
- Multi-tenant org structure → not needed (single admin model)
- OAuth / SSO → not needed
