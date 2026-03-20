---
phase: 01-ai-consolidation
verified: 2026-03-04T00:00:00Z
status: gaps_found
score: 10/13 must-haves verified
re_verification: false
gaps:
  - truth: "Analyze stage uses classify output correctly (iec_category field)"
    status: failed
    reason: "analyze.py accesses defect['category'] at lines 141, 239, 266 but classify.py exports 'iec_category' — KeyError at runtime when analyze stage runs on real pipeline data"
    artifacts:
      - path: "backend/analyze.py"
        issue: "defect['category'] at lines 141, 239, 266 — field does not exist in classify.json output which uses 'iec_category'"
      - path: "backend/classify.py"
        issue: "save_classify_results() and load_critical_findings() output 'iec_category' key, no 'category' key"
    missing:
      - "Replace defect['category'] with defect.get('iec_category', defect.get('category', 0)) in call_claude_analyze() and analyze_defect()"
      - "Or add 'category' alias when building DeepAnalysis objects"
  - truth: "Cost tracking is consistent across all three AI stages"
    status: failed
    reason: "classify.py uses $15/M input and $75/M output tokens while triage.py, analyze.py, and api.py all use $5/M input and $25/M output — 3x pricing discrepancy means classify cost figures are inflated relative to other stages"
    artifacts:
      - path: "backend/classify.py"
        issue: "Lines 69-70: _INPUT_COST_PER_TOKEN = 15.0/1_000_000 and _OUTPUT_COST_PER_TOKEN = 75.0/1_000_000 (should be 5.0 and 25.0 to match triage.py, analyze.py, and api.py)"
    missing:
      - "Align classify.py pricing to $5/M input and $25/M output to match all other modules"
  - truth: "01-01-SUMMARY.md exists (plan output artifact)"
    status: failed
    reason: "Plan 01-01 specified 'After completion, create .planning/phases/01-ai-consolidation/01-01-SUMMARY.md' but this file does not exist"
    artifacts:
      - path: ".planning/phases/01-ai-consolidation/01-01-SUMMARY.md"
        issue: "File missing — not created as required by plan output section"
    missing:
      - "Create 01-01-SUMMARY.md documenting what triage.py plan achieved (same format as 01-02, 01-03, 01-04 summaries)"
---

# Phase 1: AI Consolidation Verification Report

**Phase Goal:** Replace Kimi + Gemini with claude-opus-4-6 for all 3 AI stages. Single Anthropic SDK, single API key. No new features — pure AI stack consolidation.
**Verified:** 2026-03-04
**Status:** gaps_found — 3 gaps found, 1 is a runtime blocker
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | Triage stage calls claude-opus-4-6 via Anthropic SDK | VERIFIED | triage.py: `import anthropic`, `call_claude_triage()` uses `client.messages.create(model="claude-opus-4-6")` |
| 2 | Triage uses 0.3/0.2 confidence thresholds by location_type | VERIFIED | triage.py line 228: `threshold = 0.2 if location_type == "offshore" else 0.3` |
| 3 | Triage images sent as raw base64 (no data URI prefix) | VERIFIED | triage.py: content built with `{"type": "base64", "data": b64}` — no "data:image/" prefix anywhere |
| 4 | Classify stage calls claude-opus-4-6 via Anthropic SDK | VERIFIED | classify.py: `import anthropic`, `call_claude_classify()` uses Anthropic client |
| 5 | Classify uses IEC+BDDA dual scoring | VERIFIED | DefectFinding has `iec_category` and `bdda_score`; `iec_to_bdda()` function exists |
| 6 | Classify images resized to max 1568px before encoding | VERIFIED | classify.py: `load_and_resize_image()` uses `img.thumbnail((1568, 1568), Image.LANCZOS)` |
| 7 | Analyze stage uses claude-opus-4-6 with OverloadedError handling | VERIFIED | analyze.py line 176: model="claude-opus-4-6", line 199: `except (anthropic.RateLimitError, anthropic.OverloadedError)` |
| 8 | analyze_critical_defects() returns (results, cost) tuple | VERIFIED | analyze.py line 294: `-> Tuple[List[DeepAnalysis], float]`, returns `results, total_cost` |
| 9 | analyze.py accesses classify output using correct field key | FAILED | analyze.py uses `defect["category"]` at lines 141, 239, 266 but classify.py exports `iec_category` — KeyError at runtime |
| 10 | Single ANTHROPIC_API_KEY powers all 3 stages in api.py | VERIFIED | api.py: single `anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")` at top of pipeline; RuntimeError if missing |
| 11 | location_type flows end-to-end from upload form through all stages | VERIFIED | api.py: Form field → turbine_meta → triage_batch(location_type=...) → flagged dicts carry location_type |
| 12 | Cost tracking is consistent across all three AI stages | FAILED | classify.py uses $15/M+$75/M; triage.py, analyze.py, api.py all use $5/M+$25/M |
| 13 | requirements.txt contains only anthropic as AI SDK | VERIFIED | requirements.txt: `anthropic>=0.40.0` only — no openai or google-generativeai |

**Score:** 10/13 truths verified

---

## Required Artifacts

### Plan 01-01 (triage.py)

| Artifact | Provides | Status | Details |
|----------|----------|--------|---------|
| `backend/triage.py` | Anthropic-based triage module | VERIFIED | `call_claude_triage()` defined, imports anthropic at module top |
| `backend/triage.py` | `triage_cost_usd` in TriageSummary | VERIFIED | TriageSummary dataclass has `triage_cost_usd: float = 0.0` |

### Plan 01-02 (classify.py)

| Artifact | Provides | Status | Details |
|----------|----------|--------|---------|
| `backend/classify.py` | Anthropic-based classify module | VERIFIED | `call_claude_classify()` defined, imports anthropic |
| `backend/classify.py` | IEC+BDDA dual scoring in DefectFinding | VERIFIED | DefectFinding has `iec_category: int` and `bdda_score: int`; `category` field removed |
| `backend/classify.py` | Image resize utility | VERIFIED | `load_and_resize_image()` with `thumbnail((1568, 1568))` |

### Plan 01-03 (analyze.py)

| Artifact | Provides | Status | Details |
|----------|----------|--------|---------|
| `backend/analyze.py` | OverloadedError handling | VERIFIED | Line 199: `except (anthropic.RateLimitError, anthropic.OverloadedError)` |
| `backend/analyze.py` | `analyze_cost_usd` in return | VERIFIED | `analyze_critical_defects()` returns `(results, total_cost)` tuple |

### Plan 01-04 (api.py, requirements.txt)

| Artifact | Provides | Status | Details |
|----------|----------|--------|---------|
| `backend/api.py` | ANTHROPIC_API_KEY only orchestration | VERIFIED | `ANTHROPIC_API_KEY` only; RuntimeError if missing |
| `backend/api.py` | `/api/estimate` endpoint | VERIFIED | Line 313: `@app.post("/api/estimate")` |
| `backend/api.py` | `/api/debug/ai` endpoint | VERIFIED | Line 441: `@app.get("/api/debug/ai")` |
| `requirements.txt` | Clean dependency list | VERIFIED | Only `anthropic>=0.40.0` for AI — no openai or google-generativeai |

### Missing Artifact

| Artifact | Status | Details |
|----------|--------|---------|
| `.planning/phases/01-ai-consolidation/01-01-SUMMARY.md` | MISSING | Plan specified creation of this file; 01-02, 01-03, 01-04 summaries all exist |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `triage.py call_claude_triage()` | `anthropic.Anthropic().messages.create()` | Anthropic SDK | WIRED | `client.messages.create(model=model, ...)` at line 143 |
| `triage.py triage_batch()` | `location_type` threshold selection | 0.2/0.3 selection | WIRED | `threshold = 0.2 if location_type == "offshore" else 0.3` at line 228 |
| `classify.py call_claude_classify()` | `anthropic.Anthropic().messages.create()` | Anthropic SDK | WIRED | `client.messages.create(model=model, ...)` at line 190 |
| `classify.py` | `Image.thumbnail((1568, 1568))` | Pillow resize | WIRED | `load_and_resize_image()` line 88: `img.thumbnail((max_edge, max_edge), Image.LANCZOS)` |
| `classify.py DefectFinding` | `iec_category, bdda_score` fields | dual scoring schema | WIRED | Lines 100-101: fields declared; line 383: serialized to JSON |
| `analyze.py call_claude_analyze()` | `anthropic.OverloadedError` | retry catch clause | WIRED | Line 199: in except clause with RateLimitError |
| `analyze.py` | `response.usage.input_tokens` | cost accumulation | WIRED | Lines 191-192: `parsed["input_tokens"] = response.usage.input_tokens` |
| `analyze.py call_claude_analyze()` | `defect["category"]` | classify output key | NOT_WIRED | classify.py exports `iec_category`; `category` key does not exist in classify JSON — KeyError at runtime |
| `api.py run_pipeline()` | `triage_batch(location_type=...)` | location_type threaded | WIRED | Line 183: `location_type=turbine_meta.get("location_type", "onshore")` |
| `api.py run_pipeline()` | `state.json cost fields` | update_job calls | WIRED | Lines 193, 219, 241, 272: all four cost fields logged |
| `api.py /api/estimate` | `estimate_cost()` function | GET endpoint | WIRED | Lines 313-318: endpoint calls `estimate_cost(image_count)` |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| AI-01 | 01-01 | Triage stage uses claude-opus-4-6 vision (replaces Kimi) | SATISFIED | triage.py: `call_claude_triage()` using Anthropic SDK, model=claude-opus-4-6, no openai/moonshot references |
| AI-02 | 01-02 | Classify stage uses claude-opus-4-6 vision (replaces Gemini) | SATISFIED | classify.py: `call_claude_classify()` using Anthropic SDK, model=claude-opus-4-6, no google/genai references |
| AI-03 | 01-03 | Analyze stage upgraded to claude-opus-4-6 | SATISFIED | analyze.py line 176: model="claude-opus-4-6", OverloadedError handled |
| AI-04 | 01-04 | Single ANTHROPIC_API_KEY powers all 3 stages | SATISFIED | api.py: single key declaration, RuntimeError if missing, no legacy key reads |
| AI-05 | 01-01, 01-02, 01-03, 01-04 | Cost-per-turbine measured and logged per job | PARTIAL | triage_cost_usd, analyze_cost_usd, total_cost_usd logged correctly; classify cost uses wrong pricing ($15/M vs $5/M) making classify_cost_usd values inconsistent with other stages |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/analyze.py` | 141, 239, 266 | `defect["category"]` — key absent in classify output | Blocker | analyze stage will crash with KeyError when pipeline runs with real data from classify stage |
| `backend/classify.py` | 69-70 | Pricing constants $15/M+$75/M vs $5/M+$25/M in all other files | Warning | classify cost figures are 3x inflated relative to triage and analyze; total_cost_usd in state.json will be inaccurate |
| `.planning/phases/01-ai-consolidation/` | — | 01-01-SUMMARY.md missing | Info | Documentation gap; does not affect runtime behavior |

---

## Blocker Detail: analyze.py KeyError on `defect["category"]`

This is the most critical finding. The pipeline stage sequence is:

```
classify.py save_classify_results() → classify.json
                 ↓ field: "iec_category"
classify.py load_critical_findings() → List[Dict]
                 ↓ each dict has "iec_category" key, NO "category" key
analyze.py call_claude_analyze() → defect["category"]
                 ↑ KeyError HERE — field does not exist
```

The old classify.py exported `"category"`. The new classify.py exports `"iec_category"`. The plan for 01-02 correctly updated the DefectFinding dataclass and save/load functions. The plan for 01-03 did NOT update analyze.py to use `iec_category` — it was out of scope for that plan which focused on OverloadedError and cost tracking. The plan for 01-04 did not catch this either.

**Consequence:** Any real pipeline run that reaches the analyze stage will raise `KeyError: 'category'` in `call_claude_analyze()` at line 141, causing the job to enter error state. The analyze_cost_usd will be 0.0 for all jobs.

**Fix required:** In `analyze.py`, replace `defect["category"]` with `defect.get("iec_category", defect.get("category", 0))` at all three locations (lines 141, 239, 266). This is backward-compatible with any existing classify.json files that may have been generated before this phase.

---

## Human Verification Required

### 1. End-to-end pipeline smoke test

**Test:** Upload a small ZIP of DJI inspection images with ANTHROPIC_API_KEY set. Monitor to "complete" stage.
**Expected:** Pipeline completes, all four cost fields populated in state.json, PDF generated.
**Why human:** Integration of 4 stages with real API calls cannot be verified programmatically without a running server and live API key.

### 2. Offshore vs onshore threshold behavior

**Test:** Upload identical images twice — once with `location_type=offshore`, once with `location_type=onshore`. Compare number of flagged images.
**Expected:** Offshore run should flag more images (0.2 threshold vs 0.3).
**Why human:** Requires real API calls to observe threshold difference in practice.

---

## Gaps Summary

Three gaps found:

**Gap 1 (Blocker):** `analyze.py` will crash at runtime with `KeyError: 'category'` because the classify stage now saves `iec_category` but analyze.py still reads `defect["category"]`. This was a field rename left incomplete — the classify schema was migrated in plan 01-02 but analyze.py was not updated to match in plan 01-03. Every real pipeline run that has critical findings will fail at the analyze stage.

**Gap 2 (Warning):** classify.py uses different pricing constants ($15/M input, $75/M output) compared to triage.py, analyze.py, and api.py (all use $5/M input, $25/M output). The classify summary explicitly documents these as the "correct" classify pricing, but no plan rationale explains the 3x difference. The effect is that `classify_cost_usd` values in state.json will be ~3x higher than actual cost per the other modules' formula, making `total_cost_usd` inaccurate.

**Gap 3 (Info):** `01-01-SUMMARY.md` was never created. All other plans produced their required summary files (01-02, 01-03, 01-04). This is a documentation-only gap with no runtime impact.

---

_Verified: 2026-03-04_
_Verifier: Claude (gsd-verifier)_
