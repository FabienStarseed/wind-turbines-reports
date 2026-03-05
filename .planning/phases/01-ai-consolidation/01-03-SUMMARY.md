---
phase: 01-ai-consolidation
plan: "03"
subsystem: analyze
tags: [anthropic, cost-tracking, error-handling, offshore, retry]
dependency_graph:
  requires: []
  provides: [analyze-cost-tracking, analyze-overloaded-error, analyze-offshore-context]
  affects: [backend/api.py]
tech_stack:
  added: []
  patterns: [exponential-backoff, tuple-return, cost-accumulation]
key_files:
  created: []
  modified:
    - backend/analyze.py
key_decisions:
  - "analyze_critical_defects() now returns (results, total_cost_usd) tuple; api.py caller updated in Plan 04"
  - "Cost formula: input_tokens * $5/1M + output_tokens * $25/1M (claude-opus-4-6 pricing)"
  - "OverloadedError and RateLimitError share same retry path with 10/20/40s backoff"
  - "offshore_note injected inline into ANALYZE_USER_PROMPT when location_type == offshore"
metrics:
  duration: "8 minutes"
  completed: "2026-03-04T13:23:00Z"
  tasks_completed: 1
  tasks_total: 1
  files_modified: 1
---

# Phase 1 Plan 3: Analyze.py Cost Tracking, OverloadedError Handling, and Offshore Context Summary

**One-liner:** Added HTTP 529 OverloadedError retry coverage, per-call token cost tracking with DeepAnalysis.cost_usd, and offshore turbine context injection to the Opus 4.6 engineering analysis prompt.

---

## What Was Built

Updated `backend/analyze.py` with four targeted improvements, all within the existing architecture:

### 1. Retry Loop — Complete Exception Coverage

The existing `call_claude_analyze()` retry loop only caught `anthropic.RateLimitError` (HTTP 429) and fell through without `continue`, meaning it didn't actually retry. Fixed:

- **Added `continue`** after `time.sleep()` in the RateLimitError handler so the loop actually retries
- **Added `anthropic.OverloadedError`** (HTTP 529) to the same except clause with exponential backoff: 10s, 20s, 40s
- **Added `anthropic.APIConnectionError` and `anthropic.APITimeoutError`** to a separate clause with simpler 1s/2s/4s backoff
- Generic `Exception` remains as final fallback

### 2. Cost Tracking

- Added `cost_usd: float = 0.0` field to `DeepAnalysis` dataclass
- `call_claude_analyze()` now attaches `input_tokens` and `output_tokens` from `response.usage` to the parsed response dict
- `analyze_defect()` computes `cost_usd = input_tokens * $5/1M + output_tokens * $25/1M` (claude-opus-4-6 pricing) and assigns to the `DeepAnalysis` object
- Error path sets `cost_usd=0.0`
- `save_analysis_results()` now serializes `cost_usd` per entry

### 3. Tuple Return from analyze_critical_defects()

- Changed return type annotation from `List[DeepAnalysis]` to `Tuple[List[DeepAnalysis], float]`
- Added `total_cost = sum(a.cost_usd for a in results)` at the end
- Returns `(results, total_cost)` — api.py caller will be updated in Plan 04 to unpack
- Added `Tuple` to `from typing import` line

### 4. Offshore Context in Prompt

- Added `{offshore_note}` placeholder to `ANALYZE_USER_PROMPT` (between the visual observation block and the numbered assessment sections)
- Added `location_type: str = "onshore"` parameter to `call_claude_analyze()`
- Sets `offshore_note` to a prominent warning when offshore: "IMPORTANT: This is an OFFSHORE turbine. Repair access is significantly more expensive and difficult. Weight this in repair urgency and timeframe recommendations."
- `analyze_defect()` passes `location_type=defect.get("location_type", "onshore")` through

---

## Verification Results

All verification checks passed:

```
python3 -c "import sys; sys.path.insert(0,'backend'); import analyze; print('OK')"
# OK

grep -n 'OverloadedError' backend/analyze.py
# 199:        except (anthropic.RateLimitError, anthropic.OverloadedError):

grep -n 'claude-opus-4-6' backend/analyze.py
# 176:                model="claude-opus-4-6",

python3 -c "from analyze import DeepAnalysis; assert 'cost_usd' in DeepAnalysis.__dataclass_fields__; print('cost_usd OK')"
# cost_usd OK

grep -n 'usage.input_tokens|usage.output_tokens' backend/analyze.py
# 191:            parsed["input_tokens"] = response.usage.input_tokens
# 192:            parsed["output_tokens"] = response.usage.output_tokens

grep -n 'claude-opus-4-5|claude-3-opus' backend/analyze.py
# (no output — old model names absent)
```

---

## Deviations from Plan

None — plan executed exactly as written.

The plan noted: "Fix retry exception handling in call_claude_analyze() — Current code catches anthropic.RateLimitError with time.sleep(30) but does NOT break out of the loop properly." Confirmed and fixed with `continue` as specified.

---

## Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add OverloadedError, cost tracking, offshore context | dbd8a81 | backend/analyze.py |

---

## Self-Check: PASSED

- [x] `backend/analyze.py` exists and imports cleanly
- [x] Commit `dbd8a81` present in git log
- [x] `OverloadedError` found in analyze.py (line 199)
- [x] `claude-opus-4-6` model string confirmed (line 176)
- [x] `cost_usd` field in DeepAnalysis dataclass
- [x] Token usage extraction from response.usage confirmed (lines 191-192)
- [x] No old model names (`claude-opus-4-5`, `claude-3-opus`) in file
- [x] `analyze_critical_defects()` returns `Tuple[List[DeepAnalysis], float]`
