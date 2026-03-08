# BDDA Project Handoff

**Branch:** `claude/frosty-banach`
**Last updated:** 2026-03-08
**Status:** Phase 4 CLOSED ✅ — Phase 5 (Frontend UI) is next

---

## What was just done

### Phase 4: PDF Redesign ✅ COMPLETE (15/15 automated + 2 human sign-offs)

Professional PDF reports using fpdf2 with AWID branding:
- `backend/report.py` — REWRITTEN: `BDDAReport(FPDF)` class with branded header/footer, cover page, TOC, executive summary, per-defect pages (1/page, 80×80mm images, severity colour bands), action matrix, per-blade defect map (zone grid with severity markers), inspection details + legal disclaimer
- `backend/api.py` — Pipeline wired to `generate_pdf_fpdf2()`, thumbnail save before deletion (PIL 1568px JPEG), old templates removed
- `assets/fonts/` — Inter TTF fonts bundled (Regular, Bold, Italic)
- `requirements.txt` — Added fpdf2>=2.8.0, Pillow>=10.0.0; removed xhtml2pdf/jinja2
- `templates/` — DELETED (old HTML/CSS report templates)

**Key fixes during execution:**
- Blank page 2 bug: cover's CONFIDENTIAL footer at y=279mm triggered auto page break → fixed with `set_auto_page_break(auto=False)` around footer
- `iec_category` → `category` key normalization in `build_report_data()` (classify.py saves `iec_category`, old code read `category`)
- Rebranded from "DroneWind Asia" to "AWID - APAC Wind Inspections Drones"

---

## Immediate next step

Start Phase 5: Frontend UI

```
/gsd:discuss-phase 5
```

🔶 **Switch to Opus** for Phase 5 — full frontend redesign with Cyber Operator design system.

**Design system:** `/Users/fabien/Desktop/CLAUDE/-SKILLS/design-style/design-style.md` — apply "Cyber Operator" dark dashboard style to all frontend pages.

---

## Key technical decisions (locked)

### PDF Stack (Phase 4)
- Library: fpdf2>=2.8.0 — FPDF subclass with header()/footer() overrides
- Fonts: Inter TTF bundled in `assets/fonts/` (Render has no system fonts)
- Branding: AWID - APAC Wind Inspections Drones (navy palette, text header — no logo image)
- Layout: Cover → TOC → Exec Summary → Defect pages (1/page, 80×80mm) → Action Matrix → Blade Maps → Inspection Details
- Images: PIL thumbnail (1568px JPEG) saved before raw deletion → BytesIO embed → grey placeholder fallback
- Severity: SEVERITY_COLORS_IEC keyed 0-4 (green→yellow→orange→red→dark red)
- Blade map: 4×3 zone grid (LE/TE/PS/SS × Root/Mid/Tip) with severity-coloured cells + white circle markers

### Auth Stack (Phase 3)
- Library: PyJWT==2.11.0 (`import jwt`) — NOT python-jose (abandoned)
- Hashing: pwdlib[bcrypt]==0.3.0 with `PasswordHash((BcryptHasher(),))` — NOT `PasswordHash.recommended()` (gives Argon2), NOT passlib (broken)
- JWT payload: `{ "sub": username, "user_id": uuid_str, "is_admin": bool, "exp": unix_ts }`
- Token lifetime: 8 hours
- Silent refresh: new token in `X-New-Token` response header when <1h remaining
- Token storage: `localStorage['bdda_token']`
- Admin auth: `X-Admin-Secret` header (NOT JWT — separate secret for create-user endpoint)
- SQLite migration: PRAGMA `table_info(jobs)` before `ALTER TABLE` (Render SQLite 3.27.2 — no `IF NOT EXISTS`)

### AI Stack (Phase 1)
- Model: `claude-opus-4-6` everywhere (triage, classify, analyze)
- Triage: 4 tiles, 0.3 onshore / 0.2 offshore threshold
- Images: raw base64 only — NO `data:image/...` URI prefix

### Persistence (Phase 2)
- SQLAlchemy 2.0 sync + SQLite WAL
- `DATA_DIR` env var: `/data` on Render, `./data` local
- Raw images deleted after triage — thumbnails survive in `thumbnails/`
- 30-day job history, 507 on disk full

---

## Project overview

**What:** BDDA — AI pipeline for drone wind turbine blade inspection
**Stack:** FastAPI + SQLAlchemy + Anthropic SDK + PyJWT + pwdlib + fpdf2 + Tailwind/Alpine.js (Phase 5)
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
| 4 | PDF Redesign (fpdf2) | ✅ Complete |
| 5 | Frontend UI (Tailwind+Alpine) | ⬜ Not started |

**Requirements remaining:**
- UI-01..06: Tailwind+Alpine, login page redesign, upload form, live progress, job history, mobile-responsive

---

## ⚠️ Before deploying to Render

Set these in Render Dashboard → Environment (never in repo — sync:false):
1. `SECRET_KEY` → run `openssl rand -hex 32` and paste result
2. `ADMIN_SECRET` → any strong random string
3. `ADMIN_PASSWORD` → your admin password

---

## Reminders

- 🔶 **Switch to Opus** for Phase 5 UI architecture — full frontend redesign
- **Design system:** Apply Cyber Operator dark dashboard style from `-SKILLS/design-style/`
- Push directly to `main` — no PRs needed (solo developer)
- GSD tools: `/Users/fabien/.claude/get-shit-done/bin/gsd-tools.cjs`
- Worktree path: `/Users/fabien/Desktop/CLAUDE/applications/drone/bdda/.claude/worktrees/frosty-banach/`
