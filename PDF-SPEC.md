# PDF Report Specification — Phase 4

## Overview

Replace current xhtml2pdf/WeasyPrint HTML-to-PDF approach with **fpdf2** for direct PDF construction. The report is the primary deliverable clients receive.

**Status:** Phase 4 — discuss-phase in progress (gray areas under review)

---

## Requirements (from REQUIREMENTS.md)

| ID | Requirement | Status |
|----|-------------|--------|
| PDF-01 | PDF uses fpdf2 (replaces xhtml2pdf) | ⬜ Not started |
| PDF-02 | DroneWind Asia branding (logo, colours, header/footer) | ⬜ Not started |
| PDF-03 | Defect images embedded inline next to findings | ⬜ Not started |
| PDF-04 | Severity colour-coding (Cat 0-4 colour bands) | ⬜ Not started |
| PDF-05 | Executive summary page (defect counts, highest severity, recommendation) | ⬜ Not started |
| PDF-06 | Per-blade defect map (blade diagram with annotated zones) | ⬜ Not started |

---

## Success Criteria (from ROADMAP.md)

1. PDF renders correctly with fpdf2 (no xhtml2pdf dependency)
2. DroneWind Asia logo appears in header on every page
3. Each critical finding shows the defect image inline
4. Defect severity rows use colour bands (Cat 0=green to Cat 4=red)
5. Page 1 is an executive summary (defect counts, highest severity, recommendation)
6. Report is visually client-presentable quality

---

## Current Implementation (report.py — being replaced)

### Data Pipeline (KEEP — this logic stays)
- `build_report_data()` assembles all pipeline output into one dict
- Inputs: `turbine_meta`, `triage_data`, `classify_data`, `analyze_data`
- Outputs: condition rating (A-D), defects by category, defects by blade, critical findings, action matrix, triage stats

### What Gets Replaced
- `render_html()` — Jinja2 HTML template rendering → fpdf2 direct PDF
- `generate_pdf()` — xhtml2pdf/WeasyPrint conversion → fpdf2 native
- `templates/report.html` — HTML template → no longer needed

### What Stays
- `build_report_data()` — data assembly logic, unchanged
- `compute_condition_rating()` — A-D rating algorithm
- `SEVERITY_COLORS` — colour definitions (adapted for fpdf2 RGB tuples)
- `URGENCY_COLORS` — urgency colour map
- `CONDITION_RATINGS` — condition descriptions
- `load_*_json()` — data loading helpers

---

## Existing Data Structures

### Report Data Dict (from build_report_data)
```python
{
    "turbine": { turbine_id, site_name, country, turbine_model, hub_height_m,
                 rotor_diameter_m, blade_length_m, inspection_date, inspector_name,
                 drone_model, weather, wind_speed_ms, temperature_c, visibility_km,
                 gps_lat, gps_lon, notes, company_name, report_ref },
    "report_ref": "BDDA-JAP19-20251130",
    "generated_at": "2025-11-30 14:30 UTC",
    "total_defects": int,
    "defects_by_cat": { 1: count, 2: count, 3: count, 4: count, 5: count },
    "defects_by_blade": { "A": {1:n, 2:n, 3:n, 4:n, 5:n, "total":n}, ... },
    "blades_sorted": ["A", "B", "C"],
    "critical_count": int,
    "critical_findings": [ top 5 critical defects ],
    "condition": "A" | "B" | "C" | "D",
    "condition_info": { label, color, desc },
    "blade_findings": { "A": [sorted defects], "B": [...], ... },
    "action_matrix": [ { priority, action, blade, defect_id, defect_name,
                         category, urgency, zone, timeframe, severity_style } ],
    "triage_stats": { total, flagged, clean, errors, flag_rate },
    "severity_colors": SEVERITY_COLORS,
}
```

### Defect Object (per finding)
```python
{
    "defect_id": "A-LE-001",
    "defect_name": "Leading Edge Erosion — Stage 3",
    "category": 3,              # IEC Cat 0-4 (current code uses 1-5, needs alignment)
    "urgency": "PLANNED",       # LOG | MONITOR | PLANNED | URGENT | IMMEDIATE
    "zone": "LE",               # LE, TE, PS, SS
    "position": "Mid",          # Root, Mid, Tip
    "size_estimate": "large (>30cm)",
    "confidence": 0.88,
    "visual_description": "...",
    "ndt_recommended": bool,
    "image_path": "/data/JAP19/blade_A/LE_Mid_001.jpg",
    "severity_style": { bg, text, badge, label },
    "analysis": {               # from analyze stage (may be null)
        "root_cause": "...",
        "failure_risk": { progression_risk, failure_mode, safety_risk },
        "recommended_action": "...",
        "repair_timeframe": "30 days",
        "estimated_cost_usd": "$8,000–$18,000",
        "engineer_review_required": bool,
    }
}
```

### Severity Colour Map (current)
```python
SEVERITY_COLORS = {
    1: { bg: "#dcfce7", text: "#166534", badge: "#22c55e", label: "Cat 1 — Cosmetic" },
    2: { bg: "#fef9c3", text: "#854d0e", badge: "#eab308", label: "Cat 2 — Minor" },
    3: { bg: "#fff7ed", text: "#9a3412", badge: "#f97316", label: "Cat 3 — Planned" },
    4: { bg: "#fee2e2", text: "#991b1b", badge: "#ef4444", label: "Cat 4 — Urgent" },
    5: { bg: "#fce7f3", text: "#9d174d", badge: "#7f1d1d", label: "Cat 5 — Critical" },
}
```

---

## Proposed Report Structure

### Page 1: Cover Page
- DroneWind Asia logo (top-centre)
- Report title: "Wind Turbine Blade Inspection Report"
- Turbine ID, site name, country
- Inspection date, inspector name
- Report reference number
- Condition rating badge (A/B/C/D with colour)
- Company contact info (footer)

### Page 2: Executive Summary (PDF-05)
- Overall condition rating with description
- Total images inspected / flagged / clean
- Total defects found by category (bar or table)
- Critical count with top 3-5 critical findings summary
- Recommendation paragraph (auto-generated from condition + findings)

### Pages 3-N: Defect Findings by Blade
- One section per blade (A, B, C)
- Each defect as a card/row with:
  - Defect image thumbnail (PDF-03)
  - Defect ID, name, category, urgency
  - Zone / position / size estimate
  - Confidence score
  - Visual description
  - Analysis (root cause, recommended action, cost estimate) if available
  - Severity colour band on row/card (PDF-04)
- Defects sorted by severity (Cat 4 first)

### Action Matrix Page
- Priority-sorted table (P1→P4)
- Columns: Priority, Blade, Defect ID, Defect Name, Category, Zone, Timeframe, Action
- Colour-coded by severity

### Per-Blade Defect Map (PDF-06)
- Schematic blade outline divided into zones (Root/Mid/Tip × LE/TE/PS/SS)
- Defect markers at approximate zone positions
- Legend showing severity colours
- **Note:** This may be a programmatic drawing using fpdf2 shapes, not an external image

### Final Page: Inspection Details
- Turbine specifications (model, hub height, rotor diameter, blade length)
- Drone & camera info
- Weather conditions at time of inspection
- GPS coordinates
- Inspector notes
- Legal disclaimer / methodology note

---

## Gray Areas (under discussion — Phase 4 discuss-phase)

### A — Report structure & page flow
- Exact section ordering and page breaks
- Table of contents inclusion
- Information density per page

### B — DroneWind Asia branding & visual identity
- Logo file location and format
- Brand colours (exact hex values)
- Font choice
- Header/footer design across all pages

### C — Defect presentation & image layout
- Image size and positioning within findings
- Metadata fields shown per defect
- How many defects per page

### D — Per-blade defect map (PDF-06)
- Blade diagram source (programmatic drawing vs template image)
- Zone annotation method
- Visual style of defect markers

---

## Technical Constraints

- **fpdf2** — pure Python, no system dependencies (critical for Render deployment)
- Images may be deleted after triage (only classified/critical images retained in job directory)
- PDF must be downloadable via `GET /api/download/{job_id}` endpoint
- File stored at `DATA_DIR/jobs/{job_id}/report.pdf`
- Maximum A4 page size (210 × 297mm)
- Must handle 0 defects gracefully (clean turbine report)
- Must handle 100+ defects without page overflow issues

---

## Dependencies

### Current (being removed)
- `xhtml2pdf` — HTML to PDF conversion
- `weasyprint` — HTML to PDF (fallback, requires GTK/Pango system libs)
- `jinja2` — HTML template rendering

### Phase 4 (replacing with)
- `fpdf2` — direct PDF construction (already in requirements.txt)
- `Pillow` — image resizing for thumbnails (likely needed)

---

## File Changes Expected

| File | Change |
|------|--------|
| `backend/report.py` | Major rewrite — replace HTML/PDF pipeline with fpdf2 |
| `templates/report.html` | Delete (no longer needed) |
| `templates/report.css` | Delete (no longer needed) |
| `requirements.txt` | Remove xhtml2pdf, weasyprint, jinja2; add fpdf2, Pillow |
| `assets/logo.png` | New — DroneWind Asia logo (TBD from user) |
