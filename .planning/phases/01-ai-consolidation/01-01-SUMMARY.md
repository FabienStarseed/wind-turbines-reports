---
phase: 01-ai-consolidation
plan: "01"
subsystem: triage
tags: [anthropic, claude-opus-4-6, triage, cost-tracking, error-handling, offshore]
dependency_graph:
  requires: []
  provides: [triage-anthropic-sdk, location-based-thresholds, triage-cost-tracking, errors-json-logging]
  affects: [backend/api.py]
tech_stack:
  added: [anthropic SDK for triage stage]
  patterns: [4-tile triage, 0.3/0.2 onshore/offshore threshold, per-image retry, errors.json append]
key_files:
  created: []
  modified:
    - backend/triage.py
key_decisions:
  - "4 tiles per image (reduced from 8) — balances recall vs cost for Opus 4.6"
  - "0.3 threshold onshore, 0.2 threshold offshore — offshore repairs more expensive so stricter screening"
  - "API down fallback: has_defect=True — conservative, never miss a defect due to API failure"
  - "JSON parse failure: has_defect=True without retry — ambiguous output treated as potential defect"
  - "Per-image retry: one retry on error, then log to errors.json and continue"
metrics:
  duration: "~45 minutes"
  completed: "2026-03-04"
  tasks_completed: 1
  tasks_total: 1
  files_modified: 1
---

# Phase 1 Plan 01: Triage Stage — Anthropic SDK Migration Summary

**One-liner:** Full rewrite of `backend/triage.py` from Kimi/OpenAI client to Anthropic SDK with claude-opus-4-6, implementing 4-tile triage, location-based confidence thresholds, per-image retry, errors.json logging, and cost accumulation.

---

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Replace call_kimi_triage() with call_claude_triage() using Anthropic SDK | a5b8644 | backend/triage.py |

---

## What Was Built

### Anthropic SDK Client

New `call_claude_triage()`:
- Creates `anthropic.Anthropic(api_key=...)` client
- Builds content list with 4 base64 tile images — raw base64, no `data:image/...` URI prefix
- Calls `client.messages.create(model="claude-opus-4-6", max_tokens=300, system=..., messages=[...])`
- Returns token usage (`input_tokens`, `output_tokens`) for cost accumulation

### Location-Based Thresholds

- `location_type="offshore"` → `threshold = 0.2` (stricter — offshore repairs are significantly more expensive)
- `location_type="onshore"` → `threshold = 0.3`
- Threshold applied in `triage_image()`, derived from `location_type` (not passed as parameter)

### Retry Logic

- `RateLimitError` / `OverloadedError`: exponential backoff 10s/20s/40s, max 3 retries, fallback `has_defect=True`
- `APIConnectionError` / `APITimeoutError`: backoff 1s/2s/4s, fallback `has_defect=True`
- `APIStatusError >= 500`: retry as transient; `4xx`: raise immediately (bad key, no point retrying)
- `json.JSONDecodeError`: return `has_defect=True` immediately, no retry

### Per-Image Retry in triage_batch()

- First error on an image: retry once
- Second error: log to `errors.json` in job_dir and continue (do not fail job)
- `errors.json` format: `[{"timestamp": ..., "stage": "triage", "image_path": ..., "error": ..., "attempt": ...}]`

### Cost Tracking

- `TriageResult.cost_usd: float` — cost per image from token usage
- `TriageSummary.triage_cost_usd: float` — total batch cost
- Pricing: `$5/M input + $25/M output` (claude-opus-4-6)

### Prompts

- `TRIAGE_SYSTEM_PROMPT`: senior drone inspection specialist, recall-optimized screening, DJI P1 45MP tiles at 1092×1092px
- `TRIAGE_USER_PROMPT`: includes turbine context + offshore warning flag when applicable

---

## Verification

- `grep -n 'openai\|moonshot\|KIMI' backend/triage.py` → empty
- `grep -n 'claude-opus-4-6' backend/triage.py` → multiple hits
- `grep -n 'data:image' backend/triage.py` → empty (no URI prefix)
- `TriageResult.__dataclass_fields__` contains `cost_usd`
- `TriageSummary.__dataclass_fields__` contains `triage_cost_usd`
- Module imports cleanly: `python3 -c "import triage; print('OK')"`

## Self-Check: PASSED
