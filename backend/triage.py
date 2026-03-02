"""
triage.py — Stage 1: Fast defect triage using Kimi K2.5 API
Sends 8 representative tiles per image, gets YES/NO defect + confidence.
Flags images for full classification. Discards clean shots.

Kimi K2.5 is chosen for triage: cheapest vision model for binary screening.
~$0.50/turbine for 500 images at 8 tiles each.
"""

import os
import json
import re
import time
import base64
import asyncio
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, field

from tile import tile_image, select_representative_tiles, get_image_dimensions

# ─── TRIAGE PROMPT ────────────────────────────────────────────────────────────

TRIAGE_PROMPT = """You are a wind turbine blade inspector reviewing a drone inspection image tile.

This image tile is from a DJI P1 45MP inspection of a wind turbine.
Blade: {blade} | Zone: {zone} | Position: {position}

Your task: Determine if this tile shows any defect, damage, or anomaly that requires attention.

Look for:
- Surface damage: erosion, cracks, delamination, paint peeling, pitting
- Structural issues: fiber exposure, core exposure, bond line cracks, separation
- Impact damage: craters, gouges, strike marks
- Environmental: moisture staining, contamination (except light dust/insects)
- Lightning damage: burn marks, arc tracks, receptor damage

DO NOT flag:
- Normal surface texture
- Clean blade surface
- Shadows or lighting variations
- Edge of blade where geometry changes

Respond with ONLY valid JSON, no other text:
{
  "has_defect": true or false,
  "confidence": 0.0 to 1.0,
  "defect_hint": "brief description of what you see, or null if no defect"
}"""


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


@dataclass
class TriageSummary:
    turbine_id: str
    total_images: int
    flagged_images: int
    clean_images: int
    error_images: int
    results: List[TriageResult] = field(default_factory=list)

    @property
    def flag_rate(self) -> float:
        if self.total_images == 0:
            return 0.0
        return self.flagged_images / self.total_images


# ─── KIMI API CLIENT ──────────────────────────────────────────────────────────

def call_kimi_triage(
    image_b64_list: List[str],
    blade: str,
    zone: str,
    position: str,
    api_key: str,
    model: str = "moonshot-v1-8k-vision-preview",
    max_retries: int = 3,
) -> Dict:
    """
    Call Kimi K2.5 API with image tiles for triage.
    Returns parsed JSON response or error dict.

    Kimi API is OpenAI-compatible, base URL: https://api.moonshot.cn/v1
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("Install openai: pip install openai")

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.moonshot.cn/v1",
    )

    prompt = TRIAGE_PROMPT.format(blade=blade, zone=zone, position=position)

    # Build content with text + images
    content = [{"type": "text", "text": prompt}]
    for b64 in image_b64_list:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })

    raw = ""
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": content}],
                max_tokens=300,
                temperature=0.1,
            )
            raw = response.choices[0].message.content.strip()

            # Strip markdown code fences robustly
            cleaned = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
            cleaned = re.sub(r"\s*```\s*$", "", cleaned, flags=re.MULTILINE)
            cleaned = cleaned.strip()

            parsed = json.loads(cleaned)

            # Guard: Kimi must return a JSON object, not a scalar string
            if not isinstance(parsed, dict):
                raise json.JSONDecodeError(
                    f"Expected JSON object, got {type(parsed).__name__}", cleaned, 0
                )

            return parsed

        except json.JSONDecodeError as e:
            if attempt == max_retries - 1:
                return {"error": f"JSON parse failed: {e}", "raw": raw[:200]}
            time.sleep(1)
        except Exception as e:
            if attempt == max_retries - 1:
                return {"error": str(e)}
            time.sleep(2 ** attempt)

    return {"error": "Max retries exceeded"}


# ─── SINGLE IMAGE TRIAGE ──────────────────────────────────────────────────────

def triage_image(
    image_info: Dict,
    api_key: str,
    n_tiles: int = 8,
    tile_size: int = 1024,
    confidence_threshold: float = 0.45,
) -> TriageResult:
    """
    Triage a single image.

    image_info dict must have: path, turbine_id, blade, zone, position, mission_folder
    """
    path = Path(image_info["path"])

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
            turbine_id=image_info["turbine_id"],
            blade=image_info["blade"],
            zone=image_info["zone"],
            position=image_info["position"],
            mission_folder=image_info.get("mission_folder", ""),
            has_defect=False,
            confidence=0.0,
            defect_hint=None,
            tiles_analyzed=0,
            error=f"Tiling failed: {e}",
        )

    # Call Kimi API
    result = call_kimi_triage(
        tiles_b64,
        blade=image_info["blade"],
        zone=image_info["zone"],
        position=image_info["position"],
        api_key=api_key,
    )

    if "error" in result:
        return TriageResult(
            image_path=path,
            turbine_id=image_info["turbine_id"],
            blade=image_info["blade"],
            zone=image_info["zone"],
            position=image_info["position"],
            mission_folder=image_info.get("mission_folder", ""),
            has_defect=False,
            confidence=0.0,
            defect_hint=None,
            tiles_analyzed=len(tiles_b64),
            error=result["error"],
        )

    has_defect = result.get("has_defect", False)
    confidence = float(result.get("confidence", 0.0))

    # Apply confidence threshold
    if confidence < confidence_threshold:
        has_defect = False

    return TriageResult(
        image_path=path,
        turbine_id=image_info["turbine_id"],
        blade=image_info["blade"],
        zone=image_info["zone"],
        position=image_info["position"],
        mission_folder=image_info.get("mission_folder", ""),
        has_defect=has_defect,
        confidence=confidence,
        defect_hint=result.get("defect_hint"),
        tiles_analyzed=len(tiles_b64),
    )


# ─── BATCH TRIAGE ─────────────────────────────────────────────────────────────

def triage_batch(
    images: List[Dict],
    api_key: str,
    n_tiles: int = 8,
    confidence_threshold: float = 0.45,
    delay_between_calls: float = 0.5,
    verbose: bool = True,
) -> TriageSummary:
    """
    Triage a batch of images sequentially.

    Args:
        images: list of image_info dicts from ingest.get_all_images_flat()
        api_key: Kimi API key
        n_tiles: tiles per image to analyze
        confidence_threshold: minimum confidence to flag as defect
        delay_between_calls: seconds between API calls (rate limiting)
        verbose: print progress

    Returns:
        TriageSummary with all results
    """
    if not images:
        raise ValueError("No images to triage")

    turbine_id = images[0]["turbine_id"]
    results = []
    flagged = 0
    errors = 0

    if verbose:
        print(f"\nTriaging {len(images)} images for turbine {turbine_id}...")
        print(f"Settings: {n_tiles} tiles/image, confidence threshold: {confidence_threshold}")

    for i, img_info in enumerate(images):
        if verbose and i % 10 == 0:
            print(f"  [{i+1}/{len(images)}] {Path(img_info['path']).name} | B{img_info['blade']} {img_info['zone']} {img_info['position']}")

        result = triage_image(img_info, api_key, n_tiles=n_tiles, confidence_threshold=confidence_threshold)
        results.append(result)

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
    )

    if verbose:
        print(f"\nTriage complete:")
        print(f"  Total: {summary.total_images} | Flagged: {summary.flagged_images} ({summary.flag_rate:.0%}) | Clean: {summary.clean_images} | Errors: {summary.error_images}")

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
    print("triage.py — Stage 1 Kimi K2.5 triage module")
    print("Usage: import triage and call triage_batch(images, api_key)")
    print(f"API key expected in env: KIMI_API_KEY")

    key = os.environ.get("KIMI_API_KEY")
    if key:
        print("KIMI_API_KEY found in environment")
    else:
        print("KIMI_API_KEY not set — set it before running triage")
