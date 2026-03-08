"""
report.py — Stage 4: Professional PDF report generation using fpdf2
Assembles triage + classify + analyze JSON data into an AWID branded PDF.

Pipeline:
  triage JSON + classify JSON + analyze JSON → BDDAReport (fpdf2) → PDF
"""

import json
import io
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from fpdf import FPDF

try:
    from PIL import Image as PILImage
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


# ─── FONT CONFIG ──────────────────────────────────────────────────────────────

FONT_DIR = Path(__file__).parent.parent / "assets" / "fonts"


# ─── SEVERITY CONFIG ──────────────────────────────────────────────────────────

# Legacy hex-based dict kept for build_report_data() severity_style field
SEVERITY_COLORS = {
    1: {"bg": "#dcfce7", "text": "#166534", "badge": "#22c55e", "label": "Cat 1 — Cosmetic"},
    2: {"bg": "#fef9c3", "text": "#854d0e", "badge": "#eab308", "label": "Cat 2 — Minor"},
    3: {"bg": "#fff7ed", "text": "#9a3412", "badge": "#f97316", "label": "Cat 3 — Planned"},
    4: {"bg": "#fee2e2", "text": "#991b1b", "badge": "#ef4444", "label": "Cat 4 — Urgent"},
    5: {"bg": "#fce7f3", "text": "#9d174d", "badge": "#7f1d1d", "label": "Cat 5 — Critical"},
}

# IEC 0-4 severity colours for fpdf2 rendering (RGB tuples)
SEVERITY_COLORS_IEC = {
    0: {"rgb": (34, 197, 94),   "label": "Cat 0 — No Action",  "text_rgb": (20, 83, 45)},
    1: {"rgb": (234, 179, 8),   "label": "Cat 1 — Log",         "text_rgb": (133, 77, 14)},
    2: {"rgb": (249, 115, 22),  "label": "Cat 2 — Monitor",     "text_rgb": (154, 52, 18)},
    3: {"rgb": (239, 68, 68),   "label": "Cat 3 — Planned",     "text_rgb": (153, 27, 27)},
    4: {"rgb": (127, 29, 29),   "label": "Cat 4 — Urgent",      "text_rgb": (255, 255, 255)},
}

URGENCY_COLORS = {
    "LOG":       "#22c55e",
    "MONITOR":   "#eab308",
    "PLANNED":   "#f97316",
    "URGENT":    "#ef4444",
    "IMMEDIATE": "#7f1d1d",
}

CONDITION_RATINGS = {
    "A": {"label": "Good",     "color": "#22c55e", "desc": "No critical defects. Minor cosmetic issues only."},
    "B": {"label": "Fair",     "color": "#eab308", "desc": "Minor to moderate defects. Planned maintenance required."},
    "C": {"label": "Poor",     "color": "#f97316", "desc": "High-priority defects found. Urgent repair needed."},
    "D": {"label": "Critical", "color": "#7f1d1d", "desc": "Critical defects present. Consider stopping turbine."},
}

# Condition rating RGB colours for fpdf2
CONDITION_COLORS_RGB = {
    "A": (34, 197, 94),    # green
    "B": (234, 179, 8),    # yellow
    "C": (249, 115, 22),   # orange
    "D": (127, 29, 29),    # dark red
}

CONDITION_TEXT_RGB = {
    "A": (20, 83, 45),
    "B": (133, 77, 14),
    "C": (154, 52, 18),
    "D": (255, 255, 255),
}

# Brand palette — professional wind energy / high-tech
BRAND_NAVY   = (15, 50, 90)
BRAND_STEEL  = (0, 100, 160)
BRAND_LIGHT  = (220, 235, 248)
BRAND_ACCENT = (0, 150, 200)
BRAND_GREY   = (100, 100, 100)

# Zone colours for blade map (keyed -1 to 4; -1 = no defects)
ZONE_COLORS_IEC = {
    -1: (230, 230, 230),  # grey — no defects
    0:  (34, 197, 94),    # green
    1:  (234, 179, 8),    # yellow
    2:  (249, 115, 22),   # orange
    3:  (239, 68, 68),    # red
    4:  (127, 29, 29),    # dark red
}


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def hex_to_rgb(hex_color: str) -> tuple:
    """Convert '#fee2e2' to (254, 226, 226) for fpdf2 set_fill_color()."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def _confidence_label(conf: float) -> str:
    if conf >= 0.8:
        return "High"
    elif conf >= 0.55:
        return "Medium"
    return "Low"


def _worst_cat_in_zone(defects: list, zone: str, position: str) -> int:
    """Return worst IEC category (0-4) for a zone+position, or -1 if no defects."""
    matches = [
        d.get("category", 0)
        for d in defects
        if d.get("zone") == zone and d.get("position") == position
    ]
    return max(matches) if matches else -1


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
    """Derive overall condition rating A-D from defect category counts."""
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
    Assemble all pipeline data into a single dict for PDF rendering.

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

    # Normalize key: classify.py saves "iec_category", legacy/sample data uses "category"
    for d in all_defects:
        d.setdefault("category", d.get("iec_category", 0))

    defects_by_cat = {}
    for d in all_defects:
        cat = d["category"]
        defects_by_cat[cat] = defects_by_cat.get(cat, 0) + 1

    defects_by_blade = {}
    for d in all_defects:
        blade = d.get("blade", "?")
        if blade not in defects_by_blade:
            defects_by_blade[blade] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, "total": 0}
        cat = d["category"]
        if cat in defects_by_blade[blade]:
            defects_by_blade[blade][cat] += 1
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

            # Normalize category key for this defect dict
            cat = d.get("category", d.get("iec_category", 0))

            # Lookup deep analysis if available
            key = f"{d['defect_name']}|{blade}|{d.get('zone', '')}"
            analysis = analyze_map.get(key)

            blade_findings[blade].append({
                "defect_id": defect_id,
                "defect_name": d["defect_name"],
                "category": cat,
                "urgency": d.get("urgency", ""),
                "zone": d.get("zone", img["zone"]),
                "position": d.get("position", img["position"]),
                "size_estimate": d.get("size_estimate", "unknown"),
                "confidence": d.get("confidence", 0.0),
                "visual_description": d.get("visual_description", ""),
                "ndt_recommended": d.get("ndt_recommended", False),
                "image_path": img["image_path"],
                "image_quality": img.get("image_quality", "good"),
                "severity_style": SEVERITY_COLORS.get(cat, SEVERITY_COLORS[1]),
                "urgency_color": URGENCY_COLORS.get(d.get("urgency", "LOG"), "#22c55e"),
                "analysis": analysis,
            })

    # Sort each blade's findings by category desc
    for blade in blade_findings:
        blade_findings[blade].sort(key=lambda x: -x["category"])

    # ── Action matrix (P1-P4 priorities) ──
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

        # Style helpers (legacy — for backward compat)
        "severity_colors": SEVERITY_COLORS,
        "urgency_colors": URGENCY_COLORS,

        # Cat range
        "cat_range": [0, 1, 2, 3, 4],
    }


# ─── FPDF2 PDF GENERATION ────────────────────────────────────────────────────

class BDDAReport(FPDF):
    """AWID inspection report — fpdf2 subclass with branded header/footer."""

    def __init__(self, report_data: dict):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.report_data = report_data
        self.report_ref = report_data.get("report_ref", "")
        self._fonts_registered = False
        self._register_fonts()
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(left=15, top=20, right=15)

    def _register_fonts(self):
        """Register Inter TTF fonts; fall back to Helvetica if not found."""
        try:
            self.add_font("Inter", style="",  fname=str(FONT_DIR / "Inter-Regular.ttf"))
            self.add_font("Inter", style="B", fname=str(FONT_DIR / "Inter-Bold.ttf"))
            self.add_font("Inter", style="I", fname=str(FONT_DIR / "Inter-Italic.ttf"))
            self._fonts_registered = True
        except (FileNotFoundError, Exception) as e:
            print(f"WARNING: Inter TTF not found in assets/fonts/ — falling back to Helvetica. ({e})")
            self._fonts_registered = False

    def _font(self, style: str = "", size: int = 10):
        """Set font, using Inter if available else Helvetica."""
        if self._fonts_registered:
            self.set_font("Inter", style, size)
        else:
            self.set_font("Helvetica", style, size)

    def header(self):
        """Branded header on all pages except cover (page 1)."""
        if self.page_no() == 1:
            return
        self.set_y(8)
        self._font("B", 9)
        self.set_text_color(*BRAND_NAVY)
        self.cell(95, 6, "AWID", align="L")
        self._font("", 8)
        self.set_text_color(*BRAND_GREY)
        self.cell(0, 6, self.report_ref, align="R")
        self.ln(2)
        self.set_draw_color(200, 200, 200)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_y(self.get_y() + 4)

    def footer(self):
        """Page number + confidential footer on all pages except cover (page 1)."""
        if self.page_no() == 1:
            return
        self.set_y(-12)
        self._font("", 7)
        self.set_text_color(160, 160, 160)
        self.cell(0, 6, f"Page {self.page_no()} | Confidential — AWID Inspection Report", align="C")


# ─── PAGE RENDERERS ───────────────────────────────────────────────────────────

def _render_cover(pdf: BDDAReport, report_data: dict):
    """Full-page cover: brand, title, turbine info, condition badge."""
    pdf.add_page()
    turbine = report_data.get("turbine", {})

    # ── Dark navy background header band ──
    pdf.set_fill_color(*BRAND_NAVY)
    pdf.rect(0, 0, 210, 60, style="F")

    # ── Brand name top-left ──
    pdf.set_y(15)
    pdf.set_x(15)
    pdf.set_text_color(255, 255, 255)
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 22)
    else:
        pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 12, "AWID", align="L")

    # ── Tagline ──
    pdf.set_y(29)
    pdf.set_x(15)
    if pdf._fonts_registered:
        pdf.set_font("Inter", "", 10)
    else:
        pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(180, 205, 230)
    pdf.cell(0, 7, "APAC Wind Inspections Drones", align="L")

    # ── Light band below navy ──
    pdf.set_fill_color(*BRAND_LIGHT)
    pdf.rect(0, 60, 210, 8, style="F")

    # ── Main title ──
    pdf.set_y(82)
    pdf.set_text_color(*BRAND_NAVY)
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 20)
    else:
        pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, "Wind Turbine Blade", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 12, "Inspection Report", align="C", new_x="LMARGIN", new_y="NEXT")

    # ── Divider ──
    pdf.ln(4)
    pdf.set_draw_color(*BRAND_STEEL)
    pdf.set_line_width(0.6)
    pdf.line(40, pdf.get_y(), 170, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(8)

    # ── Turbine identification ──
    turbine_id  = turbine.get("turbine_id", "N/A")
    site_name   = turbine.get("site_name", "N/A")
    country     = turbine.get("country", "")
    insp_date   = turbine.get("inspection_date", "N/A")
    inspector   = turbine.get("inspector_name", "N/A")

    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 14)
    else:
        pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*BRAND_NAVY)
    pdf.cell(0, 10, f"Turbine {turbine_id}", align="C", new_x="LMARGIN", new_y="NEXT")

    if pdf._fonts_registered:
        pdf.set_font("Inter", "", 12)
    else:
        pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(*BRAND_STEEL)
    site_line = f"{site_name}{', ' + country if country else ''}"
    pdf.cell(0, 8, site_line, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Inspection details ──
    if pdf._fonts_registered:
        pdf.set_font("Inter", "", 10)
    else:
        pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*BRAND_GREY)
    pdf.cell(0, 7, f"Inspection Date: {insp_date}    |    Inspector: {inspector}", align="C", new_x="LMARGIN", new_y="NEXT")

    # Report reference
    report_ref = report_data.get("report_ref", "")
    if pdf._fonts_registered:
        pdf.set_font("Inter", "I", 9)
    else:
        pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(140, 140, 140)
    pdf.cell(0, 7, f"Reference: {report_ref}", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(12)

    # ── Condition rating badge ──
    condition = report_data.get("condition", "A")
    condition_info = report_data.get("condition_info", CONDITION_RATINGS["A"])
    badge_rgb = CONDITION_COLORS_RGB.get(condition, (34, 197, 94))
    badge_text_rgb = CONDITION_TEXT_RGB.get(condition, (20, 83, 45))

    badge_x = 65
    badge_y = pdf.get_y()
    badge_w = 80
    badge_h = 28

    pdf.set_fill_color(*badge_rgb)
    pdf.set_draw_color(*badge_rgb)
    pdf.rect(badge_x, badge_y, badge_w, badge_h, style="F")

    # Condition letter
    pdf.set_xy(badge_x, badge_y + 2)
    pdf.set_text_color(*badge_text_rgb)
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 20)
    else:
        pdf.set_font("Helvetica", "B", 20)
    pdf.cell(badge_w, 13, f"Condition {condition}", align="C", new_x="LMARGIN", new_y="NEXT")

    # Condition label
    pdf.set_xy(badge_x, badge_y + 15)
    if pdf._fonts_registered:
        pdf.set_font("Inter", "", 10)
    else:
        pdf.set_font("Helvetica", "", 10)
    pdf.cell(badge_w, 8, condition_info.get("label", ""), align="C")

    pdf.set_y(badge_y + badge_h + 8)

    # Condition description
    pdf.set_x(30)
    if pdf._fonts_registered:
        pdf.set_font("Inter", "I", 9)
    else:
        pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(*BRAND_GREY)
    pdf.cell(0, 6, condition_info.get("desc", ""), align="C")

    # ── CONFIDENTIAL footer ──
    # Disable auto page break — we're writing near bottom of cover page
    pdf.set_auto_page_break(auto=False)
    pdf.set_y(270)
    pdf.set_fill_color(*BRAND_NAVY)
    pdf.rect(0, 275, 210, 22, style="F")
    pdf.set_y(279)
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 8)
    else:
        pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 5, "CONFIDENTIAL — FOR AUTHORIZED RECIPIENTS ONLY", align="C", new_x="LMARGIN", new_y="NEXT")
    if pdf._fonts_registered:
        pdf.set_font("Inter", "", 7)
    else:
        pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(180, 205, 230)
    company = turbine.get("company_name", "AWID - APAC Wind Inspections Drones")
    pdf.cell(0, 5, f"{company} | wind-turbines-reports.onrender.com", align="C")
    # Re-enable auto page break
    pdf.set_auto_page_break(auto=True, margin=20)


def _render_toc(pdf: BDDAReport, report_data: dict):
    """Table of contents page (page 2)."""
    pdf.add_page()

    # ── Section heading ──
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 18)
    else:
        pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*BRAND_NAVY)
    pdf.cell(0, 12, "Table of Contents", new_x="LMARGIN", new_y="NEXT")

    # Underline
    pdf.set_draw_color(*BRAND_STEEL)
    pdf.set_line_width(0.4)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(8)

    # ── TOC entries ──
    # We pre-calculate approximate page numbers based on deterministic layout:
    # Cover=1, TOC=2, Exec Summary=3
    # Defect pages: 1 per defect per blade
    # Action Matrix: 1 page
    # Blade Maps: 1 per blade
    # Inspection Details: 1 page

    page = 3
    toc_entries = []
    toc_entries.append(("Executive Summary", page, 0))
    page += 1

    blades_sorted = report_data.get("blades_sorted", [])
    blade_findings = report_data.get("blade_findings", {})
    for blade in blades_sorted:
        defects = blade_findings.get(blade, [])
        toc_entries.append((f"Blade {blade} — Defect Findings", page, 0))
        if defects:
            for i, defect in enumerate(defects, 1):
                defect_name = defect.get("defect_name", "Unknown")
                short_name = defect_name[:50] + ("..." if len(defect_name) > 50 else "")
                toc_entries.append((f"  {blade}-{i:03d}: {short_name}", page, 1))
                page += 1
        else:
            toc_entries.append(("  (No defects found)", page, 1))
            page += 1

    toc_entries.append(("Action Matrix", page, 0))
    page += 1

    for blade in blades_sorted:
        toc_entries.append((f"Blade {blade} — Defect Map", page, 0))
        page += 1

    toc_entries.append(("Inspection Details", page, 0))

    # ── Render entries ──
    content_width = pdf.w - pdf.l_margin - pdf.r_margin

    for name, pg_num, level in toc_entries:
        indent = level * 8
        name_width = content_width - indent - 15  # space for page number

        if level == 0:
            if pdf._fonts_registered:
                pdf.set_font("Inter", "B", 10)
            else:
                pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*BRAND_NAVY)
            row_h = 8
        else:
            if pdf._fonts_registered:
                pdf.set_font("Inter", "", 8)
            else:
                pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*BRAND_GREY)
            row_h = 6

        pdf.set_x(pdf.l_margin + indent)
        x_before = pdf.get_x()
        y_before = pdf.get_y()

        # Name cell
        pdf.cell(name_width, row_h, name, align="L")

        # Dotted leader then page number
        if level == 0:
            if pdf._fonts_registered:
                pdf.set_font("Inter", "", 10)
            else:
                pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(*BRAND_GREY)

        pdf.cell(15, row_h, str(pg_num), align="R", new_x="LMARGIN", new_y="NEXT")


def _render_executive_summary(pdf: BDDAReport, report_data: dict):
    """Executive summary page (page 3): condition, stats, critical findings, recommendation."""
    pdf.add_page()

    # ── Section heading ──
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 18)
    else:
        pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*BRAND_NAVY)
    pdf.cell(0, 12, "Executive Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*BRAND_STEEL)
    pdf.set_line_width(0.4)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(6)

    # ── Condition rating ──
    condition = report_data.get("condition", "A")
    condition_info = report_data.get("condition_info", CONDITION_RATINGS["A"])
    badge_rgb = CONDITION_COLORS_RGB.get(condition, (34, 197, 94))
    badge_text_rgb = CONDITION_TEXT_RGB.get(condition, (20, 83, 45))

    # Badge rectangle
    badge_x = pdf.l_margin
    badge_y = pdf.get_y()
    badge_w = 55
    badge_h = 22
    pdf.set_fill_color(*badge_rgb)
    pdf.rect(badge_x, badge_y, badge_w, badge_h, style="F")
    pdf.set_xy(badge_x, badge_y + 3)
    pdf.set_text_color(*badge_text_rgb)
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 14)
    else:
        pdf.set_font("Helvetica", "B", 14)
    pdf.cell(badge_w, 9, f"Condition {condition}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_xy(badge_x, badge_y + 13)
    if pdf._fonts_registered:
        pdf.set_font("Inter", "", 9)
    else:
        pdf.set_font("Helvetica", "", 9)
    pdf.cell(badge_w, 7, condition_info.get("label", ""), align="C")

    # Condition description (right of badge)
    pdf.set_xy(badge_x + badge_w + 8, badge_y + 4)
    if pdf._fonts_registered:
        pdf.set_font("Inter", "", 10)
    else:
        pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*BRAND_NAVY)
    desc_width = pdf.w - pdf.l_margin - pdf.r_margin - badge_w - 8
    pdf.multi_cell(desc_width, 7, condition_info.get("desc", ""))

    pdf.set_y(badge_y + badge_h + 8)

    # ── Triage statistics ──
    triage_stats = report_data.get("triage_stats")
    if triage_stats:
        if pdf._fonts_registered:
            pdf.set_font("Inter", "B", 11)
        else:
            pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*BRAND_NAVY)
        pdf.cell(0, 8, "Inspection Statistics", new_x="LMARGIN", new_y="NEXT")

        stats = [
            ("Total images", str(triage_stats.get("total", 0))),
            ("Flagged for review", str(triage_stats.get("flagged", 0))),
            ("Clean (no damage)", str(triage_stats.get("clean", 0))),
            ("Flag rate", f"{triage_stats.get('flag_rate', 0):.1%}"),
        ]

        col_w = 45
        for i, (label, value) in enumerate(stats):
            x = pdf.l_margin + (i % 4) * col_w
            if i % 4 == 0 and i > 0:
                pdf.ln(14)
            pdf.set_xy(x, pdf.get_y())
            if pdf._fonts_registered:
                pdf.set_font("Inter", "B", 13)
            else:
                pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(*BRAND_STEEL)
            pdf.cell(col_w, 9, value, align="L")
            pdf.set_xy(x, pdf.get_y() + 9)
            if pdf._fonts_registered:
                pdf.set_font("Inter", "", 7)
            else:
                pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(*BRAND_GREY)
            pdf.cell(col_w, 5, label, align="L")

        pdf.ln(16)
        pdf.set_draw_color(220, 220, 220)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(6)

    # ── Defect summary table (IEC Cat 0-4) ──
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 11)
    else:
        pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*BRAND_NAVY)
    total_defects = report_data.get("total_defects", 0)
    critical_count = report_data.get("critical_count", 0)
    pdf.cell(0, 8, f"Defect Summary  (Total: {total_defects}  |  Critical: {critical_count})", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    defects_by_cat = report_data.get("defects_by_cat", {})
    content_width = pdf.w - pdf.l_margin - pdf.r_margin

    # Table header
    pdf.set_fill_color(*BRAND_NAVY)
    pdf.set_text_color(255, 255, 255)
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 9)
    else:
        pdf.set_font("Helvetica", "B", 9)
    col_widths = [content_width * 0.12, content_width * 0.45, content_width * 0.20, content_width * 0.23]
    pdf.cell(col_widths[0], 8, "Cat", border=0, fill=True, align="C")
    pdf.cell(col_widths[1], 8, "Description", border=0, fill=True, align="L")
    pdf.cell(col_widths[2], 8, "Count", border=0, fill=True, align="C")
    pdf.cell(col_widths[3], 8, "Action", border=0, fill=True, align="L", new_x="LMARGIN", new_y="NEXT")

    for cat in range(0, 5):
        info = SEVERITY_COLORS_IEC[cat]
        count = defects_by_cat.get(cat, 0)
        action_labels = {
            0: "No action required",
            1: "Log and monitor",
            2: "Plan maintenance",
            3: "Schedule repair",
            4: "Urgent — repair ASAP",
        }
        # Coloured category badge cell
        pdf.set_fill_color(*info["rgb"])
        pdf.set_text_color(*info["text_rgb"])
        if pdf._fonts_registered:
            pdf.set_font("Inter", "B", 9)
        else:
            pdf.set_font("Helvetica", "B", 9)
        pdf.cell(col_widths[0], 8, f"Cat {cat}", border="B", fill=True, align="C")

        # Rest of row — light background for even rows
        if cat % 2 == 0:
            pdf.set_fill_color(245, 248, 252)
        else:
            pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(50, 50, 50)
        if pdf._fonts_registered:
            pdf.set_font("Inter", "", 9)
        else:
            pdf.set_font("Helvetica", "", 9)
        pdf.cell(col_widths[1], 8, info["label"], border="B", fill=True, align="L")
        if pdf._fonts_registered:
            pdf.set_font("Inter", "B", 9)
        else:
            pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*BRAND_NAVY)
        pdf.cell(col_widths[2], 8, str(count), border="B", fill=True, align="C")
        if pdf._fonts_registered:
            pdf.set_font("Inter", "", 9)
        else:
            pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(col_widths[3], 8, action_labels[cat], border="B", fill=True, align="L", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(8)

    # ── Critical findings (top 5) ──
    critical_findings = report_data.get("critical_findings", [])
    if critical_findings:
        if pdf._fonts_registered:
            pdf.set_font("Inter", "B", 11)
        else:
            pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*BRAND_NAVY)
        pdf.cell(0, 8, "Top Critical Findings", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        for i, defect in enumerate(critical_findings[:5], 1):
            cat = defect.get("category", 0)
            info = SEVERITY_COLORS_IEC.get(cat, SEVERITY_COLORS_IEC[0])
            blade = defect.get("blade", "?")
            zone = defect.get("zone", "?")
            pos = defect.get("position", "?")
            defect_name = defect.get("defect_name", "Unknown")

            # Severity indicator
            pdf.set_fill_color(*info["rgb"])
            pdf.rect(pdf.l_margin, pdf.get_y() + 1, 4, 6, style="F")
            pdf.set_x(pdf.l_margin + 6)
            if pdf._fonts_registered:
                pdf.set_font("Inter", "B", 9)
            else:
                pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*BRAND_NAVY)
            pdf.cell(15, 8, f"Cat {cat}", align="L")
            if pdf._fonts_registered:
                pdf.set_font("Inter", "", 9)
            else:
                pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(50, 50, 50)
            pdf.cell(20, 8, f"Blade {blade}", align="L")
            pdf.cell(25, 8, f"{zone}/{pos}", align="L")
            short_name = defect_name[:70]
            pdf.cell(0, 8, short_name, align="L", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)

    # ── Recommendation ──
    reco_map = {
        "A": "The turbine blades are in good condition. Continue routine annual inspections. No immediate action required.",
        "B": "Minor to moderate defects detected. Schedule planned maintenance within the next service window. Monitor identified defects at 6-month intervals.",
        "C": "High-priority defects require urgent attention. Initiate repair scheduling immediately. Perform NDT inspection on affected blade sections before next operational season.",
        "D": "Critical structural defects detected. Consider temporarily stopping the turbine pending engineering review. Immediate repair assessment required. Do not defer action.",
    }

    pdf.set_fill_color(*BRAND_LIGHT)
    reco_x = pdf.l_margin
    reco_y = pdf.get_y()
    reco_text = reco_map.get(condition, reco_map["A"])

    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 10)
    else:
        pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*BRAND_NAVY)
    pdf.cell(0, 7, "Recommendation", new_x="LMARGIN", new_y="NEXT")

    pdf.set_fill_color(*BRAND_LIGHT)
    pdf.set_x(reco_x)
    reco_w = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_draw_color(*BRAND_STEEL)
    pdf.set_line_width(0.8)
    pdf.line(reco_x, pdf.get_y(), reco_x, pdf.get_y() + 18)
    pdf.set_line_width(0.2)
    pdf.set_x(reco_x + 5)
    if pdf._fonts_registered:
        pdf.set_font("Inter", "", 9)
    else:
        pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(60, 60, 60)
    pdf.multi_cell(reco_w - 5, 6, reco_text)


def _embed_defect_image(pdf: BDDAReport, image_path: str, x: float, y: float,
                        w: float = 80, h: float = 80):
    """Embed defect thumbnail at (x, y); draw grey placeholder if file missing or unreadable."""
    path = Path(image_path) if image_path else None
    if not path or not path.exists():
        # Grey placeholder
        pdf.set_fill_color(220, 220, 220)
        pdf.rect(x, y, w, h, style="F")
        pdf.set_draw_color(180, 180, 180)
        pdf.rect(x, y, w, h, style="D")
        pdf.set_xy(x, y + h / 2 - 4)
        if pdf._fonts_registered:
            pdf.set_font("Inter", "I", 7)
        else:
            pdf.set_font("Helvetica", "I", 7)
        pdf.set_text_color(140, 140, 140)
        pdf.cell(w, 6, "Image not available", align="C")
        return

    try:
        if HAS_PILLOW:
            with PILImage.open(path) as img:
                img = img.convert("RGB")
                img.thumbnail((472, 472), PILImage.LANCZOS)  # 80mm @ 150dpi ≈ 472px
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=82)
                buf.seek(0)
            pdf.image(buf, x=x, y=y, w=w, h=h, keep_aspect_ratio=True)
        else:
            pdf.image(str(path), x=x, y=y, w=w, h=h, keep_aspect_ratio=True)
    except Exception:
        # Fallback placeholder on any image error
        pdf.set_fill_color(220, 220, 220)
        pdf.rect(x, y, w, h, style="F")
        pdf.set_xy(x, y + h / 2 - 4)
        if pdf._fonts_registered:
            pdf.set_font("Inter", "I", 7)
        else:
            pdf.set_font("Helvetica", "I", 7)
        pdf.set_text_color(140, 140, 140)
        pdf.cell(w, 6, "Image error", align="C")


def _render_defect_page(pdf: BDDAReport, defect: dict, defect_index: int, total_defects: int):
    """Render one defect per page: severity band, 80x80mm image, metadata, deep analysis."""
    cat = defect.get("category", 0)
    severity_info = SEVERITY_COLORS_IEC.get(cat, SEVERITY_COLORS_IEC[0])

    # ── Page title ──
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 14)
    else:
        pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*BRAND_NAVY)
    pdf.cell(0, 10, f"Defect Finding {defect_index}/{total_defects}", new_x="LMARGIN", new_y="NEXT")

    # ── Severity colour band (full width) ──
    band_y = pdf.get_y()
    pdf.set_fill_color(*severity_info["rgb"])
    pdf.rect(pdf.l_margin, band_y, pdf.w - pdf.l_margin - pdf.r_margin, 10, style="F")
    pdf.set_xy(pdf.l_margin, band_y + 1)
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 10)
    else:
        pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*severity_info["text_rgb"])
    pdf.cell(0, 8, severity_info["label"], align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Two-column area: image left, metadata right ──
    col_start_y = pdf.get_y()
    left_x = pdf.l_margin
    right_x = pdf.l_margin + 88  # 80mm image + 8mm gap
    meta_width = pdf.w - right_x - pdf.r_margin

    # Left column: 80x80mm image
    _embed_defect_image(pdf, defect.get("image_path", ""), left_x, col_start_y, w=80, h=80)

    # Right column: metadata fields
    def _meta_row(label: str, value: str):
        pdf.set_x(right_x)
        if pdf._fonts_registered:
            pdf.set_font("Inter", "B", 7)
        else:
            pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*BRAND_GREY)
        pdf.cell(meta_width * 0.40, 5, label.upper(), align="L")
        if pdf._fonts_registered:
            pdf.set_font("Inter", "", 8)
        else:
            pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(40, 40, 40)
        val_str = str(value) if value is not None else "—"
        pdf.cell(meta_width * 0.60, 5, val_str[:50], align="L", new_x="LMARGIN", new_y="NEXT")

    # Position at right column start
    pdf.set_xy(right_x, col_start_y)

    defect_name = defect.get("defect_name", "Unknown")
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 10)
    else:
        pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*BRAND_NAVY)
    # Multi-cell for long names
    pdf.set_x(right_x)
    pdf.multi_cell(meta_width, 6, defect_name, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    confidence = defect.get("confidence", 0.0)
    conf_pct = f"{confidence:.0%}"
    conf_label = _confidence_label(confidence)
    ndt = "Yes" if defect.get("ndt_recommended") else "No"

    meta_fields = [
        ("Defect ID", defect.get("defect_id", "—")),
        ("IEC Category", f"Cat {cat} — {defect.get('urgency', '')}"),
        ("Zone", defect.get("zone", "—")),
        ("Position", defect.get("position", "—")),
        ("Size Estimate", defect.get("size_estimate", "—")),
        ("Confidence", f"{conf_pct} ({conf_label})"),
        ("NDT Recommended", ndt),
    ]

    for label, value in meta_fields:
        _meta_row(label, value)

    # After image (below 80mm image + gap)
    pdf.set_y(col_start_y + 84)

    # ── Visual description ──
    visual_desc = defect.get("visual_description", "")
    if visual_desc:
        if pdf._fonts_registered:
            pdf.set_font("Inter", "B", 9)
        else:
            pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*BRAND_NAVY)
        pdf.cell(0, 7, "Visual Description", new_x="LMARGIN", new_y="NEXT")
        if pdf._fonts_registered:
            pdf.set_font("Inter", "I", 8)
        else:
            pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(60, 60, 60)
        content_width = pdf.w - pdf.l_margin - pdf.r_margin
        pdf.multi_cell(content_width, 5, visual_desc)
        pdf.ln(4)

    # ── Deep analysis (if available) ──
    analysis = defect.get("analysis")
    if analysis:
        if pdf._fonts_registered:
            pdf.set_font("Inter", "B", 10)
        else:
            pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*BRAND_NAVY)
        pdf.cell(0, 8, "Deep Analysis", new_x="LMARGIN", new_y="NEXT")

        pdf.set_draw_color(*BRAND_LIGHT)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(3)

        content_width = pdf.w - pdf.l_margin - pdf.r_margin

        def _analysis_row(label: str, value: str):
            if not value:
                return
            if pdf._fonts_registered:
                pdf.set_font("Inter", "B", 8)
            else:
                pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*BRAND_GREY)
            pdf.cell(0, 5, label.upper(), new_x="LMARGIN", new_y="NEXT")
            if pdf._fonts_registered:
                pdf.set_font("Inter", "", 8)
            else:
                pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(content_width, 5, str(value))
            pdf.ln(2)

        _analysis_row("Root Cause", analysis.get("root_cause", ""))
        _analysis_row("Recommended Action", analysis.get("recommended_action", ""))
        _analysis_row("Repair Timeframe", analysis.get("repair_timeframe", ""))
        _analysis_row("Estimated Cost", analysis.get("estimated_cost_usd", ""))

        failure_risk = analysis.get("failure_risk", {})
        if failure_risk:
            safety_risk = failure_risk.get("safety_risk", "")
            if safety_risk:
                _analysis_row("Safety Risk Level", safety_risk)

        if analysis.get("engineer_review_required"):
            pdf.set_fill_color(239, 68, 68)
            pdf.set_text_color(255, 255, 255)
            if pdf._fonts_registered:
                pdf.set_font("Inter", "B", 8)
            else:
                pdf.set_font("Helvetica", "B", 8)
            pdf.cell(0, 7, "  ENGINEER REVIEW REQUIRED", fill=True, new_x="LMARGIN", new_y="NEXT")


def _render_action_matrix(pdf: BDDAReport, report_data: dict):
    """Action matrix page: priority-sorted table colour-coded by severity."""
    pdf.add_page()

    # ── Section heading ──
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 18)
    else:
        pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*BRAND_NAVY)
    pdf.cell(0, 12, "Action Matrix", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*BRAND_STEEL)
    pdf.set_line_width(0.4)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(6)

    action_matrix = report_data.get("action_matrix", [])

    if not action_matrix:
        if pdf._fonts_registered:
            pdf.set_font("Inter", "I", 11)
        else:
            pdf.set_font("Helvetica", "I", 11)
        pdf.set_text_color(*BRAND_GREY)
        pdf.cell(0, 10, "No defects found — turbine in good condition.", align="C", new_x="LMARGIN", new_y="NEXT")
        return

    content_width = pdf.w - pdf.l_margin - pdf.r_margin
    row_h = 7

    # Column definitions: (label, relative_width)
    cols = [
        ("Priority", 0.08),
        ("Blade",    0.07),
        ("Defect ID", 0.10),
        ("Defect Name", 0.28),
        ("Cat", 0.06),
        ("Zone", 0.10),
        ("Timeframe", 0.13),
        ("Action", 0.18),
    ]
    col_widths = [content_width * w for _, w in cols]

    def _draw_header():
        pdf.set_fill_color(*BRAND_NAVY)
        pdf.set_text_color(255, 255, 255)
        if pdf._fonts_registered:
            pdf.set_font("Inter", "B", 8)
        else:
            pdf.set_font("Helvetica", "B", 8)
        for (label, _), w in zip(cols, col_widths):
            pdf.cell(w, row_h, label, border=0, fill=True, align="C")
        pdf.ln(row_h)

    _draw_header()

    for item in action_matrix:
        if pdf.will_page_break(row_h):
            pdf.add_page()
            _draw_header()

        cat = item.get("category", 0)
        info = SEVERITY_COLORS_IEC.get(cat, SEVERITY_COLORS_IEC[0])

        pdf.set_fill_color(*info["rgb"])
        pdf.set_text_color(*info["text_rgb"])
        if pdf._fonts_registered:
            pdf.set_font("Inter", "B", 7)
        else:
            pdf.set_font("Helvetica", "B", 7)

        values = [
            item.get("priority", ""),
            item.get("blade", ""),
            item.get("defect_id", ""),
            item.get("defect_name", "")[:40],
            f"Cat {cat}",
            item.get("zone", ""),
            item.get("timeframe", ""),
            item.get("action", "")[:35],
        ]

        for val, w in zip(values, col_widths):
            pdf.cell(w, row_h, str(val), border="B", fill=True, align="L")
        pdf.ln(row_h)


def _render_blade_map(pdf: BDDAReport, blade_label: str, blade_defects: list):
    """Per-blade defect map: zone grid schematic with severity-coloured markers."""
    # ── Section heading ──
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 16)
    else:
        pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*BRAND_NAVY)
    pdf.cell(0, 10, f"Blade {blade_label} — Defect Map", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*BRAND_STEEL)
    pdf.set_line_width(0.4)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(6)

    zones = ["LE", "TE", "PS", "SS"]
    positions = ["Root", "Mid", "Tip"]
    cell_w, cell_h = 35, 18
    start_x = pdf.l_margin + 25  # leave room for zone labels on left
    start_y = pdf.get_y() + 10   # leave room for position labels on top

    # ── Position labels across top ──
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 8)
    else:
        pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*BRAND_NAVY)
    for col, pos in enumerate(positions):
        pdf.set_xy(start_x + col * cell_w, start_y - 8)
        pdf.cell(cell_w, 7, pos, align="C")

    # ── Zone grid ──
    for row, zone in enumerate(zones):
        # Zone label on left margin
        if pdf._fonts_registered:
            pdf.set_font("Inter", "B", 8)
        else:
            pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*BRAND_NAVY)
        pdf.set_xy(pdf.l_margin, start_y + row * cell_h + cell_h / 2 - 3)
        pdf.cell(22, 6, zone, align="R")

        for col, pos in enumerate(positions):
            x = start_x + col * cell_w
            y = start_y + row * cell_h

            worst_cat = _worst_cat_in_zone(blade_defects, zone, pos)
            rgb = ZONE_COLORS_IEC.get(worst_cat, (230, 230, 230))

            # Cell background
            pdf.set_fill_color(*rgb)
            pdf.set_draw_color(180, 180, 180)
            pdf.rect(x, y, cell_w, cell_h, style="FD")

            # Zone label inside cell (small)
            if pdf._fonts_registered:
                pdf.set_font("Inter", "", 6)
            else:
                pdf.set_font("Helvetica", "", 6)
            pdf.set_text_color(50, 50, 50)
            pdf.set_xy(x, y + 2)
            pdf.cell(cell_w, 5, zone, align="C")

            # Defect count circle — count defects in this zone+position
            zone_count = sum(
                1 for d in blade_defects
                if d.get("zone") == zone and d.get("position") == pos
            )
            if zone_count > 0:
                # Draw circle at cell center
                cx = x + cell_w / 2
                cy = y + cell_h / 2 + 2
                pdf.set_fill_color(255, 255, 255)
                pdf.set_draw_color(100, 100, 100)
                pdf.circle(x=cx, y=cy, radius=4, style="FD")  # x,y = CENTER coords
                # Count text in circle
                if pdf._fonts_registered:
                    pdf.set_font("Inter", "B", 7)
                else:
                    pdf.set_font("Helvetica", "B", 7)
                pdf.set_text_color(50, 50, 50)
                pdf.set_xy(cx - 4, cy - 3.5)
                pdf.cell(8, 7, str(zone_count), align="C")

    # ── Severity legend ──
    legend_y = start_y + len(zones) * cell_h + 8

    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 9)
    else:
        pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*BRAND_NAVY)
    pdf.set_xy(pdf.l_margin, legend_y)
    pdf.cell(0, 7, "Severity Legend", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    legend_items = [(-1, (230, 230, 230), "No defects")] + [
        (cat, ZONE_COLORS_IEC[cat], SEVERITY_COLORS_IEC[cat]["label"])
        for cat in range(0, 5)
    ]

    swatch_w, swatch_h = 20, 6
    gap = 4
    legend_x = pdf.l_margin
    legend_row_y = pdf.get_y()

    for i, (cat, rgb, label) in enumerate(legend_items):
        x = legend_x + i * (swatch_w + 25 + gap)
        # Wrap to next line if needed
        if x + swatch_w + 25 > pdf.w - pdf.r_margin:
            x = legend_x
            legend_row_y += 10
        pdf.set_fill_color(*rgb)
        pdf.set_draw_color(180, 180, 180)
        pdf.rect(x, legend_row_y, swatch_w, swatch_h, style="FD")
        if pdf._fonts_registered:
            pdf.set_font("Inter", "", 7)
        else:
            pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(50, 50, 50)
        pdf.set_xy(x + swatch_w + 2, legend_row_y)
        pdf.cell(25, swatch_h, label, align="L")

    # ── Defect list for this blade ──
    if blade_defects:
        pdf.set_y(legend_row_y + swatch_h + 8)
        if pdf._fonts_registered:
            pdf.set_font("Inter", "B", 9)
        else:
            pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*BRAND_NAVY)
        pdf.cell(0, 7, f"Blade {blade_label} Defects ({len(blade_defects)} total)", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        for defect in blade_defects:
            if pdf.will_page_break(6):
                break  # stop listing if out of space — full details in defect pages
            cat = defect.get("category", 0)
            info = SEVERITY_COLORS_IEC.get(cat, SEVERITY_COLORS_IEC[0])
            # Severity indicator dot
            pdf.set_fill_color(*info["rgb"])
            pdf.rect(pdf.l_margin, pdf.get_y() + 1, 3, 4, style="F")
            pdf.set_x(pdf.l_margin + 5)
            if pdf._fonts_registered:
                pdf.set_font("Inter", "", 8)
            else:
                pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(50, 50, 50)
            zone = defect.get("zone", "")
            pos = defect.get("position", "")
            name = defect.get("defect_name", "Unknown")[:60]
            pdf.cell(0, 6, f"[{zone}/{pos}] {name}", new_x="LMARGIN", new_y="NEXT")


def _render_inspection_details(pdf: BDDAReport, report_data: dict):
    """Final page: turbine specs, drone info, weather, GPS, legal disclaimer."""
    pdf.add_page()

    # ── Section heading ──
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 18)
    else:
        pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*BRAND_NAVY)
    pdf.cell(0, 12, "Inspection Details", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*BRAND_STEEL)
    pdf.set_line_width(0.4)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(6)

    turbine = report_data.get("turbine", {})
    content_width = pdf.w - pdf.l_margin - pdf.r_margin
    half_w = content_width / 2 - 5

    def _detail_row(label: str, value: str, x_offset: float = 0):
        pdf.set_x(pdf.l_margin + x_offset)
        if pdf._fonts_registered:
            pdf.set_font("Inter", "B", 8)
        else:
            pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*BRAND_GREY)
        pdf.cell(half_w * 0.45, 6, label.upper(), align="L")
        if pdf._fonts_registered:
            pdf.set_font("Inter", "", 9)
        else:
            pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 40)
        val_str = str(value) if value is not None else "N/A"
        pdf.cell(half_w * 0.55, 6, val_str, align="L", new_x="LMARGIN", new_y="NEXT")

    # ── Turbine specifications ──
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 11)
    else:
        pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*BRAND_NAVY)
    pdf.cell(0, 8, "Turbine Specifications", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    specs = [
        ("Turbine ID", turbine.get("turbine_id", "")),
        ("Model", turbine.get("turbine_model", "")),
        ("Hub Height", f"{turbine.get('hub_height_m', '')} m" if turbine.get('hub_height_m') else ""),
        ("Rotor Diameter", f"{turbine.get('rotor_diameter_m', '')} m" if turbine.get('rotor_diameter_m') else ""),
        ("Blade Length", f"{turbine.get('blade_length_m', '')} m" if turbine.get('blade_length_m') else ""),
        ("Site", turbine.get("site_name", "")),
        ("Country", turbine.get("country", "")),
        ("Company", turbine.get("company_name", "")),
    ]

    for label, value in specs:
        _detail_row(label, value)

    pdf.ln(5)

    # ── Drone & camera ──
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 11)
    else:
        pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*BRAND_NAVY)
    pdf.cell(0, 8, "Drone & Equipment", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    drone_info = [
        ("Drone Model", turbine.get("drone_model", "")),
        ("Camera", turbine.get("camera", "")),
    ]
    for label, value in drone_info:
        _detail_row(label, value)

    pdf.ln(5)

    # ── Environmental conditions ──
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 11)
    else:
        pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*BRAND_NAVY)
    pdf.cell(0, 8, "Environmental Conditions", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    wind_ms = turbine.get("wind_speed_ms")
    temp_c  = turbine.get("temperature_c")
    vis_km  = turbine.get("visibility_km")
    env_info = [
        ("Weather", turbine.get("weather", "")),
        ("Wind Speed", f"{wind_ms} m/s" if wind_ms is not None else ""),
        ("Temperature", f"{temp_c} °C" if temp_c is not None else ""),
        ("Visibility", f"{vis_km} km" if vis_km is not None else ""),
    ]
    for label, value in env_info:
        _detail_row(label, value)

    pdf.ln(5)

    # ── GPS coordinates ──
    gps_lat = turbine.get("gps_lat")
    gps_lon = turbine.get("gps_lon")
    if gps_lat is not None and gps_lon is not None:
        if pdf._fonts_registered:
            pdf.set_font("Inter", "B", 11)
        else:
            pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*BRAND_NAVY)
        pdf.cell(0, 8, "Location", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        _detail_row("GPS Coordinates", f"{gps_lat:.6f}°N, {gps_lon:.6f}°E")
        pdf.ln(5)

    # ── Inspector notes ──
    notes = turbine.get("notes", "")
    if notes:
        if pdf._fonts_registered:
            pdf.set_font("Inter", "B", 11)
        else:
            pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*BRAND_NAVY)
        pdf.cell(0, 8, "Inspector Notes", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        if pdf._fonts_registered:
            pdf.set_font("Inter", "I", 9)
        else:
            pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(60, 60, 60)
        pdf.multi_cell(content_width, 6, notes)
        pdf.ln(5)

    # ── Engineer review count ──
    engineer_review_count = report_data.get("engineer_review_count", 0)
    if engineer_review_count > 0:
        if pdf._fonts_registered:
            pdf.set_font("Inter", "B", 9)
        else:
            pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(239, 68, 68)
        pdf.cell(0, 7, f"Engineer Review Required: {engineer_review_count} defect(s) flagged for structural engineer sign-off.", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    # ── Generated at ──
    if pdf._fonts_registered:
        pdf.set_font("Inter", "", 8)
    else:
        pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(160, 160, 160)
    pdf.cell(0, 6, f"Report generated: {report_data.get('generated_at', '')}  |  Reference: {report_data.get('report_ref', '')}", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)

    # ── Legal disclaimer ──
    pdf.set_fill_color(245, 245, 245)
    pdf.set_draw_color(200, 200, 200)
    disclaimer_y = pdf.get_y()
    disclaimer_text = (
        "This report was generated using AI-assisted defect detection technology. "
        "All findings have been produced by automated image analysis and should be reviewed "
        "by a qualified wind turbine inspector before maintenance or repair decisions are made. "
        "AWID - APAC Wind Inspections Drones accepts no liability for decisions made solely on the basis of this report "
        "without independent engineering verification."
    )
    if pdf._fonts_registered:
        pdf.set_font("Inter", "I", 7)
    else:
        pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(content_width, 5, disclaimer_text)


# ─── MAIN ENTRY POINT ─────────────────────────────────────────────────────────

def generate_pdf_fpdf2(report_data: dict, output_path: Path) -> Path:
    """
    fpdf2-based PDF generator. Replaces generate_pdf() + render_html().

    Produces a multi-page branded PDF:
      Page 1: Cover
      Page 2: Table of Contents
      Page 3: Executive Summary
      Pages 4-N: [Defect pages — added by Plan 03]
      Page N+1: [Action Matrix — added by Plan 03]
      Page N+2: [Blade Maps — added by Plan 03]
      Final: Inspection Details

    Returns path to generated PDF.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pdf = BDDAReport(report_data)

    _render_cover(pdf, report_data)
    _render_toc(pdf, report_data)
    _render_executive_summary(pdf, report_data)

    # ── Defect pages: 1 page per defect, grouped by blade ──
    total_defects = report_data.get("total_defects", 0)
    defect_index = 1
    blades_sorted = report_data.get("blades_sorted", [])
    blade_findings = report_data.get("blade_findings", {})

    for blade in blades_sorted:
        blade_defects = blade_findings.get(blade, [])
        for defect in blade_defects:
            pdf.add_page()
            _render_defect_page(pdf, defect, defect_index, total_defects)
            defect_index += 1

    # ── Action matrix ──
    _render_action_matrix(pdf, report_data)

    # ── Per-blade defect maps ──
    for blade in blades_sorted:
        pdf.add_page()
        _render_blade_map(pdf, blade, blade_findings.get(blade, []))

    _render_inspection_details(pdf, report_data)

    pdf.output(str(output_path))
    return output_path


# ─── FULL PIPELINE ────────────────────────────────────────────────────────────

def build_report(
    turbine_meta: Dict,
    classify_json_path: Path,
    output_pdf_path: Path,
    triage_json_path: Optional[Path] = None,
    analyze_json_path: Optional[Path] = None,
    verbose: bool = True,
) -> Path:
    """
    Full report pipeline: load data → build report data → generate PDF.

    Returns path to generated PDF.
    """
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
        print(f"  Generating PDF...")

    pdf_path = generate_pdf_fpdf2(report_data, output_pdf_path)

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
        "company_name": "AWID - APAC Wind Inspections Drones",
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
                "progression_risk": "Crack will propagate under continued operational loads; high probability of full TE separation within 6-12 months without intervention.",
                "failure_mode": "Trailing Edge Separation — structural shell integrity loss leading to aerodynamic imbalance and potential blade failure",
                "safety_risk": "High"
            },
            "vestas_standard": "DNVGL-ST-0376 Section 8.3: Bond line cracks classified as Category 4 require priority repair.",
            "recommended_action": "Immediate NDT inspection to determine crack depth and extent. Schedule priority repair within 3 months.",
            "repair_timeframe": "30 days",
            "estimated_cost_usd": "$8,000-$18,000",
            "engineer_review_required": True,
            "engineer_review_reason": "Bond line cracks at root transition require structural engineer sign-off per DNVGL-ST-0376.",
            "analysis_confidence": 0.87,
            "additional_notes": "Root transition zone is the highest fatigue stress area per NREL research.",
            "error": None,
        }
    ]


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("report.py — fpdf2 PDF report module (Phase 4)")

    # Verify fpdf2
    try:
        import fpdf
        print(f"fpdf2 version: {fpdf.__version__} OK")
    except ImportError:
        print("ERROR: fpdf2 not installed — pip install fpdf2")
        sys.exit(1)

    # Test data assembly
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
    print("Data assembly OK.")

    # Test PDF generation
    output_path = Path("/tmp/test_bdda_report.pdf")
    print(f"\nGenerating test PDF to {output_path}...")
    try:
        p = generate_pdf_fpdf2(data, output_path)
        size = p.stat().st_size
        print(f"PDF generated: {p} ({size:,} bytes)")
        if size < 1000:
            print("WARNING: PDF is very small — check rendering")
        else:
            print("PDF size OK")
    except Exception as e:
        print(f"ERROR generating PDF: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
