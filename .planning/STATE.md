# BDDA Project State

**Last updated:** 2026-03-06
**Current phase:** Phase 2 — Persistence (In Progress)
**Next action:** Execute Plan 02-02 — Migrate backend/api.py to SQLAlchemy

---

## Milestone: V2 — Production-Ready Platform

| Phase | Name | Status |
|-------|------|--------|
| 1 | AI Consolidation | Done |
| 2 | Persistence | In Progress (2/3 plans done) |
| 3 | Auth | Not started |
| 4 | PDF Redesign | Not started |
| 5 | Frontend UI | Not started |

---

## Phase 1 — AI Consolidation (Complete)

All 4 plans completed on 2026-03-05.

| Plan | Name | Commit | Status |
|------|------|--------|--------|
| 01-01 | Rewrite triage.py — Anthropic SDK | a5b8644 | Done |
| 01-02 | Rewrite classify.py — IEC+BDDA dual scoring | 23a293c | Done |
| 01-03 | Update analyze.py — OverloadedError, cost, offshore | dbd8a81 | Done |
| 01-04 | Update api.py + requirements.txt — Anthropic-only pipeline | 161b895 | Done |

### Key Decisions Made

1. All AI stages → `claude-opus-4-6` via `anthropic` SDK only
2. `KIMI_API_KEY` and `GOOGLE_API_KEY` removed from pipeline entirely
3. `openai` and `google-generativeai` removed from requirements.txt
4. `estimate_cost()` uses conservative 30% flag / 20% critical pre-run estimate
5. `IMAGE_CAP = 500` applied before triage begins
6. `COST_LIMIT_USD` env var stops pipeline gracefully after triage or classify
7. Per-stage costs (`triage_cost_usd`, `classify_cost_usd`, `analyze_cost_usd`, `total_cost_usd`) logged to state.json
8. `location_type` (onshore/offshore) flows from upload form through turbine_meta to all AI stages
9. `analyze_critical_defects()` returns `Tuple[List[DeepAnalysis], float]` — api.py unpacks tuple

---

## Phase 2 — Persistence (In Progress)

| Plan | Name | Commit | Status |
|------|------|--------|--------|
| 02-01 | Create backend/database.py — SQLAlchemy ORM, Job model, CRUD | f2fb809 | Done |
| 02-02 | Migrate backend/api.py — remove _jobs dict, SQLite endpoints | pending | Not started |
| 02-03 | Update render.yaml — persistent disk, clean env vars | 33ce8ff | Done |

### Key Decisions Made

1. Persistent disk: 1GB at /data, name bdda-data — mountPath matches DATA_DIR default in database.py
2. GOOGLE_API_KEY and KIMI_API_KEY removed from render.yaml (Phase 1 cleanup)
3. COST_LIMIT_USD added to render.yaml env vars (was missing despite Phase 1 implementing it)
4. Prominent comment block in render.yaml: paid Starter tier required ($7/month) for persistent disk
5. All cost fields (triage/classify/analyze/total_cost_usd) stored as Text in SQLite — avoids float precision artifacts
6. turbine_meta stored as JSON string in Text column — explicit json.dumps/loads, portable across SQLite versions
7. DATA_DIR/JOBS_DIR created at module import time — before engine creation (prevents OperationalError)
8. WAL mode + check_same_thread=False — concurrent reads from status endpoint while pipeline writes progress
9. list_jobs_last_30_days uses Python-side datetime comparison — bypasses SQLite ISO string comparison ambiguity

---

## Context for Next Session

- **Deployed at:** https://wind-turbines-reports.onrender.com
- **Repo:** FabienStarseed/wind-turbines-reports → main branch → Render autodeploy
- **Branch:** claude/frosty-banach (push to main to deploy)
- **Blocking issue:** None — Phase 2 plans 02-01 and 02-03 complete, plan 02-02 remains
- **Key decision:** All AI stages → `claude-opus-4-6` via `anthropic` SDK only
- **Stack additions (Phase 2+):** SQLAlchemy, python-jose, passlib, fpdf2
- **Stack removals done:** openai (Kimi), google-generativeai (Gemini) removed from requirements.txt

---

## Performance Metrics

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 01 | 01 | ~15 min | 1 | 1 |
| 01 | 02 | ~4 min | 2 | 1 |
| 01 | 03 | ~8 min | 1 | 1 |
| 01 | 04 | ~56 min | 2 | 2 |
| 02 | 01 | ~2 min | 2 | 2 |
| 02 | 03 | ~2 min | 1 | 1 |

---

## Planning Artifacts

- `.planning/PROJECT.md` — full project context
- `.planning/REQUIREMENTS.md` — 21 v2 requirements across 5 categories
- `.planning/ROADMAP.md` — 5 phases with success criteria
- `.planning/codebase/` — 7 codebase map documents
