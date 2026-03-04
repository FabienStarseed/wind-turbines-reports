"""
classify.py — Stage 2: Defect classification using Claude Opus 4.6
Takes flagged images from triage, returns structured defect JSON per image.

Claude Opus 4.6 chosen for classification:
- Anthropic SDK unified with triage and analysis stages
- IEC 61400 / DNVGL-ST-0376 dual scoring (IEC Cat 0-4 + BDDA 0-10)
- Image resized to max 1568px before encoding (Anthropic vision limit)
"""

import os
import io
import json
import time
import base64
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, field

import anthropic
from taxonomy import build_taxonomy_prompt_block, DEFECTS, get_urgency_for_category

# ─── CLASSIFICATION PROMPT ────────────────────────────────────────────────────

CLASSIFY_SYSTEM_PROMPT = """You are a senior wind turbine blade inspector with 20 years of field experience in IEC 61400-1 and DNVGL-ST-0376 standards.
You specialize in DJI P1 45MP drone imagery analysis for Vestas, Siemens Gamesa, and Enercon turbines.
You have deep knowledge of composite blade failure modes and international inspection standards.
Your assessments use the IEC 61400 / international severity scale (Category 0 to 4) and a custom BDDA severity score (0 to 10).
Your assessments are used for Vestas maintenance planning — accuracy is critical."""

CLASSIFY_USER_PROMPT = """Analyze this drone inspection image from a wind turbine and identify all defects present.

TURBINE CONTEXT:
- Turbine ID: {turbine_id} | Model: {turbine_model}
- Blade: {blade} | Zone: {zone} | Position: {position}
- Image: {image_name}
- Location: {location_type}
- Triage hint: {defect_hint}

{taxonomy_block}

INSTRUCTIONS:
For each defect identified, return one entry with:
- defect_id: integer from taxonomy (1-56), or 0 if unlisted
- defect_name: exact name from taxonomy
- iec_category: IEC 61400 category 0-4 (0=No action, 1=Log, 2=Monitor/next service, 3=Planned repair <3 months, 4=Urgent/immediate action)
- bdda_score: BDDA severity 0-10 (derived from iec_category: Cat0=0, Cat1=1, Cat2=3, Cat3=6, Cat4=9)
- urgency: LOG / MONITOR / PLANNED / URGENT / IMMEDIATE
- zone: LE / TE / PS / SS
- position: Root / Transition / Mid / Tip
- size_estimate: "small (<5cm)" / "medium (5-30cm)" / "large (>30cm)" / "extensive (full zone)"
- confidence: 0.0-1.0
- visual_description: 1-2 sentences describing exactly what you see
- ndt_recommended: true/false

Return ONLY valid JSON:
{
  "defects": [...],
  "image_quality": "good" / "acceptable" / "poor",
  "image_notes": "<notes>"
}

If no defects found: {"defects": [], "image_quality": "good", "image_notes": ""}"""


# ─── SCORING UTILITIES ────────────────────────────────────────────────────────

# Claude Opus 4.6 pricing (per million tokens)
_INPUT_COST_PER_TOKEN = 15.0 / 1_000_000   # $15/M input tokens
_OUTPUT_COST_PER_TOKEN = 75.0 / 1_000_000  # $75/M output tokens

# IEC Cat 0-4 → BDDA 0-10 midpoint mapping
_IEC_TO_BDDA = {0: 0, 1: 1, 2: 3, 3: 6, 4: 9}


def iec_to_bdda(iec_cat: int) -> int:
    """Return midpoint BDDA score (0-10) for an IEC category (0-4)."""
    return _IEC_TO_BDDA.get(iec_cat, 0)


def load_and_resize_image(image_path: Path, max_edge: int = 1568) -> str:
    """Load image, resize if longest edge > max_edge, return raw base64 string (no data URI prefix)."""
    from PIL import Image
    with Image.open(image_path) as img:
        if img.mode != "RGB":
            img = img.convert("RGB")
        if max(img.size) > max_edge:
            img.thumbnail((max_edge, max_edge), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")


# ─── DATA STRUCTURES ──────────────────────────────────────────────────────────

@dataclass
class DefectFinding:
    defect_id: int
    defect_name: str
    iec_category: int
    bdda_score: int
    urgency: str
    zone: str
    position: str
    size_estimate: str
    confidence: float
    visual_description: str
    ndt_recommended: bool
    # Added by classify pipeline:
    image_path: str = ""
    turbine_id: str = ""
    blade: str = ""
    image_quality: str = "good"


@dataclass
class ClassifyResult:
    image_path: Path
    turbine_id: str
    blade: str
    zone: str
    position: str
    mission_folder: str
    defects: List[DefectFinding] = field(default_factory=list)
    image_quality: str = "good"
    image_notes: str = ""
    error: Optional[str] = None
    cost_usd: float = 0.0

    @property
    def max_category(self) -> int:
        if not self.defects:
            return 0
        return max(d.iec_category for d in self.defects)

    @property
    def has_critical(self) -> bool:
        return any(d.iec_category >= 3 for d in self.defects)


# ─── GEMINI API CLIENT ────────────────────────────────────────────────────────

def call_gemini_classify(
    image_path: Path,
    image_info: Dict,
    turbine_model: str,
    api_key: str,
    model: str = "gemini-2.5-pro-preview-06-05",
    max_retries: int = 3,
) -> Dict:
    """
    Call Gemini 2.5 Pro with full image for defect classification.
    Gemini handles the 45MP image natively — no tiling needed here.
    """
    try:
        import google.generativeai as genai
    except ImportError:
        raise RuntimeError("Install google-generativeai: pip install google-generativeai")

    genai.configure(api_key=api_key)
    model_instance = genai.GenerativeModel(model)

    # Build taxonomy block
    taxonomy_block = build_taxonomy_prompt_block()

    # Load image
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    prompt = CLASSIFY_USER_PROMPT.format(
        turbine_id=image_info["turbine_id"],
        turbine_model=turbine_model,
        blade=image_info["blade"],
        zone=image_info["zone"],
        position=image_info["position"],
        image_name=image_path.name,
        defect_hint=image_info.get("defect_hint", "Unknown"),
        taxonomy_block=taxonomy_block,
    )

    # Gemini content parts: text + image
    parts = [
        {"text": CLASSIFY_SYSTEM_PROMPT + "\n\n" + prompt},
        {
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": image_b64,
            }
        },
    ]

    for attempt in range(max_retries):
        try:
            response = model_instance.generate_content(
                parts,
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 2000,
                },
            )
            raw = response.text.strip()

            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            return json.loads(raw)

        except json.JSONDecodeError as e:
            if attempt == max_retries - 1:
                return {"error": f"JSON parse: {e}", "raw": raw[:200]}
            time.sleep(1)
        except Exception as e:
            err_str = str(e)
            if attempt == max_retries - 1:
                return {"error": err_str}
            # Rate limit backoff
            if "429" in err_str or "quota" in err_str.lower():
                time.sleep(30)
            else:
                time.sleep(2 ** attempt)

    return {"error": "Max retries exceeded"}


# ─── SINGLE IMAGE CLASSIFY ────────────────────────────────────────────────────

def classify_image(
    image_info: Dict,
    turbine_model: str,
    api_key: str,
    min_confidence: float = 0.3,
) -> ClassifyResult:
    """
    Classify defects in a single flagged image.

    image_info: dict with path, turbine_id, blade, zone, position, mission_folder, defect_hint
    """
    path = Path(image_info["path"])

    raw = call_gemini_classify(path, image_info, turbine_model, api_key)

    if "error" in raw:
        return ClassifyResult(
            image_path=path,
            turbine_id=image_info["turbine_id"],
            blade=image_info["blade"],
            zone=image_info["zone"],
            position=image_info["position"],
            mission_folder=image_info.get("mission_folder", ""),
            error=raw["error"],
        )

    defects = []
    for d in raw.get("defects", []):
        confidence = float(d.get("confidence", 0.0))
        if confidence < min_confidence:
            continue

        # Auto-derive urgency from category if not provided
        category = int(d.get("category", 1))
        urgency = d.get("urgency") or get_urgency_for_category(category)

        finding = DefectFinding(
            defect_id=int(d.get("defect_id", 0)),
            defect_name=d.get("defect_name", "Unknown"),
            category=category,
            urgency=urgency,
            zone=d.get("zone", image_info["zone"]),
            position=d.get("position", image_info["position"]),
            size_estimate=d.get("size_estimate", "unknown"),
            confidence=confidence,
            visual_description=d.get("visual_description", ""),
            ndt_recommended=bool(d.get("ndt_recommended", False)),
            image_path=str(path),
            turbine_id=image_info["turbine_id"],
            blade=image_info["blade"],
            image_quality=raw.get("image_quality", "good"),
        )
        defects.append(finding)

    return ClassifyResult(
        image_path=path,
        turbine_id=image_info["turbine_id"],
        blade=image_info["blade"],
        zone=image_info["zone"],
        position=image_info["position"],
        mission_folder=image_info.get("mission_folder", ""),
        defects=defects,
        image_quality=raw.get("image_quality", "good"),
        image_notes=raw.get("image_notes", ""),
    )


# ─── BATCH CLASSIFY ───────────────────────────────────────────────────────────

def classify_batch(
    flagged_images: List[Dict],
    turbine_model: str,
    api_key: str,
    delay_between_calls: float = 2.0,
    verbose: bool = True,
) -> List[ClassifyResult]:
    """
    Classify defects in all flagged images.

    flagged_images: list from triage output (only has_defect=True images)
    """
    results = []
    total = len(flagged_images)

    if verbose:
        print(f"\nClassifying {total} flagged images...")

    for i, img_info in enumerate(flagged_images):
        if verbose:
            print(f"  [{i+1}/{total}] {Path(img_info['path']).name} | B{img_info.get('blade','')} {img_info.get('zone','')} {img_info.get('position','')}")

        result = classify_image(img_info, turbine_model, api_key)
        results.append(result)

        if result.error:
            if verbose:
                print(f"    ERROR: {result.error}")
        elif result.defects:
            if verbose:
                for d in result.defects:
                    flag = " ⚠️ CRITICAL" if d.category >= 4 else ""
                    print(f"    → Cat{d.category} {d.defect_name} (conf={d.confidence:.2f}){flag}")
        else:
            if verbose:
                print(f"    → No defects found in classification (false positive in triage)")

        if delay_between_calls > 0:
            time.sleep(delay_between_calls)

    if verbose:
        total_defects = sum(len(r.defects) for r in results)
        critical = sum(1 for r in results if r.has_critical)
        print(f"\nClassification complete: {total_defects} defects found, {critical} images with Cat4+ findings")

    return results


def save_classify_results(results: List[ClassifyResult], output_path: Path):
    """Save classification results to JSON for analysis stage."""
    data = [
        {
            "image_path": str(r.image_path),
            "turbine_id": r.turbine_id,
            "blade": r.blade,
            "zone": r.zone,
            "position": r.position,
            "mission_folder": r.mission_folder,
            "image_quality": r.image_quality,
            "image_notes": r.image_notes,
            "error": r.error,
            "max_category": r.max_category,
            "defects": [
                {
                    "defect_id": d.defect_id,
                    "defect_name": d.defect_name,
                    "category": d.category,
                    "urgency": d.urgency,
                    "zone": d.zone,
                    "position": d.position,
                    "size_estimate": d.size_estimate,
                    "confidence": d.confidence,
                    "visual_description": d.visual_description,
                    "ndt_recommended": d.ndt_recommended,
                    "blade": r.blade,
                }
                for d in r.defects
            ],
        }
        for r in results
    ]

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Classification results saved: {output_path}")


def load_critical_findings(classify_json_path: Path, min_category: int = 4) -> List[Dict]:
    """Load only Cat 4+ findings for deep analysis."""
    with open(classify_json_path) as f:
        data = json.load(f)

    critical = []
    for img in data:
        for d in img.get("defects", []):
            if d["category"] >= min_category:
                critical.append({
                    **d,
                    "image_path": img["image_path"],
                    "turbine_id": img["turbine_id"],
                    "blade": img["blade"],
                    "zone": img["zone"],
                    "position": img["position"],
                    "image_quality": img["image_quality"],
                })
    return critical


if __name__ == "__main__":
    print("classify.py — Stage 2 Gemini 2.5 Pro classification module")
    print("Usage: import classify and call classify_batch(flagged_images, turbine_model, api_key)")
    print(f"API key expected in env: GOOGLE_API_KEY")

    key = os.environ.get("GOOGLE_API_KEY")
    if key:
        print("GOOGLE_API_KEY found in environment")
    else:
        print("GOOGLE_API_KEY not set — set it before running classification")
