# Testing Patterns

**Analysis Date:** 2026-03-03

## Test Framework

**Runner:** None — no automated test suite exists. There are no `test_*.py` files, no `tests/` directory, no `pytest.ini`, no `vitest.config`, and no test runner in `requirements.txt`.

**Testing approach:** Manual testing via:
1. Debug API endpoints (`/api/debug/kimi`, `/api/health`)
2. Module CLI entry points (`python backend/triage.py`, etc.)
3. Sample data functions built into `report.py`
4. Full pipeline runs with real drone images

## Starting the Server Locally

```bash
cd /path/to/project
pip install -r requirements.txt

# Set API keys
export KIMI_API_KEY=sk-...
export GOOGLE_API_KEY=AIza...
export ANTHROPIC_API_KEY=sk-ant-...

# Start the API server
python backend/api.py
# Server listens on http://localhost:8000
```

The server auto-discovers the frontend at `../frontend/` relative to `backend/api.py` and mounts it at `/`. Opening `http://localhost:8000` shows the full UI.

## Debug Endpoints

### `/api/health` — Verify API key configuration

```
GET http://localhost:8000/api/health
```

Expected response when all keys are set:
```json
{
  "status": "ok",
  "api_keys": {
    "ANTHROPIC_API_KEY": true,
    "GOOGLE_API_KEY": true,
    "KIMI_API_KEY": true
  },
  "jobs_dir": "/absolute/path/to/jobs"
}
```

If any key is `false`, that pipeline stage will be skipped (fallback mode). The frontend shows "Missing: KIMI, GOOGLE" in the header banner.

### `/api/debug/kimi` — Test Kimi Vision API end-to-end

```
GET http://localhost:8000/api/debug/kimi
```

This endpoint creates a synthetic 64×64 grey JPEG in memory, sends it to the Kimi `moonshot-v1-8k-vision-preview` model, and returns the raw + parsed response. Use this to confirm:
1. `KIMI_API_KEY` is valid
2. The Moonshot endpoint (`api.moonshot.ai`) is reachable
3. JSON parsing succeeds

Expected success response:
```json
{
  "model": "moonshot-v1-8k-vision-preview",
  "raw_response": "'{\"has_defect\": false, \"confidence\": 0.05, \"defect_hint\": null}'",
  "cleaned": "'{\"has_defect\": false, ...}'",
  "parse_ok": true,
  "parsed": {"has_defect": false, "confidence": 0.05, "defect_hint": null}
}
```

If `parse_ok` is a string (not `true`), it contains the JSON parse error message. If `"error"` key is present, the API call failed entirely.

### `/api/status/{job_id}` — Monitor pipeline progress

```
GET http://localhost:8000/api/status/abc12345
```

Expected response during pipeline execution:
```json
{
  "job_id": "abc12345",
  "stage": "triaging",
  "message": "Screening 312 images for defects...",
  "progress": 25,
  "total_images": 312,
  "flagged_images": null,
  "critical_findings": null,
  "created_at": "2026-03-03T10:00:00",
  "completed_at": null,
  "error": null,
  "error_traceback": null
}
```

Stage progress values: `queued=0`, `ingesting=10`, `triaging=25`, `classifying=50`, `analyzing=70`, `generating_report=85`, `complete=100`, `error=-1`.

When `stage="error"`, both `error` (short message) and `error_traceback` (full Python traceback) are populated. This is the primary debugging tool when the pipeline fails.

### `/api/jobs` — List recent jobs

```
GET http://localhost:8000/api/jobs
```

Returns last 20 jobs with turbine ID, stage, and timestamps. Useful for finding job IDs of recent runs.

## Module-Level CLI Testing

Each backend module can be run directly to verify imports and basic functionality without needing API keys.

### Test ingest (no API key required):

```bash
python backend/ingest.py /path/to/turbine/folder JAP19
```

Expected output:
```
============================================================
BDDA Ingest Summary: JAP19
============================================================
Path:           /path/to/turbine/folder
Total folders:  24
Mission folders: 20
Skipped folders: 4
Total images:   487

Images by blade and zone:
  Blade A / LE: 82 images
  Blade A / TE: 79 images
  ...
```

If the folder structure is wrong (no `DJI_*` subdirectories), `Valid mission folders: 0` indicates the upload unwrapping logic may need adjustment.

### Test taxonomy (no API key required):

```bash
python backend/taxonomy.py
```

Expected output:
```
BDDA Taxonomy loaded: 56 defect types
  Blade: 30 | Nacelle: 8 | Tower: 18

IMMEDIATE urgency defects (7):
  #4 Leading Edge Erosion — Stage 4 (Critical)
  ...
```

### Test tile (no API key required, requires an image file):

```bash
python backend/tile.py /path/to/any/image.jpg
```

Expected output:
```
Tiling: /path/to/image.jpg
Dimensions: 8192×5460 px
Generated 50 tiles
First tile coords: (0, 0, 1024, 1024)
Last tile coords: (7168, 4436, 1024, 1024)
Base64 sample (first 60 chars): /9j/4AAQSkZJRgABAQAAAQABAAD/...
```

### Test report data assembly (no API key required):

```bash
python backend/report.py
```

Expected output:
```
jinja2 OK
WARNING: weasyprint unavailable — ...  (or "weasyprint OK" if installed)

Testing data assembly with sample data...
  Turbine: JAP19
  Condition: C — Poor
  Total defects: 3
  Defects by cat: {3: 1, 4: 1, 2: 1}
  Blades: ['A', 'B', 'C']
  Action matrix: 3 items
  Engineer reviews: 1

Data assembly OK.
```

This validates the entire report data path (load → assemble → render) using the built-in sample data in `make_sample_turbine_meta()`, `make_sample_classify_data()`, and `make_sample_analyze_data()` — without generating a PDF or calling any AI API.

### Check API key presence (no actual API call):

```bash
python backend/triage.py
python backend/classify.py
python backend/analyze.py
```

Each prints whether the respective API key is set in the environment. No API calls are made.

## Full Pipeline Manual Test

### Step 1: Upload via UI

1. Open `http://localhost:8000`
2. Fill in the inspection form (Turbine ID, Site, Model, Inspector, Date are required)
3. Upload a ZIP of DJI inspection folders or individual JPEGs
4. Click "Generate Inspection Report"
5. Watch the stage progress dots: Ingest → Triage → Classify → Analyze → Report

### Step 2: Monitor via status endpoint

While the pipeline runs, poll the status:
```
GET http://localhost:8000/api/status/{job_id}
```
The `job_id` is returned immediately by the upload response and shown in the UI.

### Step 3: Verify each stage completed

After completion, check the job directory:
```
jobs/{job_id}/
├── state.json          ← full job state and all stage metadata
├── images/             ← extracted uploaded images
├── triage.json         ← Stage 1 output: flagged/clean per image
├── classify.json       ← Stage 2 output: defects per image
├── analyze.json        ← Stage 3 output: deep analysis per critical defect
├── report_{turbine_id}.pdf   ← Final PDF
└── report_{turbine_id}.html  ← HTML intermediate (saved when save_html=True)
```

### Step 4: Verify each JSON file

**triage.json** structure check — should show `flag_rate` between 0.05 and 0.6 for real images:
```json
{
  "turbine_id": "JAP19",
  "total_images": 312,
  "flagged_images": 87,
  "flag_rate": 0.279,
  "results": [...]
}
```

**classify.json** structure check — each entry should have a `defects` array and `max_category`:
```json
[
  {
    "image_path": "/...",
    "blade": "A",
    "zone": "LE",
    "max_category": 3,
    "defects": [
      {"defect_name": "Leading Edge Erosion — Stage 3", "category": 3, ...}
    ]
  }
]
```

**analyze.json** — only Cat 4+ defects appear here:
```json
[
  {
    "defect_name": "Bond Line Crack",
    "category": 4,
    "root_cause": "...",
    "failure_risk": {"safety_risk": "High", ...},
    "repair_timeframe": "30 days",
    "engineer_review_required": true,
    "error": null
  }
]
```

## Testing Without API Keys (Fallback Mode)

Run the pipeline without setting any API keys to verify fallback behavior. Each stage has a defined fallback:

| Stage | Fallback when key missing |
|-------|--------------------------|
| Triage (KIMI) | First 50 images all marked `has_defect=true`, hint = "Triage skipped" |
| Classify (GOOGLE) | Dummy classify JSON with `defects=[]` and `max_category=0` for first 20 images |
| Analyze (ANTHROPIC) | Empty `analyze.json` (`[]`) |
| Report | Always runs; generates PDF from whatever data exists |

This mode confirms the pipeline skeleton works end-to-end and the report template renders without errors. The resulting PDF will show 0 defects found (expected).

## Testing ZIP Upload Unwrapping

The pipeline handles ZIPs with a single wrapper folder automatically. To test:

1. Create a ZIP where the DJI folders are nested: `JAP19_test/DJI_202508011544_069_C-N-B-TE-N/image.jpg`
2. Upload. `api.py` detects a single subdirectory without `DJI_*` at the top level and scans the subdirectory instead.
3. Verify `ingest_turbine_folder` receives the correct path by checking `triage.json` for non-zero `total_images`.

## Verifying a Successful Pipeline Run

A complete successful run shows:
1. `state.json` has `"stage": "complete"` and a non-null `completed_at`
2. `triage.json` exists with `total_images > 0`
3. `classify.json` exists with at least one entry
4. `analyze.json` exists (may be `[]` if no Cat 4+ findings)
5. `report_{turbine_id}.pdf` exists and is readable (open in browser or PDF viewer)
6. `report_{turbine_id}.html` exists and renders correctly in a browser
7. `/api/status/{job_id}` returns `"progress": 100`
8. Download button appears in the UI and the PDF downloads correctly

## Common Failure Modes

**`stage="error"` immediately after ingesting:** Check that the uploaded ZIP contains `DJI_*` subfolders matching the regex pattern `DJI_{datetime}_{seq}_C-[A-Z]-[ABC]-(LE|TE|PS|SS)-[NTRM]`. Non-matching folders are silently skipped.

**Triage returns all images as clean (0 flagged):** Kimi API may be returning non-JSON or very low confidence scores. Check `/api/debug/kimi` to verify the API is working.

**Classify returns `error` for all images:** Check `GOOGLE_API_KEY` is valid and the Gemini API quota isn't exhausted. The `429` rate limit handler adds a 30-second sleep and retries.

**PDF generation fails:** `xhtml2pdf` is the primary renderer. If it fails, check that `xhtml2pdf>=0.2.11` is installed. The fallback is WeasyPrint which requires system GTK/Pango libraries (not available on Railway/Render without Docker).

**`error_traceback` in state.json:** The full Python traceback is saved and exposed through `/api/status/{job_id}` as `error_traceback`. This is the primary debugging tool.

## Sample Data for Isolated Testing

`report.py` exports three functions for generating valid sample pipeline data without running the full pipeline:

```python
from backend.report import make_sample_turbine_meta, make_sample_classify_data, make_sample_analyze_data

meta = make_sample_turbine_meta("JAP19")      # Vestas V90-2.0 MW in Japan
classify = make_sample_classify_data()         # 3 images, 3 defects (Cat 2, 3, 4)
analyze = make_sample_analyze_data()           # 1 deep analysis (Bond Line Crack)

# Build full report data dict
from backend.report import build_report_data
report_data = build_report_data(meta, None, classify, analyze)
```

This lets you test report template changes, condition rating logic, and action matrix generation without any API calls or real images.

---

*Testing analysis: 2026-03-03*
