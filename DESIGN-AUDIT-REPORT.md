# BDDA Design Audit Report

**Auditor:** frontend-developer agent  
**Date:** 2026-04-25  
**Target:** /Users/fabien/Desktop/CLAUDE/applications/drone/bdda/frontend/ (index.html + style.css)  
**Live URL:** https://wind-turbines-reports.onrender.com

---

## Summary

The existing UI is functionally complete and structurally sound. The layout, grid system, and component breakdown are all correct. Issues are in execution quality: inconsistent visual hierarchy, weak form affordances, the pipeline info section is passive/decorative rather than scannable, and the job card lacks urgency during active analysis.

Score before redesign: **6.2 / 10**

---

## Dimension Scores

| # | Dimension | Score | Issues |
|---|-----------|-------|--------|
| 1 | Visual Hierarchy | 5/10 | Turbine ID is buried in a form. Upload CTA looks equal in weight to section headers. No clear "hero" action. |
| 2 | Typography | 7/10 | Inter is correct. But `11px` ALL-CAPS section labels create reading fatigue. The 3-level hierarchy (panel title / section label / field label) is one level too many. |
| 3 | Color | 6/10 | Navy palette is appropriate. But blue-accent (#3b82f6) saturated against white causes eye strain on the submit button hover. `--gray-400` text (#9ca3af) at 12px fails WCAG AA contrast (ratio ~3.5:1, needs 4.5:1). |
| 4 | Spacing | 6/10 | 8px base grid used inconsistently — form sections use 16px top + 4px bottom creating asymmetric rhythm. Panel title padding (16px top / 12px bottom) does not align to grid. |
| 5 | Components | 5/10 | Drop zone has correct mechanics but `📁` emoji as icon and emoji in sub-labels (`📎`) looks unprofessional. Submit button plays both primary CTA and form submit — but visually reads the same disabled as it does idle. History items lack clear states for running vs done vs error beyond a small badge. |
| 6 | Responsiveness | 7/10 | Grid breakpoints at 900px and 700px are correct. Right panel stacks properly. But form grids collapsing to single column at 700px is too aggressive — 2-col at 600px works. |
| 7 | Motion / Feedback | 7/10 | Pulse animation on active stage dot is good. Progress bar transition (0.4s ease) is appropriate. Missing: no visual feedback when file is dragged over drop zone on mobile, no loading shimmer on history load. |
| 8 | Cognitive Load | 5/10 | Environmental conditions section (4 fields: weather, wind, temp, visibility) appears on first load alongside required turbine fields — creates perceived complexity before user can start. Could be collapsed or clearly marked optional. Pipeline info always visible even during active job — it competes with progress stages for attention. |
| 9 | Polish | 6/10 | `⚙` brand icon is generic. Panel title uses `border-bottom: 2px solid var(--navy)` which looks heavy. History empty state is too small and centered oddly. No favicon. The `▶` button icon is a Unicode fallback, not an icon system. |

**Overall: 6.2 / 10**

---

## Critical Fixes Required

1. **Contrast failure:** `--gray-400` (#9ca3af) text must be replaced with `--gray-500` (#6b7280) minimum for WCAG AA compliance at small sizes.
2. **Visual hierarchy:** Turbine ID + upload action must be the dominant elements on page load — not equal weight to section dividers.
3. **Drop zone:** Remove emoji icons. Use CSS-drawn upload icon or SVG inline. Professional tool, not a consumer app.
4. **Form density:** Mark optional sections clearly. Reduce perceived cognitive load.
5. **Submit button:** Clear disabled visual state (reduced opacity + cursor not-allowed, distinct from hover).
6. **Pipeline info:** Move below active job card, add visual connection between pipeline steps and active stages.

---

## What Works — Keep

- Two-column sidebar layout (left form / right status+history) — correct for this workflow
- Progress stages vertical list with dots — good pattern, just needs refinement
- Panel-based card structure — right abstraction
- Navy color palette — professional and appropriate for industrial inspection tool
- History item structure (turbine ID + date + status badge + download link)
- Sticky header with API health indicator

---

## Redesign Targets

- White/light background (#f8fafc page, #ffffff panels)
- Navy accent remains (#0f2744 headers, borders, CTAs)
- Improve contrast on all secondary text (minimum #6b7280)
- Turbine ID field visually prominent — larger input, top of form
- Upload drop zone: bordered card with proper visual icon, no emoji
- Submit button: full-width, navy, clear disabled state
- Section grouping: Required fields prominent, optional fields subtle
- Pipeline info: clean numbered steps, compact
- History: table-like rows with clear status indicators
- 8px grid strict compliance
- No external dependencies added (Google Fonts CDN already present — retain)
