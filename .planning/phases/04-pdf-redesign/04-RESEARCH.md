# Phase 4: PDF Redesign - Research

**Researched:** 2026-03-08 (forced re-research, overwrites 2026-03-07 version)
**Domain:** fpdf2 PDF generation, font embedding, image embedding, programmatic drawing
**Confidence:** HIGH (fpdf2 API re-verified from official docs; data structures re-verified from codebase reading; image deletion path confirmed)

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
| PDF-01 | PDF uses fpdf2 (replaces xhtml2pdf) | fpdf2 2.8.7 (latest) confirmed on PyPI; drop-in replacement for report.py's generate_pdf(); `build_report_data()` stays untouched |
| PDF-02 | DroneWind Asia branding (logo, colours, header/footer) | fpdf2 `header()`/`footer()` override pattern confirmed; TTF font bundling strategy confirmed for Render Linux |
| PDF-03 | Defect images embedded inline next to findings | **Image deletion confirmed** — originals in `job_dir/images/` are deleted post-triage; Plan 02 thumbnail fix required. fpdf2 `image()` accepts PIL Image objects, file paths, and BytesIO; Pillow already in requirements.txt |
| PDF-04 | Severity colour-coding (Cat 0-4 colour bands) | fpdf2 `set_fill_color(r,g,b)` + `cell(fill=True)` confirmed; SEVERITY_COLORS_IEC keyed 0-4 replaces old 1-5 mapping |
| PDF-05 | Executive summary page (defect counts, highest severity, recommendation) | `build_report_data()` already produces all needed fields; `condition_info`, `critical_count`, `defects_by_cat` map directly |
| PDF-06 | Per-blade defect map (blade diagram with annotated zones) | fpdf2 `rect()`, `line()`, `circle(x, y, radius)` confirmed; circle() uses center coords (not top-left); zone grid 4×3 approach works |
</phase_requirements>

---

## Summary

Phase 4 replaces the xhtml2pdf/WeasyPrint/Jinja2 HTML pipeline with a pure fpdf2 direct PDF construction approach. The scope is confined to `backend/report.py` (major rewrite) and `backend/api.py` (thumbnail fix + pipeline wiring). The `build_report_data()` function and all data assembly logic is preserved unchanged — it already produces all fields the PDF needs.

**CONFIRMED this re-research:** fpdf2 is now at 2.8.7 on PyPI (was 2.8.4 in previous research). The API is stable between minor versions. `insert_toc_placeholder()` with a `TableOfContents` render callback is confirmed available. `circle(x, y, radius)` uses center coordinates — the previous research had a bug showing `x=cx - 3, y=cy - 3` which would misplace markers; correct call is `circle(x=cx, y=cy, radius=3)`.

**CONFIRMED image deletion path:** `api.py` line 241-243 does `shutil.rmtree(job_dir / "images")` after triage. All classify image_path fields point into `job_dir/images/` which is deleted. Plan 02 (thumbnail copy before deletion) is required for PDF-03. Without it, every defect image in the PDF is a grey placeholder.

The 3-plan structure (01: foundation, 02: image pipeline fix, 03: defect pages + wiring) is correct and complete. Plans already exist — this re-research confirms they are well-founded with one correction needed (circle coordinates).

**Primary recommendation:** Execute the 3 existing plans in order. Fix the `circle()` coordinate bug in Plan 03 before execution.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fpdf2 | 2.8.7 (latest) | Direct PDF construction — cells, images, shapes, tables | Pure Python, zero system deps, works on Render Linux, locked in by requirements |
| Pillow | >=10.0.0 | Image loading, resizing, BytesIO conversion before embedding | Already in requirements.txt; fpdf2 uses Pillow internally |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Inter TTF (static) | Google Fonts v18 | Custom sans-serif font for professional look | Required — Render has no system fonts; bundle 3 static TTF files (Regular, Bold, Italic) |

### Removed (Phase 4 cleanup)
| Library | Replacing | Reason |
|---------|-----------|--------|
| xhtml2pdf >=0.2.11 | fpdf2 | HTML-to-PDF with CSS limitations, fragile on headless servers |
| weasyprint | fpdf2 | Requires GTK/Pango system libs — unusable on Render |
| jinja2 >=3.1.0 | Not needed | Templates only used for report.html which is deleted |
| python-bidi 0.4.2 | Not needed | RTL text support only needed for jinja2 HTML template |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| fpdf2 | reportlab | ReportLab has richer layout but AGPL license, heavier dep |
| fpdf2 | weasyprint | Better CSS fidelity but requires system GTK/Pango — breaks Render |
| Inter TTF | DejaVu (bundled in fpdf2) | DejaVu works out-of-box but looks dated; Inter is professional |

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
assets/fonts/                  # NEW — bundled TTF files (must be committed to git)
    Inter-Regular.ttf
    Inter-Bold.ttf
    Inter-Italic.ttf
templates/                     # DELETE after Phase 4
    report.html                # DELETE
    report.css                 # DELETE
```

### Pattern 1: FPDF Subclass with Header/Footer Override

The standard fpdf2 pattern for per-page chrome. `header()` and `footer()` are called automatically on every `add_page()`.

```python
# Source: https://py-pdf.github.io/fpdf2/Tutorial.html (verified 2026-03-08)
from fpdf import FPDF

class BDDAReport(FPDF):
    def __init__(self, report_data: dict):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.report_data = report_data
        self.report_ref = report_data.get("report_ref", "")
        self._register_fonts()
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(left=15, top=20, right=15)

    def _register_fonts(self):
        try:
            self.add_font("Inter", style="",  fname=str(FONT_DIR / "Inter-Regular.ttf"))
            self.add_font("Inter", style="B", fname=str(FONT_DIR / "Inter-Bold.ttf"))
            self.add_font("Inter", style="I", fname=str(FONT_DIR / "Inter-Italic.ttf"))
        except FileNotFoundError:
            # Fallback to Helvetica if fonts not bundled (should not happen in production)
            print("WARNING: Inter TTF not found, falling back to Helvetica")

    def header(self):
        if self.page_no() == 1:
            return  # Cover page has no standard header
        self.set_y(8)
        self.set_font("Inter", "B", 9)
        self.set_text_color(*BRAND_NAVY)
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
```

### Pattern 2: Adding Bundled TTF Fonts

Must call `add_font()` before any `set_font()`. Font files must be committed to the repo — Render has no system fonts. Path must be absolute derived from `__file__`, not from cwd.

```python
# Source: https://py-pdf.github.io/fpdf2/Unicode.html (verified 2026-03-08)
FONT_DIR = Path(__file__).parent.parent / "assets" / "fonts"
```

**Font sourcing:** Inter available at https://fonts.google.com/specimen/Inter — download the "static" zip and extract 3 files: `static/Inter-Regular.ttf`, `static/Inter-Bold.ttf`, `static/Inter-Italic.ttf`. Alternative: GitHub releases at https://github.com/rsms/inter/releases.

### Pattern 3: Table of Contents with insert_toc_placeholder()

`insert_toc_placeholder()` is confirmed available in fpdf2 2.8.x. It uses a render callback and places a placeholder that is filled after all pages are rendered. This is more robust than pre-calculating page offsets.

```python
# Source: https://py-pdf.github.io/fpdf2/DocumentOutlineAndTableOfContents.html (verified 2026-03-08)
from fpdf import FPDF
from fpdf.outline import TableOfContents

class BDDAReport(FPDF):
    def render_toc(self):
        # Called on page 2 (TOC page) after all other pages rendered
        toc = TableOfContents()
        self.insert_toc_placeholder(toc.render_toc, pages=1)

    # Alternative: custom TOC renderer for full layout control
    def _custom_toc_renderer(pdf, outline):
        """Render TOC with custom styling."""
        pdf.set_font("Inter", "B", 14)
        pdf.cell(0, 10, "Table of Contents", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        for section in outline:
            pdf.set_font("Inter", "", 10)
            # section.name, section.page_number, section.level
            indent = section.level * 5
            pdf.set_x(pdf.l_margin + indent)
            pdf.cell(120 - indent, 7, section.name, align="L")
            pdf.cell(0, 7, str(section.page_number), align="R", new_x="LMARGIN", new_y="NEXT")
```

**Key API for TOC:** Call `insert_toc_placeholder(render_fn, pages=1)` when you want the TOC to appear. Use `start_section(name, level=0)` to register sections as you render them. fpdf2 handles the page number injection automatically.

**Simpler alternative** (if TOC precision matters more than automation): pre-calculate page numbers. With 1 defect per page, the layout is deterministic: `page = 1 (cover) + 1 (toc) + 1 (exec summary) + sum(defect counts per blade) + 1 (action matrix) + N_blades (blade maps) + 1 (inspection details)`.

### Pattern 4: Image Embedding from File Path or PIL

```python
# Source: https://py-pdf.github.io/fpdf2/Images.html (verified 2026-03-08)
# fpdf2 image() accepts: file paths, PIL Image objects, BytesIO, URLs

# From file path (recommended — fpdf2 handles internally):
pdf.image(str(image_path), x=10, y=pdf.get_y(), w=80, h=80, keep_aspect_ratio=True)

# From PIL (after resize — for size control):
from PIL import Image
import io
img = Image.open(image_path).convert("RGB")
img.thumbnail((472, 472), Image.LANCZOS)   # 80mm @ 150dpi ≈ 472px
buf = io.BytesIO()
img.save(buf, format="JPEG", quality=82)
buf.seek(0)
pdf.image(buf, x=10, y=pdf.get_y(), w=80, h=80, keep_aspect_ratio=True)

# Graceful fallback if image missing:
if Path(image_path).exists():
    pdf.image(str(image_path), x=x, y=y, w=80, h=80, keep_aspect_ratio=True)
else:
    pdf.set_fill_color(230, 230, 230)
    pdf.rect(x, y, 80, 80, style="F")
    pdf.set_xy(x, y + 35)
    pdf.set_font("Inter", "I", 7)
    pdf.set_text_color(140, 140, 140)
    pdf.cell(80, 6, "Image not available", align="C")
```

### Pattern 5: Colour-Coded Table Rows (PDF-04)

```python
# Source: https://py-pdf.github.io/fpdf2/Tables.html (verified 2026-03-08)
# Manual cell approach — most control for per-row colouring:

def _severity_row(pdf, defect):
    cat = defect.get("category", 0)
    info = SEVERITY_COLORS_IEC.get(cat, SEVERITY_COLORS_IEC[0])
    pdf.set_fill_color(*info["rgb"])
    pdf.set_text_color(*info["text_rgb"])
    pdf.set_font("Inter", "B", 9)
    pdf.cell(20, 8, f"P{priority_from_cat(cat)}", border="B", fill=True)
    pdf.cell(15, 8, defect.get("blade", ""), border="B", fill=True)
    pdf.cell(30, 8, defect.get("defect_id", ""), border="B", fill=True)
    pdf.cell(0, 8, defect.get("defect_name", "")[:45], border="B", fill=True,
             new_x="LMARGIN", new_y="NEXT")
```

### Pattern 6: Programmatic Blade Map (PDF-06)

**CORRECTION from previous research:** `circle(x, y, radius)` uses `x, y` as **center** coordinates. Do NOT subtract radius. Confirmed from fpdf2 API docs (2026-03-08): the method calls `ellipse(x - radius, y - radius, 2*radius, 2*radius)` internally, so the user provides center coords.

```python
# Source: https://py-pdf.github.io/fpdf2/Shapes.html (verified 2026-03-08)
# CORRECT circle call:
pdf.circle(x=cx, y=cy, radius=3, style="F")   # cx, cy are center coordinates
# WRONG (previous research had this bug):
# pdf.circle(x=cx - 3, y=cy - 3, radius=3, style="F")  # DO NOT USE

ZONE_COLORS_IEC = {
    -1: (230, 230, 230),  # no defects
    0:  (34, 197, 94),    # green
    1:  (234, 179, 8),    # yellow
    2:  (249, 115, 22),   # orange
    3:  (239, 68, 68),    # red
    4:  (127, 29, 29),    # dark red
}

def _draw_blade_map(pdf, blade_label, blade_defects):
    zones = ["LE", "TE", "PS", "SS"]
    positions = ["Root", "Mid", "Tip"]
    cell_w, cell_h = 30, 15
    start_x = pdf.l_margin + 20
    start_y = pdf.get_y() + 5

    for row, zone in enumerate(zones):
        for col, pos in enumerate(positions):
            x = start_x + col * cell_w
            y = start_y + row * cell_h
            worst_cat = _worst_cat_in_zone(blade_defects, zone, pos)
            rgb = ZONE_COLORS_IEC.get(worst_cat, (230, 230, 230))
            pdf.set_fill_color(*rgb)
            pdf.set_draw_color(180, 180, 180)
            pdf.rect(x, y, cell_w, cell_h, style="FD")
            # Zone label in cell
            pdf.set_text_color(50, 50, 50)
            pdf.set_font("Inter", "", 7)
            pdf.set_xy(x, y + 4)
            pdf.cell(cell_w, 6, zone, align="C")

    # Defect markers: circles at zone+position center
    for defect in blade_defects:
        zone = defect.get("zone", "LE")
        pos = defect.get("position", "Mid")
        col = positions.index(pos) if pos in positions else 1
        row = zones.index(zone) if zone in zones else 0
        # Center coordinates:
        cx = start_x + col * cell_w + cell_w / 2
        cy = start_y + row * cell_h + cell_h / 2
        cat = defect.get("category", 0)
        rgb = ZONE_COLORS_IEC.get(cat, (128, 128, 128))
        pdf.set_fill_color(*rgb)
        pdf.set_draw_color(255, 255, 255)
        pdf.circle(x=cx, y=cy, radius=3, style="FD")  # center coords!
```

### Pattern 7: Page Break Management

```python
# Source: https://py-pdf.github.io/fpdf2/PageBreaks.html (verified 2026-03-08)
# For 1 defect per page: explicit add_page()
for defect in blade_defects:
    pdf.add_page()
    _render_defect_page(pdf, defect)

# For action matrix table — check before adding row:
if pdf.will_page_break(row_height):
    pdf.add_page()
    _render_action_matrix_header(pdf)  # re-draw column headers
```

### Anti-Patterns to Avoid

- **Wrong circle() coordinates:** `pdf.circle(x=cx - r, y=cy - r, radius=r)` is wrong. Use `pdf.circle(x=cx, y=cy, radius=r)` — x,y are center.
- **Setting font before add_page():** Always call `add_page()` before configuring fonts.
- **Using hex colours directly:** fpdf2 uses RGB integers (0-255). Use `set_fill_color(r, g, b)` not `set_fill_color("#fee2e2")`.
- **Embedding raw base64 strings:** `image()` accepts BytesIO but not raw base64 strings. Decode base64 → BytesIO first.
- **Reusing FPDF instance across requests:** Create a new `BDDAReport` instance per call (thread safety).
- **Calling output() then adding content:** `output()` finalizes. Build everything first.
- **Missing image path guard:** Always check `Path(image_path).exists()` before embedding. Image files from classify.json point to deleted originals unless Plan 02 is applied.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Colour-coded table rows | Custom row renderer | Manual `set_fill_color()` + `cell(fill=True)` loop | Handles page breaks, avoids fpdf2 table() complexity for coloured rows |
| Page-level chrome | Manual header/footer calls | `FPDF.header()` + `FPDF.footer()` override | Called automatically on every `add_page()` including those from auto page breaks |
| Font subsetting | No-op | fpdf2 handles it internally | fpdf2 auto-subsets TTF fonts for smaller file sizes |
| Image resizing before embed | Complex PIL code | Pillow `thumbnail()` → BytesIO → `pdf.image()` | Simple, already have Pillow |
| TOC page number tracking | Manual page counter dict | `insert_toc_placeholder()` + `start_section()` | Library handles injection; or pre-calculate (1 defect/page = deterministic) |

**Key insight:** fpdf2's cell/multi_cell primitives handle all common layout needs. Hand-rolling coordinate math is only needed for the blade map schematic (no table/cell abstraction fits a zone grid).

---

## Common Pitfalls

### Pitfall 1: Severity Scale Mismatch (1-5 vs 0-4)

**What goes wrong:** `SEVERITY_COLORS` in current report.py uses keys 1-5. The classify.py output uses `iec_category` 0-4. `build_report_data()` reads `d["category"]` — in real pipeline data this comes from `iec_category` (0-4), in sample data it's stored as `category` (using the old 1-5 scale in `make_sample_classify_data()`).

**How to avoid:** Define `SEVERITY_COLORS_IEC` keyed 0-4 for all fpdf2 rendering. Fix `build_report_data()` to normalize the key: `d.setdefault("category", d.get("iec_category", 0))` so both pipeline data and sample data work. Do NOT reuse the old `SEVERITY_COLORS` dict for rendering.

**Warning signs:** Cat 0 shows wrong colour (off by one); Cat 4 entries show no colour band (key not found).

```python
# Correct IEC 0-4 mapping for fpdf2 (RGB values)
SEVERITY_COLORS_IEC = {
    0: {"rgb": (34, 197, 94),   "label": "Cat 0 — No Action",  "text_rgb": (20, 83, 45)},
    1: {"rgb": (234, 179, 8),   "label": "Cat 1 — Log",         "text_rgb": (133, 77, 14)},
    2: {"rgb": (249, 115, 22),  "label": "Cat 2 — Monitor",     "text_rgb": (154, 52, 18)},
    3: {"rgb": (239, 68, 68),   "label": "Cat 3 — Planned",     "text_rgb": (153, 27, 27)},
    4: {"rgb": (127, 29, 29),   "label": "Cat 4 — Urgent",      "text_rgb": (255, 255, 255)},
}
```

### Pitfall 2: Image Path Availability at PDF Generation Time (CONFIRMED BUG)

**What goes wrong:** `classify_data` stores `image_path` values pointing to files under `job_dir/images/`. After triage, `api.py` calls `shutil.rmtree(job_dir / "images")` which deletes ALL these files. When report.py tries to embed defect images, ALL paths are dead.

**Confirmed from codebase:** Lines 241-243 of api.py:
```python
images_dir = job_dir / "images"
if images_dir.exists():
    shutil.rmtree(images_dir)
```
This runs after triage, before classify. The `classify_batch()` call immediately after reads from the flagged list which still has the old paths — it reads the images before they are already deleted (triage already ran). But classify.py saves `str(path)` as `image_path` into classify.json — those paths are already gone.

**How to avoid:** Plan 02 creates thumbnail copies in `job_dir/thumbnails/` before the rmtree and rewrites flagged paths to point to thumbnails. This must execute before Plan 03 or image embedding produces all placeholders.

**Warning signs:** Every defect image in PDF is a grey placeholder box.

### Pitfall 3: circle() Coordinate Bug

**What goes wrong:** Previous research (2026-03-07) showed `pdf.circle(x=cx - 3, y=cy - 3, radius=3)` — subtracting the radius from x,y. This is WRONG. fpdf2 `circle(x, y, radius)` uses `x, y` as center coordinates already (confirmed from API source: it calls `ellipse(x - radius, y - radius, 2*radius, 2*radius)` internally).

**How to avoid:** Use `pdf.circle(x=cx, y=cy, radius=3, style="F")` where `cx, cy` are the center coordinates you want. No subtraction needed.

**Warning signs:** Defect markers on blade map appear offset (shifted down-right by one radius) from their intended positions.

### Pitfall 4: Font Not Found on Render

**What goes wrong:** `add_font()` raises `FileNotFoundError` on Render because TTF files are not committed to git or the path uses `cwd` instead of `__file__`.

**How to avoid:**
1. Use `FONT_DIR = Path(__file__).parent.parent / "assets" / "fonts"` (absolute, relative to the module file)
2. Commit all TTF files (`git add assets/fonts/*.ttf`)
3. Have a fallback to Helvetica for graceful degradation

**Warning signs:** `FileNotFoundError: No such file or directory: 'Inter-Regular.ttf'` in Render logs.

### Pitfall 5: Large PDF from Unresized Images

**What goes wrong:** Embedding full-resolution JPEG thumbnails (1568×1568px) as 80mm thumbnails produces unnecessarily large PDFs.

**How to avoid:** Always resize before embedding. For 80mm at 150 DPI ≈ 472px. Use `img.thumbnail((472, 472), Image.LANCZOS)` before passing to `pdf.image()`.

**Warning signs:** PDFs >10MB for single turbine reports.

### Pitfall 6: Hex to RGB Conversion

**What goes wrong:** `set_fill_color("#fee2e2")` fails — fpdf2 expects integer 0-255 values, not hex strings.

```python
def hex_to_rgb(hex_color: str) -> tuple:
    """Convert '#fee2e2' → (254, 226, 226) for fpdf2 set_fill_color()."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
```

---

## Code Examples

### Full PDF Class Skeleton

```python
# Source: fpdf2 official docs (Tutorial.html, Unicode.html) — verified 2026-03-08
from pathlib import Path
from fpdf import FPDF
from PIL import Image
import io

FONT_DIR = Path(__file__).parent.parent / "assets" / "fonts"

SEVERITY_COLORS_IEC = {
    0: {"rgb": (34, 197, 94),   "label": "Cat 0 — No Action",  "text_rgb": (20, 83, 45)},
    1: {"rgb": (234, 179, 8),   "label": "Cat 1 — Log",         "text_rgb": (133, 77, 14)},
    2: {"rgb": (249, 115, 22),  "label": "Cat 2 — Monitor",     "text_rgb": (154, 52, 18)},
    3: {"rgb": (239, 68, 68),   "label": "Cat 3 — Planned",     "text_rgb": (153, 27, 27)},
    4: {"rgb": (127, 29, 29),   "label": "Cat 4 — Urgent",      "text_rgb": (255, 255, 255)},
}

BRAND_NAVY  = (15, 50, 90)
BRAND_STEEL = (0, 100, 160)
BRAND_LIGHT = (220, 235, 248)


class BDDAReport(FPDF):
    def __init__(self, report_data: dict):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.report_data = report_data
        self.report_ref = report_data.get("report_ref", "")
        self._register_fonts()
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(left=15, top=20, right=15)

    def _register_fonts(self):
        try:
            self.add_font("Inter", style="",  fname=str(FONT_DIR / "Inter-Regular.ttf"))
            self.add_font("Inter", style="B", fname=str(FONT_DIR / "Inter-Bold.ttf"))
            self.add_font("Inter", style="I", fname=str(FONT_DIR / "Inter-Italic.ttf"))
        except FileNotFoundError:
            print("WARNING: Inter TTF fonts not found in assets/fonts/ — falling back to Helvetica")

    def header(self):
        if self.page_no() == 1:
            return
        self.set_y(8)
        self.set_font("Inter", "B", 9)
        self.set_text_color(*BRAND_NAVY)
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
            return
        self.set_y(-12)
        self.set_font("Inter", "", 7)
        self.set_text_color(160, 160, 160)
        self.cell(0, 6, f"Page {self.page_no()} | Confidential — DroneWind Asia Inspection Report", align="C")


def generate_pdf_fpdf2(report_data: dict, output_path: Path) -> Path:
    """New fpdf2-based PDF generator. Replaces generate_pdf() + render_html()."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pdf = BDDAReport(report_data)

    _render_cover(pdf, report_data)
    # TOC page — use insert_toc_placeholder or pre-calculated page_map
    _render_toc(pdf, report_data)
    _render_executive_summary(pdf, report_data)

    # Defect pages: 1 per defect
    defect_index = 1
    total_defects = report_data.get("total_defects", 0)
    for blade in report_data.get("blades_sorted", []):
        for defect in report_data["blade_findings"].get(blade, []):
            pdf.add_page()
            _render_defect_page(pdf, defect, defect_index, total_defects)
            defect_index += 1

    _render_action_matrix(pdf, report_data)

    for blade in report_data.get("blades_sorted", []):
        pdf.add_page()
        _render_blade_map(pdf, blade, report_data["blade_findings"].get(blade, []))

    _render_inspection_details(pdf, report_data)

    pdf.output(str(output_path))
    return output_path
```

### Defect Image Embedding with Fallback

```python
# Source: fpdf2 Images.html + PIL integration — verified 2026-03-08
def _embed_defect_image(pdf, image_path: str, x: float, y: float,
                         w: float = 80, h: float = 80):
    """Embed defect image at position; show placeholder if missing."""
    path = Path(image_path) if image_path else None
    if not path or not path.exists():
        # Grey placeholder
        pdf.set_fill_color(220, 220, 220)
        pdf.rect(x, y, w, h, style="F")
        pdf.set_xy(x, y + h / 2 - 3)
        pdf.set_font("Inter", "I", 7)
        pdf.set_text_color(140, 140, 140)
        pdf.cell(w, 6, "Image not available", align="C")
        return

    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((472, 472), Image.LANCZOS)  # 80mm @ 150dpi
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=82)
            buf.seek(0)
        pdf.image(buf, x=x, y=y, w=w, h=h, keep_aspect_ratio=True)
    except Exception:
        # Any image error — draw placeholder
        pdf.set_fill_color(220, 220, 220)
        pdf.rect(x, y, w, h, style="F")
```

### Blade Map with Correct circle() Coordinates

```python
# Source: fpdf2 Shapes.html — verified 2026-03-08
# circle(x, y, radius) — x, y are CENTER coordinates!
def _worst_cat_in_zone(defects, zone, position):
    """Return worst IEC category (0-4) for a zone+position cell, or -1 if no defects."""
    matches = [
        d.get("category", 0)
        for d in defects
        if d.get("zone") == zone and d.get("position") == position
    ]
    return max(matches) if matches else -1


def _render_blade_map(pdf, blade_label, blade_defects):
    pdf.add_page()
    zones = ["LE", "TE", "PS", "SS"]
    positions = ["Root", "Mid", "Tip"]
    cell_w, cell_h = 30, 15
    start_x = pdf.l_margin + 20
    start_y = pdf.get_y() + 15

    # Zone grid
    for row, zone in enumerate(zones):
        for col, pos in enumerate(positions):
            x = start_x + col * cell_w
            y = start_y + row * cell_h
            worst_cat = _worst_cat_in_zone(blade_defects, zone, pos)
            rgb = ZONE_COLORS_IEC.get(worst_cat, (230, 230, 230))
            pdf.set_fill_color(*rgb)
            pdf.set_draw_color(180, 180, 180)
            pdf.rect(x, y, cell_w, cell_h, style="FD")
            pdf.set_text_color(50, 50, 50)
            pdf.set_font("Inter", "", 7)
            pdf.set_xy(x, y + 4)
            pdf.cell(cell_w, 6, zone, align="C")

    # Defect markers: circle at zone+position center
    for defect in blade_defects:
        zone = defect.get("zone", "LE")
        pos = defect.get("position", "Mid")
        col = positions.index(pos) if pos in positions else 1
        row = zones.index(zone) if zone in zones else 0
        # Center of cell:
        cx = start_x + col * cell_w + cell_w / 2
        cy = start_y + row * cell_h + cell_h / 2
        cat = defect.get("category", 0)
        info = SEVERITY_COLORS_IEC.get(cat, SEVERITY_COLORS_IEC[0])
        pdf.set_fill_color(*info["rgb"])
        pdf.set_draw_color(255, 255, 255)
        pdf.circle(x=cx, y=cy, radius=3, style="FD")   # x,y are CENTER coords
```

### iec_category Key Normalization in build_report_data()

```python
# Fix for build_report_data() — classify.py saves "iec_category", sample data uses "category"
# After the all_defects list is built, normalize keys:
for d in all_defects:
    d.setdefault("category", d.get("iec_category", 0))

# And in the blade_findings inner loop, read category safely:
cat = d.get("category", d.get("iec_category", 0))
```

---

## Data Structure Analysis (Verified from Codebase)

### Image Path Lifecycle (CONFIRMED)

```
1. api.py uploads images to:    job_dir/images/{blade}/{zone}/{filename}.jpg
2. triage.py runs on those paths (image_path stored in TriageResult)
3. api.py calls shutil.rmtree(job_dir / "images")  ← DELETES ALL IMAGES
4. classify.py processes thumbnails (Plan 02 rewrites paths to job_dir/thumbnails/)
5. classify.json saves: {"image_path": "job_dir/thumbnails/{filename}.jpg", ...}
6. report.py reads classify.json and embeds images from those paths  ← MUST EXIST
```

Without Plan 02, step 5 saves deleted paths. Plan 02 makes thumbnails available at step 4+.

### Key Fields Available in report_data

```python
# Cover Page:
report_data["turbine"]["turbine_id"]       # e.g. "JAP19"
report_data["turbine"]["site_name"]        # e.g. "Tomamae Wind Farm"
report_data["turbine"]["inspection_date"]
report_data["turbine"]["inspector_name"]
report_data["report_ref"]                  # e.g. "BDDA-JAP19-20251130"
report_data["condition"]                   # "A"|"B"|"C"|"D"
report_data["condition_info"]              # {"label": "Good", "color": "#22c55e", "desc": "..."}

# Executive Summary:
report_data["total_defects"]
report_data["defects_by_cat"]              # {1: n, 2: n, ...} — NOTE: may use 1-5 scale from old sample data
report_data["critical_count"]
report_data["critical_findings"]           # top 5 defects (Cat 4+)
report_data["triage_stats"]               # {"total", "flagged", "clean", "flag_rate"} or None

# Defect Findings by Blade:
report_data["blades_sorted"]              # ["A", "B", "C"]
report_data["blade_findings"]["A"]        # list of defect dicts, sorted by -category
# Each defect dict:
# "defect_id", "defect_name", "category" (IEC 0-4 after normalization),
# "urgency", "zone", "position", "size_estimate", "confidence",
# "visual_description", "ndt_recommended", "image_path" (thumbnail after Plan 02),
# "severity_style" (old 1-5 based — don't use for fpdf2 rendering, use SEVERITY_COLORS_IEC instead),
# "analysis" (dict or None)

# Action Matrix:
report_data["action_matrix"]
# Each item: {priority, action, blade, defect_id, defect_name, category, urgency, zone, timeframe}

# Blade Map:
# Use blade_findings[blade] — each defect has zone + position for grid placement

# Inspection Details:
report_data["turbine"]  # all turbine meta fields
report_data["generated_at"]
report_data["engineer_review_count"]
```

### Category Field Naming: THE FULL PICTURE

- `classify.py` `DefectFinding` stores: `iec_category: int` (0-4)
- `classify.py` `save_classify_results()` saves: `{"iec_category": d.iec_category, ...}` (no "category" key)
- `build_report_data()` reads: `d["category"]` — this FAILS on real pipeline data
- `make_sample_classify_data()` in report.py stores: `{"category": 3, ...}` — this works but masks the bug
- **Fix:** `d.setdefault("category", d.get("iec_category", 0))` after building `all_defects` list
- **Result after fix:** `defect["category"]` reliably contains IEC 0-4 for all defects in report_data

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| xhtml2pdf HTML → PDF | fpdf2 direct construction | No system deps; works on Render |
| WeasyPrint for quality | fpdf2 native | No GTK/Pango needed |
| Jinja2 HTML templates | Direct Python cell/rect calls | No template files needed |
| SEVERITY_COLORS keyed 1-5 | SEVERITY_COLORS_IEC keyed 0-4 | Aligns with IEC standard |
| fpdf2 2.8.4 (prev research) | fpdf2 2.8.7 (current PyPI) | Same API; minor bugfixes only |

**Deprecated/outdated (to delete):**
- `render_html()`: delete entirely
- `generate_pdf()`: replace with `generate_pdf_fpdf2()`
- `build_report()` wrapper: update to call new function
- `templates/report.html`: delete
- `templates/report.css`: delete

---

## Open Questions

1. **TOC implementation — insert_toc_placeholder() vs pre-calculated**
   - What we know: `insert_toc_placeholder(render_fn, pages=1)` confirmed in 2.8.7; uses `start_section()` calls to register entries during rendering; library handles page number injection automatically
   - Recommendation: Use `insert_toc_placeholder()` with a custom render function. It's cleaner than pre-calculation and confirmed available. The `start_section(name)` call should be placed at the start of each major section render function.

2. **Brand colour palette — exact RGB values**
   - What we know: "AI-selected — professional wind energy / high-tech palette" per CONTEXT.md
   - Recommendation: Use `BRAND_NAVY = (15, 50, 90)`, `BRAND_STEEL = (0, 100, 160)`, `BRAND_LIGHT = (220, 235, 248)` as shown in code examples. These are easily adjustable.

3. **Font fallback behaviour on Render if TTF not committed**
   - Recommendation: Implement explicit fallback to Helvetica in `_register_fonts()` with a warning print. This prevents hard failure during deployment. But TTF files MUST be committed to git before Render deploy.

---

## Sources

### Primary (HIGH confidence)
- https://py-pdf.github.io/fpdf2/DocumentOutlineAndTableOfContents.html — insert_toc_placeholder() signature, TableOfContents class, start_section() API (verified 2026-03-08)
- https://py-pdf.github.io/fpdf2/Shapes.html — circle(x, y, radius) center coords confirmed (verified 2026-03-08)
- https://py-pdf.github.io/fpdf2/Images.html — image() method, PIL integration, file path and BytesIO acceptance (verified 2026-03-08)
- https://py-pdf.github.io/fpdf2/fpdf/fpdf.html#fpdf.fpdf.FPDF.circle — exact circle() signature and coordinate system (verified 2026-03-08)
- PyPI: fpdf2 2.8.7 — current stable release (verified 2026-03-08 via PyPI JSON API)
- Codebase: `backend/api.py` lines 241-243 — image deletion confirmed
- Codebase: `backend/classify.py` `save_classify_results()` — iec_category key naming confirmed
- Codebase: `backend/report.py` `build_report_data()` — d["category"] mismatch with real pipeline data confirmed
- `.planning/phases/04-pdf-redesign/04-CONTEXT.md` — all user decisions

### Secondary (MEDIUM confidence)
- https://py-pdf.github.io/fpdf2/ — general feature overview; individual pages 404ed in this session but main content accessible
- Existing plan files (04-01, 04-02, 04-03 PLAN.md) — confirm 3-plan structure is appropriate
- Previous RESEARCH.md (2026-03-07) — confirmed most findings, corrected circle() coordinate bug

### Tertiary (LOW confidence)
- None remaining — all critical claims verified from primary sources

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — fpdf2 2.8.7 confirmed on PyPI; API verified from official docs
- Architecture: HIGH — FPDF subclass pattern confirmed; insert_toc_placeholder() confirmed; circle() coordinate system confirmed (correcting previous research bug)
- Pitfalls: HIGH for colour mismatch (verified from codebase key analysis); HIGH for image deletion (confirmed from api.py); HIGH for circle() bug (confirmed from API docs)
- Blade map: HIGH — shapes API verified; circle() center coords confirmed; coordinate math straightforward

**Key correction vs previous research (2026-03-07):**
- circle() coordinates: previous research showed `x=cx - 3, y=cy - 3` — this is WRONG. Correct: `x=cx, y=cy` (center coordinates)
- fpdf2 version: 2.8.4 → 2.8.7 (same API, no breaking changes)
- insert_toc_placeholder(): previously marked "LOW confidence, unconfirmed" — now HIGH confidence, confirmed available with full API

**Research date:** 2026-03-08
**Valid until:** 2026-06-08 (fpdf2 API is stable; only at risk if major version bump)
