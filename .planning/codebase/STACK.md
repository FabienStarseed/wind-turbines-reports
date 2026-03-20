# Technology Stack

**Analysis Date:** 2026-03-03

## Languages

**Primary:**
- Python 3.12.0 — all backend logic (`runtime.txt` pins `python-3.12.0`)

**Secondary:**
- JavaScript (vanilla, no framework) — frontend UI (`frontend/app.js`)
- HTML5 / CSS3 — frontend markup/styles (`frontend/index.html`, `frontend/style.css`)

## Runtime

**Environment:**
- Python 3.12.0 (pinned in `runtime.txt`)

**Package Manager:**
- pip — install command: `pip install -r requirements.txt`
- Lockfile: not present (only `requirements.txt` with `>=` version pins, except two hard-pinned packages)

## Frameworks

**Core:**
- FastAPI `0.115.5` — REST API and static file serving (`backend/api.py`)
- Uvicorn `0.32.1` (with `[standard]` extras) — ASGI server; start command: `uvicorn api:app --host 0.0.0.0 --port $PORT`
- python-multipart `0.0.12` — multipart form/file upload parsing for FastAPI

**Templating / PDF:**
- Jinja2 `>=3.1.0` — HTML report template rendering (`backend/report.py`, `templates/report.html`)
- xhtml2pdf `>=0.2.11` — primary PDF renderer (pure Python, zero system deps); used in `backend/report.py`
- python-bidi `0.4.2` — pinned to pre-built wheel to avoid Rust compilation; RTL text support dependency of xhtml2pdf
- WeasyPrint — secondary/fallback PDF renderer (requires GTK/Pango system libs); imported lazily in `backend/report.py` only if xhtml2pdf unavailable

**Testing:**
- Not detected — no test framework, test files, or test configuration present

**Build/Dev:**
- None — no build step; Python source files are run directly

## Key Dependencies

**Critical:**
- `anthropic>=0.40.0` — Anthropic Python SDK; calls Claude Opus 4.6 for deep defect analysis (`backend/analyze.py`)
- `google-generativeai>=0.8.0` — Google Generative AI SDK; calls Gemini 2.5 Pro for defect classification (`backend/classify.py`)
- `openai>=1.50.0` — OpenAI-compatible SDK used to call Kimi/Moonshot API for triage (`backend/triage.py`, `backend/api.py`)

**Image Processing:**
- `Pillow>=10.0.0` — primary image tiling, base64 conversion (`backend/tile.py`)
- `opencv-python-headless>=4.9.0` — fallback image tiling and numpy array operations (`backend/tile.py`); headless variant avoids GUI system dependencies

**Infrastructure:**
- `python-dateutil>=2.9.0` — date parsing utility; used in pipeline metadata handling

## Configuration

**Environment:**
- Three API keys required, all loaded via `os.environ.get()`:
  - `KIMI_API_KEY` — Moonshot/Kimi vision API (Stage 1: triage)
  - `GOOGLE_API_KEY` — Google Gemini API (Stage 2: classify)
  - `ANTHROPIC_API_KEY` — Anthropic Claude API (Stage 3: analyze)
- Optional: `COMPANY_NAME` — injected into report metadata (defaults to `"DroneWind Asia"`)
- Optional: `PORT` — server port (defaults to `8000` in local mode)
- Pipeline gracefully degrades: if a key is missing, that stage is skipped with stub data

**Build:**
- `render.yaml` — Render.com deployment manifest (build: `pip install -r requirements.txt`, start: `uvicorn api:app`)
- `Procfile` — Heroku-compatible process file (same start command)

## Platform Requirements

**Development:**
- Python 3.12+
- No system-level dependencies required for the default PDF renderer (xhtml2pdf)
- Optional: GTK/Pango (only needed if WeasyPrint fallback is used)

**Production:**
- Deployed to Render.com as a `web` service (`render.yaml`)
- Health check endpoint: `GET /api/health`
- Jobs and generated PDFs stored on local filesystem under `jobs/` directory (ephemeral on Render unless a persistent disk is attached)
- In-memory job registry (`_jobs` dict in `backend/api.py`) — not shared across multiple instances

## Frontend

**Technology:** Vanilla HTML5 / CSS3 / JavaScript (no framework, no build step)
- `frontend/index.html` — single-page application shell
- `frontend/app.js` — API calls, file drop zone, job polling, history display
- `frontend/style.css` — custom CSS (no utility framework detected)
- Served as static files by FastAPI: `app.mount("/", StaticFiles(..., html=True))`
- Same-origin API calls; `API` base URL constant defaults to `''` (same origin)

---

*Stack analysis: 2026-03-03*
