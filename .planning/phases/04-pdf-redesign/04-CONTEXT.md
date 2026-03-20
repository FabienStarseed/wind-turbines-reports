# Phase 4: PDF Redesign — Locked Decisions

**Date:** 2026-03-07
**Status:** Decisions locked — ready for planning

---

## A — Report Structure & Page Flow

| Decision | Choice |
|----------|--------|
| Section ordering | Cover → Table of Contents → Executive Summary → Defect Findings by Blade → Action Matrix → Blade Map → Inspection Details |
| Table of Contents | Yes — page 2 |
| Layout density | Spacious — generous whitespace, professional feel |

---

## B — Branding & Visual Identity

| Decision | Choice |
|----------|--------|
| Logo | Text-based header for now ("DroneWind Asia" styled). Layout accepts PNG at configurable path — swap in real logo later |
| Brand colours | AI-selected — professional wind energy / high-tech palette |
| Font | Custom TTF — modern, high-tech vibe (e.g., Inter, Exo 2, or similar clean sans-serif) |
| Header/footer | Yes — logo/brand name + page number + report reference on every page |

**Note:** Logo PNG generation is outside Claude Code scope. Text placeholder used until real logo is provided.

---

## C — Defect Presentation & Image Layout

| Decision | Choice |
|----------|--------|
| Image thumbnail size | Large — 80×80mm |
| Image position | Grid layout |
| Metadata fields | Full set (all available fields per defect) |
| Defects per page | 1 defect per page (spacious, maximum detail) |

---

## D — Per-Blade Defect Map (PDF-06)

| Decision | Choice |
|----------|--------|
| Blade diagram | Programmatic drawing with fpdf2 shapes (schematic) |
| Zone annotation | Mini-icons on blade diagram |
| Severity detail | Yes — severity colour on markers (colour-coded by IEC Cat) |

---

## Severity Colour Bands (from existing report.py)

| IEC Category | Label | Colour |
|-------------|-------|--------|
| Cat 0 | No damage | Green |
| Cat 1 | Minor | Yellow |
| Cat 2 | Moderate | Orange |
| Cat 3 | Major | Red |
| Cat 4 | Critical | Dark Red |

---

## Technical Constraints (carried from PDF-SPEC.md)

- fpdf2 replaces xhtml2pdf — no HTML/CSS, pure Python cell/rect/image API
- PDF generated from `build_report_data()` output in report.py
- Defect images available as base64 in triage results (stored in job JSON)
- DJI P1 source images deleted after triage — only tiles/thumbnails remain
- Must work on Render (Linux, no system fonts — bundle TTF)
