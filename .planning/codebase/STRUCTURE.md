# Codebase Structure

**Analysis Date:** 2026-03-03

## Directory Layout

```
project-root/
├── backend/                # All Python server-side code
│   ├── api.py              # FastAPI app, endpoints, job state, pipeline orchestrator
│   ├── ingest.py           # Stage 1: DJI folder parser, image metadata extraction
│   ├── triage.py           # Stage 2: Kimi K2.5 binary defect screening
│   ├── classify.py         # Stage 3: Gemini 2.5 Pro structured defect classification
│   ├── analyze.py          # Stage 4: Claude Opus 4.6 deep engineering analysis
│   ├── report.py           # Stage 5: Jinja2 → HTML → PDF report generation
│   ├── tile.py             # Utility: 1024px tiling of 45MP DJI images
│   └── taxonomy.py         # Knowledge base: 56 IEC/DNVGL/GWO defect types
├── frontend/               # Browser UI (served as static files by FastAPI)
│   ├── index.html          # Single-page upload and status tracking UI
│   ├── app.js              # Frontend JS: upload form, status polling, progress display
│   └── style.css           # Frontend styles
├── templates/              # Jinja2 report templates
│   ├── report.html         # Full PDF report template (Vestas-standard layout)
│   └── report.css          # Report PDF styles
├── jobs/                   # Runtime job data (created at runtime, not committed)
│   └── {job_id}/           # One directory per job (8-char UUID prefix)
│       ├── state.json      # Job state dict (stage, counters, timestamps, paths)
│       ├── images/         # Extracted upload contents (ZIP unpacked here)
│       ├── triage.json     # Stage 2 output (all image triage results)
│       ├── classify.json   # Stage 3 output (classified defects per image)
│       ├── analyze.json    # Stage 4 output (deep analysis of Cat 4+ defects)
│       ├── report_{id}.pdf # Stage 5 output (downloadable PDF)
│       └── report_{id}.html# Stage 5 HTML (saved alongside PDF)
├── requirements.txt        # Python dependencies
├── Procfile                # Railway/Render process definition: uvicorn api:app
├── runtime.txt             # Python version pin
├── nixpacks.toml           # Nixpacks build config (Railway)
├── railway.toml            # Railway deployment config
└── render.yaml             # Render.com deployment config
```

## File Descriptions

### Backend

**`backend/api.py`** — FastAPI application; defines all HTTP endpoints (`/api/upload`, `/api/status/{job_id}`, `/api/download/{job_id}`, `/api/jobs`, `/api/health`, `/api/debug/kimi`); manages in-memory `_jobs` dict; `run_pipeline()` orchestrator calls all 5 stages sequentially; `save_job()`/`get_job()`/`update_job()` helpers persist state to disk.

**`backend/ingest.py`** — Parses DJI P1 mission folder names with regex; maps folder name components to blade/zone/position metadata; returns `IngestResult` with all `MissionFolder` objects; `get_all_images_flat()` flattens to list of image dicts used by all downstream stages.

**`backend/triage.py`** — Calls Kimi K2.5 API (OpenAI-compatible, `https://api.moonshot.ai/v1`); sends 8 representative 1024px tiles per image as base64; parses `{"has_defect": bool, "confidence": float, "defect_hint": str}` JSON response; applies 0.45 confidence threshold; saves results to `triage.json`.

**`backend/classify.py`** — Calls Gemini 2.5 Pro API (`google-generativeai`); sends full image as base64 with embedded taxonomy prompt; parses structured `defects[]` array per image; filters by `min_confidence=0.3`; saves results to `classify.json`; `load_critical_findings()` extracts Cat 4+ entries for Stage 4.

**`backend/analyze.py`** — Calls Claude Opus 4.6 (`anthropic` SDK); sends defect context + optionally the source image; parses 8-field engineering assessment JSON (root_cause, failure_risk, vestas_standard, recommended_action, repair_timeframe, estimated_cost_usd, engineer_review_required, analysis_confidence); saves to `analyze.json`.

**`backend/report.py`** — `build_report_data()` assembles all JSON sources into Jinja2 context dict; `render_html()` runs Jinja2 against `templates/report.html`; `generate_pdf()` converts HTML to PDF via xhtml2pdf (primary) or WeasyPrint (fallback); computes condition rating A–D and P1–P4 action matrix.

**`backend/tile.py`** — `tile_image()` splits large images into overlapping 1024×1024 tiles using Pillow or OpenCV; `select_representative_tiles()` picks n=8 uniformly-spaced tiles; `tile_to_base64()` encodes tiles as JPEG base64 strings for API transmission.

**`backend/taxonomy.py`** — Static list of 56 `DEFECTS` dicts covering blade/nacelle/tower defects sourced from IEC/DNVGL/GWO standards; `build_taxonomy_prompt_block()` formats all 56 entries as compact text for embedding in Gemini prompts; `get_urgency_for_category()` maps Cat 1–5 to urgency string.

### Frontend

**`frontend/index.html`** — Single HTML page with upload form and job status display area.

**`frontend/app.js`** — Handles multipart form submission to `/api/upload`, polls `/api/status/{job_id}` every 3 seconds, renders progress bar, triggers PDF download on completion.

**`frontend/style.css`** — UI styles for the upload form and status display.

### Templates

**`templates/report.html`** — Jinja2 template rendering the complete inspection report: executive summary, turbine metadata, triage statistics, per-blade defect cards with category badges, deep analysis sections, action matrix (P1–P4), and professional footer.

**`templates/report.css`** — Print-optimized CSS for the PDF report; controls page layout, severity color coding (Cat 1–5 badge colors), table formatting.

### Config Files

**`requirements.txt`** — Python dependencies: fastapi, uvicorn, anthropic, google-generativeai, openai, Pillow, opencv-python-headless, jinja2, xhtml2pdf, python-bidi (pinned 0.4.2).

**`Procfile`** — `web: cd backend && uvicorn api:app --host 0.0.0.0 --port $PORT`

**`runtime.txt`** — Python version pin for Render/Railway.

**`nixpacks.toml`** — Nixpacks build config for Railway deployment.

**`railway.toml`** — Railway service configuration.

**`render.yaml`** — Render.com service configuration.

## Key Data Structures

### Job State Dict (`jobs/{id}/state.json`)
```python
{
    "job_id": "abc12345",           # 8-char prefix of UUID4
    "stage": "classifying",         # current pipeline stage
    "stage_message": "Classifying 35 flagged images...",
    "turbine_meta": {               # from upload form
        "turbine_id": "JAP19",
        "site_name": "Tomamae Wind Farm",
        "country": "Japan",
        "turbine_model": "Vestas V90-2.0 MW",
        "inspector_name": "...",
        "inspection_date": "2025-11-30",
        "hub_height_m": 80,
        "rotor_diameter_m": 90,
        "blade_length_m": 44,
        "weather": "Clear, sunny",
        "wind_speed_ms": 4.2,
        "temperature_c": 12.0,
        "visibility_km": 20.0,
        "gps_lat": 44.3123,
        "gps_lon": 141.6789,
        "drone_model": "DJI Matrice 300 RTK",
        "camera": "DJI Zenmuse P1 45MP",
        "notes": "...",
        "company_name": "DroneWind Asia"
    },
    "image_count": 120,             # images found in ZIP
    "total_images": 115,            # images found by ingest (valid missions only)
    "flagged_images": 35,           # images flagged by triage
    "critical_findings": 4,         # Cat 4+ defects found by classify
    "pdf_path": "/abs/path/report_JAP19.pdf",
    "created_at": "2025-11-30T10:00:00",
    "updated_at": "2025-11-30T10:05:23",
    "completed_at": "2025-11-30T10:12:45",
    "failed_at": null,
    "error_traceback": null
}
```

### Image Dict (in-memory, Stage 1 → Stage 2)
```python
{
    "path": Path("/jobs/abc/images/DJI_.../IMG_0001.jpg"),
    "turbine_id": "JAP19",
    "blade": "A",           # A | B | C
    "zone": "LE",           # LE | TE | PS | SS
    "position": "Mid",      # Root | Mid | Tip
    "mission_folder": "DJI_202508011544_069_C-N-A-LE-N",
    "sequence": 69
}
```

### Triage Result Entry (`triage.json` results array)
```json
{
    "image_path": "/abs/path/img.jpg",
    "blade": "A",
    "zone": "LE",
    "position": "Mid",
    "mission_folder": "DJI_...",
    "has_defect": true,
    "confidence": 0.87,
    "defect_hint": "Erosion pitting visible along leading edge",
    "tiles_analyzed": 8,
    "error": null
}
```

### Classify Result Entry (`classify.json` array, one per image)
```json
{
    "image_path": "/abs/path/img.jpg",
    "turbine_id": "JAP19",
    "blade": "A",
    "zone": "LE",
    "position": "Mid",
    "mission_folder": "DJI_...",
    "image_quality": "good",
    "image_notes": "",
    "error": null,
    "max_category": 3,
    "defects": [
        {
            "defect_id": 3,
            "defect_name": "Leading Edge Erosion — Stage 3",
            "category": 3,
            "urgency": "PLANNED",
            "zone": "LE",
            "position": "Mid",
            "size_estimate": "large (>30cm)",
            "confidence": 0.88,
            "visual_description": "Deep pitting and exposed composite...",
            "ndt_recommended": false,
            "blade": "A"
        }
    ]
}
```

### Analyze Result Entry (`analyze.json` array, one per Cat 4+ defect)
```json
{
    "defect_name": "Bond Line Crack",
    "category": 4,
    "turbine_id": "JAP19",
    "blade": "B",
    "zone": "TE",
    "position": "Root",
    "image_path": "/abs/path/img.jpg",
    "root_cause": "Cyclic fatigue loading at root transition...",
    "failure_risk": {
        "progression_risk": "Crack will propagate...",
        "failure_mode": "Trailing Edge Separation",
        "safety_risk": "High"
    },
    "vestas_standard": "DNVGL-ST-0376 Section 8.3...",
    "recommended_action": "NDT inspection, then injection repair...",
    "repair_timeframe": "30 days",
    "estimated_cost_usd": "$8,000–$18,000",
    "engineer_review_required": true,
    "engineer_review_reason": "Bond line cracks at root require sign-off...",
    "analysis_confidence": 0.87,
    "additional_notes": "...",
    "error": null
}
```

## JSON Intermediate Files

All intermediates live in `jobs/{job_id}/`:

| File | Written by | Read by | Optional |
|------|-----------|---------|----------|
| `state.json` | `api.py` (all stages) | `api.py` `/api/status` | No |
| `triage.json` | `triage.py` | `report.py` | Yes (skipped if no KIMI_API_KEY) |
| `classify.json` | `classify.py` (or dummy) | `analyze.py`, `report.py` | No (always created) |
| `analyze.json` | `analyze.py` (or empty) | `report.py` | Yes (empty if no ANTHROPIC_API_KEY) |
| `report_{id}.pdf` | `report.py` | Download endpoint | No (pipeline goal) |
| `report_{id}.html` | `report.py` | Manual review | Yes (saved alongside PDF) |

## Naming Conventions

**Files:**
- Snake case for Python modules: `api.py`, `ingest.py`, `triage.py`
- Descriptive stage names matching pipeline order

**Functions:**
- `{verb}_{noun}()` pattern: `triage_image()`, `classify_batch()`, `analyze_defect()`, `build_report()`
- `save_{stage}_results()` for JSON persistence functions
- `load_{data}()` for JSON loading functions

**Variables:**
- Snake case throughout: `turbine_id`, `flagged_images`, `defect_hint`
- Dataclasses for structured results: `TriageResult`, `ClassifyResult`, `DeepAnalysis`

**Job IDs:**
- First 8 characters of `uuid.uuid4()`: e.g. `"abc12345"`

**Report filenames:**
- `report_{turbine_id}.pdf` / `report_{turbine_id}.html`

## Output Artifacts

**Per-job artifacts in `jobs/{job_id}/`:**
- `state.json` — machine-readable job status (polled by frontend)
- `triage.json` — full triage results including clean images (used in report triage stats)
- `classify.json` — full classification including images with no defects found
- `analyze.json` — engineering analysis for Cat 4+ only
- `report_{turbine_id}.pdf` — final downloadable PDF (Vestas-standard format)
- `report_{turbine_id}.html` — HTML source of report (for debugging/preview)

## Where to Add New Code

**New pipeline stage:**
- Create `backend/{stage_name}.py` following existing module pattern (dataclasses, batch function, save/load helpers)
- Add stage call inside `run_pipeline()` in `backend/api.py`
- Add new stage name to `stage_progress` dict in `/api/status/{job_id}` handler
- Write intermediate JSON to `job_dir / "{stage}.json"`

**New API endpoint:**
- Add `@app.get/post(...)` handler in `backend/api.py`
- Follow existing pattern: `get_job()` for state access, `HTTPException` for errors

**New defect type:**
- Add entry to `DEFECTS` list in `backend/taxonomy.py` following existing dict schema
- Defect IDs are sequential integers; append with next available ID

**New report section:**
- Add data assembly in `build_report_data()` in `backend/report.py`
- Add rendering in `templates/report.html` using Jinja2 template syntax
- Add styles in `templates/report.css`

**New frontend feature:**
- Modify `frontend/app.js` and `frontend/index.html`
- Frontend is pure HTML/JS/CSS — no build step required

## Special Directories

**`jobs/`:**
- Purpose: Runtime job storage (state + intermediates + output files)
- Generated: Yes, at runtime by `api.py`
- Committed: No (in `.gitignore`)
- Cleanup: Via `DELETE /api/jobs/{job_id}` endpoint

**`.planning/`:**
- Purpose: GSD planning documents and codebase analysis
- Generated: Yes, by GSD map-codebase
- Committed: Yes

---

*Structure analysis: 2026-03-03*
