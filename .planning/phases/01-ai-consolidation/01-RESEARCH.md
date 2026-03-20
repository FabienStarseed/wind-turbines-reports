# Phase 1: AI Consolidation - Research

**Researched:** 2026-03-04
**Domain:** Anthropic Python SDK — vision, error handling, token cost tracking
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Error Handling**
- Per-image errors: Retry once automatically. If retry fails, skip the image and log (image path + error details) to a persistent `errors.json` per job. Do NOT fail the whole job for individual image errors.
- API down / rate-limited: Retry up to 3 times with exponential backoff. If all 3 retries fail, fall back to flagging all remaining images as `has_defect=true` (conservative).
- JSON parse failure: Treat as `has_defect=true` (safe side). Do not retry on parse failure.
- Error visibility: Show error count and failed image list in the final PDF report.
- Error log file: Save `errors.json` per job in the job directory.

**Cost Guardrails**
- Image cap: Maximum 500 images per job. Excess images skipped with warning in report.
- Cost estimate before running: Show inspector estimated cost before pipeline starts. Inspector can cancel before confirming.
- Hard cost limit: Configurable via `COST_LIMIT_USD` env var. Pipeline stops and job fails gracefully if limit exceeded mid-run.
- Tile count: Reduce from 8 tiles to **4 tiles per image** for triage.
- Cost logging: Log actual API cost per stage (triage, classify, analyze) and total to `state.json` after each job.

**Triage Sensitivity**
- Bias: Favour recall over precision.
- Confidence threshold: `0.3+` onshore, `0.2+` offshore.
- `location_type` field will carry onshore/offshore in turbine metadata.

**Prompt Strategy**
- Full rewrite for Opus 4.6 — do not adapt Kimi/Gemini prompts.
- Full context every API call: turbine ID, blade, zone, position, inspection date, turbine model, offshore flag.
- Reasoning: for confidence >= 0.7 include one sentence of reasoning alongside JSON.
- Classification standard: output both IEC Cat 0-4 AND custom BDDA 0-10 score. Map: Cat 0=0, Cat 1=1-2, Cat 2=3-4, Cat 3=5-7, Cat 4=8-10.

### Claude's Discretion
- Optimal prompt wording and structure for each stage (triage, classify, analyze).
- `location_type` field implementation detail (form field vs GPS inference).
- Exact backoff timing for retry logic.
- Cost estimation formula (tokens x pricing calculation).

### Deferred Ideas (OUT OF SCOPE)
- Error notification emails (requires Auth from Phase 3).
- Automatic model improvement from error logs (future milestone).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AI-01 | Triage stage uses `claude-opus-4-6` vision (replaces Kimi) | SDK vision call pattern confirmed; OpenAI→Anthropic migration mapped in detail |
| AI-02 | Classify stage uses `claude-opus-4-6` vision (replaces Google Gemini) | google-generativeai→Anthropic migration mapped; full-image base64 pattern confirmed |
| AI-03 | Analyze stage upgraded to `claude-opus-4-6` (was claude-opus-4-5) | Pattern already in analyze.py; only model string change needed |
| AI-04 | Single `ANTHROPIC_API_KEY` powers all 3 stages | SDK key wiring documented; env var removals listed |
| AI-05 | Cost-per-turbine measured and logged per job | `response.usage.input_tokens` + `output_tokens` confirmed; pricing formula derived |
</phase_requirements>

---

## Summary

Phase 1 replaces two foreign AI clients (OpenAI-compatible Kimi for triage, google-generativeai for classify) with the Anthropic Python SDK and `claude-opus-4-6` for all three pipeline stages. The analyze stage already uses `claude-opus-4-6` correctly; the SDK call pattern in `analyze.py` is the exact template for triage and classify rewrites.

The Anthropic SDK's vision API is simple and well-documented: images go into the content list as `{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64string}}` blocks alongside text blocks. Multiple tiles are passed as multiple image blocks in a single call — matching how triage currently works with Kimi. The response object exposes `response.usage.input_tokens` and `response.usage.output_tokens` for exact cost tracking.

Cost math for claude-opus-4-6: $5/MTok input, $25/MTok output. At 4 tiles per image (each tile ~1092x1092px ≈ 1590 tokens), triage costs ~$0.0318/image for input alone. A 500-image job costs roughly $16-20 total for all three stages, varying by defect rate. Pre-run cost estimate uses `image_count × 4 tiles × ~1600 tokens/tile × $0.000005/token` for triage input, plus fixed estimate for classify and analyze stages.

**Primary recommendation:** Use `analyze.py`'s `call_claude_analyze()` as the exact template for new `call_claude_triage()` and `call_claude_classify()` functions. Change the imports, remove the old clients, add `location_type` to turbine_meta, wire the single `ANTHROPIC_API_KEY`, and implement the cost tracker as a simple running accumulator.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `anthropic` | >=0.40.0 (already in requirements.txt) | All 3 AI stages | Single vendor, already used in analyze.py |
| `fastapi` | 0.115.5 | Web framework | Already in use, no change |
| `Pillow` | >=10.0.0 | Image tiling (via tile.py) | Already in use |

### To Remove
| Library | Currently Used In | Reason for Removal |
|---------|------------------|--------------------|
| `openai` | triage.py (Kimi via OpenAI-compat) | Replaced by anthropic SDK |
| `google-generativeai` | classify.py | Replaced by anthropic SDK |

### Requirements Changes
```bash
# Remove from requirements.txt:
# openai>=1.50.0
# google-generativeai>=0.8.0

# Keep (already present):
# anthropic>=0.40.0
```

---

## Architecture Patterns

### Verified SDK Call Pattern (from analyze.py — HIGH confidence)
```python
# Source: analyze.py (existing, working code)
import anthropic

client = anthropic.Anthropic(api_key=api_key)

# Build content list: images first, then text
content = []
content.append({
    "type": "image",
    "source": {
        "type": "base64",
        "media_type": "image/jpeg",
        "data": image_b64,  # base64-encoded string, no data URI prefix
    },
})
content.append({"type": "text", "text": prompt})

response = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=1500,
    system=SYSTEM_PROMPT,
    messages=[{"role": "user", "content": content}],
)
raw = response.content[0].text.strip()
```

### Multiple Images (Triage Tiles) — Verified Pattern
```python
# Source: official Anthropic vision docs (platform.claude.com/docs/en/build-with-claude/vision)
# Pass 4 tiles as 4 image blocks in a single call
content = []
for b64 in tiles_b64:  # list of 4 base64 strings
    content.append({
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": b64,
        },
    })
content.append({"type": "text", "text": triage_prompt})
```

### Token Usage from Response (HIGH confidence)
```python
# Source: Anthropic SDK GitHub + official docs
response = client.messages.create(...)
input_tokens  = response.usage.input_tokens
output_tokens = response.usage.output_tokens
```

### Cost Calculation Formula (HIGH confidence)
```python
# Source: Anthropic pricing page (platform.claude.com/docs/en/about-claude/pricing)
# claude-opus-4-6: $5/MTok input, $25/MTok output

INPUT_PRICE_PER_TOKEN  = 5.0 / 1_000_000   # $0.000005
OUTPUT_PRICE_PER_TOKEN = 25.0 / 1_000_000  # $0.000025

def tokens_to_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * INPUT_PRICE_PER_TOKEN) + (output_tokens * OUTPUT_PRICE_PER_TOKEN)
```

### Pre-Run Cost Estimate Formula
```python
# Conservative estimate before pipeline runs
# Tile size target: 1092x1092px -> ~1590 tokens per tile (per official Anthropic table)
# 4 tiles per image for triage
TOKENS_PER_TILE = 1600
TILES_PER_IMAGE = 4
TRIAGE_OUTPUT_TOKENS_EST = 80   # small JSON response
CLASSIFY_INPUT_TOKENS_EST = 1600  # 1 full image
CLASSIFY_OUTPUT_TOKENS_EST = 500
ANALYZE_INPUT_TOKENS_EST = 1600
ANALYZE_OUTPUT_TOKENS_EST = 600

# Assume 30% of images flagged by triage, 20% have Cat4+ findings
def estimate_cost(image_count: int) -> dict:
    triage_input = image_count * TILES_PER_IMAGE * TOKENS_PER_TILE
    triage_output = image_count * TRIAGE_OUTPUT_TOKENS_EST
    flagged_est = int(image_count * 0.30)
    classify_input = flagged_est * CLASSIFY_INPUT_TOKENS_EST
    classify_output = flagged_est * CLASSIFY_OUTPUT_TOKENS_EST
    critical_est = int(flagged_est * 0.20)
    analyze_input = critical_est * ANALYZE_INPUT_TOKENS_EST
    analyze_output = critical_est * ANALYZE_OUTPUT_TOKENS_EST

    total_input = triage_input + classify_input + analyze_input
    total_output = triage_output + classify_output + analyze_output
    total_cost = tokens_to_cost(total_input, total_output)
    return {
        "estimated_cost_usd": round(total_cost, 2),
        "image_count": image_count,
        "flagged_estimate": flagged_est,
    }
```

### Anthropic Exception Hierarchy (HIGH confidence)
```python
# Source: anthropic-sdk-python/_exceptions.py (verified)
import anthropic

# Catch for retry logic:
try:
    response = client.messages.create(...)
except anthropic.RateLimitError:        # HTTP 429 — back off, retry
    time.sleep(backoff)
except anthropic.APIConnectionError:    # Network failure — retry
    time.sleep(backoff)
except anthropic.APITimeoutError:       # Timeout — retry
    time.sleep(backoff)
except anthropic.OverloadedError:       # HTTP 529 (Anthropic-specific) — retry
    time.sleep(backoff)
except anthropic.APIStatusError as e:   # Other 4xx/5xx — check e.status_code
    if e.status_code >= 500:
        time.sleep(backoff)             # Server errors — retry
    else:
        raise                           # Client errors (400, 401, 403) — don't retry
except json.JSONDecodeError:
    # Per decision: treat as has_defect=True, do NOT retry
    return {"has_defect": True, "confidence": 1.0, "error": "json_parse_fail"}
```

### Exponential Backoff Pattern
```python
# From analyze.py pattern, extended for 3-retry policy with jitter
import time

MAX_RETRIES = 3

for attempt in range(MAX_RETRIES):
    try:
        # ... API call ...
        break
    except (anthropic.RateLimitError, anthropic.OverloadedError):
        if attempt == MAX_RETRIES - 1:
            # All retries exhausted — flag remaining as has_defect=True
            return fallback_result
        sleep_time = (2 ** attempt) * 10  # 10s, 20s, 40s
        time.sleep(sleep_time)
    except (anthropic.APIConnectionError, anthropic.APITimeoutError):
        if attempt == MAX_RETRIES - 1:
            return fallback_result
        time.sleep(2 ** attempt)  # 1s, 2s, 4s
```

---

## Migration Map: Old Clients to Anthropic SDK

### triage.py Migration

**What changes:**
- Remove: `from openai import OpenAI` and `OpenAI(api_key=..., base_url="https://api.moonshot.ai/v1")`
- Remove: OpenAI content format (`{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}`)
- Add: `import anthropic` and `anthropic.Anthropic(api_key=...)`
- Add: Anthropic content format (`{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}}`)
- Change: `client.chat.completions.create(model="moonshot-v1-8k-vision-preview", messages=[...])` → `client.messages.create(model="claude-opus-4-6", system=..., messages=[...], max_tokens=...)`
- Change: `response.choices[0].message.content` → `response.content[0].text`
- Change: `n_tiles=8` default → `n_tiles=4`
- Change: `confidence_threshold=0.45` default → threshold passed from caller (0.3 onshore / 0.2 offshore)
- Add: `location_type` parameter to `triage_image()` and `triage_batch()`
- Add: cost accumulation (`response.usage.input_tokens`, `response.usage.output_tokens`)
- Add: `errors.json` per-job error logging

**Key difference:** Kimi used `image_url` with data URI prefix; Anthropic uses `image` with `source.data` as raw base64 (NO `data:image/jpeg;base64,` prefix).

### classify.py Migration

**What changes:**
- Remove: `import google.generativeai as genai`, `genai.configure(api_key=...)`, `genai.GenerativeModel(...)`
- Remove: Google parts format (`[{"text": ...}, {"inline_data": {"mime_type": ..., "data": ...}}]`)
- Remove: `model_instance.generate_content(parts, generation_config={...})`
- Remove: `response.text`
- Add: Same Anthropic SDK pattern as analyze.py — `client.messages.create()` with system + user messages
- Add: `system=CLASSIFY_SYSTEM_PROMPT` (currently merged into user prompt for Gemini)
- Change: `response.text` → `response.content[0].text`
- Change: Category range update: was Vestas 1-5, must become IEC Cat 0-4 AND add BDDA 0-10 score
- Add: BDDA score mapping in classify result and dataclass
- Add: cost accumulation

**Key difference:** Gemini handled the 45MP image natively — Anthropic will too (up to 5MB API limit). No tiling needed for classify — just load full image and pass as single base64 block.

### analyze.py Migration

**What changes (minimal):**
- Model string update only if needed (already uses `claude-opus-4-6`)
- Add: cost accumulation (`response.usage.input_tokens`, `response.usage.output_tokens`)
- Add: `location_type` / offshore context to prompt when applicable
- Exception handling already good — catches `anthropic.RateLimitError` correctly; add `anthropic.OverloadedError` (HTTP 529)

### api.py Migration

**What changes:**
- Stage 2 (Triage): `kimi_key = os.environ.get("KIMI_API_KEY", "")` → `anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")`
- Stage 3 (Classify): `google_key = os.environ.get("GOOGLE_API_KEY", "")` → same `anthropic_key`
- Remove: API key fallback dummy paths (no-key cases become proper error states)
- Add: pre-run cost estimate call before pipeline starts
- Add: inspector confirmation step (check vs `COST_LIMIT_USD` env var)
- Add: 500-image cap check in Stage 1 (ingest) with warning
- Add: cost accumulation from all stages, log to `state.json`
- Add: `location_type` field from `turbine_meta` throughout pipeline
- Add: `errors.json` accumulation across all stages
- Update `/api/health` to remove `GOOGLE_API_KEY` and `KIMI_API_KEY` checks

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rate limit detection | String-parsing exception messages | `anthropic.RateLimitError` class | SDK raises typed exceptions; string matching is fragile |
| Token counting | Estimating tokens from character count | `response.usage.input_tokens` | Always exact; no estimation needed post-call |
| Image base64 encoding | Custom encoding utilities | `base64.b64encode(bytes).decode("utf-8")` | Standard library; already used in analyze.py |
| Retry logic | Custom decorator or wrapper class | Inline `for attempt in range(MAX_RETRIES)` | Simple is sufficient; already proven in analyze.py |
| Cost accumulation | Separate cost-tracking service | Running sum in pipeline function | State is simple; log to existing `state.json` |

---

## Common Pitfalls

### Pitfall 1: Data URI Prefix in Base64 Data
**What goes wrong:** Kimi (via OpenAI client) uses `"url": f"data:image/jpeg;base64,{b64}"`. If you copy this to Anthropic format, the `data` field will contain `data:image/jpeg;base64,...` which is INVALID — Anthropic expects ONLY the raw base64 string.
**Why it happens:** OpenAI image_url format embeds the data URI scheme; Anthropic separates `media_type` as its own field and wants only the encoded bytes.
**How to avoid:** Use `base64.b64encode(image_bytes).decode("utf-8")` — no prefix. Verify with: `assert not b64.startswith("data:")`.
**Warning signs:** `anthropic.BadRequestError` with message about invalid base64.

### Pitfall 2: Missing OverloadedError (HTTP 529)
**What goes wrong:** Current analyze.py catches `anthropic.RateLimitError` (429) but not `anthropic.OverloadedError` (529). Under heavy load Anthropic returns 529, which falls through to the generic `except Exception` and is NOT retried properly.
**Why it happens:** 529 is Anthropic-specific and not in the standard HTTP spec. Most developers only know about 429.
**How to avoid:** Catch both `anthropic.RateLimitError` and `anthropic.OverloadedError` in the same retry branch.

### Pitfall 3: Category Scale Mismatch in classify.py
**What goes wrong:** Current classify.py prompts Gemini for "category: Vestas severity 1-5" and DefectFinding uses `category: int` (1-5). The new requirement is IEC Cat 0-4 AND BDDA 0-10. If prompts still ask for 1-5, the mapping to IEC Cat 0-4 will be wrong.
**Why it happens:** The old Gemini prompt was never updated and DefectFinding dataclass assumes 1-5.
**How to avoid:** Rewrite classify prompt to output IEC `iec_category: 0-4` and derive `bdda_score: 0-10` via the mapping table. Update `DefectFinding` dataclass accordingly. Update `has_critical` property to use `iec_category >= 3` (was `category >= 4`).

### Pitfall 4: Image Size Exceeding 5MB API Limit
**What goes wrong:** DJI P1 produces 45MP images. A full-resolution image can be 15-30MB. Sending it raw to Anthropic classify stage causes `anthropic.RequestTooLargeError` (413).
**Why it happens:** Gemini had native high-resolution handling. Anthropic API enforces 5MB per image.
**How to avoid:** In classify.py, before base64 encoding, check file size and resize if > 4MB. Target 1568px longest edge per Anthropic documentation (that is the threshold where downscaling preserves all model performance). Use Pillow: `img.thumbnail((1568, 1568), Image.LANCZOS)`.

### Pitfall 5: Confidence Threshold Not Passed to Triage
**What goes wrong:** Current `triage_batch()` has a fixed `confidence_threshold=0.45`. New requirement is 0.3 onshore, 0.2 offshore. If `location_type` is not threaded through from `turbine_meta` to `triage_batch()`, it defaults to the wrong threshold.
**Why it happens:** `turbine_meta` lives in `api.py`; `triage_batch()` in `triage.py` doesn't receive it.
**How to avoid:** Add `location_type: str = "onshore"` parameter to `triage_batch()` and `triage_image()`. In `api.py`, pass `turbine_meta.get("location_type", "onshore")`. Set threshold inside triage: `threshold = 0.2 if location_type == "offshore" else 0.3`.

### Pitfall 6: Cost Limit Check Timing
**What goes wrong:** If `COST_LIMIT_USD` is checked only at the end, the pipeline runs to completion and exceeds the limit. If it's checked before each call, it breaks mid-image.
**Why it happens:** Async cost accumulation with synchronous checks can create race conditions.
**How to avoid:** Check accumulated cost at the start of each image's processing (not per-tile). Pattern: `if running_cost > cost_limit: break # flag remaining as skipped`. This is safe because the loop is sequential (not async).

---

## Code Examples

### Verified: Existing Anthropic Call in analyze.py
```python
# Source: backend/analyze.py (working production code)
client = anthropic.Anthropic(api_key=api_key)
response = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=1500,
    system=ANALYZE_SYSTEM_PROMPT,
    messages=[{"role": "user", "content": content}],
)
raw = response.content[0].text.strip()
```

### Verified: Multi-Image Content Block (Anthropic docs)
```python
# Source: platform.claude.com/docs/en/build-with-claude/vision
content = [
    {"type": "text", "text": "Image 1:"},
    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img1_b64}},
    {"type": "text", "text": "Image 2:"},
    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img2_b64}},
    {"type": "text", "text": "Analyze these tiles."},
]
```

### Verified: Usage Token Access
```python
# Source: Anthropic SDK GitHub anthropics/anthropic-sdk-python
response = client.messages.create(...)
cost_usd = (response.usage.input_tokens * 5.0 / 1_000_000
          + response.usage.output_tokens * 25.0 / 1_000_000)
```

### Verified: Image Resize for 5MB Limit
```python
# Source: Anthropic vision docs — 1568px threshold for max model performance
from PIL import Image
import io

def load_and_resize_image(image_path: Path, max_edge: int = 1568) -> str:
    """Load image, resize if needed, return base64 string."""
    with Image.open(image_path) as img:
        if max(img.size) > max_edge:
            img.thumbnail((max_edge, max_edge), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
```

### Verified: location_type Field Addition to turbine_meta (api.py)
```python
# In /api/upload endpoint, add to turbine_meta dict:
turbine_meta = {
    # ... existing fields ...
    "location_type": location_type or "onshore",  # new field
}

# In form handler, add parameter:
# location_type: Optional[str] = Form(None)
```

### Verified: errors.json Structure
```python
# Per-job error accumulation format
error_entry = {
    "timestamp": datetime.now().isoformat(),
    "stage": "triage",           # "triage" | "classify" | "analyze"
    "image_path": str(img_path),
    "error": str(e),
    "attempt": attempt_number,
}
# Append to job_dir / "errors.json"
```

---

## location_type Implementation Recommendation

Based on the codebase, the simplest implementation is a **form field** (Claude's discretion area):

- The upload form already has Country + GPS fields. Offshore/onshore is a known fact for the inspector, not something to infer from GPS (GPS inference requires external wind farm database lookup which is not in scope).
- Add a `<select name="location_type">` dropdown with options: `onshore` (default), `offshore`.
- Add to FastAPI upload endpoint as `location_type: Optional[str] = Form(None)` defaulting to `"onshore"`.
- Add to `turbine_meta` dict as `"location_type": location_type or "onshore"`.
- Thread through to `triage_batch(location_type=turbine_meta["location_type"])`.
- Make it prominent in the form (the CONTEXT.md notes this is a key differentiator).

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| OpenAI client pointed at Kimi base URL | `anthropic.Anthropic()` | Removes dependency on third-party API compatibility layer |
| `google.generativeai.GenerativeModel` | `anthropic.Anthropic()` | Single SDK, single key, unified error handling |
| Catch generic `Exception`, check "429" in string | `anthropic.RateLimitError`, `anthropic.OverloadedError` | Typed, reliable error routing |
| No cost tracking | `response.usage.input_tokens/output_tokens` | Exact per-call cost measurement |
| 8 tiles per image | 4 tiles per image | ~50% triage cost reduction; Opus 4.6 vision is significantly more capable than Kimi |
| Vestas Cat 1-5 only | IEC Cat 0-4 + BDDA 0-10 | Aligns with international standards + custom severity scale |

---

## Open Questions

1. **Image size for classify stage**
   - What we know: Anthropic enforces 5MB per image; DJI P1 files can be 15-30MB.
   - What's unclear: Exact typical file size of DJI P1 JPEGs after in-camera compression. Test images not available.
   - Recommendation: Always resize to max 1568px longest edge before classify. This is safe and preserves Anthropic-documented optimal model performance.

2. **Cost limit mid-pipeline UX**
   - What we know: If `COST_LIMIT_USD` is hit mid-triage, remaining images must be flagged `has_defect=true`.
   - What's unclear: Whether the frontend needs a dedicated "cost limit exceeded" status vs generic error.
   - Recommendation: Add a new pipeline stage `"cost_limit_exceeded"` to the stage_progress map in api.py. Keep it visually distinct from `"error"`.

3. **Pre-run confirmation UX**
   - What we know: The inspector should see cost estimate and confirm before pipeline starts.
   - What's unclear: Whether this is a modal in the frontend (Phase 5 Frontend is separate) or an API-level step.
   - Recommendation: For Phase 1, return cost estimate in the upload response before starting the pipeline. The frontend can show it. Full modal confirmation can come in Phase 5. API flow: POST /api/estimate (returns cost) → POST /api/upload (starts pipeline).

---

## Sources

### Primary (HIGH confidence)
- `backend/analyze.py` — Existing verified Anthropic SDK call pattern; exception handling; base64 image block format
- `platform.claude.com/docs/en/build-with-claude/vision` — Vision API: base64 format, multi-image blocks, 5MB limit, resize recommendations, token cost per image
- `platform.claude.com/docs/en/about-claude/models/overview` — Confirmed model ID `claude-opus-4-6`, pricing table
- `platform.claude.com/docs/en/about-claude/pricing` — $5/MTok input, $25/MTok output for claude-opus-4-6
- `github.com/anthropics/anthropic-sdk-python/_exceptions.py` — Full exception class hierarchy including `OverloadedError` (HTTP 529)

### Secondary (MEDIUM confidence)
- `backend/triage.py` — OpenAI/Kimi call pattern mapped to migration diff
- `backend/classify.py` — Gemini call pattern mapped to migration diff
- `backend/api.py` — Pipeline flow, turbine_meta dict structure, env var usage
- `backend/ingest.py` — image_info dict fields flowing into triage/classify

### Tertiary (LOW confidence — not needed, covered by primary sources)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified in existing codebase and official Anthropic docs
- Migration patterns: HIGH — direct diff from existing code to target pattern documented
- Exception handling: HIGH — verified from SDK source code
- Token pricing: HIGH — from official Anthropic pricing page
- Image size limits: HIGH — from official vision docs
- Architecture pitfalls: HIGH — derived directly from code analysis of existing files
- Pre-run cost formula: MEDIUM — formula is correct; constants are estimates that will be validated empirically

**Research date:** 2026-03-04
**Valid until:** 2026-06-04 (pricing can change; model IDs are stable aliases)
