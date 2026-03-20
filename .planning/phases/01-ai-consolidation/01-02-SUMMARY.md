---
phase: 01-ai-consolidation
plan: 02
subsystem: classify
tags: [anthropic, claude-opus-4-6, iec-61400, bdda-scoring, image-resize, cost-tracking]
dependency-graph:
  requires: []
  provides: [classify-anthropic-sdk, iec-bdda-dual-scoring, classify-cost-tracking]
  affects: [backend/api.py, backend/analyze.py]
tech-stack:
  added: [anthropic SDK for classify stage, Pillow image resize pipeline]
  patterns: [IEC Cat 0-4 + BDDA 0-10 dual scoring, thumbnail resize before base64 encode]
key-files:
  modified: [backend/classify.py]
decisions:
  - "bdda_score always derived from iec_to_bdda() on client side — API response bdda_score ignored for consistency"
  - "json_parse_fail treated as empty defects result (do not retry) — safer than flagging false positives"
  - "classify_batch() accumulates cost in ClassifyResult.cost_usd, return type unchanged (Option B)"
  - "has_critical threshold changed from category >= 4 (Vestas 1-5) to iec_category >= 3 (IEC Cat 3 = Planned repair)"
metrics:
  duration: "~4 minutes"
  completed: "2026-03-04"
  tasks: 2
  files: 1
---

# Phase 1 Plan 02: Classify Stage — Anthropic SDK Migration Summary

Rewrote `backend/classify.py` from google-generativeai/Gemini to Anthropic SDK with claude-opus-4-6, implementing IEC 61400 + BDDA dual scoring, image resizing for the 1568px Anthropic limit, and per-call cost tracking.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Update DefectFinding dataclass and add image resize utility | b8ea77a | backend/classify.py |
| 2 | Replace call_gemini_classify() with call_claude_classify() and update prompts | 23a293c | backend/classify.py |

## What Was Built

### DefectFinding Dataclass (IEC + BDDA Dual Scoring)

Replaced the old Vestas 1-5 `category: int` field with two fields aligned to international standards:
- `iec_category: int` — IEC 61400 severity scale 0-4 (0=No action, 1=Log, 2=Monitor, 3=Planned repair, 4=Urgent)
- `bdda_score: int` — BDDA custom 0-10 score derived from IEC category via midpoint mapping

Added `iec_to_bdda()` mapping function: `{0:0, 1:1, 2:3, 3:6, 4:9}`

### Image Resize Utility

Added `load_and_resize_image()` using Pillow `thumbnail()` to resize to max 1568px longest edge before JPEG encoding. Returns raw base64 (no data URI prefix). This is the Anthropic-documented threshold where downscaling preserves full model performance.

### Anthropic API Client

New `call_claude_classify()`:
- Creates `anthropic.Anthropic(api_key=...)` client per call
- Encodes image as `{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": ...}}`
- Retry loop with typed exception handling: `RateLimitError` (10x exponential backoff), `APIStatusError` (retry 5xx, raise 4xx), `APIConnectionError`/`APITimeoutError` (exponential backoff)
- JSON parse failures return `{"error": "json_parse_fail", "defects": []}` — no retry, treated as no defects
- Returns token usage in result dict (`input_tokens`, `output_tokens`)

### Cost Tracking

- `ClassifyResult.cost_usd: float` accumulates per-call cost from token usage
- Pricing constants: `$15/M input`, `$75/M output` (claude-opus-4-6)
- `classify_batch()` logs total cost in verbose mode
- `save_classify_results()` persists `cost_usd` per image to JSON
- Return type of `classify_batch()` unchanged (Option B — no caller breakage)

### Updated Prompts

- New `CLASSIFY_SYSTEM_PROMPT` references IEC 61400-1, DNVGL-ST-0376, DJI P1 45MP imagery
- New `CLASSIFY_USER_PROMPT` includes `location_type` context variable, outputs `iec_category` + `bdda_score` fields

### Downstream Updates

- `load_critical_findings()` now filters on `iec_category` (was `category`)
- `save_classify_results()` serializes `iec_category` and `bdda_score` (drops `category`)
- `classify_batch()` verbose output shows IEC Cat + BDDA score per defect

## Deviations from Plan

None — plan executed exactly as written.

## Decisions Made

1. **bdda_score derived client-side always** — API response bdda_score field is ignored. `iec_to_bdda(iec_category)` always called in `classify_image()` for consistency. This prevents drift if the model returns a non-standard bdda_score.

2. **json_parse_fail not retried** — Per plan spec. JSON parse failures are ambiguous — the model may have returned partial output. Treating as empty defects is safer than flagging potentially wrong defects.

3. **Option B for classify_batch cost** — Cost accumulated in `ClassifyResult.cost_usd` fields. `classify_batch()` return type stays `List[ClassifyResult]`. Callers in `api.py` can sum `r.cost_usd for r in results` without a breaking change.

4. **has_critical threshold: iec_category >= 3** — IEC Cat 3 = "Planned repair within 3 months". This is equivalent to the previous Vestas Cat 4 threshold conceptually (both represent urgent-but-not-immediate action required). The old Vestas 1-5 scale mapped 4→urgent, the IEC 0-4 scale maps 3→planned/urgent.

## Self-Check

Verified:
- `backend/classify.py` exists and imports cleanly
- `DefectFinding.__dataclass_fields__` contains `iec_category` and `bdda_score`, does not contain `category`
- `iec_to_bdda(4)` returns `9`
- `iec_to_bdda(0)` returns `0`
- `ClassifyResult.__dataclass_fields__` contains `cost_usd`
- No `google`, `genai`, `GOOGLE_API_KEY`, or `gemini` references in classify.py
- `claude-opus-4-6` model string present
- `call_claude_classify` defined
- No `data:image` prefix in image encoding
- `thumbnail` and `1568` present in `load_and_resize_image`

## Self-Check: PASSED
