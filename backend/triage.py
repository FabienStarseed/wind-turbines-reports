"""
triage.py — Stage 1: Fast defect triage using Claude Opus 4.6
Sends 4 representative tiles per image, gets YES/NO defect + confidence.
Flags images for full classification. Discards clean shots.

Confidence thresholds:
  - Onshore:  >= 0.3 to flag
  - Offshore: >= 0.2 to flag (stricter recall — offshore repairs are expensive)
"""

import os
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, field

import anthropic

from tile import tile_image, select_representative_tiles, get_image_dimensions

# ─── TRIAGE PROMPTS ───────────────────────────────────────────────────────────

TRIAGE_SYSTEM_PROMPT = """You are a senior drone inspection specialist performing fast binary defect screening on wind turbine blades.

You are reviewing 1092x1092px tiles extracted from DJI P1 45MP imagery. Each set of 4 tiles is sampled from a single blade image to give representative coverage.

Your goal is recall-optimized screening: flag anything that could plausibly be a defect, including low-confidence observations. It is better to pass a borderline image to the next stage than to miss a real defect.

Be fast and decisive. Your output is binary — flag or clear."""

TRIAGE_USER_PROMPT = """The 4 tiles above are from: Turbine {turbine_id} ({turbine_model}), Blade {blade}, Zone {zone}, Position {position}, Inspected {inspection_date}. {offshore_flag}

Look for:
- Surface damage: erosion, cracks, delamination, paint peeling, pitting
- Structural issues: fiber/core exposure, bond line cracks
- Impact damage: craters, gouges, strike marks
- Environmental staining or contamination
- Lightning damage: burn marks, arc tracks

Do NOT flag:
- Normal surface texture
- Clean blade surface
- Shadows or lighting variation
- Blade edge geometry changes

For confidence >= 0.7, include one sentence of reasoning in the `reasoning` field. For confidence < 0.7, set `reasoning` to null.

Return ONLY valid JSON:
{{"has_defect": true|false, "confidence": 0.0-1.0, "defect_hint": "brief description or null", "reasoning": "one sentence or null"}}"""

OFFSHORE_FLAG = "OFFSHORE TURBINE — apply stricter scrutiny, offshore repairs are significantly more expensive"


# ─── DATA STRUCTURES ──────────────────────────────────────────────────────────

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
    error: Optional[str] = None
    cost_usd: float = 0.0


@dataclass
class TriageSummary:
    turbine_id: str
    total_images: int
    flagged_images: int
    clean_images: int
    error_images: int
    results: List[TriageResult] = field(default_factory=list)
    triage_cost_usd: float = 0.0

    @property
    def flag_rate(self) -> float:
        if self.total_images == 0:
            return 0.0
        return self.flagged_images / self.total_images


# ─── ANTHROPIC API CLIENT ──────────────────────────────────────────────────────

def call_claude_triage(
    image_b64_list: List[str],  # list of raw base64 strings (NO data:image/... prefix)
    blade: str,
    zone: str,
    position: str,
    turbine_id: str,
    turbine_model: str,
    inspection_date: str,
    location_type: str,  # "onshore" or "offshore"
    api_key: str,
    model: str = "claude-opus-4-5",
    max_retries: int = 3,
) -> Dict:
    """
    Call Claude Opus 4.6 with image tiles for triage.
    Returns parsed JSON response dict or error dict.

    CRITICAL: image_b64_list must contain raw base64 strings with NO data URI prefix
    (i.e., no "data:image/jpeg;base64," prefix — Anthropic SDK uses raw base64 only).
    """
    client = anthropic.Anthropic(api_key=api_key)

    # Build Anthropic-format content: images first, then the text prompt
    content = []
    for b64 in image_b64_list:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": b64,
            },
        })

    offshore_flag = OFFSHORE_FLAG if location_type == "offshore" else ""
    user_prompt = TRIAGE_USER_PROMPT.format(
        turbine_id=turbine_id,
        turbine_model=turbine_model,
        blade=blade,
        zone=zone,
        position=position,
        inspection_date=inspection_date,
        offshore_flag=offshore_flag,
    )
    content.append({"type": "text", "text": user_prompt})

    raw = ""
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=300,
                system=TRIAGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
            )
            raw = response.content[0].text.strip()

            # Strip markdown code fences robustly
            cleaned = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
            cleaned = re.sub(r"\s*```\s*$", "", cleaned, flags=re.MULTILINE)
            cleaned = cleaned.strip()

            parsed = json.loads(cleaned)

            # Guard: must return a JSON object
            if not isinstance(parsed, dict):
                raise json.JSONDecodeError(
                    f"Expected JSON object, got {type(parsed).__name__}", cleaned, 0
                )

            # Attach token usage for cost tracking
            parsed["input_tokens"] = response.usage.input_tokens
            parsed["output_tokens"] = response.usage.output_tokens
            return parsed

        except json.JSONDecodeError:
            # Per spec: JSON parse failures set has_defect=True without retry
            return {"has_defect": True, "confidence": 1.0, "error": "json_parse_fail"}

        except anthropic.RateLimitError:
            sleep_secs = (2 ** attempt) * 10  # 10s, 20s, 40s
            if attempt == max_retries - 1:
                return {"error": "rate_limit", "has_defect": True}
            time.sleep(sleep_secs)

        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                # Transient server error — retry with backoff
                if attempt == max_retries - 1:
                    return {"error": f"server_error_{e.status_code}", "has_defect": True}
                time.sleep(2 ** attempt)
            else:
                # 4xx client error (bad key, invalid request) — raise immediately
                raise

        except (anthropic.APIConnectionError, anthropic.APITimeoutError):
            sleep_secs = 2 ** attempt  # 1s, 2s, 4s
            if attempt == max_retries - 1:
                return {"error": "connection", "has_defect": True}
            time.sleep(sleep_secs)

        except Exception as e:
            if attempt == max_retries - 1:
                return {"error": str(e), "has_defect": True}
            time.sleep(2 ** attempt)

    return {"error": "max_retries_exceeded", "has_defect": True}


# ─── SINGLE IMAGE TRIAGE ──────────────────────────────────────────────────────

def triage_image(
    image_info: Dict,
    api_key: str,
    n_tiles: int = 4,
    tile_size: int = 1024,
    location_type: str = "onshore",
    turbine_id: str = "",
    turbine_model: str = "",
    inspection_date: str = "",
) -> TriageResult:
    """
    Triage a single image using Claude Opus 4.6.

    image_info dict must have: path, turbine_id, blade, zone, position, mission_folder

    Confidence thresholds are derived from location_type:
      - offshore: 0.2  (stricter recall)
      - onshore:  0.3
    """
    path = Path(image_info["path"])
    effective_turbine_id = turbine_id or image_info.get("turbine_id", "")

    # Derive threshold from location type
    threshold = 0.2 if location_type == "offshore" else 0.3

    # Generate tiles
    try:
        tiles, coords = tile_image(path, tile_size=tile_size, overlap=0.2, as_base64=False)
        w, h = get_image_dimensions(path)
        rep_tiles, rep_coords = select_representative_tiles(tiles, coords, w, h, n=n_tiles)
        # Convert to base64
        from tile import tile_to_base64
        tiles_b64 = [tile_to_base64(t) for t in rep_tiles]
    except Exception as e:
        return TriageResult(
            image_path=path,
            turbine_id=effective_turbine_id,
            blade=image_info["blade"],
            zone=image_info["zone"],
            position=image_info["position"],
            mission_folder=image_info.get("mission_folder", ""),
            has_defect=False,
            confidence=0.0,
            defect_hint=None,
            tiles_analyzed=0,
            error=f"Tiling failed: {e}",
            cost_usd=0.0,
        )

    # Call Claude API
    result = call_claude_triage(
        tiles_b64,
        blade=image_info["blade"],
        zone=image_info["zone"],
        position=image_info["position"],
        turbine_id=effective_turbine_id,
        turbine_model=turbine_model,
        inspection_date=inspection_date,
        location_type=location_type,
        api_key=api_key,
    )

    # Handle API-down fallback (error with has_defect=True conservative flag)
    if result.get("error") and "input_tokens" not in result:
        return TriageResult(
            image_path=path,
            turbine_id=effective_turbine_id,
            blade=image_info["blade"],
            zone=image_info["zone"],
            position=image_info["position"],
            mission_folder=image_info.get("mission_folder", ""),
            has_defect=result.get("has_defect", True),
            confidence=result.get("confidence", 1.0),
            defect_hint=None,
            tiles_analyzed=len(tiles_b64),
            error=result["error"],
            cost_usd=0.0,
        )

    has_defect = result.get("has_defect", False)
    confidence = float(result.get("confidence", 0.0))

    # Apply location-based confidence threshold
    if confidence < threshold:
        has_defect = False

    # Calculate cost: $5/M input tokens, $25/M output tokens (Opus 4.6 pricing)
    input_tokens = result.get("input_tokens", 0)
    output_tokens = result.get("output_tokens", 0)
    call_cost = (input_tokens * 5.0 / 1_000_000) + (output_tokens * 25.0 / 1_000_000)

    return TriageResult(
        image_path=path,
        turbine_id=effective_turbine_id,
        blade=image_info["blade"],
        zone=image_info["zone"],
        position=image_info["position"],
        mission_folder=image_info.get("mission_folder", ""),
        has_defect=has_defect,
        confidence=confidence,
        defect_hint=result.get("defect_hint"),
        tiles_analyzed=len(tiles_b64),
        cost_usd=call_cost,
    )


# ─── ERROR LOGGING ─────────────────────────────────────────────────────────────

def _append_error_json(job_dir: Path, entry: Dict) -> None:
    """Append an error entry to errors.json in job_dir (creates file if needed)."""
    errors_path = job_dir / "errors.json"
    existing = []
    if errors_path.exists():
        try:
            with open(errors_path) as f:
                existing = json.load(f)
        except Exception:
            existing = []
    existing.append(entry)
    with open(errors_path, "w") as f:
        json.dump(existing, f, indent=2)


# ─── BATCH TRIAGE ─────────────────────────────────────────────────────────────

def triage_batch(
    images: List[Dict],
    api_key: str,
    n_tiles: int = 4,
    location_type: str = "onshore",
    job_dir: Optional[Path] = None,
    turbine_model: str = "",
    inspection_date: str = "",
    delay_between_calls: float = 0.5,
    verbose: bool = True,
) -> TriageSummary:
    """
    Triage a batch of images sequentially using Claude Opus 4.6.

    Args:
        images: list of image_info dicts from ingest.get_all_images_flat()
        api_key: Anthropic API key
        n_tiles: tiles per image to analyze (default 4 for Opus 4.6)
        location_type: "onshore" or "offshore" — selects confidence threshold
        job_dir: directory for errors.json output (optional)
        turbine_model: turbine model string for prompt context
        inspection_date: ISO date string for prompt context
        delay_between_calls: seconds between API calls (rate limiting)
        verbose: print progress

    Returns:
        TriageSummary with all results and triage_cost_usd
    """
    if not images:
        raise ValueError("No images to triage")

    turbine_id = images[0]["turbine_id"]
    results = []
    flagged = 0
    errors = 0
    running_cost: float = 0.0

    threshold = 0.2 if location_type == "offshore" else 0.3

    if verbose:
        print(f"\nTriaging {len(images)} images for turbine {turbine_id}...")
        print(f"Settings: {n_tiles} tiles/image, location: {location_type}, threshold: {threshold}")

    for i, img_info in enumerate(images):
        if verbose and i % 10 == 0:
            print(f"  [{i+1}/{len(images)}] {Path(img_info['path']).name} | B{img_info['blade']} {img_info['zone']} {img_info['position']}")

        # First attempt
        result = triage_image(
            img_info,
            api_key,
            n_tiles=n_tiles,
            location_type=location_type,
            turbine_id=turbine_id,
            turbine_model=turbine_model,
            inspection_date=inspection_date,
        )

        # Per-image retry: if first attempt errored, retry once
        if result.error:
            if verbose:
                print(f"    Retry attempt 2 for {Path(img_info['path']).name} (first error: {result.error})")
            result = triage_image(
                img_info,
                api_key,
                n_tiles=n_tiles,
                location_type=location_type,
                turbine_id=turbine_id,
                turbine_model=turbine_model,
                inspection_date=inspection_date,
            )
            # If second attempt also errors, log and continue
            if result.error and job_dir is not None:
                _append_error_json(job_dir, {
                    "timestamp": datetime.now().isoformat(),
                    "stage": "triage",
                    "image_path": str(result.image_path),
                    "error": result.error,
                    "attempt": 2,
                })

        results.append(result)
        running_cost += result.cost_usd

        if result.error:
            errors += 1
            if verbose:
                print(f"    ERROR: {result.error}")
        elif result.has_defect:
            flagged += 1
            if verbose:
                print(f"    FLAGGED (conf={result.confidence:.2f}): {result.defect_hint}")

        if delay_between_calls > 0:
            time.sleep(delay_between_calls)

    summary = TriageSummary(
        turbine_id=turbine_id,
        total_images=len(images),
        flagged_images=flagged,
        clean_images=len(images) - flagged - errors,
        error_images=errors,
        results=results,
        triage_cost_usd=running_cost,
    )

    if verbose:
        print(f"\nTriage complete:")
        print(f"  Total: {summary.total_images} | Flagged: {summary.flagged_images} ({summary.flag_rate:.0%}) | Clean: {summary.clean_images} | Errors: {summary.error_images}")
        print(f"  Triage cost: ${running_cost:.4f}")

    return summary


def save_triage_results(summary: TriageSummary, output_path: Path):
    """Save triage results to JSON for next pipeline stage."""
    data = {
        "turbine_id": summary.turbine_id,
        "total_images": summary.total_images,
        "flagged_images": summary.flagged_images,
        "clean_images": summary.clean_images,
        "error_images": summary.error_images,
        "flag_rate": summary.flag_rate,
        "triage_cost_usd": summary.triage_cost_usd,
        "results": [
            {
                "image_path": str(r.image_path),
                "blade": r.blade,
                "zone": r.zone,
                "position": r.position,
                "mission_folder": r.mission_folder,
                "has_defect": r.has_defect,
                "confidence": r.confidence,
                "defect_hint": r.defect_hint,
                "tiles_analyzed": r.tiles_analyzed,
                "error": r.error,
                "cost_usd": r.cost_usd,
            }
            for r in summary.results
        ],
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Triage results saved: {output_path}")


def load_flagged_images(triage_json_path: Path) -> List[Dict]:
    """Load only flagged images from a saved triage JSON."""
    with open(triage_json_path) as f:
        data = json.load(f)
    return [r for r in data["results"] if r["has_defect"]]


if __name__ == "__main__":
    import sys
    print("triage.py — Stage 1 Claude Opus 4.6 triage module")
    print("Usage: import triage and call triage_batch(images, api_key)")
    print(f"API key expected in env: ANTHROPIC_API_KEY")

    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        print("ANTHROPIC_API_KEY found in environment")
    else:
        print("ANTHROPIC_API_KEY not set — set it before running triage")
