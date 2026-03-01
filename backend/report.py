"""
report.py — Stage 4: Professional PDF report generation using WeasyPrint
Assembles triage + classify + analyze JSON data into a Vestas-standard PDF.

Pipeline:
  triage JSON + classify JSON + analyze JSON → report.html → PDF
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    HAS_JINJA = True
except ImportError:
    HAS_JINJA = False

# WeasyPrint requires system GTK/Pango libs — lazy import inside generate_pdf()
HAS_WEASYPRINT = None  # checked on first use


# ─── SEVERITY CONFIG ──────────────────────────────────────────────────────────

SEVERITY_COLORS = {
    1: {"bg": "#dcfce7", "text": "#166534", "badge": "#22c55e", "label": "Cat 1 — Cosmetic"},
    2: {"bg": "#fef9c3", "text": "#854d0e", "badge": "#eab308", "label": "Cat 2 — Minor"},
    3: {"bg": "#fff7ed", "text": "#9a3412", "badge": "#f97316", "label": "Cat 3 — Planned"},
    4: {"bg": "#fee2e2", "text": "#991b1b", "badge": "#ef4444", "label": "Cat 4 — Urgent"},
    5: {"bg": "#fce7f3", "text": "#9d174d", "badge": "#7f1d1d", "label": "Cat 5 — Critical"},
}

URGENCY_COLORS = {
    "LOG":       "#22c55e",
    "MONITOR":   "#eab308",
    "PLANNED":   "#f97316",
    "URGENT":    "#ef4444",
    "IMMEDIATE": "#7f1d1d",
}

CONDITION_RATINGS = {
    "A": {"label": "Good", "color": "#22c55e", "desc": "No critical defects. Minor cosmetic issues only."},
    "B": {"label": "Fair", "color": "#eab308", "desc": "Minor to moderate defects. Planned maintenance required."},
    "C": {"label": "Poor", "color": "#f97316", "desc": "High-priority defects found. Urgent repair needed."},
    "D": {"label": "Critical", "color": "#7f1d1d", "desc": "Critical defects present. Consider stopping turbine."},
}


# ─── DATA LOADING ─────────────────────────────────────────────────────────────

def load_triage_json(path: Path) -> Dict:
    with open(path) as f:
        return json.load(f)


def load_classify_json(path: Path) -> List[Dict]:
    with open(path) as f:
        return json.load(f)


def load_analyze_json(path: Path) -> List[Dict]:
    with open(path) as f:
        return json.load(f)


# ─── DATA ASSEMBLY ────────────────────────────────────────────────────────────

def compute_condition_rating(defects_by_cat: Dict[int, int]) -> str:
    """Derive overall condition rating A–D from defect category counts."""
    if defects_by_cat.get(5, 0) > 0:
        return "D"
    elif defects_by_cat.get(4, 0) > 0:
        return "C"
    elif defects_by_cat.get(3, 0) >= 3:
        return "C"
    elif defects_by_cat.get(3, 0) > 0 or defects_by_cat.get(2, 0) > 3:
        return "B"
    else:
        return "A"


def build_report_data(
    turbine_meta: Dict,
    triage_data: Optional[Dict],
    classify_data: List[Dict],
    analyze_data: List[Dict],
) -> Dict:
    """
    Assemble all pipeline data into a single dict for Jinja2 rendering.

    turbine_meta: {
        turbine_id, site_name, country, turbine_model, hub_height_m,
        rotor_diameter_m, blade_length_m, inspection_date, inspector_name,
        drone_model, weather, wind_speed_ms, temperature_c, visibility_km,
        gps_lat, gps_lon, notes, company_name, report_ref
    }
    """

    # ── Defect stats ──
    all_defects = []
    for img in classify_data:
        for d in img.get("defects", []):
            all_defects.append({
                **d,
                "image_path": img["image_path"],
                "turbine_id": img["turbine_id"],
                "image_quality": img.get("image_quality", "good"),
            })

    defects_by_cat = {}
    for d in all_defects:
        cat = d["category"]
        defects_by_cat[cat] = defects_by_cat.get(cat, 0) + 1

    defects_by_blade = {}
    for d in all_defects:
        blade = d.get("blade", "?")
        if blade not in defects_by_blade:
            defects_by_blade[blade] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, "total": 0}
        defects_by_blade[blade][d["category"]] += 1
        defects_by_blade[blade]["total"] += 1

    # Sort blades alphabetically
    blades_sorted = sorted(defects_by_blade.keys())

    # ── Critical findings (Cat 4+) ──
    critical_findings = [d for d in all_defects if d["category"] >= 4]

    # ── Build analyze map: defect_name+blade+zone → analysis ──
    analyze_map = {}
    for a in analyze_data:
        key = f"{a['defect_name']}|{a.get('blade', '')}|{a.get('zone', '')}"
        analyze_map[key] = a

    # ── Per-blade defect cards ──
    blade_findings = {}
    defect_counter = {}  # blade → counter for defect IDs
    for img in classify_data:
        blade = img["blade"]
        if blade not in blade_findings:
            blade_findings[blade] = []
            defect_counter[blade] = 0

        for d in img.get("defects", []):
            defect_counter[blade] += 1
            defect_id = f"{blade}-{d.get('zone','?')}-{defect_counter[blade]:03d}"

            # Lookup deep analysis if available
            key = f"{d['defect_name']}|{blade}|{d.get('zone', '')}"
            analysis = analyze_map.get(key)

            blade_findings[blade].append({
                "defect_id": defect_id,
                "defect_name": d["defect_name"],
                "category": d["category"],
                "urgency": d.get("urgency", ""),
                "zone": d.get("zone", img["zone"]),
                "position": d.get("position", img["position"]),
                "size_estimate": d.get("size_estimate", "unknown"),
                "confidence": d.get("confidence", 0.0),
                "visual_description": d.get("visual_description", ""),
                "ndt_recommended": d.get("ndt_recommended", False),
                "image_path": img["image_path"],
                "image_quality": img.get("image_quality", "good"),
                "severity_style": SEVERITY_COLORS.get(d["category"], SEVERITY_COLORS[1]),
                "urgency_color": URGENCY_COLORS.get(d.get("urgency", "LOG"), "#22c55e"),
                "analysis": analysis,
            })

    # Sort each blade's findings by category desc
    for blade in blade_findings:
        blade_findings[blade].sort(key=lambda x: -x["category"])

    # ── Action matrix (P1–P4 priorities) ──
    action_matrix = []
    for blade, findings in blade_findings.items():
        for f in findings:
            if f["category"] >= 5:
                priority = "P1"
                action_label = "Immediate action / Stop turbine"
            elif f["category"] >= 4:
                priority = "P2"
                action_label = "Repair within 3 months"
            elif f["category"] >= 3:
                priority = "P3"
                action_label = "Schedule at next service window"
            else:
                priority = "P4"
                action_label = "Monitor at next annual inspection"

            action_matrix.append({
                "priority": priority,
                "action": action_label,
                "blade": blade,
                "defect_id": f["defect_id"],
                "defect_name": f["defect_name"],
                "category": f["category"],
                "urgency": f["urgency"],
                "zone": f"{f['zone']} / {f['position']}",
                "timeframe": f["analysis"]["repair_timeframe"] if f["analysis"] else "",
                "severity_style": f["severity_style"],
            })

    action_matrix.sort(key=lambda x: x["priority"])

    # ── Triage stats ──
    triage_stats = None
    if triage_data:
        triage_stats = {
            "total": triage_data.get("total_images", 0),
            "flagged": triage_data.get("flagged_images", 0),
            "clean": triage_data.get("clean_images", 0),
            "errors": triage_data.get("error_images", 0),
            "flag_rate": triage_data.get("flag_rate", 0.0),
        }

    # ── Condition rating ──
    condition = compute_condition_rating(defects_by_cat)

    # ── Report reference ──
    report_ref = turbine_meta.get("report_ref") or f"BDDA-{turbine_meta.get('turbine_id','???')}-{datetime.now().strftime('%Y%m%d')}"
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    return {
        # Metadata
        "turbine": turbine_meta,
        "report_ref": report_ref,
        "generated_at": generated_at,
        "inspection_date_fmt": turbine_meta.get("inspection_date", ""),

        # Summary stats
        "total_defects": len(all_defects),
        "defects_by_cat": defects_by_cat,
        "defects_by_blade": defects_by_blade,
        "blades_sorted": blades_sorted,
        "critical_count": len(critical_findings),
        "critical_findings": critical_findings[:5],  # top 5 for executive summary

        # Condition
        "condition": condition,
        "condition_info": CONDITION_RATINGS[condition],

        # Findings per blade
        "blade_findings": blade_findings,
        "all_defects": all_defects,

        # Action matrix
        "action_matrix": action_matrix,

        # Analysis results
        "analyze_data": analyze_data,
        "engineer_review_count": sum(1 for a in analyze_data if a.get("engineer_review_required")),

        # Triage stats
        "triage_stats": triage_stats,

        # Style helpers
        "severity_colors": SEVERITY_COLORS,
        "urgency_colors": URGENCY_COLORS,

        # Cat range for template loops
        "cat_range": [1, 2, 3, 4, 5],
    }


# ─── HTML RENDERING ───────────────────────────────────────────────────────────

def render_html(report_data: Dict, templates_dir: Path) -> str:
    """Render the report HTML from Jinja2 templates."""
    if not HAS_JINJA:
        raise RuntimeError("Install jinja2: pip install jinja2")

    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html"]),
    )

    # Add custom filters
    def confidence_label(conf: float) -> str:
        if conf >= 0.8:
            return "High"
        elif conf >= 0.55:
            return "Medium"
        return "Low"

    def format_cost(cost_str: str) -> str:
        return cost_str if cost_str else "N/A"

    env.filters["confidence_label"] = confidence_label
    env.filters["format_cost"] = format_cost

    template = env.get_template("report.html")
    return template.render(**report_data)


# ─── PDF GENERATION ───────────────────────────────────────────────────────────

def generate_pdf(html_content: str, output_path: Path, css_path: Optional[Path] = None) -> Path:
    """Convert HTML to PDF using xhtml2pdf (pure Python, no system deps required)."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Primary: xhtml2pdf — zero system dependencies, works on Railway out of the box
    try:
        from xhtml2pdf import pisa
        with open(output_path, "wb") as f:
            result = pisa.CreatePDF(html_content, dest=f)
        if result.err:
            raise RuntimeError(f"xhtml2pdf render error (code {result.err})")
        return output_path
    except ImportError:
        pass  # Fall through to WeasyPrint

    # Fallback: WeasyPrint (best quality, but requires GTK/Pango system libs)
    try:
        from weasyprint import HTML as WeasyHTML, CSS as WeasyCSS
        stylesheets = []
        if css_path and Path(css_path).exists():
            stylesheets.append(WeasyCSS(filename=str(css_path)))
        WeasyHTML(string=html_content).write_pdf(
            str(output_path),
            stylesheets=stylesheets,
        )
        return output_path
    except Exception as e:
        raise RuntimeError(
            f"PDF generation failed. Install xhtml2pdf or weasyprint. Last error: {e}"
        )


# ─── FULL PIPELINE ────────────────────────────────────────────────────────────

def build_report(
    turbine_meta: Dict,
    classify_json_path: Path,
    output_pdf_path: Path,
    triage_json_path: Optional[Path] = None,
    analyze_json_path: Optional[Path] = None,
    templates_dir: Optional[Path] = None,
    save_html: bool = False,
    verbose: bool = True,
) -> Path:
    """
    Full report pipeline: load data → render HTML → generate PDF.

    Returns path to generated PDF.
    """
    if templates_dir is None:
        templates_dir = Path(__file__).parent.parent / "templates"

    css_path = templates_dir / "report.css"

    if verbose:
        print(f"\nBuilding report for turbine {turbine_meta.get('turbine_id')}...")

    # Load data
    classify_data = load_classify_json(classify_json_path)

    triage_data = None
    if triage_json_path and Path(triage_json_path).exists():
        triage_data = load_triage_json(triage_json_path)

    analyze_data = []
    if analyze_json_path and Path(analyze_json_path).exists():
        analyze_data = load_analyze_json(analyze_json_path)

    if verbose:
        total = sum(len(img.get("defects", [])) for img in classify_data)
        print(f"  Loaded: {len(classify_data)} classified images, {total} defects, {len(analyze_data)} deep analyses")

    # Build data dict
    report_data = build_report_data(turbine_meta, triage_data, classify_data, analyze_data)

    if verbose:
        print(f"  Condition: {report_data['condition']} | Total defects: {report_data['total_defects']} | Critical: {report_data['critical_count']}")

    # Render HTML
    html_content = render_html(report_data, templates_dir)

    if save_html:
        html_path = Path(output_pdf_path).with_suffix(".html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        if verbose:
            print(f"  HTML saved: {html_path}")

    # Generate PDF
    if verbose:
        print(f"  Generating PDF...")

    pdf_path = generate_pdf(html_content, output_pdf_path, css_path)

    if verbose:
        size_kb = pdf_path.stat().st_size // 1024
        print(f"  PDF generated: {pdf_path} ({size_kb} KB)")

    return pdf_path


# ─── SAMPLE DATA FOR TESTING ─────────────────────────────────────────────────

def make_sample_turbine_meta(turbine_id: str = "JAP19") -> Dict:
    return {
        "turbine_id": turbine_id,
        "site_name": "Tomamae Wind Farm",
        "country": "Japan",
        "turbine_model": "Vestas V90-2.0 MW",
        "hub_height_m": 80,
        "rotor_diameter_m": 90,
        "blade_length_m": 44,
        "inspection_date": "2025-11-30",
        "inspector_name": "Fabien",
        "drone_model": "DJI Matrice 300 RTK",
        "camera": "DJI Zenmuse P1 45MP",
        "weather": "Clear, sunny",
        "wind_speed_ms": 4.2,
        "temperature_c": 12,
        "visibility_km": 20,
        "gps_lat": 44.3123,
        "gps_lon": 141.6789,
        "notes": "All three blades inspected. Blade B tip slightly restricted by wind gusts at time of inspection.",
        "company_name": "DroneWind Asia",
        "report_ref": None,  # auto-generated
    }


def make_sample_classify_data() -> List[Dict]:
    """Minimal sample classification data for testing report generation."""
    return [
        {
            "image_path": "/data/JAP19/blade_A/LE_Mid_001.jpg",
            "turbine_id": "JAP19",
            "blade": "A",
            "zone": "LE",
            "position": "Mid",
            "mission_folder": "DJI_202511301000_001_C-N-A-LE-N",
            "image_quality": "good",
            "image_notes": "",
            "error": None,
            "max_category": 3,
            "defects": [
                {
                    "defect_id": 3,
                    "defect_name": "Leading Edge Erosion — Stage 3",
                    "category": 3,
                    "urgency": "PLANNED",
                    "zone": "LE",
                    "position": "Mid",
                    "size_estimate": "large (>30cm)",
                    "confidence": 0.88,
                    "visual_description": "Deep pitting and exposed composite material visible along the leading edge mid-span section. Paint layer fully removed over approximately 40cm.",
                    "ndt_recommended": False,
                    "blade": "A",
                }
            ],
        },
        {
            "image_path": "/data/JAP19/blade_B/TE_Root_001.jpg",
            "turbine_id": "JAP19",
            "blade": "B",
            "zone": "TE",
            "position": "Root",
            "mission_folder": "DJI_202511301030_002_C-N-B-TE-R",
            "image_quality": "good",
            "image_notes": "",
            "error": None,
            "max_category": 4,
            "defects": [
                {
                    "defect_id": 18,
                    "defect_name": "Bond Line Crack",
                    "category": 4,
                    "urgency": "URGENT",
                    "zone": "TE",
                    "position": "Root",
                    "size_estimate": "medium (5-30cm)",
                    "confidence": 0.91,
                    "visual_description": "Thin dark crack line visible along the trailing edge adhesive joint at root section, approximately 15cm in length.",
                    "ndt_recommended": True,
                    "blade": "B",
                }
            ],
        },
        {
            "image_path": "/data/JAP19/blade_C/LE_Tip_001.jpg",
            "turbine_id": "JAP19",
            "blade": "C",
            "zone": "LE",
            "position": "Tip",
            "mission_folder": "DJI_202511301100_003_C-N-C-LE-T",
            "image_quality": "acceptable",
            "image_notes": "Slight motion blur at tip due to wind.",
            "error": None,
            "max_category": 2,
            "defects": [
                {
                    "defect_id": 1,
                    "defect_name": "Leading Edge Erosion — Stage 1",
                    "category": 2,
                    "urgency": "MONITOR",
                    "zone": "LE",
                    "position": "Tip",
                    "size_estimate": "medium (5-30cm)",
                    "confidence": 0.74,
                    "visual_description": "Surface roughening and mild pitting at LE tip. Paint gloss loss over 20cm section.",
                    "ndt_recommended": False,
                    "blade": "C",
                }
            ],
        },
    ]


def make_sample_analyze_data() -> List[Dict]:
    return [
        {
            "defect_name": "Bond Line Crack",
            "category": 4,
            "turbine_id": "JAP19",
            "blade": "B",
            "zone": "TE",
            "position": "Root",
            "image_path": "/data/JAP19/blade_B/TE_Root_001.jpg",
            "root_cause": "Cyclic fatigue loading at root transition zone causing adhesive disbond between PS and SS shells at the trailing edge bond line. High bending stress concentration at root is the primary driver.",
            "failure_risk": {
                "progression_risk": "Crack will propagate under continued operational loads; high probability of full TE separation within 6–12 months without intervention.",
                "failure_mode": "Trailing Edge Separation — structural shell integrity loss leading to aerodynamic imbalance and potential blade failure",
                "safety_risk": "High"
            },
            "vestas_standard": "DNVGL-ST-0376 Section 8.3: Bond line cracks classified as Category 4 require priority repair. GWO Blade Repair Standard V5 specifies injection repair with approved structural adhesive and CFRP patch overlay for TE bond line cracks >10cm.",
            "recommended_action": "Immediate NDT inspection to determine crack depth and extent. Schedule priority repair within 3 months: injection of Sikaflex-552 AT or equivalent structural adhesive, followed by CFRP patch overlay per GWO repair protocol. Monthly visual monitoring until repair is completed.",
            "repair_timeframe": "30 days",
            "estimated_cost_usd": "$8,000–$18,000",
            "engineer_review_required": True,
            "engineer_review_reason": "Bond line cracks at root transition require structural engineer sign-off per DNVGL-ST-0376. NDT results must be reviewed before repair authorization.",
            "analysis_confidence": 0.87,
            "additional_notes": "Root transition zone is the highest fatigue stress area per NREL research. Early intervention critical. Monitor adjacent PS/SS surface for delamination signs.",
            "error": None,
        }
    ]


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    print("report.py — Stage 4 WeasyPrint PDF report module")

    if not HAS_JINJA:
        print("WARNING: jinja2 not installed — pip install jinja2")
    else:
        print("jinja2 OK")

    # Test weasyprint import separately
    try:
        from weasyprint import HTML as _W
        print("weasyprint OK")
    except (ImportError, OSError) as e:
        print(f"WARNING: weasyprint unavailable — {e}")

    # Quick data assembly test (no PDF generation)
    print("\nTesting data assembly with sample data...")
    meta = make_sample_turbine_meta()
    classify = make_sample_classify_data()
    analyze = make_sample_analyze_data()
    data = build_report_data(meta, None, classify, analyze)

    print(f"  Turbine: {data['turbine']['turbine_id']}")
    print(f"  Condition: {data['condition']} — {data['condition_info']['label']}")
    print(f"  Total defects: {data['total_defects']}")
    print(f"  Defects by cat: {data['defects_by_cat']}")
    print(f"  Blades: {data['blades_sorted']}")
    print(f"  Action matrix: {len(data['action_matrix'])} items")
    print(f"  Engineer reviews: {data['engineer_review_count']}")
    print("\nData assembly OK.")
