# Roadmap: BDDA V2 — Production-Ready Platform

## Overview

5 phases transforming BDDA from a working V1 prototype into a professional, multi-user inspection platform powered entirely by claude-opus-4-6. Each phase is independently deployable.

## Phases

- [x] **Phase 1: AI Consolidation** - Replace Kimi + Gemini with claude-opus-4-6 everywhere (COMPLETE 2026-03-05)
- [ ] **Phase 2: Persistence** - SQLite + Render Persistent Disk (survive restarts)
- [x] **Phase 3: Auth** - JWT multi-inspector login (COMPLETE 2026-03-06)
- [ ] **Phase 4: PDF Redesign** - Professional branded report with fpdf2
- [ ] **Phase 5: Frontend UI** - Tailwind + Alpine.js polished interface

## Phase Details

### Phase 1: AI Consolidation
**Goal**: All AI stages (triage, classify, analyze) use claude-opus-4-6 via a single Anthropic SDK. Remove Kimi and Google Gemini dependencies entirely.
**Depends on**: Nothing (first phase)
**Requirements**: AI-01, AI-02, AI-03, AI-04, AI-05
**Success Criteria** (what must be TRUE):
  1. Full pipeline runs successfully with only ANTHROPIC_API_KEY set
  2. Triage stage calls claude-opus-4-6 vision with base64 tile images
  3. Classify stage calls claude-opus-4-6 vision with full images
  4. requirements.txt no longer includes openai or google-generativeai packages
  5. /api/debug/ai endpoint confirms claude-opus-4-6 responds correctly
  6. Cost per job is logged to job state
**Plans**: 4 plans

Plans:
- [x] 01-01-PLAN.md — Rewrite triage.py: Anthropic SDK, 4 tiles, location thresholds, cost tracking, errors.json (commit: a5b8644)
- [x] 01-02-PLAN.md — Rewrite classify.py: Anthropic SDK, image resize, IEC+BDDA dual scoring, cost tracking (commit: 23a293c)
- [x] 01-03-PLAN.md — Update analyze.py: OverloadedError handling, cost tracking, offshore prompt context (commit: dbd8a81)
- [x] 01-04-PLAN.md — Update api.py + requirements.txt: single ANTHROPIC_API_KEY, /api/estimate, cost guardrails (commit: 161b895)

### Phase 2: Persistence
**Goal**: Job state and files survive Render restarts and redeployments using SQLite on a Persistent Disk.
**Depends on**: Phase 1
**Requirements**: PERS-01, PERS-02, PERS-03, PERS-04
**Success Criteria** (what must be TRUE):
  1. Jobs table in SQLite stores all job state (replaces in-memory _jobs dict)
  2. After simulated Render restart, /api/jobs still returns previous jobs
  3. PDF files accessible after restart via /api/download/{job_id}
  4. render.yaml includes persistent disk at /data mountPath
  5. SQLite DB at /data/bdda.db, job files at /data/jobs/{job_id}/
**Plans**: 3 plans

Plans:
- [x] 02-01-PLAN.md — Create backend/database.py: SQLAlchemy 2.0 engine, Job model, CRUD helpers; add sqlalchemy>=2.0 to requirements.txt (commit: f2fb809)
- [ ] 02-02-PLAN.md — Migrate backend/api.py: remove _jobs dict, add lifespan startup, SQLite-backed endpoints, disk space guard, image deletion after triage
- [x] 02-03-PLAN.md — Update render.yaml: add persistent disk config, clean stale env vars, note paid-tier requirement (commit: 33ce8ff)

### Phase 3: Auth
**Goal**: Inspector login with JWT. All pipeline endpoints protected. Admin can create inspector accounts.
**Depends on**: Phase 2
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05
**Success Criteria** (what must be TRUE):
  1. POST /api/auth/token returns JWT for valid credentials
  2. POST /api/upload returns 401 without valid token
  3. GET /api/jobs returns only jobs belonging to authenticated inspector
  4. POST /api/admin/create-user creates new inspector (protected by ADMIN_SECRET)
  5. Login page at /login redirects to dashboard on success
**Plans**: 4 plans

Plans:
- [x] 03-01-PLAN.md — Add User model + migrate_schema() + user CRUD to database.py (AUTH-05) (commit: cf9c904)
- [x] 03-02-PLAN.md — Create backend/auth.py: PyJWT + pwdlib[bcrypt], get_current_user dependency with silent refresh (AUTH-01, AUTH-02, AUTH-03) (commit: 13752cf)
- [x] 03-03-PLAN.md — Wire auth into api.py: protect endpoints, add /api/auth/token + /api/admin/create-user, silent-refresh middleware (AUTH-01..AUTH-05) (commit: d7463fe)
- [x] 03-04-PLAN.md — Create frontend/login.html, update requirements.txt + render.yaml with auth env vars (AUTH-01, AUTH-02) (commit: a31645f)

### Phase 4: PDF Redesign
**Goal**: Professional client-deliverable PDF report using fpdf2 with branding, embedded defect images, and severity colour-coding.
**Depends on**: Phase 1
**Requirements**: PDF-01, PDF-02, PDF-03, PDF-04, PDF-05, PDF-06
**Success Criteria** (what must be TRUE):
  1. PDF renders correctly with fpdf2 (no xhtml2pdf dependency)
  2. DroneWind Asia logo appears in header on every page
  3. Each critical finding shows the defect image inline
  4. Defect severity rows use colour bands (Cat 0=green to Cat 4=red)
  5. Executive summary section present with defect counts, critical count, and recommendation
  6. Report is visually client-presentable quality
**Plans**: 3 plans

Plans:
- [x] 04-01-PLAN.md — Foundation: Inter fonts, fpdf2 setup, BDDAReport class with cover/TOC/exec summary/inspection details (PDF-01, PDF-02, PDF-05) (commit: 09648b4)
- [ ] 04-02-PLAN.md — Image pipeline fix: save thumbnail copies before deletion so defect images survive to PDF generation (PDF-03)
- [ ] 04-03-PLAN.md — Defect pages, action matrix, blade maps, severity colours, pipeline integration (PDF-03, PDF-04, PDF-06)

### Phase 5: Frontend UI
**Goal**: Polished branded interface using Tailwind CSS + Alpine.js. Login, upload, progress tracking, and job history — all redesigned.
**Depends on**: Phase 3
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05, UI-06
**Success Criteria** (what must be TRUE):
  1. UI uses Tailwind CSS + Alpine.js loaded via CDN (no build pipeline)
  2. Login page is branded and professional
  3. Upload form shows clear multi-step flow
  4. Pipeline progress shows current stage name + animated progress bar
  5. Job history table shows all past inspections with download links
  6. Layout works on tablet screen (used in the field)
**Plans**: TBD
