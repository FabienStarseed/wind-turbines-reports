"""
report.py — Stage 4: Professional PDF report generation using fpdf2
Assembles triage + classify + analyze JSON data into an AWID branded PDF.

Pipeline:
  triage JSON + classify JSON + analyze JSON → BDDAReport (fpdf2) → PDF
"""

import json
import io
import math
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from fpdf import FPDF

try:
    from PIL import Image as PILImage, ImageEnhance, ImageFilter
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

# ─── ASSET PATHS ─────────────────────────────────────────────────────────────
ASSET_DIR   = Path(__file__).parent.parent / "assets"
FONT_DIR    = ASSET_DIR / "fonts"
IMAGES_DIR  = ASSET_DIR / "images"

# Bundled background images (copied into assets/images/ at deploy time)
BG_IMAGE_TURBINE = IMAGES_DIR / "bg_turbine.jpg"    # greyscale turbine field
BG_IMAGE_BLADE   = IMAGES_DIR / "bg_blade.jpg"      # close-up blade


# ─── SEVERITY CONFIG ──────────────────────────────────────────────────────────

# Legacy hex-based dict kept for build_report_data() severity_style field
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
    "A": {"label": "Good",     "color": "#A8CB1A", "desc": "No critical defects. Minor cosmetic issues only."},
    "B": {"label": "Fair",     "color": "#E3B341", "desc": "Minor to moderate defects. Planned maintenance required."},
    "C": {"label": "Poor",     "color": "#F85149", "desc": "High-priority defects found. Urgent repair needed."},
    "D": {"label": "Critical", "color": "#8b0000", "desc": "Critical defects present. Consider stopping turbine."},
}

# ─── AWID "WIND OPERATOR" BRAND PALETTE ──────────────────────────────────────
BRAND_PRIMARY    = (168, 203, 26)    # #A8CB1A — Lime green (THE brand color)
BRAND_DARK       = (7, 19, 29)       # #07131D — Deepest background
BRAND_NAVY       = (0, 30, 47)       # #001E2F — Section backgrounds, header/footer
BRAND_SLATE      = (47, 55, 98)      # #2F3762 — Elevated surfaces, cards
BRAND_GREY       = (103, 101, 120)   # #676578 — Muted text, borders, metadata
BRAND_LAVENDER   = (182, 180, 202)   # #B6B4CA — Body text on dark
BRAND_WHITE      = (255, 255, 255)   # #FFFFFF — Headlines, primary text
BRAND_AMBER      = (227, 179, 65)    # #E3B341 — Warning
BRAND_RED        = (248, 81, 73)     # #F85149 — Danger/critical

# IEC 0-4 severity colours for fpdf2 rendering (RGB tuples)
SEVERITY_COLORS_IEC = {
    0: {"rgb": (168, 203, 26),  "label": "Cat 0 — No Action",  "text_rgb": (255, 255, 255)},
    1: {"rgb": (168, 203, 26),  "label": "Cat 1 — Log",        "text_rgb": (255, 255, 255)},
    2: {"rgb": (227, 179, 65),  "label": "Cat 2 — Monitor",    "text_rgb": (7, 19, 29)},
    3: {"rgb": (248, 81, 73),   "label": "Cat 3 — Planned",    "text_rgb": (255, 255, 255)},
    4: {"rgb": (139, 0, 0),     "label": "Cat 4 — Urgent",     "text_rgb": (255, 255, 255)},
}

# Condition rating RGB colours for fpdf2
CONDITION_COLORS_RGB = {
    "A": (168, 203, 26),    # lime green
    "B": (227, 179, 65),    # amber
    "C": (248, 81, 73),     # red
    "D": (139, 0, 0),       # dark red
}

CONDITION_TEXT_RGB = {
    "A": (7, 19, 29),
    "B": (7, 19, 29),
    "C": (255, 255, 255),
    "D": (255, 255, 255),
}

# Zone colours for blade map (keyed -1 to 4; -1 = no defects)
ZONE_COLORS_IEC = {
    -1: (47, 55, 98),       # slate — no defects (dark)
    0:  (168, 203, 26),     # lime green
    1:  (168, 203, 26),     # lime green
    2:  (227, 179, 65),     # amber
    3:  (248, 81, 73),      # red
    4:  (139, 0, 0),        # dark red
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


def _fill_page_bg(pdf: "BDDAReport"):
    """Fill the entire A4 page with BRAND_DARK background."""
    pdf.set_fill_color(*BRAND_DARK)
    pdf.rect(0, 0, 210, 297, style="F")


def _draw_dot_grid(pdf: "BDDAReport", x: float, y: float,
                   cols: int = 12, rows: int = 10,
                   spacing: float = 5.0, dot_r: float = 0.6,
                   alpha_color: tuple = (168, 203, 26)):
    """Draw a dot grid pattern (decorative, lime green at low opacity).
    Used on cover top-left corner and section intro pages.
    Since fpdf2 has no per-shape alpha, we simulate low opacity with a
    dark-blended colour: mix BRAND_DARK + lime at ~15%.
    """
    r = int(BRAND_DARK[0] * 0.82 + alpha_color[0] * 0.18)
    g = int(BRAND_DARK[1] * 0.82 + alpha_color[1] * 0.18)
    b = int(BRAND_DARK[2] * 0.82 + alpha_color[2] * 0.18)
    pdf.set_fill_color(r, g, b)
    for row in range(rows):
        for col in range(cols):
            cx = x + col * spacing
            cy = y + row * spacing
            pdf.circle(x=cx, y=cy, radius=dot_r, style="F")


def _embed_bg_image(pdf: "BDDAReport", img_path: Path,
                    x: float = 0, y: float = 0,
                    w: float = 210, h: float = 297,
                    opacity: float = 0.15):
    """Embed a background image desaturated and darkened for atmosphere.
    opacity: 0.0–1.0 — how much the image shows through the dark overlay.
    """
    if not img_path.exists() or not HAS_PILLOW:
        return
    try:
        with PILImage.open(img_path) as img:
            img = img.convert("RGB")
            # Desaturate fully → greyscale look
            img = ImageEnhance.Color(img).enhance(0.0)
            # Darken
            img = ImageEnhance.Brightness(img).enhance(0.5)
            # Resize to fit
            target_px = (int(w * 11.8), int(h * 11.8))  # 300dpi ≈ 11.8px/mm
            img = img.resize(target_px, PILImage.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            buf.seek(0)
        # Draw the dark page fill first, then image on top at desired opacity
        # We achieve opacity by blending: draw dark rect, then image
        # fpdf2 supports transparency via set_alpha when using FPDF.set_alpha
        try:
            pdf.set_alpha(opacity)
            pdf.image(buf, x=x, y=y, w=w, h=h)
            pdf.set_alpha(1.0)
        except AttributeError:
            # Older fpdf2 — just embed without alpha
            pdf.image(buf, x=x, y=y, w=w, h=h)
    except Exception:
        pass  # Silent fail — bg image is decorative only


def _draw_section_title(pdf: "BDDAReport", number: str, title: str,
                        x: float = None, y: float = None,
                        num_size: int = 11, title_size: int = 22):
    """Draw WINDIA-style section title: '02 section\\ntitle.' layout.
    Number in lime green, title in white, trailing dot in lime.
    """
    if x is None:
        x = pdf.l_margin
    if y is None:
        y = pdf.get_y()

    # Number prefix (lime, smaller)
    pdf.set_xy(x, y)
    pdf._font("B", num_size)
    pdf.set_text_color(*BRAND_PRIMARY)
    pdf.cell(14, num_size * 0.6, number, align="L")

    # Title word (white, large) on same line after number
    pdf._font("B", title_size)
    pdf.set_text_color(*BRAND_WHITE)
    # Split title: first word on number line, rest on next line
    parts = title.split(" ", 1)
    pdf.set_xy(x + 14, y - 2)
    pdf.cell(0, title_size * 0.6, parts[0], align="L", new_x="LMARGIN", new_y="NEXT")

    if len(parts) > 1:
        # Rest of title with trailing lime dot
        rest = parts[1]
        pdf.set_xy(x, pdf.get_y() - 2)
        pdf._font("B", title_size)
        pdf.set_text_color(*BRAND_WHITE)
        pdf.cell(0, title_size * 0.6, rest + ".", align="L", new_x="LMARGIN", new_y="NEXT")
    else:
        # Add lime dot inline
        pdf.set_xy(x, pdf.get_y())
        pdf._font("B", title_size)
        pdf.set_text_color(*BRAND_PRIMARY)
        pdf.cell(8, title_size * 0.5, ".", align="L", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)


def _draw_accent_bar(pdf: "BDDAReport", x: float, y: float,
                     w: float = None, h: float = 0.8, vertical: bool = False):
    """Draw a lime green accent bar (horizontal or vertical)."""
    if w is None:
        w = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_fill_color(*BRAND_PRIMARY)
    if vertical:
        pdf.rect(x, y, h, w, style="F")   # h=thickness, w=length when vertical
    else:
        pdf.rect(x, y, w, h, style="F")


def _draw_module_card(pdf: "BDDAReport", x: float, y: float,
                      w: float, h: float,
                      icon: str, title: str, body: str,
                      tags: str = ""):
    """Draw a WINDIA-style module card with lime left-accent bar.
    icon: unicode char (e.g. '⚡'), title: card heading, body: description text.
    Matches the 'analyse plane / conceptualise plane' card style.
    """
    # Card background
    pdf.set_fill_color(*BRAND_NAVY)
    pdf.set_draw_color(*BRAND_SLATE)
    pdf.set_line_width(0.3)
    pdf.rect(x, y, w, h, style="FD")

    # Lime left accent bar (3px)
    pdf.set_fill_color(*BRAND_PRIMARY)
    pdf.rect(x, y, 3, h, style="F")

    # Icon box (small lime-bordered square)
    icon_box_size = 8
    pdf.set_fill_color(*BRAND_SLATE)
    pdf.rect(x + 6, y + 4, icon_box_size, icon_box_size, style="F")
    pdf.set_xy(x + 6, y + 4)
    pdf._font("B", 8)
    pdf.set_text_color(*BRAND_PRIMARY)
    pdf.cell(icon_box_size, icon_box_size, icon, align="C")

    # Title
    pdf.set_xy(x + 17, y + 5)
    pdf._font("B", 9)
    pdf.set_text_color(*BRAND_WHITE)
    pdf.multi_cell(w - 20, 5, title, new_x="LMARGIN", new_y="NEXT")

    # Body text
    body_y = max(pdf.get_y(), y + 16)
    pdf.set_xy(x + 6, body_y)
    pdf._font("", 7)
    pdf.set_text_color(*BRAND_LAVENDER)
    pdf.multi_cell(w - 10, 4, body, new_x="LMARGIN", new_y="NEXT")

    # Tags (lime, small)
    if tags:
        tag_y = y + h - 7
        pdf.set_xy(x + 6, tag_y)
        pdf._font("", 6)
        pdf.set_text_color(*BRAND_PRIMARY)
        pdf.cell(w - 10, 5, tags, align="L")


def _draw_stat_card(pdf: "BDDAReport", x: float, y: float,
                    w: float, h: float,
                    icon: str, label: str, value: str,
                    value_color: tuple = None):
    """KPI stat card: dark navy bg, lime top accent, icon, large value, small label.
    Matches the 'IN PROGRESS / SCHEDULED / COMPLETED' style from reference.
    """
    if value_color is None:
        value_color = BRAND_WHITE

    # Card bg
    pdf.set_fill_color(*BRAND_NAVY)
    pdf.set_draw_color(*BRAND_SLATE)
    pdf.set_line_width(0.2)
    pdf.rect(x, y, w, h, style="FD")

    # Top lime accent bar
    pdf.set_fill_color(*BRAND_PRIMARY)
    pdf.rect(x, y, w, 2, style="F")

    # Icon (top-left inside card)
    pdf.set_xy(x + 3, y + 5)
    pdf._font("", 9)
    pdf.set_text_color(*BRAND_GREY)
    pdf.cell(10, 6, icon, align="L")

    # Label (uppercase, grey, small — top-right area)
    pdf.set_xy(x + 13, y + 6)
    pdf._font("", 6)
    pdf.set_text_color(*BRAND_GREY)
    pdf.cell(w - 16, 5, label.upper(), align="L")

    # Large value
    pdf.set_xy(x + 3, y + 12)
    pdf._font("B", 18)
    pdf.set_text_color(*value_color)
    pdf.cell(w - 6, 12, value, align="L")


def _draw_image_frame(pdf: "BDDAReport", img_path: Optional[str],
                      x: float, y: float, w: float, h: float,
                      caption: str = "", badge: str = "",
                      badge_color: tuple = None):
    """Draw an image in a dark frame with optional caption strip and severity badge.
    Matches the surveillance/blade photo card style from reference.
    """
    # Outer dark border frame
    pdf.set_fill_color(*BRAND_NAVY)
    pdf.set_draw_color(*BRAND_SLATE)
    pdf.set_line_width(0.4)
    pdf.rect(x, y, w, h, style="FD")

    # Image area (inset 1mm from border)
    img_x, img_y = x + 1, y + 1
    img_w, img_h = w - 2, h - 2 - (8 if caption else 0)

    path = Path(img_path) if img_path else None
    if path and path.exists():
        try:
            if HAS_PILLOW:
                with PILImage.open(path) as img:
                    img = img.convert("RGB")
                    img.thumbnail((int(img_w * 11.8), int(img_h * 11.8)), PILImage.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=80)
                    buf.seek(0)
                pdf.image(buf, x=img_x, y=img_y, w=img_w, h=img_h, keep_aspect_ratio=True)
            else:
                pdf.image(str(path), x=img_x, y=img_y, w=img_w, h=img_h, keep_aspect_ratio=True)
        except Exception:
            _draw_placeholder(pdf, img_x, img_y, img_w, img_h)
    else:
        _draw_placeholder(pdf, img_x, img_y, img_w, img_h)

    # Caption strip (semi-dark bar at bottom of image)
    if caption:
        cap_y = y + h - 9
        pdf.set_fill_color(*BRAND_NAVY)
        pdf.rect(x + 1, cap_y, w - 2, 8, style="F")
        pdf.set_xy(x + 3, cap_y + 1)
        pdf._font("", 6)
        pdf.set_text_color(*BRAND_LAVENDER)
        pdf.cell(w - 6, 6, caption[:40], align="L")

    # Severity badge (top-right corner)
    if badge:
        bc = badge_color or BRAND_RED
        badge_w = min(len(badge) * 2 + 6, 30)
        pdf.set_fill_color(*bc)
        pdf.rect(x + w - badge_w - 1, y + 2, badge_w, 6, style="F")
        pdf.set_xy(x + w - badge_w - 1, y + 2)
        pdf._font("B", 5)
        pdf.set_text_color(*BRAND_WHITE)
        pdf.cell(badge_w, 6, badge, align="C")


def _draw_placeholder(pdf: "BDDAReport", x: float, y: float, w: float, h: float):
    """Grey placeholder rect when no image available."""
    pdf.set_fill_color(*BRAND_SLATE)
    pdf.rect(x, y, w, h, style="F")
    pdf.set_xy(x, y + h / 2 - 3)
    pdf._font("I", 6)
    pdf.set_text_color(*BRAND_GREY)
    pdf.cell(w, 6, "No image", align="C")


def _draw_isometric_turbine(pdf: "BDDAReport", cx: float, cy: float, scale: float = 1.0):
    """Draw a simplified isometric wind turbine in white line art with lime green accents.
    cx, cy = center base of tower. scale = size multiplier.
    Matches the 'diagram of production of wind energy' reference illustration style.
    """
    # — Tower (vertical rectangle, white outline) —
    tw = 4 * scale    # tower width
    th = 55 * scale   # tower height
    tx = cx - tw / 2
    ty = cy - th

    pdf.set_draw_color(*BRAND_WHITE)
    pdf.set_fill_color(*BRAND_SLATE)
    pdf.set_line_width(0.4)
    pdf.rect(tx, ty, tw, th, style="FD")

    # — Nacelle (box at top of tower) —
    nw = 12 * scale
    nh = 6 * scale
    nx = cx - nw / 2
    ny = ty - nh
    pdf.set_fill_color(*BRAND_SLATE)
    pdf.rect(nx, ny, nw, nh, style="FD")

    # — Hub (small circle at nacelle front) —
    hx = nx
    hy = ny + nh / 2
    pdf.set_fill_color(*BRAND_PRIMARY)
    pdf.circle(x=hx, y=hy, radius=2 * scale, style="FD")

    # — 3 Rotor blades (simplified: lines at 0°, 120°, 240°) —
    blade_len = 28 * scale
    pdf.set_draw_color(*BRAND_WHITE)
    pdf.set_line_width(0.8 * scale)
    for angle_deg in [90, 210, 330]:
        angle = math.radians(angle_deg)
        bx2 = hx + blade_len * math.cos(angle)
        by2 = hy + blade_len * math.sin(angle)
        pdf.line(hx, hy, bx2, by2)

    # — Power cable (lime green, goes down tower to transformer) —
    pdf.set_draw_color(*BRAND_PRIMARY)
    pdf.set_line_width(0.6)
    cable_x = cx + 1
    pdf.line(cable_x, ty + th, cable_x, cy + 8 * scale)  # down tower

    # Ground line
    pdf.set_draw_color(*BRAND_GREY)
    pdf.set_line_width(0.3)
    pdf.line(cx - 50 * scale, cy, cx + 60 * scale, cy)

    # — Transformer box (lime fill) —
    trf_x = cx + 12 * scale
    trf_y = cy - 8 * scale
    trf_w = 10 * scale
    trf_h = 8 * scale
    pdf.set_fill_color(*BRAND_PRIMARY)
    pdf.set_draw_color(*BRAND_DARK)
    pdf.set_line_width(0.3)
    pdf.rect(trf_x, trf_y, trf_w, trf_h, style="FD")

    # Horizontal cable to transformer
    pdf.set_draw_color(*BRAND_PRIMARY)
    pdf.set_line_width(0.6)
    pdf.line(cable_x, cy + 8 * scale - 4 * scale, trf_x, trf_y + trf_h / 2)

    # Lime arrow from transformer (→ consumer/grid)
    arr_x1 = trf_x + trf_w
    arr_y = trf_y + trf_h / 2
    arr_x2 = arr_x1 + 14 * scale
    pdf.line(arr_x1, arr_y, arr_x2, arr_y)
    # Arrowhead
    pdf.line(arr_x2, arr_y, arr_x2 - 3 * scale, arr_y - 2 * scale)
    pdf.line(arr_x2, arr_y, arr_x2 - 3 * scale, arr_y + 2 * scale)

    # — Wind arrows (left side, wavy lines) —
    pdf.set_draw_color(*BRAND_PRIMARY)
    pdf.set_line_width(0.5)
    for i, wind_y in enumerate([hy - 8 * scale, hy, hy + 8 * scale]):
        wx1 = hx - 30 * scale
        wx2 = hx - 8 * scale
        # Simple horizontal arrow
        pdf.line(wx1, wind_y, wx2, wind_y)
        pdf.line(wx2, wind_y, wx2 - 3 * scale, wind_y - 2 * scale)
        pdf.line(wx2, wind_y, wx2 - 3 * scale, wind_y + 2 * scale)

    # — Simple tree silhouettes (white line art) —
    pdf.set_draw_color(*BRAND_WHITE)
    pdf.set_line_width(0.3)
    for i, tree_cx in enumerate([cx - 40 * scale, cx - 32 * scale,
                                  cx + 35 * scale, cx + 45 * scale]):
        tree_h = (10 + i % 2 * 3) * scale
        tree_w = 5 * scale
        tree_base = cy
        # Triangle tree
        pdf.line(tree_cx, tree_base, tree_cx, tree_base - tree_h)
        pdf.line(tree_cx - tree_w / 2, tree_base, tree_cx, tree_base - tree_h)
        pdf.line(tree_cx + tree_w / 2, tree_base, tree_cx, tree_base - tree_h)

    # Reset line width
    pdf.set_line_width(0.2)


def _draw_component_label(pdf: "BDDAReport", text: str, px: float, py: float,
                           lx: float, ly: float):
    """Draw a label with a leader line from (px,py) pointing to (lx,ly)."""
    pdf.set_draw_color(*BRAND_GREY)
    pdf.set_line_width(0.2)
    pdf.line(px, py, lx, ly)
    # Dot at pointer end
    pdf.set_fill_color(*BRAND_PRIMARY)
    pdf.circle(x=lx, y=ly, radius=0.8, style="F")
    # Label text
    pdf._font("", 6)
    pdf.set_text_color(*BRAND_WHITE)
    pdf.set_xy(px - 15 if px < lx else px + 1, py - 2)
    pdf.cell(14, 4, text, align="C" if abs(px - lx) < 5 else ("R" if px < lx else "L"))


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
    """AWID inspection report — fpdf2 subclass with dark-themed branded header/footer."""

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
        """Dark-themed branded header on all pages except cover (page 1)."""
        if self.page_no() == 1:
            return

        # Dark navy header bar
        self.set_fill_color(*BRAND_NAVY)
        self.rect(0, 0, 210, 16, style="F")

        self.set_y(5)
        self.set_x(15)
        self._font("B", 9)
        self.set_text_color(*BRAND_PRIMARY)
        self.cell(95, 6, "AWID", align="L")

        self._font("", 8)
        self.set_text_color(*BRAND_GREY)
        self.cell(0, 6, self.report_ref, align="R")

        # Lime green accent line below header bar
        self.set_draw_color(*BRAND_PRIMARY)
        self.set_line_width(0.4)
        self.line(0, 16, 210, 16)
        self.set_line_width(0.2)
        self.set_y(20)

    def footer(self):
        """Dark-themed footer on all pages except cover (page 1)."""
        if self.page_no() == 1:
            return

        # Dark navy footer bar
        self.set_fill_color(*BRAND_NAVY)
        self.rect(0, 283, 210, 14, style="F")

        self.set_y(286)
        self._font("", 7)
        self.set_text_color(*BRAND_GREY)
        self.cell(80, 5, "AWID — APAC Wind Inspections Drones", align="L")

        self.set_text_color(*BRAND_GREY)
        self.cell(0, 5, f"Page {self.page_no()}", align="C")

        self.set_text_color(*BRAND_RED)
        self._font("B", 7)
        self.cell(0, 5, "CONFIDENTIAL", align="R")


# ─── PAGE RENDERERS ───────────────────────────────────────────────────────────

def _render_cover(pdf: BDDAReport, report_data: dict):
    """Full-page dark cover: AWID brand, title, turbine info, condition badge."""
    pdf.add_page()
    _fill_page_bg(pdf)

    # ── Background image (greyscale turbine at low opacity) ──
    _embed_bg_image(pdf, BG_IMAGE_TURBINE, x=0, y=60, w=210, h=200, opacity=0.18)

    turbine = report_data.get("turbine", {})

    # ── Top navy brand band ──
    pdf.set_fill_color(*BRAND_NAVY)
    pdf.rect(0, 0, 210, 60, style="F")

    # ── Dot grid (decorative, top-left corner — over brand band) ──
    _draw_dot_grid(pdf, x=15, y=8, cols=14, rows=5, spacing=5.5, dot_r=0.5)

    # ── "AWID" brand name ──
    pdf.set_y(14)
    pdf.set_x(15)
    pdf.set_text_color(*BRAND_PRIMARY)
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 22)
    else:
        pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 12, "AWID", align="L")

    # ── Tagline ──
    pdf.set_y(28)
    pdf.set_x(15)
    pdf._font("", 10)
    pdf.set_text_color(*BRAND_GREY)
    pdf.cell(0, 7, "APAC Wind Inspections Drones", align="L")

    # ── Lime green accent line divider ──
    pdf.set_draw_color(*BRAND_PRIMARY)
    pdf.set_line_width(2.0)
    pdf.line(0, 60, 210, 60)
    pdf.set_line_width(0.2)

    # ── Main title ──
    pdf.set_y(78)
    pdf.set_text_color(*BRAND_WHITE)
    if pdf._fonts_registered:
        pdf.set_font("Inter", "B", 20)
    else:
        pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, "Wind Turbine Blade", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 12, "Inspection Report", align="C", new_x="LMARGIN", new_y="NEXT")

    # ── Divider ──
    pdf.ln(4)
    pdf.set_draw_color(*BRAND_GREY)
    pdf.set_line_width(0.4)
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
    pdf.set_text_color(*BRAND_WHITE)
    pdf.cell(0, 10, f"Turbine {turbine_id}", align="C", new_x="LMARGIN", new_y="NEXT")

    if pdf._fonts_registered:
        pdf.set_font("Inter", "", 12)
    else:
        pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(*BRAND_LAVENDER)
    site_line = f"{site_name}{', ' + country if country else ''}"
    pdf.cell(0, 8, site_line, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Inspection details ──
    pdf._font("", 10)
    pdf.set_text_color(*BRAND_GREY)
    pdf.cell(0, 7, f"Inspection Date: {insp_date}    |    Inspector: {inspector}", align="C", new_x="LMARGIN", new_y="NEXT")

    # Report reference
    report_ref = report_data.get("report_ref", "")
    pdf._font("I", 9)
    pdf.set_text_color(*BRAND_GREY)
    pdf.cell(0, 7, f"Reference: {report_ref}", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(12)

    # ── Condition rating badge ──
    condition = report_data.get("condition", "A")
    condition_info = report_data.get("condition_info", CONDITION_RATINGS["A"])
    badge_rgb = CONDITION_COLORS_RGB.get(condition, (168, 203, 26))
    badge_text_rgb = CONDITION_TEXT_RGB.get(condition, (7, 19, 29))

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
    pdf._font("", 10)
    pdf.cell(badge_w, 8, condition_info.get("label", ""), align="C")

    pdf.set_y(badge_y + badge_h + 8)

    # Condition description
    pdf.set_x(30)
    pdf._font("I", 9)
    pdf.set_text_color(*BRAND_GREY)
    pdf.cell(0, 6, condition_info.get("desc", ""), align="C")

    # ── CONFIDENTIAL footer strip ──
    # Disable auto page break — we're writing near bottom of cover page
    pdf.set_auto_page_break(auto=False)
    pdf.set_fill_color(*BRAND_NAVY)
    pdf.rect(0, 275, 210, 22, style="F")

    # Lime accent line above footer
    pdf.set_draw_color(*BRAND_PRIMARY)
    pdf.set_line_width(1.0)
    pdf.line(0, 275, 210, 275)
    pdf.set_line_width(0.2)

    pdf.set_y(279)
    pdf._font("B", 8)
    pdf.set_text_color(*BRAND_RED)
    pdf.cell(0, 5, "CONFIDENTIAL — FOR AUTHORIZED RECIPIENTS ONLY", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf._font("", 7)
    pdf.set_text_color(*BRAND_GREY)
    company = turbine.get("company_name", "AWID - APAC Wind Inspections Drones")
    pdf.cell(0, 5, f"{company} | wind-turbines-reports.onrender.com", align="C")
    # Re-enable auto page break
    pdf.set_auto_page_break(auto=True, margin=20)


def _render_toc(pdf: BDDAReport, report_data: dict):
    """Table of contents page (page 2) — dark theme."""
    pdf.add_page()
    _fill_page_bg(pdf)

    # ── Section heading ──
    pdf._font("B", 18)
    pdf.set_text_color(*BRAND_PRIMARY)
    pdf.cell(0, 12, "TABLE OF CONTENTS", new_x="LMARGIN", new_y="NEXT")

    # Lime green underline
    pdf.set_draw_color(*BRAND_PRIMARY)
    pdf.set_line_width(0.6)
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
            pdf._font("B", 10)
            pdf.set_text_color(*BRAND_WHITE)
            row_h = 8
        else:
            pdf._font("", 8)
            pdf.set_text_color(*BRAND_LAVENDER)
            row_h = 6

        pdf.set_x(pdf.l_margin + indent)

        # Name cell
        pdf.cell(name_width, row_h, name, align="L")

        # Page number
        if level == 0:
            pdf._font("", 10)
            pdf.set_text_color(*BRAND_GREY)

        pdf.cell(15, row_h, str(pg_num), align="R", new_x="LMARGIN", new_y="NEXT")


def _render_executive_summary(pdf: BDDAReport, report_data: dict):
    """Executive summary page — dark theme with stat cards."""
    pdf.add_page()
    _fill_page_bg(pdf)

    # ── Section heading ──
    pdf._font("B", 18)
    pdf.set_text_color(*BRAND_PRIMARY)
    pdf.cell(0, 12, "Executive Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*BRAND_PRIMARY)
    pdf.set_line_width(0.6)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(6)

    # ── Condition rating ──
    condition = report_data.get("condition", "A")
    condition_info = report_data.get("condition_info", CONDITION_RATINGS["A"])
    badge_rgb = CONDITION_COLORS_RGB.get(condition, (168, 203, 26))
    badge_text_rgb = CONDITION_TEXT_RGB.get(condition, (7, 19, 29))

    # Badge rectangle
    badge_x = pdf.l_margin
    badge_y = pdf.get_y()
    badge_w = 55
    badge_h = 22
    pdf.set_fill_color(*badge_rgb)
    pdf.rect(badge_x, badge_y, badge_w, badge_h, style="F")
    pdf.set_xy(badge_x, badge_y + 3)
    pdf.set_text_color(*badge_text_rgb)
    pdf._font("B", 14)
    pdf.cell(badge_w, 9, f"Condition {condition}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_xy(badge_x, badge_y + 13)
    pdf._font("", 9)
    pdf.cell(badge_w, 7, condition_info.get("label", ""), align="C")

    # Condition description (right of badge) — dark navy card
    desc_x = badge_x + badge_w + 4
    desc_y = badge_y
    desc_w = pdf.w - pdf.l_margin - pdf.r_margin - badge_w - 4
    pdf.set_fill_color(*BRAND_NAVY)
    pdf.rect(desc_x, desc_y, desc_w, badge_h, style="F")
    pdf.set_xy(desc_x + 4, desc_y + 4)
    pdf._font("", 9)
    pdf.set_text_color(*BRAND_LAVENDER)
    pdf.multi_cell(desc_w - 8, 6, condition_info.get("desc", ""))

    pdf.set_y(badge_y + badge_h + 8)

    # ── Triage statistics — WINDIA-style stat cards ──
    triage_stats = report_data.get("triage_stats")
    if triage_stats:
        pdf._font("B", 9)
        pdf.set_text_color(*BRAND_GREY)
        pdf.cell(0, 7, "INSPECTION STATISTICS", new_x="LMARGIN", new_y="NEXT")

        total_def = report_data.get("total_defects", 0)
        crit_def  = report_data.get("critical_count", 0)
        stats = [
            ("#",  "IMAGES SCANNED",    str(triage_stats.get("total", 0)),   None),
            ("!",  "FLAGGED",           str(triage_stats.get("flagged", 0)),  BRAND_AMBER),
            (">",  "DEFECTS FOUND",     str(total_def),                       None),
            ("X",  "CRITICAL",          str(crit_def),                        BRAND_RED if crit_def else None),
        ]

        card_w = 42
        card_h = 26
        card_gap = (pdf.w - pdf.l_margin - pdf.r_margin - 4 * card_w) / 3
        card_y = pdf.get_y() + 2

        for i, (icon, label, value, val_color) in enumerate(stats):
            cx = pdf.l_margin + i * (card_w + card_gap)
            _draw_stat_card(pdf, cx, card_y, card_w, card_h,
                            icon=icon, label=label, value=value,
                            value_color=val_color or BRAND_WHITE)

        pdf.set_y(card_y + card_h + 8)
        pdf.set_draw_color(*BRAND_SLATE)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(6)

    # ── Defect summary table (IEC Cat 0-4) ──
    pdf._font("B", 11)
    pdf.set_text_color(*BRAND_PRIMARY)
    total_defects = report_data.get("total_defects", 0)
    critical_count = report_data.get("critical_count", 0)
    pdf.cell(0, 8, f"Defect Summary  (Total: {total_defects}  |  Critical: {critical_count})", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    defects_by_cat = report_data.get("defects_by_cat", {})
    content_width = pdf.w - pdf.l_margin - pdf.r_margin

    # Table header — dark navy with lime green text
    pdf.set_fill_color(*BRAND_NAVY)
    pdf.set_text_color(*BRAND_PRIMARY)
    pdf._font("B", 9)
    col_widths = [content_width * 0.12, content_width * 0.45, content_width * 0.20, content_width * 0.23]
    pdf.cell(col_widths[0], 8, "Cat", border=0, fill=True, align="C")
    pdf.cell(col_widths[1], 8, "Description", border=0, fill=True, align="L")
    pdf.cell(col_widths[2], 8, "Count", border=0, fill=True, align="C")
    pdf.cell(col_widths[3], 8, "Action", border=0, fill=True, align="L", new_x="LMARGIN", new_y="NEXT")

    action_labels_map = {
        0: "No action required",
        1: "Log and monitor",
        2: "Plan maintenance",
        3: "Schedule repair",
        4: "Urgent — repair ASAP",
    }

    for cat in range(0, 5):
        info = SEVERITY_COLORS_IEC[cat]
        count = defects_by_cat.get(cat, 0)

        # Coloured category badge cell
        pdf.set_fill_color(*info["rgb"])
        pdf.set_text_color(*info["text_rgb"])
        pdf._font("B", 9)
        pdf.cell(col_widths[0], 8, f"Cat {cat}", border="B", fill=True, align="C")

        # Alternating dark row fill
        if cat % 2 == 0:
            row_fill = BRAND_DARK
        else:
            row_fill = BRAND_NAVY
        pdf.set_fill_color(*row_fill)
        pdf.set_text_color(*BRAND_LAVENDER)
        pdf._font("", 9)
        pdf.cell(col_widths[1], 8, info["label"], border="B", fill=True, align="L")
        pdf._font("B", 9)
        pdf.set_text_color(*BRAND_WHITE)
        pdf.cell(col_widths[2], 8, str(count), border="B", fill=True, align="C")
        pdf._font("", 9)
        pdf.set_text_color(*BRAND_LAVENDER)
        pdf.cell(col_widths[3], 8, action_labels_map[cat], border="B", fill=True, align="L", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(8)

    # ── Critical findings (top 5) ──
    critical_findings = report_data.get("critical_findings", [])
    if critical_findings:
        pdf._font("B", 11)
        pdf.set_text_color(*BRAND_PRIMARY)
        pdf.cell(0, 8, "Top Critical Findings", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        for i, defect in enumerate(critical_findings[:5], 1):
            cat = defect.get("category", 0)
            info = SEVERITY_COLORS_IEC.get(cat, SEVERITY_COLORS_IEC[0])
            blade = defect.get("blade", "?")
            zone = defect.get("zone", "?")
            pos = defect.get("position", "?")
            defect_name = defect.get("defect_name", "Unknown")

            # Severity indicator bar
            pdf.set_fill_color(*info["rgb"])
            pdf.rect(pdf.l_margin, pdf.get_y() + 1, 4, 6, style="F")
            pdf.set_x(pdf.l_margin + 6)
            pdf._font("B", 9)
            pdf.set_text_color(*info["rgb"])
            pdf.cell(15, 8, f"Cat {cat}", align="L")
            pdf._font("", 9)
            pdf.set_text_color(*BRAND_LAVENDER)
            pdf.cell(20, 8, f"Blade {blade}", align="L")
            pdf.cell(25, 8, f"{zone}/{pos}", align="L")
            short_name = defect_name[:70]
            pdf.set_text_color(*BRAND_WHITE)
            pdf.cell(0, 8, short_name, align="L", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)

    # ── Recommendation — dark navy card with lime accent ──
    reco_map = {
        "A": "The turbine blades are in good condition. Continue routine annual inspections. No immediate action required.",
        "B": "Minor to moderate defects detected. Schedule planned maintenance within the next service window. Monitor identified defects at 6-month intervals.",
        "C": "High-priority defects require urgent attention. Initiate repair scheduling immediately. Perform NDT inspection on affected blade sections before next operational season.",
        "D": "Critical structural defects detected. Consider temporarily stopping the turbine pending engineering review. Immediate repair assessment required. Do not defer action.",
    }

    reco_text = reco_map.get(condition, reco_map["A"])

    pdf._font("B", 10)
    pdf.set_text_color(*BRAND_PRIMARY)
    pdf.cell(0, 7, "Recommendation", new_x="LMARGIN", new_y="NEXT")

    reco_x = pdf.l_margin
    reco_y = pdf.get_y()
    reco_w = pdf.w - pdf.l_margin - pdf.r_margin

    # Dark navy recommendation card
    pdf.set_fill_color(*BRAND_NAVY)
    card_height = 20
    pdf.rect(reco_x, reco_y, reco_w, card_height, style="F")

    # Lime accent bar on left
    pdf.set_fill_color(*BRAND_PRIMARY)
    pdf.rect(reco_x, reco_y, 3, card_height, style="F")

    # Recommendation text
    pdf.set_xy(reco_x + 7, reco_y + 4)
    pdf._font("", 9)
    pdf.set_text_color(*BRAND_LAVENDER)
    pdf.multi_cell(reco_w - 10, 6, reco_text)

    # ── Approach module cards (2-column grid) ──
    # Shows the inspection workflow like the WINDIA 'exercise approach' cards
    pdf.set_y(reco_y + card_height + 10)
    if pdf.get_y() < 200:  # Only if there's space remaining
        pdf._font("B", 9)
        pdf.set_text_color(*BRAND_GREY)
        pdf.cell(0, 7, "INSPECTION METHODOLOGY", new_x="LMARGIN", new_y="NEXT")

        content_width = pdf.w - pdf.l_margin - pdf.r_margin
        mod_w = content_width / 2 - 3
        mod_h = 32
        mod_y = pdf.get_y() + 2

        modules = [
            ("01", "Drone Triage", "High-resolution aerial survey of all blade surfaces. 4-quadrant tile analysis identifies potential damage zones automatically.", "AI · Vision · 4-tile"),
            ("02", "Defect Classification", "IEC 61400-based severity scoring (Cat 0-4) combined with BDDA 0-10 proprietary scale. All defects georeferenced to blade zone.", "IEC 61400 · BDDA Scale"),
            ("03", "Deep Analysis",  "AI structural analysis of critical findings. Root cause, failure risk, and repair cost estimation per defect.", "claude-opus-4-6 · NLP"),
            ("04", "Report Generation", "Professional client-deliverable PDF with per-blade zone maps, action matrix, and prioritised recommendations.", "fpdf2 · AWID Brand"),
        ]

        for i, (icon, title, body, tags) in enumerate(modules):
            col = i % 2
            row = i // 2
            mx = pdf.l_margin + col * (mod_w + 6)
            my = mod_y + row * (mod_h + 4)
            _draw_module_card(pdf, mx, my, mod_w, mod_h, icon, title, body, tags)


def _embed_defect_image(pdf: BDDAReport, image_path: str, x: float, y: float,
                        w: float = 80, h: float = 80):
    """Embed defect thumbnail at (x, y); draw dark placeholder if file missing or unreadable."""
    path = Path(image_path) if image_path else None
    if not path or not path.exists():
        # Dark slate placeholder
        pdf.set_fill_color(*BRAND_SLATE)
        pdf.rect(x, y, w, h, style="F")
        pdf.set_draw_color(*BRAND_GREY)
        pdf.rect(x, y, w, h, style="D")
        pdf.set_xy(x, y + h / 2 - 4)
        pdf._font("I", 7)
        pdf.set_text_color(*BRAND_GREY)
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
        pdf.set_fill_color(*BRAND_SLATE)
        pdf.rect(x, y, w, h, style="F")
        pdf.set_xy(x, y + h / 2 - 4)
        pdf._font("I", 7)
        pdf.set_text_color(*BRAND_GREY)
        pdf.cell(w, 6, "Image error", align="C")


def _render_defect_page(pdf: BDDAReport, defect: dict, defect_index: int, total_defects: int):
    """Render one defect per page — dark theme: severity band, image, metadata, analysis."""
    _fill_page_bg(pdf)

    cat = defect.get("category", 0)
    severity_info = SEVERITY_COLORS_IEC.get(cat, SEVERITY_COLORS_IEC[0])

    # ── Page title ──
    pdf._font("B", 14)
    pdf.set_text_color(*BRAND_WHITE)
    pdf.cell(0, 10, f"Defect Finding {defect_index}/{total_defects}", new_x="LMARGIN", new_y="NEXT")

    # ── Severity colour band (full content width) ──
    band_y = pdf.get_y()
    band_w = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_fill_color(*severity_info["rgb"])
    pdf.rect(pdf.l_margin, band_y, band_w, 10, style="F")
    pdf.set_xy(pdf.l_margin, band_y + 1)
    pdf._font("B", 10)
    pdf.set_text_color(*severity_info["text_rgb"])
    pdf.cell(0, 8, severity_info["label"], align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Two-column area: image left, metadata right ──
    col_start_y = pdf.get_y()
    left_x = pdf.l_margin
    right_x = pdf.l_margin + 88  # 80mm image + 8mm gap
    meta_width = pdf.w - right_x - pdf.r_margin

    # Left column: image using _draw_image_frame (dark frame + caption + badge)
    sev_label = severity_info["label"]
    _draw_image_frame(pdf, defect.get("image_path", ""),
                      left_x, col_start_y, w=82, h=82,
                      caption=defect.get("zone", "") + " / " + defect.get("position", ""),
                      badge=f"Cat {cat}",
                      badge_color=severity_info["rgb"])

    # Right column: metadata fields
    def _meta_row(label: str, value: str):
        pdf.set_x(right_x)
        pdf._font("B", 7)
        pdf.set_text_color(*BRAND_GREY)
        pdf.cell(meta_width * 0.40, 5, label.upper(), align="L")
        pdf._font("", 8)
        pdf.set_text_color(*BRAND_LAVENDER)
        val_str = str(value) if value is not None else "—"
        pdf.cell(meta_width * 0.60, 5, val_str[:50], align="L", new_x="LMARGIN", new_y="NEXT")

    # Position at right column start
    pdf.set_xy(right_x, col_start_y)

    defect_name = defect.get("defect_name", "Unknown")
    pdf._font("B", 10)
    pdf.set_text_color(*BRAND_WHITE)
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

    # ── Visual description — module card ──
    visual_desc = defect.get("visual_description", "")
    content_width = pdf.w - pdf.l_margin - pdf.r_margin
    if visual_desc:
        desc_card_h = min(30, 12 + len(visual_desc) // 8)
        _draw_module_card(pdf,
                          x=pdf.l_margin, y=pdf.get_y(),
                          w=content_width, h=desc_card_h,
                          icon=">", title="Visual Description",
                          body=visual_desc[:280])
        pdf.set_y(pdf.get_y() + desc_card_h + 4)

    # ── Deep analysis (if available) — 2-column module cards ──
    analysis = defect.get("analysis")
    content_width = pdf.w - pdf.l_margin - pdf.r_margin
    if analysis:
        # Section label with accent bar
        _draw_accent_bar(pdf, pdf.l_margin, pdf.get_y(), w=content_width, h=0.6)
        pdf.ln(3)
        pdf._font("B", 9)
        pdf.set_text_color(*BRAND_PRIMARY)
        pdf.cell(0, 6, "DEEP ANALYSIS", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # 2-column module cards for the analysis data
        mod_w = content_width / 2 - 3
        mod_h = 28
        mod_y = pdf.get_y()

        failure_risk = analysis.get("failure_risk", {})
        safety_risk = failure_risk.get("safety_risk", "") if failure_risk else ""

        analysis_cards = [
            ("01", "Root Cause",          analysis.get("root_cause", "—")),
            ("02", "Recommended Action", analysis.get("recommended_action", "—")),
            ("03", "Repair Timeframe",   analysis.get("repair_timeframe", "—")),
            ("$",  "Estimated Cost",     str(analysis.get("estimated_cost_usd", "—"))),
        ]
        if safety_risk:
            analysis_cards.append(("!", "Safety Risk", safety_risk))

        for i, (icon, title, body) in enumerate(analysis_cards):
            col = i % 2
            row = i // 2
            mx = pdf.l_margin + col * (mod_w + 6)
            my = mod_y + row * (mod_h + 3)
            _draw_module_card(pdf, mx, my, mod_w, mod_h, icon, title, body[:200])

        rows_used = (len(analysis_cards) + 1) // 2
        pdf.set_y(mod_y + rows_used * (mod_h + 3) + 3)

        if analysis.get("engineer_review_required"):
            pdf.set_fill_color(*BRAND_RED)
            pdf.set_draw_color(*BRAND_RED)
            pdf.rect(pdf.l_margin, pdf.get_y(), content_width, 8, style="F")
            pdf.set_xy(pdf.l_margin, pdf.get_y() + 1)
            pdf.set_text_color(*BRAND_WHITE)
            pdf._font("B", 8)
            pdf.cell(content_width, 6, "  ▲  ENGINEER REVIEW REQUIRED — Structural sign-off needed before repair", align="C", new_x="LMARGIN", new_y="NEXT")


def _render_turbine_diagram(pdf: BDDAReport, report_data: dict):
    """Turbine diagram page — isometric line-art turbine with component labels + blade image grid.
    Matches the WINDIA 'diagram of production of wind energy' reference illustration.
    """
    pdf.add_page()
    _fill_page_bg(pdf)

    # ── Background image (blade close-up, very low opacity) ──
    _embed_bg_image(pdf, BG_IMAGE_BLADE, x=0, y=0, w=210, h=297, opacity=0.08)

    # ── Section title (WINDIA style) ──
    _draw_section_title(pdf, "01", "Turbine Overview.", x=15, y=24, num_size=9, title_size=20)

    # ── Introductory text ──
    pdf.set_xy(15, pdf.get_y())
    pdf._font("", 9)
    pdf.set_text_color(*BRAND_LAVENDER)
    turbine = report_data.get("turbine", {})
    turbine_id = turbine.get("turbine_id", "N/A")
    site = turbine.get("site_name", "N/A")
    model = turbine.get("turbine_model", "")
    intro = f"Turbine {turbine_id} · {site}{' · ' + model if model else ''}"
    pdf.cell(0, 7, intro, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # ── Isometric turbine diagram (left half of page) ──
    # Draw centered in left ~120mm × 120mm region
    diagram_cx = 65
    diagram_cy = 180
    _draw_isometric_turbine(pdf, cx=diagram_cx, cy=diagram_cy, scale=1.1)

    # ── Component labels (matching the reference illustration) ──
    # Label positions: (label_text, label_x, label_y, pointer_x, pointer_y)
    labels = [
        ("NACELLE",          22, 110, diagram_cx - 5, 125),
        ("ROTOR BLADES",      22, 95,  diagram_cx - 20, 135),
        ("TOWER",            22, 155, diagram_cx - 2, 170),
        ("TRANSFORMER",      100, 185, diagram_cx + 22, 180),
        ("GRID CONNECTION",  100, 175, diagram_cx + 36, 179),
        ("WIND DIRECTION →", 22, 138, diagram_cx - 30, 138),
    ]
    for text, px, py, lx, ly in labels:
        _draw_component_label(pdf, text, px, py, lx, ly)

    # ── Blade image grid (right side, 2 columns) ──
    # Show up to 4 blade thumbnails from classify data
    right_x = 120
    grid_title_y = 24 + 14  # below section header

    pdf.set_xy(right_x, grid_title_y + 4)
    pdf._font("B", 8)
    pdf.set_text_color(*BRAND_GREY)
    pdf.cell(0, 6, "BLADE IMAGES — SAMPLE", new_x="LMARGIN", new_y="NEXT")
    _draw_accent_bar(pdf, right_x, pdf.get_y(), w=75, h=0.5)
    pdf.ln(3)

    # Gather up to 6 sample image paths from blade_findings
    blade_findings = report_data.get("blade_findings", {})
    sample_paths = []
    for blade, findings in blade_findings.items():
        for f in findings[:2]:  # max 2 per blade
            ip = f.get("image_path", "")
            if ip:
                sample_paths.append((f"Blade {blade} — {f.get('zone','')}", ip,
                                     f.get("category", 0)))
            if len(sample_paths) >= 6:
                break
        if len(sample_paths) >= 6:
            break

    # Draw 2-column image grid (3 rows max)
    img_w, img_h = 35, 28
    img_gap = 3
    grid_start_y = pdf.get_y()

    for idx, (caption, img_path, cat) in enumerate(sample_paths[:6]):
        col = idx % 2
        row = idx // 2
        gx = right_x + col * (img_w + img_gap)
        gy = grid_start_y + row * (img_h + img_gap + 4)
        sev_info = SEVERITY_COLORS_IEC.get(cat, SEVERITY_COLORS_IEC[0])
        badge_text = f"Cat {cat}"
        _draw_image_frame(pdf, img_path, gx, gy, img_w, img_h,
                          caption=caption[:22],
                          badge=badge_text,
                          badge_color=sev_info["rgb"])

    if not sample_paths:
        # Placeholder when no images available
        _draw_placeholder(pdf, right_x, grid_start_y, 75, 60)

    # ── Wind energy flow annotation box (bottom right) ──
    anno_y = max(grid_start_y + (len(sample_paths)//2 + 1) * 32, 210)
    if anno_y < 250:
        pdf.set_fill_color(*BRAND_NAVY)
        pdf.rect(right_x, anno_y, 75, 38, style="F")
        pdf.set_fill_color(*BRAND_PRIMARY)
        pdf.rect(right_x, anno_y, 2, 38, style="F")
        pdf.set_xy(right_x + 5, anno_y + 4)
        pdf._font("B", 8)
        pdf.set_text_color(*BRAND_WHITE)
        pdf.cell(68, 5, "Wind Energy Flow", new_x="LMARGIN", new_y="NEXT")
        pdf.set_xy(right_x + 5, pdf.get_y())
        pdf._font("", 7)
        pdf.set_text_color(*BRAND_LAVENDER)
        pdf.multi_cell(68, 4.5,
            "Wind → Rotor blades convert kinetic energy → Nacelle gearbox & generator "
            "→ Electrical power → Transformer steps up voltage → Grid distribution.")


def _render_action_matrix(pdf: BDDAReport, report_data: dict):
    """Action matrix page — dark theme, priority-sorted table colour-coded by severity."""
    pdf.add_page()
    _fill_page_bg(pdf)

    # ── Section heading ──
    pdf._font("B", 18)
    pdf.set_text_color(*BRAND_PRIMARY)
    pdf.cell(0, 12, "Action Matrix", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*BRAND_PRIMARY)
    pdf.set_line_width(0.6)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(6)

    action_matrix = report_data.get("action_matrix", [])

    if not action_matrix:
        pdf._font("I", 11)
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
        # Dark navy header with lime green text
        pdf.set_fill_color(*BRAND_NAVY)
        pdf.set_text_color(*BRAND_PRIMARY)
        pdf._font("B", 8)
        for (label, _), w in zip(cols, col_widths):
            pdf.cell(w, row_h, label, border=0, fill=True, align="C")
        pdf.ln(row_h)

    _draw_header()

    for i, item in enumerate(action_matrix):
        if pdf.will_page_break(row_h):
            pdf.add_page()
            _fill_page_bg(pdf)
            _draw_header()

        cat = item.get("category", 0)
        info = SEVERITY_COLORS_IEC.get(cat, SEVERITY_COLORS_IEC[0])

        # Severity-coloured priority badge cell
        pdf.set_fill_color(*info["rgb"])
        pdf.set_text_color(*info["text_rgb"])
        pdf._font("B", 7)
        pdf.cell(col_widths[0], row_h, item.get("priority", ""), border="B", fill=True, align="C")

        # Alternating dark row fills
        row_bg = BRAND_DARK if i % 2 == 0 else BRAND_NAVY
        pdf.set_fill_color(*row_bg)
        pdf.set_text_color(*BRAND_LAVENDER)
        pdf._font("", 7)

        values = [
            item.get("blade", ""),
            item.get("defect_id", ""),
            item.get("defect_name", "")[:40],
        ]
        widths_data = col_widths[1:4]

        for val, w in zip(values, widths_data):
            pdf.cell(w, row_h, str(val), border="B", fill=True, align="L")

        # Cat cell — severity colored badge
        pdf.set_fill_color(*info["rgb"])
        pdf.set_text_color(*info["text_rgb"])
        pdf._font("B", 7)
        pdf.cell(col_widths[4], row_h, f"Cat {cat}", border="B", fill=True, align="C")

        # Remaining cells
        pdf.set_fill_color(*row_bg)
        pdf.set_text_color(*BRAND_LAVENDER)
        pdf._font("", 7)
        remaining_values = [
            item.get("zone", ""),
            item.get("timeframe", ""),
            item.get("action", "")[:35],
        ]
        remaining_widths = col_widths[5:]
        for val, w in zip(remaining_values, remaining_widths):
            pdf.cell(w, row_h, str(val), border="B", fill=True, align="L")
        pdf.ln(row_h)


def _render_blade_map(pdf: BDDAReport, blade_label: str, blade_defects: list):
    """Per-blade defect map — dark theme: zone grid with severity colours, white circle markers."""
    _fill_page_bg(pdf)

    # ── Section heading ──
    pdf._font("B", 16)
    pdf.set_text_color(*BRAND_PRIMARY)
    pdf.cell(0, 10, f"Blade {blade_label} — Defect Map", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*BRAND_PRIMARY)
    pdf.set_line_width(0.6)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(6)

    zones = ["LE", "TE", "PS", "SS"]
    positions = ["Root", "Mid", "Tip"]
    cell_w, cell_h = 35, 18
    start_x = pdf.l_margin + 25  # leave room for zone labels on left
    start_y = pdf.get_y() + 10   # leave room for position labels on top

    # ── Position labels across top ──
    pdf._font("B", 8)
    pdf.set_text_color(*BRAND_LAVENDER)
    for col, pos in enumerate(positions):
        pdf.set_xy(start_x + col * cell_w, start_y - 8)
        pdf.cell(cell_w, 7, pos, align="C")

    # ── Zone grid ──
    for row, zone in enumerate(zones):
        # Zone label on left margin
        pdf._font("B", 8)
        pdf.set_text_color(*BRAND_LAVENDER)
        pdf.set_xy(pdf.l_margin, start_y + row * cell_h + cell_h / 2 - 3)
        pdf.cell(22, 6, zone, align="R")

        for col, pos in enumerate(positions):
            x = start_x + col * cell_w
            y = start_y + row * cell_h

            worst_cat = _worst_cat_in_zone(blade_defects, zone, pos)
            rgb = ZONE_COLORS_IEC.get(worst_cat, BRAND_SLATE)

            # Cell background with dark border
            pdf.set_fill_color(*rgb)
            pdf.set_draw_color(*BRAND_DARK)
            pdf.set_line_width(0.8)
            pdf.rect(x, y, cell_w, cell_h, style="FD")
            pdf.set_line_width(0.2)

            # Zone label inside cell (small, white)
            pdf._font("", 6)
            if worst_cat == -1:
                pdf.set_text_color(*BRAND_GREY)
            else:
                pdf.set_text_color(*BRAND_WHITE)
            pdf.set_xy(x, y + 2)
            pdf.cell(cell_w, 5, zone, align="C")

            # Defect count circle
            zone_count = sum(
                1 for d in blade_defects
                if d.get("zone") == zone and d.get("position") == pos
            )
            if zone_count > 0:
                cx = x + cell_w / 2
                cy = y + cell_h / 2 + 2
                # White circle marker
                pdf.set_fill_color(*BRAND_WHITE)
                pdf.set_draw_color(*BRAND_DARK)
                pdf.circle(x=cx, y=cy, radius=4, style="FD")
                # Count text in circle (dark)
                pdf._font("B", 7)
                pdf.set_text_color(*BRAND_DARK)
                pdf.set_xy(cx - 4, cy - 3.5)
                pdf.cell(8, 7, str(zone_count), align="C")

    # ── Severity legend ──
    legend_y = start_y + len(zones) * cell_h + 8

    pdf._font("B", 9)
    pdf.set_text_color(*BRAND_PRIMARY)
    pdf.set_xy(pdf.l_margin, legend_y)
    pdf.cell(0, 7, "Severity Legend", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    legend_items = [(-1, ZONE_COLORS_IEC[-1], "No defects")] + [
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
        pdf.set_draw_color(*BRAND_DARK)
        pdf.rect(x, legend_row_y, swatch_w, swatch_h, style="FD")
        pdf._font("", 7)
        pdf.set_text_color(*BRAND_LAVENDER)
        pdf.set_xy(x + swatch_w + 2, legend_row_y)
        pdf.cell(25, swatch_h, label, align="L")

    # ── Defect list for this blade ──
    if blade_defects:
        pdf.set_y(legend_row_y + swatch_h + 8)
        pdf._font("B", 9)
        pdf.set_text_color(*BRAND_PRIMARY)
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
            pdf._font("", 8)
            pdf.set_text_color(*BRAND_LAVENDER)
            zone = defect.get("zone", "")
            pos = defect.get("position", "")
            name = defect.get("defect_name", "Unknown")[:60]
            pdf.cell(0, 6, f"[{zone}/{pos}] {name}", new_x="LMARGIN", new_y="NEXT")


def _render_inspection_details(pdf: BDDAReport, report_data: dict):
    """Final page — dark theme: turbine specs, drone info, weather, GPS, legal disclaimer."""
    pdf.add_page()
    _fill_page_bg(pdf)

    # ── Section heading ──
    pdf._font("B", 18)
    pdf.set_text_color(*BRAND_PRIMARY)
    pdf.cell(0, 12, "Inspection Details", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*BRAND_PRIMARY)
    pdf.set_line_width(0.6)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(6)

    turbine = report_data.get("turbine", {})
    content_width = pdf.w - pdf.l_margin - pdf.r_margin
    half_w = content_width / 2 - 5

    def _section_box(title: str):
        """Draw a dark navy section heading box."""
        box_x = pdf.l_margin
        box_y = pdf.get_y()
        box_w = content_width
        pdf.set_fill_color(*BRAND_NAVY)
        pdf.rect(box_x, box_y, box_w, 9, style="F")
        # Lime accent bar on left
        pdf.set_fill_color(*BRAND_PRIMARY)
        pdf.rect(box_x, box_y, 3, 9, style="F")
        pdf.set_xy(box_x + 6, box_y + 1)
        pdf._font("B", 10)
        pdf.set_text_color(*BRAND_WHITE)
        pdf.cell(box_w - 6, 7, title)
        pdf.ln(11)

    def _detail_row(label: str, value: str, x_offset: float = 0):
        pdf.set_x(pdf.l_margin + x_offset)
        pdf._font("B", 8)
        pdf.set_text_color(*BRAND_GREY)
        pdf.cell(half_w * 0.45, 6, label.upper(), align="L")
        pdf._font("", 9)
        pdf.set_text_color(*BRAND_LAVENDER)
        val_str = str(value) if value is not None else "N/A"
        pdf.cell(half_w * 0.55, 6, val_str, align="L", new_x="LMARGIN", new_y="NEXT")

    # ── Turbine specifications ──
    _section_box("Turbine Specifications")

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
    _section_box("Drone & Equipment")

    drone_info = [
        ("Drone Model", turbine.get("drone_model", "")),
        ("Camera", turbine.get("camera", "")),
    ]
    for label, value in drone_info:
        _detail_row(label, value)

    pdf.ln(5)

    # ── Environmental conditions ──
    _section_box("Environmental Conditions")

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
        _section_box("Location")
        _detail_row("GPS Coordinates", f"{gps_lat:.6f}°N, {gps_lon:.6f}°E")
        pdf.ln(5)

    # ── Inspector notes ──
    notes = turbine.get("notes", "")
    if notes:
        _section_box("Inspector Notes")
        pdf._font("I", 9)
        pdf.set_text_color(*BRAND_LAVENDER)
        pdf.multi_cell(content_width, 6, notes)
        pdf.ln(5)

    # ── Engineer review count ──
    engineer_review_count = report_data.get("engineer_review_count", 0)
    if engineer_review_count > 0:
        pdf._font("B", 9)
        pdf.set_text_color(*BRAND_RED)
        pdf.cell(0, 7, f"Engineer Review Required: {engineer_review_count} defect(s) flagged for structural engineer sign-off.", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    # ── Generated at ──
    pdf._font("", 8)
    pdf.set_text_color(*BRAND_GREY)
    pdf.cell(0, 6, f"Report generated: {report_data.get('generated_at', '')}  |  Reference: {report_data.get('report_ref', '')}", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)

    # ── Legal disclaimer — dark navy card ──
    disclaimer_text = (
        "This report was generated using AI-assisted defect detection technology. "
        "All findings have been produced by automated image analysis and should be reviewed "
        "by a qualified wind turbine inspector before maintenance or repair decisions are made. "
        "AWID - APAC Wind Inspections Drones accepts no liability for decisions made solely on the basis of this report "
        "without independent engineering verification."
    )
    dis_x = pdf.l_margin
    dis_y = pdf.get_y()
    dis_w = content_width
    pdf.set_fill_color(*BRAND_NAVY)
    pdf.rect(dis_x, dis_y, dis_w, 22, style="F")
    pdf.set_fill_color(*BRAND_SLATE)
    pdf.rect(dis_x, dis_y, 3, 22, style="F")
    pdf.set_xy(dis_x + 6, dis_y + 4)
    pdf._font("I", 7)
    pdf.set_text_color(*BRAND_GREY)
    pdf.multi_cell(dis_w - 10, 4.5, disclaimer_text)


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

    # ── Turbine overview diagram (isometric + blade image grid) ──
    _render_turbine_diagram(pdf, report_data)

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

    print("report.py — fpdf2 PDF report module (Phase 4, dark theme)")

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
