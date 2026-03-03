# Architecture

**Analysis Date:** 2026-03-03

## Pattern Overview

**Overall:** Linear AI pipeline with REST API orchestration

**Key Characteristics:**
- Five sequential pipeline stages, each calling a different external AI API
- Stateless FastAPI server with in-memory + on-disk job registry
- Background task execution via FastAPI `BackgroundTasks` (synchronous run in thread)
- All inter-stage data passed as JSON files written to a per-job directory
- No database — state is a `state.json` dict on disk per job

## System Purpose

BDDA (Blade Defect Detection Agent) analyzes drone inspection imagery of wind turbine blades. A user uploads a ZIP of DJI P1 images, the system runs five AI processing stages, and produces a PDF inspection report conforming to Vestas/IEC/DNVGL standards.

## The 5-Stage Pipeline

```
Upload ZIP/images
       │
       ▼
Stage 1: ingest.py  — parse DJI folder structure, extract blade/zone/position metadata
       │  output: flat list of image dicts in memory
       ▼
Stage 2: triage.py  — Kimi K2.5 vision (fast binary screen: has_defect YES/NO per image)
       │  output: jobs/{id}/triage.json
       ▼
Stage 3: classify.py — Gemini 2.5 Pro (full image, structured defect JSON per flagged image)
       │  output: jobs/{id}/classify.json
       ▼
Stage 4: analyze.py  — Claude Opus 4.6 (deep structural engineering analysis, Cat 4+ only)
       │  output: jobs/{id}/analyze.json
       ▼
Stage 5: report.py   — Jinja2 → HTML → xhtml2pdf (PDF generation)
          output: jobs/{id}/report_{turbine_id}.pdf
                  jobs/{id}/report_{turbine_id}.html (saved alongside)
```

All stages are called sequentially inside `run_pipeline()` in `backend/api.py`. The pipeline runs in a FastAPI background task (not async — blocking the background thread).

## Layers

**HTTP Layer:**
- Purpose: Accept uploads, expose status/download endpoints, serve frontend
- Location: `backend/api.py`
- Contains: FastAPI app, endpoint handlers, job state management, `run_pipeline()` orchestrator
- Depends on: All pipeline modules (imported lazily inside `run_pipeline`)
- Used by: Browser frontend at `frontend/`

**Pipeline Stage Modules:**
- Purpose: One module per AI stage; each is independently importable and testable
- Location: `backend/ingest.py`, `backend/triage.py`, `backend/classify.py`, `backend/analyze.py`, `backend/report.py`
- Contains: Data classes, API client functions, batch processing functions, JSON save/load helpers
- Depends on: External AI APIs, `backend/tile.py`, `backend/taxonomy.py`
- Used by: `backend/api.py` via `run_pipeline()`

**Utility Layer:**
- Purpose: Shared image tiling and defect taxonomy knowledge base
- Location: `backend/tile.py`, `backend/taxonomy.py`
- Contains: Image tiling logic (PIL/OpenCV), 56-defect taxonomy, prompt builders
- Depends on: Pillow, OpenCV (optional fallback)
- Used by: `backend/triage.py` (tile.py), `backend/classify.py` (taxonomy.py)

**Template Layer:**
- Purpose: HTML/CSS template for PDF report rendering
- Location: `templates/report.html`, `templates/report.css`
- Contains: Jinja2 template with full report layout
- Used by: `backend/report.py` via Jinja2 `Environment`

**Frontend Layer:**
- Purpose: Browser UI for upload and status polling
- Location: `frontend/index.html`, `frontend/app.js`, `frontend/style.css`
- Served as static files by FastAPI at `/`

## Job State Management

**In-memory registry:** `_jobs: Dict[str, Dict]` in `backend/api.py` — process-scoped, lost on restart.

**Disk persistence:** `jobs/{job_id}/state.json` — written on every state change, loaded on cache miss.

**Job state dict schema:**
```python
{
    "job_id": str,           # 8-char UUID prefix
    "stage": str,            # queued | ingesting | triaging | classifying |
                             # analyzing | generating_report | complete | error
    "stage_message": str,    # human-readable progress description
    "turbine_meta": dict,    # full turbine/inspection metadata from upload form
    "image_count": int,      # total images extracted from ZIP
    "total_images": int,     # images found by ingest
    "flagged_images": int,   # images flagged by triage
    "critical_findings": int,# Cat 4+ defects found by classify
    "pdf_path": str,         # absolute path to generated PDF
    "created_at": str,       # ISO datetime
    "updated_at": str,       # ISO datetime of last stage update
    "completed_at": str,     # ISO datetime on success
    "failed_at": str,        # ISO datetime on error
    "error_traceback": str,  # full Python traceback on error
}
```

**Stage → progress% mapping** (returned by `/api/status/{job_id}`):
```
queued → 0%  |  ingesting → 10%  |  triaging → 25%  |  classifying → 50%
analyzing → 70%  |  generating_report → 85%  |  complete → 100%  |  error → -1
```

## Stage-by-Stage Data Flow

### Stage 1: Ingest (`backend/ingest.py`)
- **Input:** Path to extracted images directory containing DJI mission folders
- **Parsing:** Regex `DJI_{datetime}_{seq}_C-{cam}-{blade}-{zone}-{position}` on folder names
- **Output (in-memory):** `List[Dict]` — one dict per image:
  ```python
  {
      "path": Path,           # absolute image path
      "turbine_id": str,      # e.g. "JAP19"
      "blade": str,           # A | B | C
      "zone": str,            # LE | TE | PS | SS
      "position": str,        # Root | Mid | Tip
      "mission_folder": str,  # raw DJI folder name
      "sequence": int,        # mission sequence number
  }
  ```
- **Key dataclasses:** `MissionFolder`, `IngestResult`

### Stage 2: Triage (`backend/triage.py`)
- **Input:** `List[Dict]` image dicts from Stage 1
- **AI:** Kimi K2.5 (`moonshot-v1-8k-vision-preview`) via OpenAI-compatible client at `https://api.moonshot.ai/v1`
- **Image handling:** `tile.py` — each image is split into 8 representative 1024×1024 tiles; tiles sent as base64 to Kimi
- **Decision:** `has_defect` (bool) + `confidence` (float); confidence threshold 0.45
- **Batch cap:** All images (no hard cap at this stage, but API key required)
- **Fallback (no key):** First 50 images all flagged as `has_defect=True`
- **Output file:** `jobs/{id}/triage.json`
  ```json
  {
      "turbine_id": "JAP19",
      "total_images": 120,
      "flagged_images": 35,
      "clean_images": 82,
      "error_images": 3,
      "flag_rate": 0.29,
      "results": [
          {
              "image_path": "/abs/path/img.jpg",
              "blade": "A", "zone": "LE", "position": "Mid",
              "mission_folder": "DJI_...",
              "has_defect": true,
              "confidence": 0.87,
              "defect_hint": "Erosion pitting visible at leading edge",
              "tiles_analyzed": 8,
              "error": null
          }
      ]
  }
  ```
- **Key dataclasses:** `TriageResult`, `TriageSummary`

### Stage 3: Classify (`backend/classify.py`)
- **Input:** Flagged images list (only `has_defect=True` entries from triage)
- **AI:** Gemini 2.5 Pro (`gemini-2.5-pro-preview-06-05`) via `google-generativeai`
- **Image handling:** Full image loaded as base64 — no tiling (Gemini handles natively)
- **Taxonomy:** `taxonomy.py` — all 56 defect types embedded as prompt context via `build_taxonomy_prompt_block()`
- **Batch cap:** First 80 flagged images
- **Fallback (no key):** Dummy classify JSON with empty defects list
- **Output file:** `jobs/{id}/classify.json`
  ```json
  [
      {
          "image_path": "/abs/path/img.jpg",
          "turbine_id": "JAP19",
          "blade": "A", "zone": "LE", "position": "Mid",
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
                  "zone": "LE", "position": "Mid",
                  "size_estimate": "large (>30cm)",
                  "confidence": 0.88,
                  "visual_description": "...",
                  "ndt_recommended": false,
                  "blade": "A"
              }
          ]
      }
  ]
  ```
- **Key dataclasses:** `DefectFinding`, `ClassifyResult`
- **Loading for next stage:** `load_critical_findings(classify_path)` — returns only Cat 4+ defects

### Stage 4: Analyze (`backend/analyze.py`)
- **Input:** `List[Dict]` of Cat 4+ defect findings from `load_critical_findings()`
- **AI:** Claude Opus 4.6 (`claude-opus-4-6`) via `anthropic` SDK
- **Image handling:** Full image optionally sent as base64 alongside structured defect data
- **Scope:** Only Cat 4–5 defects (~10–20 per turbine)
- **Fallback (no key or no critical findings):** Empty `analyze.json`
- **Output file:** `jobs/{id}/analyze.json`
  ```json
  [
      {
          "defect_name": "Bond Line Crack",
          "category": 4,
          "turbine_id": "JAP19",
          "blade": "B", "zone": "TE", "position": "Root",
          "image_path": "/abs/path/img.jpg",
          "root_cause": "...",
          "failure_risk": {
              "progression_risk": "...",
              "failure_mode": "...",
              "safety_risk": "High"
          },
          "vestas_standard": "DNVGL-ST-0376 ...",
          "recommended_action": "...",
          "repair_timeframe": "30 days",
          "estimated_cost_usd": "$8,000–$18,000",
          "engineer_review_required": true,
          "engineer_review_reason": "...",
          "analysis_confidence": 0.87,
          "additional_notes": "...",
          "error": null
      }
  ]
  ```
- **Key dataclass:** `DeepAnalysis`

### Stage 5: Report (`backend/report.py`)
- **Input:** `turbine_meta` dict + `classify.json` + `triage.json` (optional) + `analyze.json`
- **Processing:** `build_report_data()` assembles all data into a single context dict; computes condition rating (A–D), action matrix (P1–P4 priorities), per-blade defect cards, triage stats
- **HTML rendering:** Jinja2 template at `templates/report.html`
- **PDF generation:** xhtml2pdf (primary, pure Python); WeasyPrint (fallback, requires system GTK)
- **Output files:**
  - `jobs/{id}/report_{turbine_id}.pdf` — downloadable PDF
  - `jobs/{id}/report_{turbine_id}.html` — saved alongside PDF (`save_html=True`)
- **Condition rating logic:**
  - Any Cat 5 → D (Critical)
  - Any Cat 4 → C (Poor)
  - 3+ Cat 3 → C (Poor)
  - Any Cat 3 or >3 Cat 2 → B (Fair)
  - Otherwise → A (Good)

## API Endpoints

All endpoints under `/api/` prefix.

**`POST /api/upload`** — Start a job
- Form fields: `turbine_id`, `site_name`, `country`, `turbine_model`, `inspector_name`, `inspection_date`, plus optional fields (dimensions, weather, GPS, drone_model, notes)
- File: `images` (ZIP or single image)
- Response: `{"job_id": "abc12345", "image_count": 120, "message": "Pipeline started"}`
- Side effect: Creates `jobs/{id}/` directory, saves initial state, starts `run_pipeline()` as background task

**`GET /api/status/{job_id}`** — Poll job progress
- Returns: stage name, progress %, message, image counts, timestamps, error details (with full traceback on failure)

**`GET /api/download/{job_id}`** — Download completed PDF
- Returns: `FileResponse` with content-disposition filename `inspection_report_{turbine_id}_{date}.pdf`
- 400 if job not in `complete` stage

**`GET /api/jobs`** — List last 20 jobs
- Scans `jobs/*/state.json` sorted by mtime, returns summary list

**`DELETE /api/jobs/{job_id}`** — Delete job and all artifacts
- Removes `jobs/{id}/` directory and evicts from in-memory cache

**`GET /api/health`** — Health check
- Returns API key presence (bool, not values) and jobs directory path

**`GET /api/debug/kimi`** — Kimi API smoke test
- Sends a 64×64 grey test image to Kimi, returns raw/parsed response for diagnosis

**`/` (static)** — Frontend
- `frontend/` directory served as static files with HTML mode enabled

## Image Tiling (`backend/tile.py`)

Used only by Stage 2 (triage). Stage 3 (classify) sends full images directly to Gemini.

- A 45MP DJI P1 image (~8192×5460px) produces ~70 tiles at 1024px with 20% overlap
- `select_representative_tiles()` picks 8 uniformly-spaced tiles for triage (covers full blade span)
- Auto-selects between Pillow (preferred) and OpenCV (fallback)
- Tiles encoded as JPEG base64 at quality=85 for API transmission

## Defect Taxonomy (`backend/taxonomy.py`)

Static knowledge base, not a database. Defines:
- 56 defect types across blade (A–G), nacelle (H), and tower (I) systems
- Each defect: id, name, zones, positions, cat_range (min/max), urgency, timeframe, visual_cue, standard reference, ndt_required flag
- `build_taxonomy_prompt_block()` compiles all 56 entries into a compact text block embedded in every Gemini classification prompt
- `get_urgency_for_category(cat)` maps Cat 1–5 → LOG/MONITOR/PLANNED/URGENT/IMMEDIATE

## Error Handling

**Strategy:** Pipeline errors are caught at the top level of `run_pipeline()`. On any exception, the job transitions to `stage="error"` with `stage_message=str(e)` and `error_traceback=full_tb`. The job remains queryable via `/api/status/{job_id}`.

**Per-stage API failures:** Each stage has retry logic with exponential backoff:
- Kimi (triage): 3 retries, 1s sleep on JSON decode failure, exponential on connection errors
- Gemini (classify): 3 retries, 30s sleep on 429/quota errors
- Claude (analyze): 3 retries, catches `anthropic.RateLimitError` for 30s sleep

**Missing API keys:** Each stage gracefully degrades — triage flags all images, classify produces empty defect lists, analyze produces empty analysis. The pipeline still completes and a PDF is generated.

## Background Task Execution

`run_pipeline()` is added via `background_tasks.add_task(run_pipeline, job_id, job_dir, turbine_meta)` in the upload endpoint. FastAPI runs background tasks after the response is sent, in the same thread pool. This is a synchronous (blocking) function — it ties up one thread for the entire pipeline duration (potentially minutes for large inspections).

There is no task queue, worker process, or async execution. For production scaling, this approach limits concurrency to the number of available server threads.

---

*Architecture analysis: 2026-03-03*
