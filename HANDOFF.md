# BDDA Project Handoff

**Branch:** `claude/frosty-banach`
**Last updated:** 2026-03-06
**Status:** Phase 2 execution complete — verification + phase close pending

---

## What was just done

### Phase 1: AI Consolidation ✅ COMPLETE
Replaced Kimi (OpenAI client) + Gemini with claude-opus-4-6 via Anthropic SDK across all 3 AI stages:
- `backend/triage.py` — full rewrite: 4-tile triage, 0.3/0.2 onshore/offshore thresholds, errors.json logging, cost tracking
- `backend/classify.py` — full rewrite: Anthropic SDK, image resize ≤1568px, IEC Cat 0-4 + BDDA 0-10 dual scoring
- `backend/analyze.py` — updated: OverloadedError retry, cost tracking, offshore context in prompt
- `backend/api.py` — Anthropic-only pipeline: COST_LIMIT_USD, 500-image cap, /api/estimate, /api/debug/ai
- `requirements.txt` — openai + google-generativeai removed

### Phase 2: Persistence ✅ COMPLETE (code committed, verification pending)
SQLite persistence replacing in-memory `_jobs` dict:
- `backend/database.py` — NEW: SQLAlchemy 2.0, WAL mode, Job ORM model, all CRUD helpers
- `backend/api.py` — migrated: lifespan startup (marks interrupted jobs failed), SQLite-backed endpoints, image cleanup after triage, 507 disk-full guard, 30-day history filter, manual job delete
- `render.yaml` — updated: persistent disk block (1GB at /data), stale KIMI/GOOGLE keys removed
- `requirements.txt` — sqlalchemy>=2.0 added

---

## Immediate next step (do this first)

Run verification + phase close for Phase 2:

```
# 1. Verify Phase 2 goal achievement
spawn gsd-verifier for phase 02 (checks backend/api.py, backend/database.py, render.yaml)

# 2. Fix any gaps found (usually minor)

# 3. Mark Phase 2 complete
node /Users/fabien/.claude/get-shit-done/bin/gsd-tools.cjs phase complete "02"

# 4. Commit
git add .planning/ && git commit -m "docs(phase-02): complete Phase 2 — SQLite persistence done"

# 5. Push to main (merge worktree)
git push origin claude/frosty-banach
```

**Missing:** `02-02-SUMMARY.md` — executor hit rate limit mid-run but commit `8db14fd` shows api.py was migrated. Create summary manually or re-run.

---

## Key technical decisions (locked — do not re-discuss)

### AI Stack (Phase 1)
- Model: `claude-opus-4-6` everywhere (triage, classify, analyze)
- Pricing: $5/M input, $25/M output (all 3 stages consistent)
- Triage: 4 tiles per image, 0.3 onshore / 0.2 offshore confidence threshold
- Images: raw base64 only — NO `data:image/...` URI prefix (Anthropic SDK requirement)
- Errors: per-image retry once → log to `errors.json` → continue (never fail whole job)

### Persistence (Phase 2)
- SQLAlchemy 2.0 sync + SQLite (no async driver — project pattern)
- `DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))` — set `DATA_DIR=./data` for local dev
- WAL mode enabled (concurrent reads during pipeline writes)
- Raw images deleted after triage completes (DJI P1 = 15-30MB each)
- Job history: last 30 days only
- Interrupted jobs: marked `stage="failed"` on startup
- Disk full: HTTP 507 refusal (not silent auto-delete)
- Render: 1GB persistent disk at /data — **requires Starter tier ($7/month), not free tier**

### Defect Classification
- IEC Cat 0-4 (international standard) + BDDA 0-10 (custom scoring)
- `has_critical` uses `iec_category >= 3` (Cat 3 = Planned repair urgently needed)
- Taxonomy: 56 defect types in `backend/taxonomy.py`

---

## Project overview

**What:** BDDA (Blade Defect Detection Agent) — AI pipeline for drone wind turbine blade inspection
**Stack:** FastAPI + SQLAlchemy + Anthropic SDK + fpdf2 + Tailwind/Alpine.js (Phase 5)
**Deploy:** Render.com (currently free tier, needs Starter for Phase 2 persistent disk)
**Live URL:** https://wind-turbines-reports.onrender.com
**Real test images:** `/Users/fabien/Desktop/CLAUDE/applications/drone/bdda/sources/resume/images/enercon/EN01/` (63 DJI P1 JPGs from Aug 2023)

---

## Roadmap status

| Phase | Name | Status |
|-------|------|--------|
| 1 | AI Consolidation | ✅ Complete |
| 2 | Persistence | ✅ Code done, close pending |
| 3 | Auth (JWT login) | ⬜ Not started |
| 4 | PDF Redesign (fpdf2) | ⬜ Not started |
| 5 | Frontend UI (Tailwind+Alpine) | ⬜ Not started |

**Requirements remaining:**
- AUTH-01..05: Inspector login, JWT, protected endpoints, admin account creation
- PDF-01..06: fpdf2, DroneWind Asia branding, defect images inline, severity colour-coding
- UI-01..06: Tailwind+Alpine, login page, upload form, live progress, job history, mobile

---

## Visual outputs → Nimbalyst

Any charts, graphs, or dashboards generated for this project → **view in Nimbalyst** (not inline).

---

## Reminders

- 🔶 **Switch to Opus** for: Phase 4 PDF layout design, Phase 5 UI architecture
- 🟢 **Sonnet fine** for: Phase 3 Auth (mechanical JWT implementation)
- Push directly to `main` — no PRs needed (solo developer)
- GSD tools: `/Users/fabien/.claude/get-shit-done/bin/gsd-tools.cjs`
- Worktree path: `/Users/fabien/Desktop/CLAUDE/applications/drone/bdda/.claude/worktrees/frosty-banach/`
