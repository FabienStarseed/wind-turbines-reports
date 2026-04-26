"""
analyze.py — Stage 3: Deep analysis of Cat 4+ defects using Claude Opus 4.7
Provides root cause, failure risk, Vestas SMP recommendation, and cost estimate.

Only runs on Cat 4+ defects — ~10-20 findings per turbine.
"""

import os
import io
import json
import time
import base64
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

import anthropic

# ─── ANALYSIS PROMPT ─────────────────────────────────────────────────────────

ANALYZE_SYSTEM_PROMPT = """You are a senior structural engineer with 25 years specializing in wind turbine blade failure analysis.
You have worked with Vestas, Siemens Gamesa, and Enercon on blade failure investigations and root cause analysis.
You are deeply familiar with DNVGL-ST-0376, IEC 61400-23, GWO repair standards, and Vestas Standard Maintenance Procedures (SMP).
Your analyses inform turbine operator decisions on repair priority, safety stops, and maintenance budgets.
Be precise, professional, and conservative — when in doubt, escalate severity."""

ANALYZE_USER_PROMPT = """Review this Cat {category} defect finding from a drone inspection and provide a detailed structural engineering assessment.

TURBINE: {turbine_id} | Model: {turbine_model}
BLADE: {blade} | Zone: {zone} / {position}
DEFECT: {defect_name} (Category {category} — {urgency})
SIZE: {size_estimate}
CLASSIFICATION CONFIDENCE: {confidence:.0%}
VISUAL OBSERVATION: {visual_description}
{offshore_note}
Please provide a professional engineering assessment for the Vestas maintenance team:

1. ROOT CAUSE
   Most likely cause(s) of this defect, based on defect type, location, and visual characteristics.

2. FAILURE RISK
   If this defect is not repaired within the recommended timeframe:
   - What is the progression risk?
   - What failure mode could result?
   - What is the safety risk (Low / Medium / High / Critical)?

3. VESTAS STANDARD REFERENCE
   What does Vestas SMP / DNVGL-ST-0376 / GWO standard specify for this defect type?
   What is the standard repair method?

4. RECOMMENDED ACTION
   Exact repair action in professional language suitable for a Vestas work order.

5. REPAIR TIMEFRAME
   Recommended timeline: Immediate (stop turbine) / Within 30 days / Within 3 months / Within 6 months / Next scheduled service

6. ESTIMATED REPAIR COST
   Rough cost range in USD for this type of repair (field repair vs. full replacement context).

7. ENGINEER REVIEW REQUIRED
   Does this defect require review by a structural engineer before repair? (Yes / No)
   Reason if Yes.

Return ONLY valid JSON, no other text:
{{
  "root_cause": "<string>",
  "failure_risk": {{
    "progression_risk": "<string>",
    "failure_mode": "<string>",
    "safety_risk": "Low | Medium | High | Critical"
  }},
  "vestas_standard": "<string>",
  "recommended_action": "<string>",
  "repair_timeframe": "Immediate | 30 days | 3 months | 6 months | Next service",
  "estimated_cost_usd": "<range string, e.g. $5,000–$15,000>",
  "engineer_review_required": true | false,
  "engineer_review_reason": "<string or null>",
  "analysis_confidence": 0.0-1.0,
  "additional_notes": "<any other professional observations>"
}}"""


# ─── DATA STRUCTURES ──────────────────────────────────────────────────────────

@dataclass
class DeepAnalysis:
    defect_name: str
    category: int
    blade: str
    zone: str
    position: str
    root_cause: str
    failure_risk: Dict
    vestas_standard: str
    recommended_action: str
    repair_timeframe: str
    estimated_cost_usd: str
    engineer_review_required: bool
    engineer_review_reason: Optional[str]
    analysis_confidence: float
    additional_notes: str
    image_path: str = ""
    turbine_id: str = ""
    cost_usd: float = 0.0
    error: Optional[str] = None


# ─── CLAUDE API CLIENT ────────────────────────────────────────────────────────

# Claude Opus 4.7 pricing (per million tokens)
_INPUT_COST_PER_TOKEN  = 5.00 / 1_000_000
_OUTPUT_COST_PER_TOKEN = 25.00 / 1_000_000

_MODEL = "claude-opus-4-7"


def load_and_encode_image(image_path: Path, max_edge: int = 1568) -> str:
    """Load an image, resize to max_edge on longest side, return base64 JPEG."""
    from PIL import Image
    with Image.open(image_path) as img:
        if img.mode != "RGB":
            img = img.convert("RGB")
        if max(img.size) > max_edge:
            img.thumbnail((max_edge, max_edge), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return base64.b64encode(buf.getvalue()).decode()


def call_claude_analyze(
    defect: Dict,
    turbine_model: str,
    api_key: str,
    include_image: bool = True,
    max_retries: int = 3,
    location_type: str = "onshore",
) -> Dict:
    client = anthropic.Anthropic(api_key=api_key)

    offshore_note = (
        "IMPORTANT: This is an OFFSHORE turbine. Repair access is significantly more expensive and difficult. "
        "Weight this in repair urgency and timeframe recommendations."
        if location_type == "offshore"
        else ""
    )

    prompt = ANALYZE_USER_PROMPT.format(
        turbine_id=defect.get("turbine_id", "Unknown"),
        turbine_model=turbine_model,
        blade=defect.get("blade", "Unknown"),
        zone=defect.get("zone", "Unknown"),
        position=defect.get("position", "Unknown"),
        defect_name=defect["defect_name"],
        category=defect.get("iec_category", defect.get("category", 0)),
        urgency=defect.get("urgency", "URGENT"),
        size_estimate=defect.get("size_estimate", "Unknown"),
        confidence=float(defect.get("confidence", 0.0)),
        visual_description=defect.get("visual_description", "No description"),
        offshore_note=offshore_note,
    )

    content = []

    if include_image and defect.get("image_path"):
        img_path = Path(defect["image_path"])
        if img_path.exists():
            try:
                b64 = load_and_encode_image(img_path)
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": b64,
                    },
                })
            except Exception:
                pass

    content.append({"type": "text", "text": prompt})

    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=_MODEL,
                max_tokens=1500,
                system=ANALYZE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
            )
            raw = response.content[0].text.strip()

            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            parsed = json.loads(raw)
            parsed["input_tokens"] = response.usage.input_tokens
            parsed["output_tokens"] = response.usage.output_tokens
            return parsed

        except json.JSONDecodeError as e:
            if attempt == max_retries - 1:
                return {"error": f"JSON parse: {e}"}
            time.sleep(1)
        except anthropic.RateLimitError:
            sleep_time = (2 ** attempt) * 10
            if attempt == max_retries - 1:
                return {"error": "rate_limit"}
            time.sleep(sleep_time)
        except anthropic.APIStatusError as e:
            if e.status_code in (500, 503):
                if attempt == max_retries - 1:
                    return {"error": f"server_error: {e}"}
                time.sleep(2 ** attempt)
            else:
                if attempt == max_retries - 1:
                    return {"error": str(e)}
                time.sleep(2 ** attempt)
        except Exception as e:
            if attempt == max_retries - 1:
                return {"error": str(e)}
            time.sleep(2 ** attempt)

    return {"error": "Max retries exceeded"}


# ─── SINGLE DEFECT ANALYSIS ──────────────────────────────────────────────────

def analyze_defect(
    defect: Dict,
    turbine_model: str,
    api_key: str,
    include_image: bool = True,
) -> DeepAnalysis:
    raw = call_claude_analyze(
        defect, turbine_model, api_key, include_image,
        location_type=defect.get("location_type", "onshore"),
    )

    if "error" in raw:
        return DeepAnalysis(
            defect_name=defect["defect_name"],
            category=defect.get("iec_category", defect.get("category", 0)),
            blade=defect.get("blade", ""),
            zone=defect.get("zone", ""),
            position=defect.get("position", ""),
            root_cause="",
            failure_risk={},
            vestas_standard="",
            recommended_action="",
            repair_timeframe="",
            estimated_cost_usd="",
            engineer_review_required=True,
            engineer_review_reason="Analysis failed — manual review required",
            analysis_confidence=0.0,
            additional_notes="",
            image_path=defect.get("image_path", ""),
            turbine_id=defect.get("turbine_id", ""),
            cost_usd=0.0,
            error=raw["error"],
        )

    cost_usd = (
        raw.get("input_tokens", 0) * _INPUT_COST_PER_TOKEN
        + raw.get("output_tokens", 0) * _OUTPUT_COST_PER_TOKEN
    )

    return DeepAnalysis(
        defect_name=defect["defect_name"],
        category=defect.get("iec_category", defect.get("category", 0)),
        blade=defect.get("blade", ""),
        zone=defect.get("zone", ""),
        position=defect.get("position", ""),
        root_cause=raw.get("root_cause", ""),
        failure_risk=raw.get("failure_risk", {}),
        vestas_standard=raw.get("vestas_standard", ""),
        recommended_action=raw.get("recommended_action", ""),
        repair_timeframe=raw.get("repair_timeframe", ""),
        estimated_cost_usd=raw.get("estimated_cost_usd", ""),
        engineer_review_required=bool(raw.get("engineer_review_required", False)),
        engineer_review_reason=raw.get("engineer_review_reason"),
        analysis_confidence=float(raw.get("analysis_confidence", 0.0)),
        additional_notes=raw.get("additional_notes", ""),
        image_path=defect.get("image_path", ""),
        turbine_id=defect.get("turbine_id", ""),
        cost_usd=cost_usd,
    )


# ─── BATCH ANALYSIS ──────────────────────────────────────────────────────────

def analyze_critical_defects(
    critical_findings: List[Dict],
    turbine_model: str,
    api_key: str,
    delay_between_calls: float = 2.0,
    verbose: bool = True,
) -> Tuple[List[DeepAnalysis], float]:
    results = []
    total = len(critical_findings)

    if verbose:
        print(f"\nDeep analysis: {total} critical findings (Cat 4+, model: {_MODEL})...")

    for i, defect in enumerate(critical_findings):
        if verbose:
            print(f"  [{i+1}/{total}] Cat{defect.get('iec_category', defect.get('category', 0))} {defect['defect_name']} | B{defect.get('blade','')} {defect.get('zone','')} {defect.get('position','')}")

        analysis = analyze_defect(defect, turbine_model, api_key)
        results.append(analysis)

        if analysis.error:
            if verbose:
                print(f"    ERROR: {analysis.error}")
        else:
            if verbose:
                safety = analysis.failure_risk.get("safety_risk", "Unknown")
                print(f"    Safety risk: {safety} | Review needed: {analysis.engineer_review_required}")

        if delay_between_calls > 0:
            time.sleep(delay_between_calls)

    if verbose:
        review_needed = sum(1 for a in results if a.engineer_review_required)
        critical_risk = sum(1 for a in results if a.failure_risk.get("safety_risk") == "Critical")
        total_cost = sum(a.cost_usd for a in results)
        print(f"\nAnalysis complete: {review_needed}/{total} need engineer review, {critical_risk} critical safety risk")
        print(f"Analyze cost: ${total_cost:.4f}")

    total_cost = sum(a.cost_usd for a in results)
    return results, total_cost


def save_analysis_results(results: List[DeepAnalysis], output_path: Path):
    data = [
        {
            "defect_name": a.defect_name,
            "category": a.category,
            "turbine_id": a.turbine_id,
            "blade": a.blade,
            "zone": a.zone,
            "position": a.position,
            "image_path": a.image_path,
            "root_cause": a.root_cause,
            "failure_risk": a.failure_risk,
            "vestas_standard": a.vestas_standard,
            "recommended_action": a.recommended_action,
            "repair_timeframe": a.repair_timeframe,
            "estimated_cost_usd": a.estimated_cost_usd,
            "engineer_review_required": a.engineer_review_required,
            "engineer_review_reason": a.engineer_review_reason,
            "analysis_confidence": a.analysis_confidence,
            "additional_notes": a.additional_notes,
            "cost_usd": a.cost_usd,
            "error": a.error,
        }
        for a in results
    ]

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Analysis results saved: {output_path}")


if __name__ == "__main__":
    print("analyze.py — Stage 3 Claude Opus 4.7 deep analysis module")
    key = os.environ.get("ANTHROPIC_API_KEY")
    print("ANTHROPIC_API_KEY found" if key else "ANTHROPIC_API_KEY not set")
