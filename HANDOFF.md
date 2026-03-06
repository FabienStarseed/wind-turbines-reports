# BDDA Project Handoff

**Branch:** `claude/frosty-banach`
**Last updated:** 2026-03-06
**Status:** Phase 3 CLOSED ✅ — Phase 4 (PDF Redesign) is next

---

## What was just done

### Phase 3: Auth ✅ COMPLETE (fully verified 5/5 + 15/15 checks)

JWT authentication + endpoint protection:
- `backend/auth.py` — NEW: PyJWT + pwdlib/bcrypt, `get_current_user` dependency, silent refresh via `request.state.new_token`
- `backend/database.py` — User ORM model, `migrate_schema()` (PRAGMA-safe), `_seed_admin_user()`, `owner_id` FK on Job
- `backend/api.py` — 5 endpoints protected, `POST /api/auth/token`, `POST /api/admin/create-user`, `GET /login`, silent refresh middleware, `expose_headers=["X-New-Token"]`
- `frontend/login.html` — functional login page (unstyled — Phase 5 redesigns)
- `render.yaml` — `SECRET_KEY`, `ADMIN_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` env vars

---

## ⚠️ Before deploying Phase 3 to Render

Set these in Render Dashboard → Environment (never in repo — sync:false):
1. `SECRET_KEY` → run `openssl rand -hex 32` and paste result
2. `ADMIN_SECRET` → any strong random string (you'll use this header to create inspector accounts)
3. `ADMIN_PASSWORD` → your admin password

After deploy, create inspector accounts:
```bash
curl -X POST https://wind-turbines-reports.onrender.com/api/admin/create-user \
  -H "X-Admin-Secret: YOUR_ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"username": "inspector1", "password": "strong_password"}'
```

---

## Immediate next step

Start Phase 4: PDF Redesign

```
/gsd:discuss-phase 4
```

🔶 **Switch to Opus** for Phase 4 — PDF layout design is complex visual/architectural work.

---

## Key technical decisions (locked)

### Auth Stack (Phase 3)
- Library: PyJWT==2.11.0 (`import jwt`) — NOT python-jose (abandoned)
- Hashing: pwdlib[bcrypt]==0.3.0 with `PasswordHash((BcryptHasher(),))` — NOT `PasswordHash.recommended()` (gives Argon2), NOT passlib (broken)
- JWT payload: `{ "sub": username, "user_id": uuid_str, "is_admin": bool, "exp": unix_ts }`
- Token lifetime: 8 hours
- Silent refresh: new token in `X-New-Token` response header when <1h remaining
- Token storage: `localStorage['bdda_token']`
- Admin auth: `X-Admin-Secret` header (NOT JWT — separate secret for create-user endpoint)
- SQLite migration: PRAGMA `table_info(jobs)` before `ALTER TABLE` (Render SQLite 3.27.2 — no `IF NOT EXISTS`)
- Legacy jobs (pre-auth): `owner_id = NULL` → admin sees them, inspectors do not
- Public endpoints (no auth): `/api/estimate`, `/api/health`, `/api/debug/ai`

### AI Stack (Phase 1)
- Model: `claude-opus-4-6` everywhere (triage, classify, analyze)
- Pricing: $5/M input, $25/M output
- Triage: 4 tiles, 0.3 onshore / 0.2 offshore threshold
- Images: raw base64 only — NO `data:image/...` URI prefix

### Persistence (Phase 2)
- SQLAlchemy 2.0 sync + SQLite WAL
- `DATA_DIR` env var: `/data` on Render, `./data` local
- Raw images deleted after triage (15-30MB DJI P1 each)
- 30-day job history, 507 on disk full, interrupted jobs → failed on restart

### Defect Classification
- IEC Cat 0-4 + BDDA 0-10 dual scoring
- `has_critical` = `iec_category >= 3`
- 56 defect types in `backend/taxonomy.py`

---

## Project overview

**What:** BDDA — AI pipeline for drone wind turbine blade inspection
**Stack:** FastAPI + SQLAlchemy + Anthropic SDK + PyJWT + pwdlib + fpdf2 (Phase 4) + Tailwind/Alpine.js (Phase 5)
**Deploy:** Render.com Starter tier ($7/mo — needed for 1GB persistent disk)
**Live URL:** https://wind-turbines-reports.onrender.com
**Test images:** `/Users/fabien/Desktop/CLAUDE/applications/drone/bdda/sources/resume/images/enercon/EN01/` (63 DJI P1 JPGs)

---

## Roadmap status

| Phase | Name | Status |
|-------|------|--------|
| 1 | AI Consolidation | ✅ Complete |
| 2 | Persistence | ✅ Complete |
| 3 | Auth (JWT login) | ✅ Complete |
| 4 | PDF Redesign (fpdf2) | ⬜ Not started |
| 5 | Frontend UI (Tailwind+Alpine) | ⬜ Not started |

**Requirements remaining:**
- PDF-01..06: fpdf2, DroneWind Asia branding, defect images inline, severity colour-coding, executive summary, per-blade defect map
- UI-01..06: Tailwind+Alpine, login page redesign, upload form, live progress, job history, mobile-responsive

---

## Visual outputs → Nimbalyst

Any charts, graphs, or dashboards generated for this project → **view in Nimbalyst** (not inline).

---

## Reminders

- 🔶 **Switch to Opus** for Phase 4 PDF layout design — complex visual/architectural decisions
- 🔶 **Switch to Opus** for Phase 5 UI architecture — full frontend redesign
- Push directly to `main` — no PRs needed (solo developer)
- GSD tools: `/Users/fabien/.claude/get-shit-done/bin/gsd-tools.cjs`
- Worktree path: `/Users/fabien/Desktop/CLAUDE/applications/drone/bdda/.claude/worktrees/frosty-banach/`
