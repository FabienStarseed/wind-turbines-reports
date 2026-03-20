---
phase: 04-pdf-redesign
plan: "01"
subsystem: PDF generation
tags: [fpdf2, pdf, branding, fonts, report]
dependency_graph:
  requires: []
  provides: [BDDAReport class, generate_pdf_fpdf2, Inter TTF fonts, fpdf2 foundation]
  affects: [backend/report.py, requirements.txt, assets/fonts/]
tech_stack:
  added: [fpdf2>=2.8.0, Inter TTF v3.19]
  removed: [xhtml2pdf, jinja2, python-bidi]
  patterns: [FPDF subclass with header/footer override, TTF font bundling, RGB colour constants]
key_files:
  created:
    - assets/fonts/Inter-Regular.ttf
    - assets/fonts/Inter-Bold.ttf
    - assets/fonts/Inter-Italic.ttf
  modified:
    - backend/report.py
    - requirements.txt
decisions:
  - "Inter TTF v3.19 from GitHub releases (Hinted for Windows/Desktop variant — best cross-platform compatibility)"
  - "Helvetica fallback in _register_fonts() guards against missing TTF on deployment"
  - "SEVERITY_COLORS_IEC keyed 0-4 (RGB) added alongside legacy SEVERITY_COLORS (kept for severity_style field)"
  - "iec_category key normalization added in build_report_data() via d.setdefault('category', d.get('iec_category', 0))"
  - "Pre-calculated page numbers for TOC (1 defect/page = deterministic layout) instead of insert_toc_placeholder()"
  - "BRAND_NAVY (15,50,90) / BRAND_STEEL (0,100,160) / BRAND_LIGHT (220,235,248) palette selected"
metrics:
  duration: "5 minutes"
  completed: "2026-03-08T03:47:11Z"
  tasks: 2
  files: 5
---

# Phase 04 Plan 01: PDF Foundation Summary

**One-liner:** fpdf2 BDDAReport class with DroneWind Asia branding, Inter TTF fonts, cover/TOC/executive-summary/inspection-details pages replacing xhtml2pdf/jinja2 pipeline.

---

## What Was Built

A complete fpdf2 PDF foundation replacing the old xhtml2pdf/Jinja2 HTML rendering pipeline.

### Task 1: Font Assets + requirements.txt (commit 7dab214)

- Created `assets/fonts/` directory with Inter TTF v3.19 (Regular, Bold, Italic)
- Fonts sourced from GitHub release (Inter v3.19, "Hinted for Windows/Desktop" variant — proper TTF files with hinting)
- Updated `requirements.txt`: added `fpdf2>=2.8.0`, removed `jinja2>=3.1.0`, `python-bidi==0.4.2`, `xhtml2pdf>=0.2.11`

### Task 2: BDDAReport Class + Page Renderers (commit 09648b4)

Complete rewrite of `backend/report.py` with fpdf2. Kept: `build_report_data()`, `compute_condition_rating()`, `load_*_json()`, `make_sample_*()`, `CONDITION_RATINGS`, `URGENCY_COLORS`, `SEVERITY_COLORS`. Removed: `render_html()`, `generate_pdf()`, jinja2/weasyprint import blocks.

**New additions:**

- `FONT_DIR` constant — absolute path via `Path(__file__).parent.parent / "assets" / "fonts"`
- `SEVERITY_COLORS_IEC` — IEC 0-4 keyed dict with RGB tuples for fpdf2 rendering
- Brand palette constants: `BRAND_NAVY`, `BRAND_STEEL`, `BRAND_LIGHT`, `BRAND_ACCENT`, `BRAND_GREY`
- `CONDITION_COLORS_RGB` / `CONDITION_TEXT_RGB` — for condition badges
- `ZONE_COLORS_IEC` — for blade map (Plan 03)
- `hex_to_rgb()` utility
- `BDDAReport(FPDF)` — subclass with `_register_fonts()`, `_font()` helper, `header()`, `footer()`
- `_render_cover()` — navy band, title, turbine ID, condition badge, CONFIDENTIAL footer
- `_render_toc()` — section entries with pre-calculated page numbers
- `_render_executive_summary()` — condition badge, triage stats, IEC 0-4 table, critical findings, recommendation paragraph
- `_render_inspection_details()` — specs, drone, weather, GPS, notes, engineer review count, disclaimer
- `generate_pdf_fpdf2(report_data, output_path)` — new main entry point
- Updated `build_report()` to call `generate_pdf_fpdf2()` instead of HTML pipeline

**iec_category key normalization fix (BLOCKER fix applied):**
```python
# After building all_defects list:
for d in all_defects:
    d.setdefault("category", d.get("iec_category", 0))

# In blade_findings inner loop:
cat = d.get("category", d.get("iec_category", 0))
```
Ensures both real pipeline data (saves `iec_category`) and sample data (saves `category`) work correctly.

---

## Verification Results

| Check | Result |
|-------|--------|
| `from fpdf import FPDF` | PASS |
| `from backend.report import BDDAReport` | PASS |
| PDF generated from sample data | PASS — 40,989 bytes |
| No xhtml2pdf/weasyprint/jinja2 in report.py | PASS — 0 matches |
| 3 TTF files in assets/fonts/ | PASS |
| fpdf2 in requirements.txt | PASS |
| Old deps removed from requirements.txt | PASS |

---

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

**Minor implementation notes (not deviations):**
- Used pre-calculated page numbers for TOC instead of `insert_toc_placeholder()` — both approaches are valid per research. Pre-calculation is simpler and fully deterministic with 1-defect-per-page layout.
- Added `_font()` helper method on `BDDAReport` to consolidate Inter vs Helvetica fallback logic — reduces code repetition across all page renderers.
- `ZONE_COLORS_IEC` added to `report.py` now (needed by blade map renderer in Plan 03) to avoid import split.

---

## Self-Check

**Files check:**
- `assets/fonts/Inter-Regular.ttf` — FOUND
- `assets/fonts/Inter-Bold.ttf` — FOUND
- `assets/fonts/Inter-Italic.ttf` — FOUND
- `backend/report.py` with `class BDDAReport` — FOUND

**Commits check:**
- `7dab214` — fonts + requirements — FOUND
- `09648b4` — BDDAReport implementation — FOUND

## Self-Check: PASSED
