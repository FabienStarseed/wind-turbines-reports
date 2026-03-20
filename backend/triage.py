"""
triage.py — Stage 1: Fast defect triage using Gemini 2.0 Flash
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

import google.generativeai as genai

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


# ─── GEMINI API CLIENT ────────────────────────────────────────────────────────

# Gemini 2.0 Flash pricing (per million tokens)
# Input: $0.10/M tokens   Output: $0.40/M tokens
_INPUT_COST_PER_TOKEN  = 0.10 / 1_000_000
_OUTPUT_COST_PER_TOKEN = 0.40 / 1_000_000

_MODEL = "gemini-2.0-flash"


def _build_parts(image_b64_list: List[str], user_prompt: str) -> List:
    """Build Gemini content parts: images then text."""
    import base64
    parts = []
    for b64 in image_b64_list:
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": b64,
            }
        })
    parts.append(user_prompt)
    return parts


def call_gemini_triage(
    image_b64_list: List[str],
    blade: str,
    zone: str,
    position: str,
    turbine_id: str,
    turbine_model: str,
    inspection_date: str,
    location_type: str,
    api_key: str,
    max_retries: int = 3,
) -> Dict:
    """
    Call Gemini 2.0 Flash with image tiles for triage.
    Returns parsed JSON response dict or error dict.
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=_MODEL,
        system_instruction=TRIAGE_SYSTEM_PROMPT,
    )

    import base64
    from PIL import Image as PILImage
    import io

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

    # Build content: PIL images then text
    content = []
    for b64 in image_b64_list:
        img_bytes = base64.b64decode(b64)
        pil_img = PILImage.open(io.BytesIO(img_bytes))
        content.append(pil_img)
    content.append(user_prompt)

    for attempt in range(max_retries):
        try:
            response = model.generate_content(
                content,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=300,
                    temperature=0.1,
                ),
            )
            raw = response.text.strip()

            # Strip markdown code fences
            cleaned = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
            cleaned = re.sub(r"\s*```\s*$", "", cleaned, flags=re.MULTILINE).strip()

            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict):
                raise json.JSONDecodeError(f"Expected dict, got {type(parsed).__name__}", cleaned, 0)

            # Attach token usage
            usage = response.usage_metadata
            parsed["input_tokens"] = usage.prompt_token_count or 0
            parsed["output_tokens"] = usage.candidates_token_count or 0
            return parsed

        except json.JSONDecodeError:
            return {"has_defect": True, "confidence": 1.0, "error": "json_parse_fail"}

        except Exception as e:
            err_str = str(e).lower()
            if "quota" in err_str or "rate" in err_str or "429" in err_str:
                sleep_secs = (2 ** attempt) * 10
                if attempt == max_retries - 1:
                    return {"error": "rate_limit", "has_defect": True}
                time.sleep(sleep_secs)
            elif "500" in err_str or "503" in err_str or "unavailable" in err_str:
                if attempt == max_retries - 1:
                    return {"error": f"server_error: {e}", "has_defect": True}
                time.sleep(2 ** attempt)
            else:
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
    path = Path(image_info["path"])
    effective_turbine_id = turbine_id or image_info.get("turbine_id", "")
    threshold = 0.2 if location_type == "offshore" else 0.3

    try:
        tiles, coords = tile_image(path, tile_size=tile_size, overlap=0.2, as_base64=False)
        w, h = get_image_dimensions(path)
        rep_tiles, rep_coords = select_representative_tiles(tiles, coords, w, h, n=n_tiles)
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

    result = call_gemini_triage(
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
    if confidence < threshold:
        has_defect = False

    input_tokens = result.get("input_tokens", 0)
    output_tokens = result.get("output_tokens", 0)
    call_cost = (input_tokens * _INPUT_COST_PER_TOKEN) + (output_tokens * _OUTPUT_COST_PER_TOKEN)

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
        print(f"Settings: {n_tiles} tiles/image, location: {location_type}, threshold: {threshold}, model: {_MODEL}")

    for i, img_info in enumerate(images):
        if verbose and i % 10 == 0:
            print(f"  [{i+1}/{len(images)}] {Path(img_info['path']).name} | B{img_info['blade']} {img_info['zone']} {img_info['position']}")

        result = triage_image(
            img_info, api_key, n_tiles=n_tiles, location_type=location_type,
            turbine_id=turbine_id, turbine_model=turbine_model, inspection_date=inspection_date,
        )

        if result.error:
            if verbose:
                print(f"    Retry for {Path(img_info['path']).name} (error: {result.error})")
            result = triage_image(
                img_info, api_key, n_tiles=n_tiles, location_type=location_type,
                turbine_id=turbine_id, turbine_model=turbine_model, inspection_date=inspection_date,
            )
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
        print(f"\nTriage complete: Total={summary.total_images} | Flagged={summary.flagged_images} ({summary.flag_rate:.0%}) | Clean={summary.clean_images} | Errors={summary.error_images}")
        print(f"  Triage cost: ${running_cost:.4f}")

    return summary


def save_triage_results(summary: TriageSummary, output_path: Path):
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
    with open(triage_json_path) as f:
        data = json.load(f)
    return [r for r in data["results"] if r["has_defect"]]


if __name__ == "__main__":
    print("triage.py — Stage 1 Gemini 2.0 Flash triage module")
    key = os.environ.get("GOOGLE_API_KEY")
    print("GOOGLE_API_KEY found" if key else "GOOGLE_API_KEY not set")
