# BDDA — Blade Defect Detection Agent

## Project Summary

AI-powered wind turbine blade inspection platform. Drone operators upload a ZIP of DJI inspection images; the system runs a 4-stage AI pipeline (triage → classify → analyze → report) and produces a professional PDF inspection report. Primary users are wind farm operators who act on the findings.

**Status:** V1 deployed on Render (live at wind-turbines-reports.onrender.com). Pipeline functional, API keys confirmed working. Kimi triage blocked pending Moonshot account top-up.

**Owner:** Fabien / DroneWind Asia
**Repo:** FabienStarseed/wind-turbines-reports (main branch → Render autodeploy)

---

## Core Value

**Upload drone images → get a professional turbine inspection report in minutes**, powered by AI defect detection across 4 specialized models.

---

## The Problem We're Solving

Manual wind turbine blade inspection analysis is:
- Slow (engineers manually review hundreds of drone images per turbine)
- Inconsistent (subjective classification of defect severity)
- Expensive (senior engineers' time on routine triage)

BDDA automates the image triage and classification pipeline, letting engineers focus on critical findings and action decisions.

---

## The 5-Stage Pipeline

| Stage | Module | AI Model | Purpose |
|-------|--------|----------|---------|
| 1 | `ingest.py` | — | Parse DJI folder structure, extract blade/zone/position metadata |
| 2 | `triage.py` | Kimi moonshot-v1-8k-vision-preview | Fast binary defect screening (~$0.50/turbine) |
| 3 | `classify.py` | Google Gemini | Detailed defect classification per flagged image |
| 4 | `analyze.py` | Anthropic Claude | Deep engineering analysis of critical findings |
| 5 | `report.py` | — | xhtml2pdf PDF generation with defect maps and recommendations |

---

## Tech Stack

- **Backend:** Python 3.12, FastAPI, uvicorn
- **AI APIs:** Moonshot/Kimi (triage), Google Gemini (classify), Anthropic Claude (analyze)
- **PDF:** xhtml2pdf (WeasyPrint removed — no GTK on Render)
- **Deployment:** Render.com free tier (wind-turbines-reports.onrender.com)
- **Frontend:** Vanilla HTML/CSS/JS static files

---

## Requirements

### Validated (already built)

- ✓ ZIP upload of DJI drone inspection images
- ✓ Automatic DJI folder structure parsing (blade/zone/position extraction)
- ✓ Kimi vision triage (binary defect screening per image tile)
- ✓ Job state management with progress tracking (/api/status/{job_id})
- ✓ Background pipeline execution (non-blocking upload)
- ✓ PDF report generation with defect findings
- ✓ Report download endpoint (/api/download/{job_id})
- ✓ Multi-API key support (Kimi + Google + Anthropic, each optional with fallback)
- ✓ Debug endpoint (/api/debug/kimi) for API key validation
- ✓ Render.com deployment with environment variable config
- ✓ International Moonshot endpoint (api.moonshot.ai)

### Active (next to build)

- [ ] Professional PDF report quality — richer layout, branding, defect images embedded
- [ ] Multi-user authentication — login system for multiple inspectors
- [ ] Job persistence — survive Render restarts (SQLite or Redis)
- [ ] Frontend UI redesign — polished interface with frontend-design skill

### Out of Scope (V1)

- Real-time collaboration — not needed yet
- Mobile app — web-first
- Custom model training — using existing vision APIs
- On-premise deployment — cloud-first

---

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Kimi for triage | Cheapest vision model, ~$0.50/turbine at scale | ✓ Implemented |
| Google Gemini for classify | Strong multimodal classification | ✓ Implemented |
| Anthropic Claude for analyze | Best engineering reasoning for critical findings | ✓ Implemented |
| xhtml2pdf over WeasyPrint | No GTK/Pango on Render free tier | ✓ Fixed |
| api.moonshot.ai over api.moonshot.cn | International account on platform.moonshot.ai | ✓ Fixed |
| Render over Railway | Better free tier for Python web services | ✓ Deployed |
| In-memory job state | Simple for V1, known limitation | Needs persistence in V2 |

---

## Known Concerns (from codebase map)

- **No persistence:** Job state is in-memory dict — lost on Render restart/spin-down
- **No authentication:** Any user can upload/view jobs (public API)
- **Ephemeral disk:** Uploaded images and PDFs lost on Render redeploy
- **No retry logic:** Pipeline fails silently mid-stage with no recovery
- **Rate limiting:** Triage calls Kimi once per image — could be slow/expensive for large batches
- **Free tier spin-down:** 50+ second cold start on Render free tier

---

## Stakeholders

| Role | Who | Notes |
|------|-----|-------|
| Owner/Developer | Fabien | Building and deploying |
| End Users | Wind farm operators | Receive and act on reports |
| Service Company | DroneWind Asia | Generates reports for clients |

---

## What's Been Done

- [x] Full V1 pipeline implemented (all 5 stages)
- [x] FastAPI backend with job management
- [x] Render deployment with render.yaml
- [x] Fixed WeasyPrint → xhtml2pdf (no GTK on Render)
- [x] Fixed Moonshot endpoint (.cn → .ai)
- [x] Debug endpoint for API key validation
- [x] Codebase mapped (7 documents in .planning/codebase/)

## What's Next

1. Top up Moonshot account → verify full pipeline end-to-end
2. Improve PDF report quality (layout, branding, embedded images)
3. Add authentication (multi-user login)
4. Add job persistence (SQLite)
5. UI redesign with frontend-design skill

---

*Last updated: 2026-03-03 after GSD initialization*
