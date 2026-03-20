# BDDA — Blade Defect Detection Agent

## What This Is

AI-powered pipeline for drone wind turbine blade inspection. Upload drone photos, get automated defect detection and professional PDF reports.

**Live URL:** https://wind-turbines-reports.onrender.com
**Branch:** `claude/frosty-banach`
**Deploy:** Render.com (Starter tier $7/mo for persistent disk)

---

## Current Status

| Phase | Name | Status | Key Commit |
|-------|------|--------|------------|
| 1 | AI Consolidation | ✅ Complete | a5b8644 |
| 2 | Persistence (SQLite) | ✅ Complete | 8db14fd |
| 3 | Auth (JWT login) | ✅ Complete | d7463fe |
| 4 | PDF Redesign (fpdf2) | 🟡 Discussing | — |
| 5 | Frontend UI (Tailwind+Alpine) | ⬜ Not started | — |

**Current activity:** Phase 4 discuss-phase in progress (gray areas identified, awaiting user input on branding, layout, defect presentation, blade map)

---

## Tech Stack

- **Backend:** FastAPI + SQLAlchemy 2.0 sync + SQLite (WAL mode)
- **AI:** Anthropic SDK → claude-opus-4-6 (triage, classify, analyze)
- **Auth:** PyJWT 2.11.0 + pwdlib[bcrypt] 0.3.0
- **PDF:** fpdf2 (Phase 4 — replacing xhtml2pdf)
- **Frontend:** Tailwind CSS + Alpine.js (Phase 5 — currently basic HTML)
- **Deploy:** Render.com with 1GB persistent disk at `/data`

---

## File Structure

```
bdda/
├── backend/
│   ├── api.py              # FastAPI app — all endpoints, JWT protection
│   ├── auth.py             # JWT issue/verify, bcrypt, get_current_user
│   ├── database.py         # SQLAlchemy ORM (Job + User), CRUD, migration
│   ├── triage.py           # Stage 1: 4-tile damage detection (claude-opus-4-6)
│   ├── classify.py         # Stage 2: IEC Cat 0-4 + BDDA 0-10 scoring
│   ├── analyze.py          # Stage 3: critical defect analysis + recommendations
│   ├── report.py           # PDF generation (current — being replaced in Phase 4)
│   ├── taxonomy.py         # 56 defect types for blade damage classification
│   ├── ingest.py           # Image ingestion helpers
│   └── tile.py             # Image tiling for triage stage
├── frontend/
│   ├── index.html          # Main dashboard (basic — Phase 5 redesigns)
│   ├── login.html          # Login page (functional, unstyled — Phase 5 redesigns)
│   ├── app.js              # Frontend JavaScript
│   └── style.css           # Current styles
├── requirements.txt        # Python deps (anthropic, sqlalchemy, PyJWT, pwdlib, fpdf2)
├── render.yaml             # Render deployment config + env vars
├── Procfile                # uvicorn start command
├── HANDOFF.md              # Session continuity handoff document
└── .planning/              # GSD planning artifacts
    ├── ROADMAP.md           # 5-phase roadmap with success criteria
    ├── REQUIREMENTS.md      # All requirements (AI, PERS, AUTH, PDF, UI)
    ├── STATE.md             # Current phase states
    └── phases/
        ├── 01-ai-consolidation/  # ✅ Complete
        ├── 02-persistence/       # ✅ Complete
        └── 03-auth/              # ✅ Complete (4 plans + verification)
```

---

## Pipeline Flow

```
Upload images → Ingest → Triage (4 tiles/image, damage detection)
                            ↓
                     Classify (IEC Cat 0-4 + BDDA 0-10)
                            ↓
                     Analyze (critical defects → recommendations)
                            ↓
                     Generate PDF report → Download
```

Each stage uses `claude-opus-4-6` vision. Cost tracked per-job. Images deleted after triage (15-30MB DJI P1 files).

---

## API Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/auth/token` | None | Login → JWT |
| POST | `/api/admin/create-user` | ADMIN_SECRET | Create inspector account |
| POST | `/api/upload` | JWT | Upload images + start pipeline |
| POST | `/api/estimate` | None | Cost estimate before upload |
| GET | `/api/status/{job_id}` | JWT | Pipeline progress |
| GET | `/api/download/{job_id}` | JWT | Download PDF report |
| GET | `/api/jobs` | JWT | Job history (30 days, owner-filtered) |
| DELETE | `/api/jobs/{job_id}` | JWT | Delete job |
| GET | `/api/health` | None | Health check |
| GET | `/api/debug/ai` | None | AI connectivity test |
| GET | `/login` | None | Login HTML page |

---

## Key Technical Decisions (Locked)

### AI
- claude-opus-4-6 everywhere — $5/M input, $25/M output
- Raw base64 only (no `data:image/...` URI prefix)
- Per-image retry once → errors.json → continue (never fail whole job)
- Triage: 0.3 onshore / 0.2 offshore confidence thresholds

### Auth
- PyJWT (NOT python-jose — abandoned) + pwdlib/bcrypt (NOT passlib — broken)
- 8-hour JWT, silent refresh via `X-New-Token` header when <1h remaining
- `PRAGMA table_info` migration (Render SQLite 3.27.2)
- Admin (Fabien) creates all inspector accounts — no self-registration

### Persistence
- SQLAlchemy 2.0 sync + SQLite WAL
- `DATA_DIR=/data` (Render) / `DATA_DIR=./data` (local)
- 30-day job retention, 507 on disk full, failed stage on interrupted jobs

### Classification
- IEC Cat 0-4 (international) + BDDA 0-10 (custom)
- `has_critical` = `iec_category >= 3`
- 56 defect types in taxonomy.py

---

## Environment Variables (Render)

| Var | Required | Purpose |
|-----|----------|---------|
| `ANTHROPIC_API_KEY` | Yes | AI model access |
| `SECRET_KEY` | Yes | JWT signing (openssl rand -hex 32) |
| `ADMIN_SECRET` | Yes | Protect create-user endpoint |
| `ADMIN_PASSWORD` | Yes | Seed admin password on first deploy |
| `ADMIN_USERNAME` | No | Default: `admin` |
| `DATA_DIR` | No | Default: `/data` on Render |

---

## Requirements Remaining

### PDF-01..06 (Phase 4 — next)
- fpdf2 replaces xhtml2pdf
- DroneWind Asia branding (logo, colours, header/footer)
- Defect images embedded inline
- Severity colour-coding (Cat 0-4 bands)
- Executive summary page
- Per-blade defect map with annotated zones

### UI-01..06 (Phase 5)
- Tailwind CSS + Alpine.js (no build pipeline)
- Branded login page, upload form, live progress, job history, mobile-responsive

---

## Development Commands

```bash
# Run locally
DATA_DIR=./data SECRET_KEY=$(openssl rand -hex 32) ADMIN_SECRET=dev-secret \
  uvicorn backend.api:app --reload --port 8000

# Test login
curl -X POST http://localhost:8000/api/auth/token \
  -d "username=admin&password=changeme"

# Create inspector
curl -X POST http://localhost:8000/api/admin/create-user \
  -H "X-Admin-Secret: dev-secret" \
  -H "Content-Type: application/json" \
  -d '{"username": "inspector1", "password": "test123"}'
```

---

## Token Efficiency

### Context Reset Pattern
- Write HANDOFF.md at phase end → /clear → resume with "Read @HANDOFF.md and continue"
- Never let context accumulate across more than one phase

### Model Switching
- 🔶 **Opus** for: Phase 4 (PDF layout), Phase 5 (UI architecture)
- 🟢 **Sonnet** for: Phases 1-3 (mechanical implementation)

---

## Reminders

- Push directly to `main` — no PRs (solo developer)
- GSD tools: `/Users/fabien/.claude/get-shit-done/bin/gsd-tools.cjs`
- Worktree: `/Users/fabien/Desktop/CLAUDE/applications/drone/bdda/.claude/worktrees/frosty-banach/`
- Test images: `/Users/fabien/Desktop/CLAUDE/applications/drone/bdda/sources/resume/images/enercon/EN01/` (63 DJI P1 JPGs)
- Visual outputs (charts/graphs) → flag with "Check Nimbalyst"
