---
phase: 01-ai-consolidation
plan: "04"
subsystem: api
tags: [anthropic, cost-tracking, guardrails, location-type, image-cap, estimate, api-cleanup]
dependency_graph:
  requires: [01-01, 01-02, 01-03]
  provides: [anthropic-only-pipeline, cost-visibility, location-type-flow, image-cap-500]
  affects: [backend/api.py, requirements.txt]
tech_stack:
  added: []
  patterns: [cost-estimation, pipeline-guardrails, per-stage-cost-accumulation]
key_files:
  created: []
  modified:
    - backend/api.py
    - requirements.txt
key_decisions:
  - "Single ANTHROPIC_API_KEY replaces KIMI_API_KEY + GOOGLE_API_KEY — pipeline fails fast if key missing"
  - "estimate_cost() uses conservative 30% flag rate and 20% critical rate to pre-estimate cost"
  - "IMAGE_CAP=500 applied before triage; image_cap_warning logged to state.json when triggered"
  - "COST_LIMIT_USD checked after triage and after classify — terminates gracefully with error stage"
  - "analyze_critical_defects() tuple return (results, total_cost) unpacked in run_pipeline()"
metrics:
  duration: "~56 minutes"
  completed: "2026-03-05T07:10:00Z"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 2
---

# Phase 1 Plan 04: API Orchestration — Anthropic-Only Pipeline with Cost Guardrails Summary

**One-liner:** Rewired api.py to orchestrate all three AI stages (triage, classify, analyze) under a single ANTHROPIC_API_KEY with 500-image cap, COST_LIMIT_USD guardrail, /api/estimate endpoint, per-stage cost logging to state.json, and removed openai + google-generativeai from requirements.txt.

---

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Update api.py — form field, pipeline wiring, cost tracking, guardrails | 161b895 | backend/api.py |
| 2 | Clean up requirements.txt — remove openai and google-generativeai | 9d04bc7 | requirements.txt |

---

## What Was Built

### Anthropic-Only Pipeline Wiring

Replaced the three conditional blocks in `run_pipeline()` that checked for `KIMI_API_KEY`, `GOOGLE_API_KEY`, and `ANTHROPIC_API_KEY` separately with a single unified authentication block:

- `anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")` declared once at the top of Stage 2
- `RuntimeError` raised immediately if key is missing (no fallback to dummy data)
- All three stages (`triage_batch`, `classify_batch`, `analyze_critical_defects`) receive `anthropic_key`

### estimate_cost() Function

New module-level function with conservative pre-run cost estimate:
- `INPUT_PRICE = $5/M tokens`, `OUTPUT_PRICE = $25/M tokens` (claude-opus-4-6 pricing)
- Assumes 30% flag rate (triage → classify), 20% critical rate (classify → analyze)
- Returns breakdown by stage (triage_usd, classify_usd, analyze_usd) plus total estimated_cost_usd
- Example: 100 images → `$4.15`, 200 images → `$8.31`

### POST /api/estimate Endpoint

New endpoint for pre-run cost visibility:
- Accepts `image_count` as form field
- Caps image count at 500 to match pipeline cap
- Returns the same dict as `estimate_cost()`

### location_type Form Field

- Added `location_type: Optional[str] = Form(None)` to `/api/upload` signature
- Validated to `"onshore"` or `"offshore"` before storing in `turbine_meta`
- Defaults to `"onshore"` if not provided or invalid
- Flows through `turbine_meta` to `triage_batch(location_type=...)` which selects the confidence threshold (0.3 onshore / 0.2 offshore)
- Also attached to each flagged image dict for downstream classify/analyze stages

### 500-Image Cap

- `IMAGE_CAP = 500` applied after `get_all_images_flat()` before triage begins
- When triggered: `images = images[:500]`, `image_cap_warning` logged to state.json
- Warning format: `"Capped at 500 images. {N} images skipped."`
- `image_cap_warning` exposed in `/api/status/{job_id}` response

### COST_LIMIT_USD Guardrail

- `cost_limit_usd = float(os.environ.get("COST_LIMIT_USD", "999999"))` — defaults to effectively unlimited
- `running_cost` accumulated as each stage completes
- Checked after triage and after classify; if exceeded, sets stage to `"error"` with descriptive message and returns early
- No check after analyze (final stage before report)

### Per-Stage Cost Logging

`update_job()` calls added at each AI stage completion:
- `triage_cost_usd` from `summary.triage_cost_usd`
- `classify_cost_usd` from `sum(r.cost_usd for r in classify_results)`
- `analyze_cost_usd` from tuple return of `analyze_critical_defects()`
- `total_cost_usd = round(running_cost, 4)` in final completion update

All four cost fields exposed in `/api/status/{job_id}` response.

### /api/debug/ai Endpoint

Replaced `/api/debug/kimi` (which used openai SDK + moonshot-v1 model) with `/api/debug/ai`:
- Creates a 64x64 solid grey test JPEG in memory
- Calls `claude-opus-4-6` with the image via Anthropic SDK
- Returns `model`, `input_tokens`, `output_tokens`, `raw_response`, `parse_ok`, `parsed`
- Returns `{"error": "ANTHROPIC_API_KEY not set"}` if key missing

### /api/health Update

Removed `GOOGLE_API_KEY` and `KIMI_API_KEY` from the health check keys dict. Now reports:
- `ANTHROPIC_API_KEY: bool` — whether the key is set
- `COST_LIMIT_USD: str` — the configured limit or `"not set"`

### /api/upload Response Update

Upload response now includes a cost estimate computed before starting the pipeline:
```json
{
  "job_id": "...",
  "image_count": 150,
  "message": "Pipeline started",
  "cost_estimate": { "estimated_cost_usd": 6.22, ... }
}
```

### requirements.txt Cleanup

Removed two deprecated AI dependencies:
- `google-generativeai>=0.8.0` (Gemini — replaced by Plan 01-02)
- `openai>=1.50.0` (Kimi API — replaced by Plan 01-01)

`anthropic>=0.40.0` remains as the sole AI SDK dependency. No new packages added.

---

## Deviations from Plan

None — plan executed exactly as written.

---

## Verification Results

All verification checks passed:

```
python3 -c "import sys; sys.path.insert(0,'backend'); import api; print('OK')"
# OK

grep -n 'KIMI_API_KEY|GOOGLE_API_KEY|kimi_key|google_key|moonshot|openai|debug/kimi' backend/api.py
# (no output — all legacy references removed)

grep -n 'ANTHROPIC_API_KEY|anthropic_key|estimate_cost|debug/ai|triage_cost_usd|total_cost_usd|location_type|COST_LIMIT_USD' backend/api.py
# Multiple hits confirmed

grep -n 'api/estimate|api/debug/ai' backend/api.py
# 313: @app.post("/api/estimate")
# 441: @app.get("/api/debug/ai")

python3 -c "from api import estimate_cost; r = estimate_cost(100); assert 'estimated_cost_usd' in r; print('estimate_cost OK:', r['estimated_cost_usd'])"
# estimate_cost OK: 4.15

grep -n 'openai|google-generativeai' requirements.txt
# (no output — deprecated packages removed)

grep -n 'anthropic' requirements.txt
# 10: anthropic>=0.40.0
```

---

## Self-Check

Verified:

- [x] `backend/api.py` exists and imports cleanly (python3 import OK)
- [x] Commit `161b895` present in git log (Task 1)
- [x] Commit `9d04bc7` present in git log (Task 2)
- [x] No `KIMI_API_KEY`, `GOOGLE_API_KEY`, `moonshot`, `kimi_key`, `google_key`, `openai`, `debug/kimi` in api.py
- [x] `estimate_cost()` function defined and works — returns dict with `estimated_cost_usd`
- [x] `POST /api/estimate` endpoint present (line 313)
- [x] `GET /api/debug/ai` endpoint present (line 441)
- [x] `location_type` form field added to upload signature and turbine_meta
- [x] `IMAGE_CAP = 500` and `image_cap_warning` in run_pipeline()
- [x] `COST_LIMIT_USD` guardrail present with two check points
- [x] `triage_cost_usd`, `classify_cost_usd`, `analyze_cost_usd`, `total_cost_usd` logged to state.json
- [x] All four cost fields exposed in /api/status/{job_id} response
- [x] `google-generativeai` removed from requirements.txt
- [x] `openai` removed from requirements.txt
- [x] `anthropic>=0.40.0` remains in requirements.txt

## Self-Check: PASSED
