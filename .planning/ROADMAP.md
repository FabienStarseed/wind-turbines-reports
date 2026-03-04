# BDDA V2 Roadmap

**Project:** Blade Defect Detection Agent
**Milestone:** V2 — Production-Ready Platform
**Created:** 2026-03-04
**Status:** Planning

---

## Overview

5 phases. Each phase is independently deployable and testable.

| # | Phase | Goal | Requirements | Status |
|---|-------|------|--------------|--------|
| 1 | AI Consolidation | All AI stages use claude-opus-4-6 | AI-01…05 | 🔲 Not started |
| 2 | Persistence | Jobs survive restarts | PERS-01…04 | 🔲 Not started |
| 3 | Auth | Multi-inspector login | AUTH-01…05 | 🔲 Not started |
| 4 | PDF Redesign | Professional branded report | PDF-01…06 | 🔲 Not started |
| 5 | Frontend UI | Polished branded interface | UI-01…06 | 🔲 Not started |

---

## Phase 1 — AI Consolidation

**Goal:** Replace Kimi (triage) and Google Gemini (classify) with `claude-opus-4-6`. Single API key, single SDK, best available model end-to-end.

**Requirements:** AI-01, AI-02, AI-03, AI-04, AI-05

**Success Criteria:**
1. `/api/debug/kimi` endpoint returns success using `claude-opus-4-6` (rename to `/api/debug/ai`)
2. Full pipeline run completes with only `ANTHROPIC_API_KEY` set (no Kimi or Google keys)
3. Triage stage calls `claude-opus-4-6` vision with base64 tile images
4. Classify stage calls `claude-opus-4-6` vision with full images
5. `requirements.txt` no longer includes `openai` or `google-generativeai`
6. Cost per job logged to state.json

**Key changes:**
- `backend/triage.py` — replace OpenAI client + Kimi model with `anthropic` SDK + `claude-opus-4-6`
- `backend/classify.py` — replace Google Gemini client with `anthropic` SDK + `claude-opus-4-6`
- `backend/analyze.py` — bump model from `claude-opus-4-5` to `claude-opus-4-6`
- `backend/api.py` — rename `/api/debug/kimi` → `/api/debug/ai`, update health check
- `requirements.txt` — remove `openai`, `google-generativeai`; add `anthropic>=0.44.0`

**Deploy gate:** Push to main → Render redeploys → hit `/api/debug/ai` → confirm success

---

## Phase 2 — Persistence

**Goal:** Job state and files survive Render restarts and redeployments.

**Requirements:** PERS-01, PERS-02, PERS-03, PERS-04

**Success Criteria:**
1. Jobs table in SQLite stores all job state (replaces `_jobs` in-memory dict)
2. After simulated Render restart, `/api/jobs` still returns previous jobs
3. PDF files accessible after restart via `/api/download/{job_id}`
4. `render.yaml` includes persistent disk at `/data`
5. SQLite DB at `/data/bdda.db`, job files at `/data/jobs/{job_id}/`

**Key changes:**
- `backend/models.py` — new file: SQLAlchemy Job + User models
- `backend/database.py` — new file: SQLAlchemy engine + session factory
- `backend/api.py` — replace `_jobs` dict with SQLite reads/writes
- `render.yaml` — add persistent disk config
- `requirements.txt` — add `sqlalchemy>=2.0.36`

---

## Phase 3 — Auth

**Goal:** Inspector login with JWT. All pipeline endpoints protected.

**Requirements:** AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05

**Success Criteria:**
1. `POST /api/auth/token` returns JWT for valid credentials
2. `POST /api/upload` returns 401 without valid token
3. `GET /api/jobs` returns only jobs belonging to authenticated inspector
4. `POST /api/admin/create-user` creates new inspector (protected by `ADMIN_SECRET` env var)
5. Login page at `/login` redirects to dashboard on success

**Key changes:**
- `backend/auth.py` — new file: JWT logic (python-jose + passlib)
- `backend/api.py` — add `Depends(get_current_user)` to protected endpoints
- `frontend/login.html` — new login page
- `requirements.txt` — add `python-jose[cryptography]>=3.3.0`, `passlib[bcrypt]>=1.7.4`
- Render env vars: `JWT_SECRET_KEY`, `ADMIN_SECRET`

---

## Phase 4 — PDF Redesign

**Goal:** Professional, client-deliverable PDF report with branding and embedded images.

**Requirements:** PDF-01, PDF-02, PDF-03, PDF-04, PDF-05, PDF-06

**Success Criteria:**
1. PDF renders correctly with fpdf2 (no xhtml2pdf)
2. DroneWind Asia logo appears in header on every page
3. Each critical finding shows the defect image inline
4. Defect severity rows use colour bands (Cat 0=green → Cat 4=red)
5. Page 1 is an executive summary (defect counts, highest severity, recommendation)
6. Report passes visual review — client-presentable quality

**Key changes:**
- `backend/report.py` — full rewrite: Jinja2+xhtml2pdf → fpdf2 programmatic layout
- `templates/` — remove HTML template; add logo asset
- `requirements.txt` — remove `xhtml2pdf`, `python-bidi`; add `fpdf2>=2.7.9`

---

## Phase 5 — Frontend UI

**Goal:** Polished branded interface. Login, upload, progress, history — all redesigned.

**Requirements:** UI-01, UI-02, UI-03, UI-04, UI-05, UI-06

**Success Criteria:**
1. UI uses Tailwind CSS + Alpine.js (no custom CSS framework)
2. Login page is branded and professional
3. Upload form shows clear multi-step flow
4. Pipeline progress shows current stage name + animated progress bar
5. Job history table shows all past inspections with download links
6. Layout works on tablet screen (used in the field)

**Key changes:**
- `frontend/index.html` — full redesign with Tailwind + Alpine
- `frontend/app.js` — simplified; Alpine handles reactive state
- `frontend/login.html` — branded login page
- `frontend/style.css` — remove most custom CSS (Tailwind replaces it)

---

## Build Order Rationale

```
Phase 1 (AI) → standalone, no deps, highest value, unblocks testing
Phase 2 (Persistence) → needed before Auth (User table)
Phase 3 (Auth) → needs User table from Phase 2
Phase 4 (PDF) → independent of 1-3, can overlap with Phase 2-3
Phase 5 (UI) → needs Auth (login page) — do last
```

Phases 2 and 4 can run in parallel after Phase 1 completes.
