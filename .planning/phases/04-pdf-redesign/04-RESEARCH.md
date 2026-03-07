# Phase 4: PDF Redesign - Research

**Researched:** 2026-03-07
**Domain:** fpdf2 PDF generation, font embedding, image embedding, programmatic drawing
**Confidence:** HIGH (fpdf2 API verified from official docs + source; data structures verified from codebase reading)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**A — Report Structure & Page Flow**
| Decision | Choice |
|----------|--------|
| Section ordering | Cover → Table of Contents → Executive Summary → Defect Findings by Blade → Action Matrix → Blade Map → Inspection Details |
| Table of Contents | Yes — page 2 |
| Layout density | Spacious — generous whitespace, professional feel |

**B — Branding & Visual Identity**
| Decision | Choice |
|----------|--------|
| Logo | Text-based header for now ("DroneWind Asia" styled). Layout accepts PNG at configurable path — swap in real logo later |
| Brand colours | AI-selected — professional wind energy / high-tech palette |
| Font | Custom TTF — modern, high-tech vibe (e.g., Inter, Exo 2, or similar clean sans-serif) |
| Header/footer | Yes — logo/brand name + page number + report reference on every page |

**Note:** Logo PNG generation is outside Claude Code scope. Text placeholder used until real logo is provided.

**C — Defect Presentation & Image Layout**
| Decision | Choice |
|----------|--------|
| Image thumbnail size | Large — 80×80mm |
| Image position | Grid layout |
| Metadata fields | Full set (all available fields per defect) |
| Defects per page | 1 defect per page (spacious, maximum detail) |

**D — Per-Blade Defect Map (PDF-06)**
| Decision | Choice |
|----------|--------|
| Blade diagram | Programmatic drawing with fpdf2 shapes (schematic) |
| Zone annotation | Mini-icons on blade diagram |
| Severity detail | Yes — severity colour on markers (colour-coded by IEC Cat) |

**Severity Colour Bands (from existing report.py)**
| IEC Category | Label | Colour |
|-------------|-------|--------|
| Cat 0 | No damage | Green |
| Cat 1 | Minor | Yellow |
| Cat 2 | Moderate | Orange |
| Cat 3 | Major | Red |
| Cat 4 | Critical | Dark Red |

**Technical Constraints (carried from PDF-SPEC.md)**
- fpdf2 replaces xhtml2pdf — no HTML/CSS, pure Python cell/rect/image API
- PDF generated from `build_report_data()` output in report.py
- Defect images available as base64 in triage results (stored in job JSON)
- DJI P1 source images deleted after triage — only tiles/thumbnails remain
- Must work on Render (Linux, no system fonts — bundle TTF)

### Claude's Discretion

None remaining — all gray areas resolved in CONTEXT.md.

### Deferred Ideas (OUT OF SCOPE)

None listed.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PDF-01 | PDF uses fpdf2 (replaces xhtml2pdf) | fpdf2 2.8.4 API verified; drop-in replacement for report.py's generate_pdf(); `build_report_data()` stays untouched |
| PDF-02 | DroneWind Asia branding (logo, colours, header/footer) | fpdf2 `header()`/`footer()` override pattern; TTF font bundling strategy confirmed for Render Linux |
| PDF-03 | Defect images embedded inline next to findings | fpdf2 `image()` accepts PIL Image objects and file paths; BytesIO confirmed in source; Pillow already in requirements.txt |
| PDF-04 | Severity colour-coding (Cat 0-4 colour bands) | fpdf2 `set_fill_color(r,g,b)` + `cell(fill=True)` or `table()` with FontFace; existing SEVERITY_COLORS hex values convert to RGB |
| PDF-05 | Executive summary page (defect counts, highest severity, recommendation) | `build_report_data()` already produces all needed fields; `condition_info`, `critical_count`, `defects_by_cat` map directly |
| PDF-06 | Per-blade defect map (blade diagram with annotated zones) | fpdf2 `rect()`, `line()`, `circle()`, `polygon()` with `style="FD"` for programmatic schematic; zone coords pre-calculable |
</phase_requirements>

---

## Summary

Phase 4 replaces the xhtml2pdf/WeasyPrint/Jinja2 HTML pipeline with a pure fpdf2 direct PDF construction approach. The scope is confined to `backend/report.py`: the `render_html()` and `generate_pdf()` functions are replaced by a new fpdf2-based generator. The `build_report_data()` function and all data assembly logic is preserved unchanged — it already produces all fields the PDF needs.

fpdf2 2.8.4 is the current stable release (confirmed on PyPI). The API is well-suited to this use case: header/footer overrides, TTF font embedding, image placement by coordinates, table context managers with colored rows, and primitive shape drawing for the blade map. All required capabilities are verified from official docs.

The key implementation risks are: (1) image availability at PDF generation time (original DJI files deleted post-triage — must use tiles/thumbnails stored in job dir), (2) font bundling for Render's Linux environment (no system fonts — TTF must ship with repo), and (3) the blade map diagram which requires coordinate math for zone layout. One defect per page with 80×80mm thumbnails is generous but straightforward with fpdf2's coordinate API.

**Primary recommendation:** Rewrite `report.py` in a single plan — replace the two HTML functions with an `FPDF` subclass that overrides `header()`/`footer()`, add a `generate_pdf_fpdf2(report_data, output_path)` function, and remove jinja2/xhtml2pdf/weasyprint from requirements.txt.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fpdf2 | 2.8.4 | Direct PDF construction — cells, images, shapes, tables | Pure Python, zero system deps, works on Render Linux, already in codebase plan |
| Pillow | >=10.0.0 | Image loading, resizing, BytesIO conversion before embedding | Already in requirements.txt; fpdf2 uses Pillow internally |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Inter or Exo 2 | TTF (static) | Custom sans-serif font for professional look | Required — Render has no system fonts; bundle 2-4 TTF files (Regular, Bold, Italic) |

### Removed
| Library | Replacing | Reason |
|---------|-----------|--------|
| xhtml2pdf >=0.2.11 | fpdf2 | xhtml2pdf is HTML-to-PDF with CSS limitations, fragile on headless servers |
| weasyprint | fpdf2 | Requires GTK/Pango system libs — unusable on Render |
| jinja2 >=3.1.0 | Not needed | Templates only used for report.html which is deleted |
| python-bidi 0.4.2 | Not needed | RTL text support only needed for jinja2 HTML template |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| fpdf2 | reportlab | ReportLab has richer layout but AGPL license, heavier dep |
| fpdf2 | weasyprint | Better CSS fidelity but requires system GTK/Pango — breaks Render |
| Inter TTF | DejaVu | DejaVu ships with fpdf2 (historical), but Inter/Exo2 is more modern-looking |

**Installation:**
```bash
pip install fpdf2>=2.8.0
# Remove: xhtml2pdf, weasyprint, jinja2, python-bidi
```

---

## Architecture Patterns

### Recommended Module Structure

```
backend/report.py              # MAJOR REWRITE — keep build_report_data(), replace rest
assets/fonts/                  # NEW — bundled TTF files (ship with repo)
    Inter-Regular.ttf
    Inter-Bold.ttf
    Inter-Italic.ttf
templates/                     # DELETE after Phase 4
    report.html                # DELETE
    report.css                 # DELETE
```

### Pattern 1: FPDF Subclass with Header/Footer Override

The standard fpdf2 pattern for per-page chrome. Called automatically on every `add_page()`.

```python
# Source: https://py-pdf.github.io/fpdf2/Tutorial.html
from fpdf import FPDF

class BDDAReport(FPDF):
    def __init__(self, report_data: dict):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.report_data = report_data
        self.report_ref = report_data.get("report_ref", "")

    def header(self):
        # Logo/brand left, report ref right
        self.set_font("Inter", style="B", size=10)
        self.set_text_color(15, 50, 90)          # brand dark blue
        self.cell(0, 8, "DroneWind Asia", align="L")
        self.set_font("Inter", style="", size=8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, self.report_ref, align="R")
        self.ln(2)
        # Thin rule under header
        self.set_draw_color(220, 220, 220)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Inter", style="", size=8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")
```

### Pattern 2: Adding Bundled TTF Fonts

Must call `add_font()` before any `set_font()`. Font files must be bundled in the repo — Render has no system fonts.

```python
# Source: https://py-pdf.github.io/fpdf2/Unicode.html
FONT_DIR = Path(__file__).parent.parent / "assets" / "fonts"

def _register_fonts(pdf: FPDF):
    pdf.add_font("Inter", style="",  fname=str(FONT_DIR / "Inter-Regular.ttf"))
    pdf.add_font("Inter", style="B", fname=str(FONT_DIR / "Inter-Bold.ttf"))
    pdf.add_font("Inter", style="I", fname=str(FONT_DIR / "Inter-Italic.ttf"))
```

**Font sourcing:** Inter is available at https://fonts.google.com/specimen/Inter — download static TTF files. Three files needed: Regular, Bold, Italic (no build step, pure TTF).

### Pattern 3: Image Embedding from File Path or PIL

Defect images stored as JPEG tiles in job directory. Images deleted after triage means only tiles remain — must use `image_path` from classify_data carefully.

```python
# Source: https://py-pdf.github.io/fpdf2/Images.html
# From file path (if file exists):
pdf.image(str(image_path), x=10, y=pdf.get_y(), w=80, h=80, keep_aspect_ratio=True)

# From PIL Image (e.g., after resize):
from PIL import Image
import io
img = Image.open(image_path).convert("RGB")
img.thumbnail((800, 800))   # resize before embed
buf = io.BytesIO()
img.save(buf, format="JPEG", quality=85)
buf.seek(0)
pdf.image(buf, x=10, y=pdf.get_y(), w=80, h=80)

# If image is missing — graceful fallback:
if Path(image_path).exists():
    pdf.image(str(image_path), x=x, y=y, w=80, h=80, keep_aspect_ratio=True)
else:
    # Draw placeholder rect
    pdf.set_fill_color(230, 230, 230)
    pdf.rect(x, y, 80, 80, style="F")
    pdf.set_xy(x, y + 35)
    pdf.set_font("Inter", style="I", size=8)
    pdf.cell(80, 10, "Image not available", align="C")
```

**IMPORTANT: Image availability issue.** DJI P1 source images are deleted after triage. The `image_path` field in classify_data points to paths like `/data/jobs/{job_id}/blade_A/LE_Mid_001.jpg` which are the classified images stored pre-deletion. Check whether these files survive (they should, since only the raw uploaded ZIPs are deleted, not the individual images used in classify). Must verify in `api.py` what exactly gets deleted.

### Pattern 4: Colour-Coded Table Rows (PDF-04)

fpdf2 `table()` context manager with `FontFace` for header styling. For per-row colour, use manual `set_fill_color()` + `cell(fill=True)`.

```python
# Source: https://py-pdf.github.io/fpdf2/Tables.html
from fpdf.fonts import FontFace

# Method A: fpdf2 table() with cell_fill_color per row (requires fpdf2 >= 2.7)
with pdf.table(borders_layout="MINIMAL", line_height=7) as table:
    for defect in blade_defects:
        row = table.row()
        rgb = hex_to_rgb(SEVERITY_RGB[defect["category"]])
        row.cell(defect["defect_id"], style=FontFace(fill_color=rgb))
        row.cell(defect["defect_name"], style=FontFace(fill_color=rgb))
        # etc.

# Method B: Manual cells (more control, simpler)
def _severity_row(pdf, defect):
    rgb = SEVERITY_RGB[defect["category"]]
    pdf.set_fill_color(*rgb)
    pdf.set_font("Inter", style="B", size=9)
    pdf.cell(30, 8, defect["defect_id"], border="B", fill=True)
    pdf.cell(0, 8, defect["defect_name"], border="B", fill=True, new_x="LMARGIN", new_y="NEXT")
```

### Pattern 5: Programmatic Blade Map (PDF-06)

Draw blade schematic using `rect()`, `line()`, and `circle()`. The blade is represented as a tapered rectangle with zone grid overlay.

```python
# Source: https://py-pdf.github.io/fpdf2/Shapes.html
# Blade schematic: root (wide) → tip (narrow)
# Layout: 12 cells (3 positions × 4 zones) in a grid

ZONE_COLORS = {
    0: (200, 230, 200),  # green — Cat 0
    1: (255, 240, 180),  # yellow
    2: (255, 200, 100),  # orange
    3: (230, 80, 80),    # red
    4: (140, 0, 0),      # dark red
}

def _draw_blade_map(pdf, blade_label, blade_defects):
    # Draw tapered blade outline
    pdf.set_draw_color(80, 80, 80)
    pdf.set_line_width(0.8)
    # Zones: Root/Mid/Tip columns, LE/TE/PS/SS rows
    cell_w, cell_h = 25, 12
    start_x, start_y = pdf.l_margin + 20, pdf.get_y()
    zones = ["LE", "TE", "PS", "SS"]
    positions = ["Root", "Mid", "Tip"]

    for row, zone in enumerate(zones):
        for col, pos in enumerate(positions):
            x = start_x + col * cell_w
            y = start_y + row * cell_h
            # Find worst defect in this zone+position
            worst_cat = _worst_cat_in_zone(blade_defects, zone, pos)
            rgb = ZONE_COLORS.get(worst_cat, (230, 230, 230))
            pdf.set_fill_color(*rgb)
            pdf.rect(x, y, cell_w, cell_h, style="FD")
            # Label
            pdf.set_xy(x, y + 3)
            pdf.set_font("Inter", size=7)
            pdf.cell(cell_w, 6, f"{zone}", align="C")

    # Add defect markers as circles
    for defect in blade_defects:
        col = positions.index(defect.get("position", "Mid")) if defect.get("position") in positions else 1
        row = zones.index(defect.get("zone", "LE")) if defect.get("zone") in zones else 0
        cx = start_x + col * cell_w + cell_w / 2
        cy = start_y + row * cell_h + cell_h / 2
        worst_rgb = ZONE_COLORS.get(defect["category"], (128, 128, 128))
        pdf.set_fill_color(*worst_rgb)
        pdf.circle(x=cx - 3, y=cy - 3, radius=3, style="F")
```

### Pattern 6: Page Break Management

For 1 defect per page layout, explicit `add_page()` before each defect section. For tables that might span pages, use `will_page_break()`.

```python
# Source: https://py-pdf.github.io/fpdf2/PageBreaks.html
# Explicit page break before each defect:
for i, defect in enumerate(blade_defects):
    pdf.add_page()   # each defect gets its own page
    _render_defect_page(pdf, defect)

# Or for action matrix table — check before adding row:
if pdf.will_page_break(row_height):
    pdf.add_page()
```

### Pattern 7: Table of Contents (Page 2)

fpdf2 does not have built-in TOC support. Implementation: render all pages first, track page numbers in a dict, then insert TOC page at position 2. In practice: generate TOC after all other pages, since page numbers are known.

```python
# Strategy: deferred TOC with known page numbers
# After rendering all content pages, use pdf.page to get final page count
# Insert TOC as page 2 using FPDF.insert_toc_placeholder() if available,
# or use two-pass: first pass collects page numbers, second pass renders.
# SIMPLER: since content is deterministic (1 defect/page), calculate page
# numbers before rendering:
page_map = {
    "cover": 1,
    "toc": 2,
    "executive_summary": 3,
    "blade_A": 4,   # adjust based on defect count
    # etc.
}
```

**Note:** fpdf2 has `insert_toc_placeholder()` and `set_section_title_styles()` in recent versions for automatic TOC. Verify availability in 2.8.4 — if present, use it. If not, pre-calculate page offsets (deterministic since 1 defect/page).

### Anti-Patterns to Avoid
- **Setting font before add_page():** Always call `add_page()` first, then configure fonts.
- **Using hex colours directly:** fpdf2 uses RGB integers (0-255), not hex strings. Convert hex to RGB tuples before use.
- **Embedding raw base64 strings directly:** fpdf2's `image()` can accept BytesIO but not raw base64 strings. Decode base64 → BytesIO first.
- **Reusing FPDF instance across requests:** Create a new `BDDAReport` instance per PDF generation call (thread safety).
- **Calling output() then adding content:** `output()` finalizes the document. Build everything first.
- **Missing image path assumption:** Don't assume image paths from `classify_data` exist. Files may be gone if job directory was cleaned. Always guard with `Path(p).exists()`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Colour-coded table rows | Custom row renderer | fpdf2 `table()` + `FontFace(fill_color=...)` | Handles page breaks, column widths, borders natively |
| Page-level chrome | Manual header/footer calls | `FPDF.header()` + `FPDF.footer()` override | Called automatically on every page including add_page() |
| Font subsetting | No-op | fpdf2 handles it internally | fpdf2 auto-subsets TTF fonts for small file sizes |
| Image resizing | Manual PIL code before embed | Pillow `thumbnail()` → BytesIO → `pdf.image()` | Simple, already in codebase via Pillow in requirements.txt |
| Unicode support | Fallback logic | TTF font via `add_font()` | Built-in once font is registered |

**Key insight:** fpdf2's cell/multi_cell/table primitives handle all common layout needs. Hand-rolling coordinate math is only needed for the blade map schematic (no table/cell abstraction fits that use case).

---

## Common Pitfalls

### Pitfall 1: Severity Colour Scale Mismatch

**What goes wrong:** `SEVERITY_COLORS` in current report.py uses keys 1-5 (not 0-4). The CONTEXT.md and REQUIREMENTS.md describe IEC Cat 0-4. The classify.py output uses `iec_category` 0-4. There is an off-by-one if you use the existing `SEVERITY_COLORS` dict directly for IEC Cat 0-4.
**Why it happens:** The old taxonomy used a 1-5 scale; classify.py was rewritten to use 0-4 (IEC standard).
**How to avoid:** Define a new `SEVERITY_COLORS_IEC` dict keyed 0-4 in the new report.py. Do not reuse the old 1-5 dict.
**Warning signs:** Cat 0 (no defects) displays wrong colour; Cat 4 defects show no entry.

```python
# Correct IEC 0-4 mapping (new report.py)
SEVERITY_COLORS_IEC = {
    0: {"rgb": (34, 197, 94),   "label": "Cat 0 — No Action"},    # green
    1: {"rgb": (234, 179, 8),   "label": "Cat 1 — Log"},           # yellow
    2: {"rgb": (249, 115, 22),  "label": "Cat 2 — Monitor"},       # orange
    3: {"rgb": (239, 68, 68),   "label": "Cat 3 — Planned"},       # red
    4: {"rgb": (127, 29, 29),   "label": "Cat 4 — Urgent"},        # dark red
}
```

### Pitfall 2: Image Path Availability at PDF Generation Time

**What goes wrong:** `classify_data` stores `image_path` pointing to files under the job directory. The API deletes raw uploaded images post-triage, but classified image files (in `{job_dir}/classify/` or similar) may or may not exist depending on what `api.py` deletes.
**Why it happens:** The delete-after-triage policy was designed for the large DJI P1 RAW files (15-30MB each), not for the smaller JPEG tiles used in classify.
**How to avoid:** In `_render_defect_page()`, always guard: `if Path(defect["image_path"]).exists()`. If missing, render a grey placeholder box. Never crash on missing image.
**Warning signs:** PDF generation fails with FileNotFoundError on image paths.

### Pitfall 3: Font Not Found on Render

**What goes wrong:** `add_font()` raises `FileNotFoundError` because TTF files are not committed to the repo or not at the expected path.
**Why it happens:** Fonts bundled locally but not added to git, or path relative to cwd instead of `__file__`.
**How to avoid:** Use `Path(__file__).parent.parent / "assets" / "fonts"` for the font path (absolute relative to the module file). Commit all TTF files. Add `assets/fonts/*.ttf` to git.
**Warning signs:** `FileNotFoundError: No such file or directory: 'Inter-Regular.ttf'` in Render logs.

### Pitfall 4: TOC Page Numbers Unknown at Render Time

**What goes wrong:** TOC is page 2 but page numbers for subsequent sections aren't known until after all pages are rendered.
**Why it happens:** Page numbers depend on defect count per blade, which is dynamic.
**How to avoid:** Pre-calculate page numbers before rendering. Since 1 defect per page, the layout is deterministic: `page = 1 (cover) + 1 (toc) + 1 (exec summary) + cumulative_defect_count`. Build `page_map` dict before rendering any content, pass to `BDDAReport.__init__`.
**Warning signs:** TOC shows wrong page numbers.

### Pitfall 5: Large PDF Size from Unresized Defect Images

**What goes wrong:** Embedding full-resolution JPEG tiles (1024×1024px) as 80mm thumbnails produces unnecessarily large PDFs.
**Why it happens:** fpdf2 embeds the full image data even if display size is small.
**How to avoid:** Always resize to target display dimensions before embedding. For 80mm at 150 DPI ≈ 472px. Resize with Pillow `thumbnail((472, 472))` before passing to `pdf.image()`.
**Warning signs:** PDFs >10MB for single turbine reports.

### Pitfall 6: Hex to RGB Conversion

**What goes wrong:** `set_fill_color("#fee2e2")` fails — fpdf2 expects `set_fill_color(r, g, b)` with integer 0-255 values, not hex strings.
**Why it happens:** Current `SEVERITY_COLORS` stores hex strings (CSS format).
**How to avoid:** Write a `hex_to_rgb(hex_str)` utility at top of report.py. Or store RGB tuples from the start.
```python
def hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
```

---

## Code Examples

Verified patterns from official sources and codebase analysis:

### Full PDF Class Skeleton
```python
# Source: fpdf2 official docs (Tutorial.html, Unicode.html)
from pathlib import Path
from fpdf import FPDF

FONT_DIR = Path(__file__).parent.parent / "assets" / "fonts"

# IEC 0-4 severity RGB (corrected from old 1-5 scale)
SEVERITY_RGB = {
    0: (34, 197, 94),
    1: (234, 179, 8),
    2: (249, 115, 22),
    3: (239, 68, 68),
    4: (127, 29, 29),
}

BRAND_DARK = (15, 50, 90)    # dark navy
BRAND_MID  = (0, 100, 160)   # steel blue
BRAND_LIGHT = (220, 235, 248) # pale blue background


class BDDAReport(FPDF):
    def __init__(self, report_data: dict):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.report_data = report_data
        self.report_ref = report_data.get("report_ref", "")
        self._register_fonts()
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(left=15, top=20, right=15)

    def _register_fonts(self):
        self.add_font("Inter", style="",  fname=str(FONT_DIR / "Inter-Regular.ttf"))
        self.add_font("Inter", style="B", fname=str(FONT_DIR / "Inter-Bold.ttf"))
        self.add_font("Inter", style="I", fname=str(FONT_DIR / "Inter-Italic.ttf"))

    def header(self):
        if self.page_no() == 1:
            return  # Cover page has no standard header
        self.set_y(8)
        self.set_font("Inter", "B", 9)
        self.set_text_color(*BRAND_DARK)
        self.cell(95, 6, "DroneWind Asia", align="L")
        self.set_font("Inter", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 6, self.report_ref, align="R")
        self.ln(2)
        self.set_draw_color(200, 200, 200)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_y(self.get_y() + 4)

    def footer(self):
        if self.page_no() == 1:
            return  # Cover page has no footer
        self.set_y(-12)
        self.set_font("Inter", "", 7)
        self.set_text_color(160, 160, 160)
        self.cell(0, 6, f"Page {self.page_no()} | Confidential — DroneWind Asia Inspection Report", align="C")


def generate_pdf_fpdf2(report_data: dict, output_path: Path) -> Path:
    """New fpdf2-based PDF generator. Replaces generate_pdf() + render_html()."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pdf = BDDAReport(report_data)

    # Build page map first (deterministic with 1 defect/page)
    page_map = _build_page_map(report_data)

    _render_cover(pdf, report_data)
    _render_toc(pdf, report_data, page_map)
    _render_executive_summary(pdf, report_data)
    for blade in report_data["blades_sorted"]:
        for defect in report_data["blade_findings"].get(blade, []):
            pdf.add_page()
            _render_defect_page(pdf, defect)
    _render_action_matrix(pdf, report_data)
    for blade in report_data["blades_sorted"]:
        pdf.add_page()
        _render_blade_map(pdf, blade, report_data["blade_findings"].get(blade, []))
    _render_inspection_details(pdf, report_data)

    pdf.output(str(output_path))
    return output_path
```

### Hex to RGB Utility
```python
def hex_to_rgb(hex_color: str) -> tuple:
    """Convert '#fee2e2' → (254, 226, 226) for fpdf2 set_fill_color()."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
```

### Defect Image Embedding with Fallback
```python
# Source: fpdf2 Images.html + PIL integration pattern
from PIL import Image
import io

def _embed_defect_image(pdf: FPDF, image_path: str, x: float, y: float,
                         w: float = 80, h: float = 80):
    """Embed defect image at position; show placeholder if missing."""
    path = Path(image_path)
    if not path.exists():
        # Grey placeholder
        pdf.set_fill_color(220, 220, 220)
        pdf.rect(x, y, w, h, style="F")
        pdf.set_xy(x, y + h/2 - 3)
        pdf.set_font("Inter", "I", 7)
        pdf.set_text_color(140, 140, 140)
        pdf.cell(w, 6, "Image not available", align="C")
        return

    # Resize before embed to keep PDF size manageable
    try:
        with Image.open(path).convert("RGB") as img:
            img.thumbnail((472, 472), Image.LANCZOS)  # 80mm @ 150dpi ≈ 472px
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=82)
            buf.seek(0)
        pdf.image(buf, x=x, y=y, w=w, h=h, keep_aspect_ratio=True)
    except Exception:
        # On any image error — draw placeholder
        pdf.set_fill_color(220, 220, 220)
        pdf.rect(x, y, w, h, style="F")
```

### Page Map Pre-calculation
```python
def _build_page_map(report_data: dict) -> dict:
    """Pre-calculate page numbers for TOC. 1 defect per page."""
    page = 1
    page_map = {"cover": page}
    page += 1; page_map["toc"] = page
    page += 1; page_map["executive_summary"] = page
    page += 1

    for blade in report_data["blades_sorted"]:
        defects = report_data["blade_findings"].get(blade, [])
        page_map[f"blade_{blade}"] = page
        page += max(len(defects), 1)  # at least 1 page per blade (even if no defects)

    page_map["action_matrix"] = page
    page += 1  # may be multi-page for large defect counts — simplify to 1 for TOC

    for blade in report_data["blades_sorted"]:
        page_map[f"map_{blade}"] = page
        page += 1

    page_map["inspection_details"] = page
    return page_map
```

---

## Data Structure Analysis (Verified from Codebase)

### Key Fields Available in report_data

The existing `build_report_data()` function (staying unchanged) provides everything needed:

```python
# Fields used per section:

# Cover Page:
report_data["turbine"]["turbine_id"]       # e.g. "JAP19"
report_data["turbine"]["site_name"]        # e.g. "Tomamae Wind Farm"
report_data["turbine"]["inspection_date"]  # ISO date
report_data["turbine"]["inspector_name"]
report_data["report_ref"]                  # e.g. "BDDA-JAP19-20251130"
report_data["condition"]                   # "A"|"B"|"C"|"D"
report_data["condition_info"]              # {"label": "Good", "color": "#22c55e", "desc": "..."}

# Executive Summary:
report_data["total_defects"]
report_data["defects_by_cat"]              # {1: n, 2: n, 3: n, 4: n, 5: n}
report_data["critical_count"]
report_data["critical_findings"]           # top 5 defects (Cat 4+)
report_data["triage_stats"]               # {"total", "flagged", "clean", "flag_rate"}

# Defect Findings by Blade:
report_data["blades_sorted"]              # ["A", "B", "C"]
report_data["blade_findings"]["A"]        # list of defect dicts, sorted by -category
# Each defect has: defect_id, defect_name, category (IEC), urgency, zone, position,
#                  size_estimate, confidence, visual_description, ndt_recommended,
#                  image_path, severity_style, analysis (may be None)

# Analysis fields per defect (if present):
defect["analysis"]["root_cause"]
defect["analysis"]["recommended_action"]
defect["analysis"]["repair_timeframe"]
defect["analysis"]["estimated_cost_usd"]
defect["analysis"]["engineer_review_required"]
defect["analysis"]["failure_risk"]["safety_risk"]

# Action Matrix:
report_data["action_matrix"]  # [{priority, action, blade, defect_id, defect_name, category, urgency, zone, timeframe}]

# Blade Map:
report_data["blade_findings"]["A"]  # defects have zone + position for grid placement

# Inspection Details:
report_data["turbine"]  # all turbine meta fields
report_data["generated_at"]
report_data["engineer_review_count"]
```

### CRITICAL: Category Field Naming Inconsistency

The `blade_findings` defect objects have a field called `category` (not `iec_category`). This is set in `build_report_data()` directly from classify_data which stores `iec_category`. Verify: `defect["category"]` in blade_findings maps to IEC 0-4 scale. The old `SEVERITY_COLORS` keys (1-5) will NOT match. Use the new `SEVERITY_COLORS_IEC` keyed 0-4.

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| xhtml2pdf HTML → PDF | fpdf2 direct construction | No system deps; works on Render |
| WeasyPrint for quality | fpdf2 native | No GTK/Pango needed |
| Jinja2 HTML templates | Direct Python cell/rect calls | No template files needed |
| SEVERITY_COLORS keyed 1-5 | New SEVERITY_COLORS_IEC keyed 0-4 | Aligns with IEC standard |

**Deprecated/outdated:**
- `render_html()`: delete entirely
- `generate_pdf()`: replace with `generate_pdf_fpdf2()`
- `build_report()` (full pipeline wrapper): update to call new function
- `templates/report.html`: delete
- `templates/report.css`: delete

---

## Open Questions

1. **Do classified image files survive post-triage deletion?**
   - What we know: `api.py` deletes raw uploaded images (15-30MB DJI P1 files) after triage to save disk space
   - What's unclear: Whether the JPEG copies created during classify stage (stored in job dir) are also deleted
   - Recommendation: Read `api.py` image deletion logic before implementing. If classified images are deleted, the thumbnail strategy changes: embed tile images from triage stage instead.

2. **TOC implementation — `insert_toc_placeholder()` availability**
   - What we know: fpdf2 2.8.x has some TOC support; pre-calculation is the safe fallback
   - What's unclear: Exact API for `insert_toc_placeholder()` in 2.8.4
   - Recommendation: Use pre-calculated page_map approach (deterministic, 1 defect/page). Avoid complex TOC API for Phase 4.

3. **Brand colour palette — exact RGB values**
   - What we know: "AI-selected — professional wind energy / high-tech palette" (CONTEXT.md)
   - What's unclear: Who selects the palette — will be chosen during implementation
   - Recommendation: Use professional dark navy + steel blue + light grey palette (shown in code examples above). Can be adjusted without structural changes.

4. **Font choice — Inter vs Exo 2**
   - What we know: CONTEXT.md says "Inter, Exo 2, or similar clean sans-serif"
   - What's unclear: Final font selection
   - Recommendation: Use Inter (most professional, free, widely used in tech reports). Download 3 static TTF files (Regular, Bold, Italic) from Google Fonts.

---

## Sources

### Primary (HIGH confidence)
- https://py-pdf.github.io/fpdf2/Tutorial.html — header/footer pattern, basic API
- https://py-pdf.github.io/fpdf2/Unicode.html — add_font() signature, TTF embedding
- https://py-pdf.github.io/fpdf2/Tables.html — table() context manager, FontFace, col_widths
- https://py-pdf.github.io/fpdf2/Images.html — image() method, PIL integration, positioning
- https://py-pdf.github.io/fpdf2/Shapes.html — rect(), line(), circle() with style parameter
- https://py-pdf.github.io/fpdf2/PageBreaks.html — will_page_break(), add_page(), set_auto_page_break()
- https://py-pdf.github.io/fpdf2/UsageInWebAPI.html — output() bytes, FastAPI integration
- PyPI: fpdf2 2.8.4 — verified as current stable release
- Codebase: `backend/report.py` — build_report_data() structure fully audited
- Codebase: `backend/classify.py` — ClassifyResult, DefectFinding, iec_category field names
- Codebase: `backend/analyze.py` — DeepAnalysis fields for analysis section
- `.planning/phases/04-pdf-redesign/04-CONTEXT.md` — all user decisions

### Secondary (MEDIUM confidence)
- https://py-pdf.github.io/fpdf2/ — general feature overview
- WebSearch results confirming fpdf2 image() accepts BytesIO and PIL objects

### Tertiary (LOW confidence)
- insert_toc_placeholder() availability in 2.8.4 — mentioned in docs but not verified against exact 2.8.4 changelog. Treat as unconfirmed; use pre-calculated page_map instead.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — fpdf2 2.8.4 confirmed on PyPI; Pillow already in requirements.txt; verified from official docs
- Architecture: HIGH — FPDF subclass pattern confirmed from tutorial; all code examples derived from verified API signatures
- Pitfalls: HIGH for colour mismatch (verified from codebase category field analysis); MEDIUM for image availability (requires api.py review)
- Blade map: MEDIUM — shapes API verified; coordinate strategy is straightforward but untested

**Research date:** 2026-03-07
**Valid until:** 2026-06-07 (fpdf2 API is stable; only at risk if major version bump)
