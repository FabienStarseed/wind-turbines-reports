# BDDA V2 Requirements

**Project:** Blade Defect Detection Agent
**Version:** 2.0
**Date:** 2026-03-04

---

## v1 Requirements (Already Built ✓)

- ✓ ZIP upload of DJI drone inspection images
- ✓ DJI folder structure parsing (blade/zone/position metadata)
- ✓ AI triage — binary defect screening per image
- ✓ Background pipeline execution (non-blocking)
- ✓ Job progress tracking (/api/status/{job_id})
- ✓ PDF report generation
- ✓ Report download (/api/download/{job_id})
- ✓ Multi-API key support with graceful fallback
- ✓ Debug endpoint (/api/debug/kimi)
- ✓ Render.com deployment

---

## v2 Requirements

### AI — Consolidate to claude-opus-4-6

- [x] **AI-01**: Triage stage uses `claude-opus-4-6` vision (replaces Kimi) — Plan 01-01
- [x] **AI-02**: Classify stage uses `claude-opus-4-6` vision (replaces Google Gemini) — Plan 01-02
- [x] **AI-03**: Analyze stage upgraded to `claude-opus-4-6` (was claude-opus-4-5) — Plan 01-03
- [x] **AI-04**: Single `ANTHROPIC_API_KEY` powers all 3 stages (remove `KIMI_API_KEY`, `GOOGLE_API_KEY`) — Plan 01-04
- [x] **AI-05**: Cost-per-turbine measured and logged per job — Plan 01-04

### Persistence — SQLite + Render Disk

- [x] **PERS-01**: Job state stored in SQLite (survives Render restarts) — database.py (Plan 02-01) + api.py migration (Plan 02-02)
- [x] **PERS-02**: Uploaded images and PDFs stored on Render Persistent Disk — JOBS_DIR at /data/jobs, images deleted post-triage (Plan 02-02)
- [x] **PERS-03**: Job history visible across sessions (no more lost jobs on restart) — list_jobs_last_30_days() + lifespan recovery (Plan 02-02)
- [x] **PERS-04**: render.yaml updated with persistent disk config — Plan 02-03

### Auth — Multi-Inspector Login

- [x] **AUTH-01**: Inspector can log in with username + password
- [x] **AUTH-02**: JWT token issued on login (8-hour session)
- [x] **AUTH-03**: All upload/status/download endpoints require valid token
- [x] **AUTH-04**: Admin can create new inspector accounts via protected endpoint
- [x] **AUTH-05**: Each job linked to the inspector who created it

### PDF — Professional Branded Report

- [x] **PDF-01**: PDF uses fpdf2 (replaces xhtml2pdf — better layout control) — Plan 04-01 (commit: 09648b4)
- [x] **PDF-02**: Report has DroneWind Asia branding (logo, colours, header/footer) — Plan 04-01 (commit: 09648b4)
- [ ] **PDF-03**: Defect images embedded inline next to findings — Plan 04-02 (pipeline fix) + Plan 04-03 (PDF embedding)
- [ ] **PDF-04**: Severity colour-coding (Cat 0-4 colour bands in findings table) — Plan 04-03
- [x] **PDF-05**: Executive summary page (total defects, critical count, recommendation) — Plan 04-01 (commit: 09648b4)
- [ ] **PDF-06**: Per-blade defect map (blade diagram with annotated zones) — Plan 04-03

### Frontend — Polished UI

- [ ] **UI-01**: Tailwind CSS + Alpine.js (no build pipeline)
- [ ] **UI-02**: Branded login page
- [ ] **UI-03**: Upload form redesigned — clear steps, progress indicator
- [ ] **UI-04**: Live pipeline progress (stage name + % bar + estimated time)
- [ ] **UI-05**: Job history list (all past inspections, status, download link)
- [ ] **UI-06**: Mobile-responsive layout

---

## Out of Scope (V2)

- OAuth / SSO — username+password sufficient for small inspector team
- Real-time collaboration — single-inspector workflow per job
- Custom model training — using Anthropic API
- On-premise / self-hosted — Render cloud only
- Native M300 controller app — web-first, Android app is V3+
- Multi-turbine batch jobs — one turbine per upload in V2

---

## Traceability

| Phase | Requirements Covered |
|-------|---------------------|
| Phase 1 — AI Consolidation | AI-01, AI-02, AI-03, AI-04, AI-05 |
| Phase 2 — Persistence | PERS-01, PERS-02, PERS-03, PERS-04 |
| Phase 3 — Auth | AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05 |
| Phase 4 — PDF Redesign | PDF-01, PDF-02, PDF-03, PDF-04, PDF-05, PDF-06 |
| Phase 5 — Frontend UI | UI-01, UI-02, UI-03, UI-04, UI-05, UI-06 |
