# Coding Conventions

**Analysis Date:** 2026-03-03

## Module Structure

Each backend module follows a consistent internal layout with section separators:

```python
# ─── SECTION NAME ─────────────────────────────────────────────────────────────
```

Every module begins with a module-level docstring that states purpose, pipeline stage, AI model used, and approximate cost per turbine. This pattern is mandatory for new pipeline modules.

```python
"""
triage.py — Stage 1: Fast defect triage using Kimi K2.5 API
Sends 8 representative tiles per image, gets YES/NO defect + confidence.
...
~$0.50/turbine for 500 images at 8 tiles each.
"""
```

## Naming Patterns

**Files:** `snake_case.py` — all backend modules use snake_case (`api.py`, `triage.py`, `classify.py`, `analyze.py`, `report.py`, `ingest.py`, `tile.py`, `taxonomy.py`)

**Functions:** `snake_case` — `triage_batch`, `classify_image`, `call_kimi_triage`, `build_report_data`

**Classes/Dataclasses:** `PascalCase` — `TriageResult`, `TriageSummary`, `ClassifyResult`, `DefectFinding`, `DeepAnalysis`, `MissionFolder`, `IngestResult`

**Constants:** `UPPER_SNAKE_CASE` — `TRIAGE_PROMPT`, `CLASSIFY_SYSTEM_PROMPT`, `SEVERITY_COLORS`, `URGENCY_LEVELS`, `DEFECTS`, `IMAGE_EXTENSIONS`

**API endpoints:** `/api/snake_case/{param}` — `/api/upload`, `/api/status/{job_id}`, `/api/debug/kimi`

**Job state keys:** `snake_case` strings — `"stage"`, `"stage_message"`, `"flagged_images"`, `"error_traceback"`

## Dataclasses Usage

All structured pipeline results use `@dataclass`. The pattern:

```python
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class TriageResult:
    image_path: Path
    turbine_id: str
    blade: str
    zone: str
    position: str
    mission_folder: str
    has_defect: bool
    confidence: float
    defect_hint: Optional[str]
    tiles_analyzed: int
    error: Optional[str] = None   # optional fields with defaults always last
```

- Required fields come first (no defaults)
- Optional/error fields use `Optional[str] = None` and come last
- `field(default_factory=list)` used for list fields in dataclasses (`results: List[TriageResult] = field(default_factory=list)`)
- Computed properties are added as `@property` on dataclasses (`max_category`, `has_critical`, `flag_rate`)

## Type Hints

All functions use full type hints. The pattern is consistent across all modules:

```python
def call_kimi_triage(
    image_b64_list: List[str],
    blade: str,
    zone: str,
    position: str,
    api_key: str,
    model: str = "moonshot-v1-8k-vision-preview",
    max_retries: int = 3,
) -> Dict:
```

Imports: `from typing import List, Dict, Optional, Any` (explicit, not `list[str]` style).

## Docstrings

Functions use single-line or multi-line Google-style docstrings. Args sections are written as prose, not formal Google Args blocks:

```python
def triage_batch(
    images: List[Dict],
    api_key: str,
    ...
) -> TriageSummary:
    """
    Triage a batch of images sequentially.

    Args:
        images: list of image_info dicts from ingest.get_all_images_flat()
        api_key: Kimi API key
        ...
    """
```

Short functions may use a single-line docstring. Module-level functions that save data always say what format they save to: `"""Save triage results to JSON for next pipeline stage."""`

## Error Handling Patterns

### API Call Retry Pattern

All three API clients (`call_kimi_triage`, `call_gemini_classify`, `call_claude_analyze`) use the same retry loop:

```python
for attempt in range(max_retries):
    try:
        response = client.chat.completions.create(...)
        raw = response.choices[0].message.content.strip()
        # ... parse JSON ...
        return parsed

    except json.JSONDecodeError as e:
        if attempt == max_retries - 1:
            return {"error": f"JSON parse failed: {e}", "raw": raw[:200]}
        time.sleep(1)
    except Exception as e:
        if attempt == max_retries - 1:
            return {"error": str(e)}
        time.sleep(2 ** attempt)   # exponential backoff

return {"error": "Max retries exceeded"}
```

- `max_retries=3` is the default across all API clients
- `time.sleep(1)` after JSON parse failure, `time.sleep(2 ** attempt)` for other errors
- Gemini adds special handling for rate limits: `if "429" in err_str: time.sleep(30)`
- Anthropic adds typed exception: `except anthropic.RateLimitError: time.sleep(30)`
- On final failure, always return `{"error": "..."}` dict (never raise)

### Error Check Pattern After API Call

Every function that calls an API checks for the error key before proceeding:

```python
result = call_kimi_triage(tiles_b64, ...)

if "error" in result:
    return TriageResult(
        ...,
        has_defect=False,
        confidence=0.0,
        defect_hint=None,
        error=result["error"],
    )
```

Error results always return a valid dataclass instance with safe defaults, never raise. This lets batch functions continue processing remaining images even when individual images fail.

### Missing API Key Fallback Pattern

`api.py` implements graceful degradation for each pipeline stage when API keys are absent:

```python
kimi_key = os.environ.get("KIMI_API_KEY", "")
if not kimi_key:
    # Skip triage — treat all images as flagged (up to 50)
    flagged = [{"path": str(img["path"]), ..., "has_defect": True,
                "defect_hint": "Triage skipped (no KIMI_API_KEY)"} for img in images[:50]]
else:
    from triage import triage_batch
    summary = triage_batch(images, kimi_key, verbose=False)
    ...
```

Each stage has its own fallback that writes valid JSON the next stage can consume, allowing the pipeline to always produce a report (even if incomplete).

### Top-Level Pipeline Error Handler

`api.py`'s `run_pipeline` wraps the entire pipeline in a single broad except:

```python
def run_pipeline(job_id: str, job_dir: Path, turbine_meta: Dict):
    try:
        # ... all stages ...
    except Exception as e:
        tb = traceback.format_exc()
        update_job(job_id, stage="error", stage_message=str(e),
                   error_traceback=tb, failed_at=datetime.now().isoformat())
```

The full traceback is saved to state.json and exposed through `/api/status/{job_id}` as `error_traceback`.

### Optional Import Guarding

Libraries that may be absent are guarded with try/except at module top level:

```python
try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
```

Functions then check `HAS_PIL`/`HAS_CV2` and fall back between implementations. For jinja2 in `report.py`: `HAS_JINJA = True/False` with `RuntimeError` if rendering is attempted without it.

Inside functions, heavy imports (openai, anthropic, google.generativeai) are done lazily with helpful error messages:

```python
try:
    from openai import OpenAI
except ImportError:
    raise RuntimeError("Install openai: pip install openai")
```

## JSON Parsing Pattern

All three LLM API clients use the same two-step clean-then-parse approach for handling markdown-fenced JSON responses.

### Kimi/Triage pattern (regex-based, most robust):

```python
raw = response.choices[0].message.content.strip()

# Strip markdown code fences robustly
cleaned = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
cleaned = re.sub(r"\s*```\s*$", "", cleaned, flags=re.MULTILINE)
cleaned = cleaned.strip()

parsed = json.loads(cleaned)

# Guard: must return a JSON object, not a scalar string
if not isinstance(parsed, dict):
    raise json.JSONDecodeError(
        f"Expected JSON object, got {type(parsed).__name__}", cleaned, 0
    )
```

### Gemini/Classify pattern (simpler split-based):

```python
raw = response.text.strip()

if raw.startswith("```"):
    raw = raw.split("```")[1]
    if raw.startswith("json"):
        raw = raw[4:]
raw = raw.strip()

return json.loads(raw)
```

### Claude/Analyze pattern (same as Gemini):

```python
raw = response.content[0].text.strip()

if raw.startswith("```"):
    raw = raw.split("```")[1]
    if raw.startswith("json"):
        raw = raw[4:]
raw = raw.strip()

return json.loads(raw)
```

The `/api/debug/kimi` endpoint uses the regex approach (same as triage). New API integrations should use the regex approach from triage as it handles multiline fences correctly.

## Prompt Engineering Patterns

### System/User Split

Claude (analyze) uses the Anthropic system/user split:
- `system=ANALYZE_SYSTEM_PROMPT` (persona: senior structural engineer)
- `messages=[{"role": "user", "content": [...]}]`

Gemini combines both into a single text part: `CLASSIFY_SYSTEM_PROMPT + "\n\n" + prompt`

Kimi uses a single user message with text + image parts in `content`.

### Prompt Template Filling

Prompts are module-level constants with `{placeholder}` format strings. They are filled with `.format()` immediately before the API call:

```python
TRIAGE_PROMPT = """You are a wind turbine blade inspector...
Blade: {blade} | Zone: {zone} | Position: {position}
..."""

prompt = TRIAGE_PROMPT.format(blade=blade, zone=zone, position=position)
```

### JSON-only Response Instruction

Every prompt ends with a strict JSON-only instruction:

```
Respond with ONLY valid JSON, no other text:
{
  "has_defect": true or false,
  ...
}
```

Or:
```
Return ONLY valid JSON, no other text:
```

This is paired with the markdown fence stripping in JSON parsing.

### Temperature

All three API calls use `temperature=0.1` for deterministic, consistent output:
- Kimi: `temperature=0.1`, `max_tokens=300`
- Gemini: `temperature=0.1`, `max_output_tokens=2000`
- Claude: no explicit temperature (uses API default), `max_tokens=1500`

### Taxonomy Block Injection

`classify.py` injects the full defect taxonomy into each classification prompt via `build_taxonomy_prompt_block()` from `taxonomy.py`. This generates a compact text table of all 56 defect types with IDs, visual cues, zones, and urgency levels for the AI to reference.

## Serialization Pattern

Pipeline results are always serialized to JSON by explicit `save_*` functions rather than inline. Each `save_*` function builds a plain `dict`/`list` from the dataclass fields (no dataclass serialization helpers are used):

```python
def save_triage_results(summary: TriageSummary, output_path: Path):
    data = {
        "turbine_id": summary.turbine_id,
        "results": [
            {
                "image_path": str(r.image_path),  # Path → str conversion
                "has_defect": r.has_defect,
                ...
            }
            for r in summary.results
        ],
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
```

`Path` objects are always converted to `str` via `str(path)` before serialization. `json.dump` uses `indent=2` everywhere. `api.py`'s `save_job` uses `default=str` to handle datetime objects.

## Pipeline Stage State

Job progress is tracked via a state dict persisted to `jobs/{job_id}/state.json`. Stage names are strings: `"queued"`, `"ingesting"`, `"triaging"`, `"classifying"`, `"analyzing"`, `"generating_report"`, `"complete"`, `"error"`.

Stage updates use `set_stage(job_id, stage_name, human_readable_message)`. Progress percentage is derived from stage name in `/api/status` (not stored in state).

## Verbose Parameter

All batch functions accept `verbose: bool = True` which gates `print()` statements for CLI use. Pipeline calls from `api.py` always pass `verbose=False`. Interactive/script use defaults to `True`.

## Image Info Dict Shape

The canonical image metadata dict passed between pipeline stages:

```python
{
    "path": str,           # absolute path to image file
    "turbine_id": str,
    "blade": str,          # "A", "B", or "C"
    "zone": str,           # "LE", "TE", "PS", "SS"
    "position": str,       # "Root", "Mid", "Tip"
    "mission_folder": str, # DJI folder name
    # triage adds:
    "has_defect": bool,
    "defect_hint": Optional[str],
    "confidence": float,
}
```

## Frontend Patterns

`frontend/app.js` uses vanilla JavaScript (no framework). Patterns:
- DOM refs stored in `const` at module top level
- Async/await for all API calls with try/catch error display
- Polling via `setInterval` (3000ms) for job status
- Silent failure on non-critical errors (history load, network blips): empty `catch {}` blocks
- `alert()` used for user-facing upload errors (not a custom modal)
- `const API = ''` for same-origin; comment instructs setting to `http://localhost:8000` for local dev

---

*Convention analysis: 2026-03-03*
