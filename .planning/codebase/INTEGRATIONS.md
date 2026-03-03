# External Integrations

**Analysis Date:** 2026-03-03

## APIs & External Services

### 1. Moonshot / Kimi Vision API (Stage 1 — Triage)

- **Purpose:** Fast binary defect screening — YES/NO per image tile, low cost (~$0.50/turbine)
- **SDK/Client:** `openai>=1.50.0` (OpenAI-compatible interface)
- **Auth:** `KIMI_API_KEY` environment variable — loaded via `os.environ.get("KIMI_API_KEY", "")` in `backend/api.py` and `backend/triage.py`
- **Base URL:** `https://api.moonshot.ai/v1` (international endpoint, not `.cn`)
- **Model:** `moonshot-v1-8k-vision-preview`
- **How called:**
  ```python
  from openai import OpenAI
  client = OpenAI(api_key=api_key, base_url="https://api.moonshot.ai/v1")
  response = client.chat.completions.create(
      model="moonshot-v1-8k-vision-preview",
      messages=[{"role": "user", "content": [...]}],
      max_tokens=300,
      temperature=0.1,
  )
  ```
- **Input:** Up to 8 representative 1024×1024 JPEG tiles per image (base64-encoded), plus a structured text prompt with blade/zone/position context
- **Output:** JSON `{"has_defect": bool, "confidence": float, "defect_hint": str|null}`
- **Error handling:** 3 retries with exponential backoff (`2^attempt` seconds); JSON parse errors retry with 1s delay; returns `{"error": ...}` dict on exhausted retries
- **Pipeline entry:** `backend/triage.py` → `call_kimi_triage()` → called by `triage_batch()` → called by `run_pipeline()` in `backend/api.py`
- **Graceful degradation:** If `KIMI_API_KEY` not set, all images (capped at 50) are marked as flagged and triage is skipped
- **Debug endpoint:** `GET /api/debug/kimi` — sends a 64×64 grey test image and returns raw API response for diagnosis

---

### 2. Google Gemini API (Stage 2 — Classification)

- **Purpose:** Full defect classification with structured taxonomy — identifies defect type, category (1–5), urgency, size, confidence (~$3/turbine for 80 images)
- **SDK/Client:** `google-generativeai>=0.8.0`
- **Auth:** `GOOGLE_API_KEY` environment variable — loaded via `os.environ.get("GOOGLE_API_KEY", "")` in `backend/api.py`; passed to `genai.configure(api_key=api_key)` in `backend/classify.py`
- **Base URL:** Managed by SDK (default Google API endpoint)
- **Model:** `gemini-2.5-pro-preview-06-05`
- **How called:**
  ```python
  import google.generativeai as genai
  genai.configure(api_key=api_key)
  model_instance = genai.GenerativeModel("gemini-2.5-pro-preview-06-05")
  response = model_instance.generate_content(
      parts,
      generation_config={"temperature": 0.1, "max_output_tokens": 2000},
  )
  ```
- **Input:** Full-resolution JPEG image (base64 inline_data) + structured prompt with turbine context, triage hint, and 56-item defect taxonomy block
- **Output:** JSON `{"defects": [...], "image_quality": str, "image_notes": str}` — each defect has `defect_id`, `defect_name`, `category`, `urgency`, `zone`, `position`, `size_estimate`, `confidence`, `visual_description`, `ndt_recommended`
- **Error handling:** 3 retries; rate limit (429/quota) triggers 30s sleep; other errors use `2^attempt` backoff; returns `{"error": ...}` on exhausted retries
- **Pipeline entry:** `backend/classify.py` → `call_gemini_classify()` → called by `classify_batch()` → called by `run_pipeline()` in `backend/api.py`
- **Cap:** Maximum 80 flagged images processed per job (`classify_batch(flagged[:80], ...)` in `backend/api.py`)
- **Graceful degradation:** If `GOOGLE_API_KEY` not set, dummy classify JSON is generated with `max_category: 0` and no defects; `critical_findings` is empty list
- **Downstream filter:** Only Cat 4+ findings from classify output are passed to Stage 3 (`load_critical_findings(classify_path, min_category=4)`)

---

### 3. Anthropic Claude API (Stage 3 — Deep Analysis)

- **Purpose:** Structural engineering assessment of Cat 4–5 defects — root cause, failure risk, Vestas SMP recommendation, repair timeframe, cost estimate (~$8/turbine)
- **SDK/Client:** `anthropic>=0.40.0`
- **Auth:** `ANTHROPIC_API_KEY` environment variable — loaded via `os.environ.get("ANTHROPIC_API_KEY", "")` in `backend/api.py`
- **Base URL:** Default Anthropic SDK endpoint (no custom base_url)
- **Model:** `claude-opus-4-6`
- **How called:**
  ```python
  import anthropic
  client = anthropic.Anthropic(api_key=api_key)
  response = client.messages.create(
      model="claude-opus-4-6",
      max_tokens=1500,
      system=ANALYZE_SYSTEM_PROMPT,
      messages=[{"role": "user", "content": content}],
  )
  ```
- **Input:** Optional full-resolution JPEG image (base64, type `"image"` with `source.type: "base64"`) + structured text prompt with defect details (category, turbine model, blade/zone/position, visual description, size, confidence)
- **Output:** JSON with `root_cause`, `failure_risk` (sub-object with `progression_risk`, `failure_mode`, `safety_risk`), `vestas_standard`, `recommended_action`, `repair_timeframe`, `estimated_cost_usd`, `engineer_review_required`, `engineer_review_reason`, `analysis_confidence`, `additional_notes`
- **Error handling:** 3 retries; `anthropic.RateLimitError` triggers 30s sleep; other errors use `2^attempt` backoff; returns `{"error": ...}` on exhausted retries
- **Pipeline entry:** `backend/analyze.py` → `call_claude_analyze()` → called by `analyze_critical_defects()` → called by `run_pipeline()` in `backend/api.py`
- **Image inclusion:** `include_image=True` by default in `analyze_defect()`; silently skips image if file not found
- **Rate limiting:** 3s delay between consecutive defect calls (`delay_between_calls=3.0` in `analyze_critical_defects`)
- **Graceful degradation:** If `ANTHROPIC_API_KEY` not set or no critical findings exist, `analyze.json` is written as empty list; report generates without deep analysis data

---

## Data Storage

**Databases:**
- None — no database used

**File Storage:**
- Local filesystem under `jobs/{job_id}/`:
  - `state.json` — job state and metadata
  - `images/` — uploaded/extracted inspection images
  - `triage.json` — Stage 1 output
  - `classify.json` — Stage 2 output
  - `analyze.json` — Stage 3 output
  - `report_{turbine_id}.pdf` — final PDF output
  - `report_{turbine_id}.html` — HTML intermediate (when `save_html=True`)
- Note: On Render.com free tier, filesystem is ephemeral; no persistent disk configured in `render.yaml`

**Caching:**
- None — no caching layer

## Authentication & Identity

**Auth Provider:** None — no user authentication system
- API is open (CORS `allow_origins=["*"]`)
- API keys for external services stored as environment variables only

## Monitoring & Observability

**Error Tracking:** None

**Logs:**
- Python `print()` statements throughout pipeline modules (verbose mode)
- Job errors captured in `state.json` fields: `stage_message`, `error_traceback`, `failed_at`
- Error traceback exposed via `GET /api/status/{job_id}` response field `error_traceback`

## CI/CD & Deployment

**Hosting:** Render.com (`render.yaml`)
- Service type: `web`
- Service name: `bdda`
- Runtime: `python`
- Build: `pip install -r requirements.txt`
- Start: `cd backend && uvicorn api:app --host 0.0.0.0 --port $PORT`
- Health check: `GET /api/health`

**CI Pipeline:** Not detected

## Environment Configuration

**Required env vars (all three needed for full pipeline):**
- `KIMI_API_KEY` — Moonshot/Kimi vision API key
- `GOOGLE_API_KEY` — Google Gemini API key
- `ANTHROPIC_API_KEY` — Anthropic Claude API key

**Optional env vars:**
- `COMPANY_NAME` — displayed in report header (defaults to `"DroneWind Asia"`)
- `PORT` — server port (defaults to `8000` in CLI mode; set by Render automatically)

**Secrets location:** Environment variables only — set via Render dashboard (`sync: false` in `render.yaml` means they are not committed to source control)

**Key status endpoint:** `GET /api/health` returns `{"status": "ok", "api_keys": {"ANTHROPIC_API_KEY": bool, "GOOGLE_API_KEY": bool, "KIMI_API_KEY": bool}, "jobs_dir": str}`

## Webhooks & Callbacks

**Incoming:** None

**Outgoing:** None — all AI calls are synchronous request/response within a background task thread

---

*Integration audit: 2026-03-03*
