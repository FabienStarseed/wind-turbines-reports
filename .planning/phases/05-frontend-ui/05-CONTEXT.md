# Phase 5 Context — Frontend UI

**Phase:** 5 — Frontend UI (Tailwind + Alpine.js)
**Created:** 2026-04-18
**Status:** Ready for research

---

## Locked Decisions (from prior phases)

- Stack: Tailwind CSS + Alpine.js via CDN — no build pipeline, no npm
- Auth: JWT in `localStorage['bdda_token']`, silent refresh via `X-New-Token` header
- Backend: FastAPI serving static files from `frontend/` — all pages are `.html`
- Branding: AWID — APAC Wind Inspections Drones (was "DroneWind Asia" — stale in current frontend)
- Pipeline stages: Triage / Classify / Analyze / PDF — all via `claude-opus-4-6` (stale Kimi/Gemini labels in current UI must be updated)
- Deploy: Render.com, `frontend/` served as static

---

## Design System

**Name:** Cyber Operator (dark terminal, data-dense)
**Source file:** `/Users/fabien/Desktop/CLAUDE/-SKILLS/f-design-branding-web/design-style.md`

### Color palette (locked)
```css
:root {
  --bg:      #050510;
  --cyan:    #00F5FF;
  --green:   #00FF88;
  --magenta: #FF006E;
  --amber:   #FFB800;
  --purple:  #7B2FFF;
  --dim:     rgba(255,255,255,0.06);
  --border:  rgba(255,255,255,0.08);
  --glass:   rgba(5,5,20,0.7);
}
```

### Typography (locked — Google Fonts via CDN)
- `Bebas Neue` — logo, large display numbers
- `JetBrains Mono` — badges, labels, section headers, metadata
- `Syne` — body text, navigation, buttons
- `DM Mono` — descriptions, secondary content

### Background (locked — always present)
- Animated bg-gradient (radial cyan/purple pulses)
- CSS grid drift (60×60px cyan grid lines)
- Scanlines overlay

### Anti-patterns (never do)
- No white/light backgrounds
- No border-radius > 4px
- No drop shadows (glow only)
- No Bootstrap/Material patterns

---

## Area A — Dashboard Layout & Navigation

### Decision: Full redesign of layout structure
The current 2-column panel layout is replaced with a proper Cyber Operator dashboard.

**Layout:**
- Fixed header (64px): AWID logo (Bebas Neue, cyan gradient), username pill, logout button, live-dot status indicator
- Full-width content below header, two views: **New Inspection** and **Job History**
- Navigation: Header tabs (Alpine.js `x-show`) — "NEW INSPECTION" (active) and "HISTORY" — amber bottom border on active tab

**Tablet behavior (UI-06):**
- 2-column form grid collapses to 1-column below 768px
- Header tabs remain (do NOT stack vertically — inspector uses tablet in field and needs fast tab switching)
- Right panel (progress) moves below form on small screens

**Header content (locked):**
- Left: `AWID` logo text + `APAC WIND INSPECTIONS DRONES` subtitle (small, muted)
- Center: Tab nav — `NEW INSPECTION` / `HISTORY`
- Right: username (JetBrains Mono, cyan) + `LOGOUT` action-btn (amber clip-path style)

**Empty state:**
- When no jobs exist: right panel shows a muted placeholder with `–` and text `NO INSPECTIONS YET` in ghost style
- No decorative illustrations — pure text placeholder

---

## Area B — Upload Form Flow & Feedback

### Decision: Single scrollable form with expandable sections + Cyber Operator styling

**Form structure (order unchanged):**
1. Turbine Identity (fields: Turbine ID, Model, Site Name, Country, Hub Height, Rotor Diameter, Blade Length, GPS Lat/Lon)
2. Inspection Details (Inspector Name, Date, Drone Model)
3. Environmental Conditions (Weather, Wind Speed, Temperature, Visibility)
4. Inspection Notes (textarea)
5. Image Upload (drop zone)

**Expandable sections:**
- Each section collapses/expands via Alpine.js `x-show` + max-height transition
- Section header: `section-label` style (cyan line + uppercase JetBrains Mono) with a `▼` / `▶` toggle icon
- Default state: ALL sections expanded on page load
- User can collapse sections they've already filled

**File selected state:**
- Drop zone border turns `--green` (#00FF88) when file is selected
- File name shown in mono text inside the zone, with a green `✓` badge
- File size shown as secondary muted text

**Submit button:**
- `action-btn` clip-path style (cyan background, dark text)
- Text: `▶ GENERATE INSPECTION REPORT`
- Disabled + opacity 0.5 while pipeline is running

---

## Area C — Live Progress Tracking Experience

### Decision: Animated stage tracker + celebration state + inline download + optional auto-redirect

**Stage list (updated labels — NO more Kimi/Gemini):**
1. INGEST IMAGES
2. TRIAGE — claude-opus-4-6
3. CLASSIFY — claude-opus-4-6
4. ANALYZE — claude-opus-4-6
5. BUILD PDF
6. COMPLETE

**Stage dot states:**
- Pending: muted grey dot
- Active: amber pulsing dot (`livePulse` animation) + amber text
- Done: green dot + green text + `✓`
- Failed: magenta dot + magenta text + `✗`

**Progress bar:**
- 4-6px thin bar, `--border` background, amber→green gradient fill
- Advances per stage completion (16% per stage)

**On pipeline COMPLETE — celebration state:**
- Progress bar fills fully → turns green
- All stage dots go green
- A `INSPECTION COMPLETE` badge appears (green, JetBrains Mono, pulsing)
- Inline download button appears: `⬇ DOWNLOAD REPORT PDF` (action-btn, cyan)
- Auto-redirect toggle: small checkbox below download btn: `[ ] AUTO-REDIRECT TO HISTORY` — unchecked by default
  - If checked: redirects to Job History tab after 3s countdown shown in text
  - If unchecked: stays on current view with download button visible

**Error state:**
- Pipeline error: stage dot goes magenta, error message in magenta below progress bar

---

## Area D — Job History Table

### Decision: Data-dense table with Cyber Operator styling

**Columns (in order):**
| Column | Format |
|--------|--------|
| DATE | `APR 18 · 14:32` (JetBrains Mono, muted) |
| TURBINE ID | Uppercase, cyan |
| SITE | Sentence case, white |
| STATUS | Badge: `COMPLETE` (green) / `FAILED` (magenta) / `RUNNING` (amber, pulsing) |
| DEFECTS | Number, monospace — `–` if failed/running |
| COST | `$4.23` monospace — `–` if not available |
| DOWNLOAD | `⬇ PDF` action-btn (cyan, small) — greyed out if not complete |

**Failed jobs:** shown in table with `FAILED` badge (magenta), `–` for defects/cost, download button greyed out
**Running jobs:** shown with `RUNNING` badge (amber pulsing live-dot), no download yet

**Row behavior:**
- Hover: `rgba(255,255,255,0.03)` background
- No expand-on-click in Phase 5 (detail view is Phase 6+)
- `border-bottom: 1px solid var(--border)` between rows

**Empty state:**
- `NO REPORTS GENERATED YET` in ghost muted style, centered in the table area

**Sort:** Most recent first (backend already returns 30-day history ordered by created_at DESC)

---

## Files to Modify

| File | Change |
|------|--------|
| `frontend/index.html` | Full rewrite — Cyber Operator layout, Alpine.js, Tailwind CDN |
| `frontend/login.html` | Full rewrite — branded login page (Cyber Operator) |
| `frontend/style.css` | Replace with Cyber Operator CSS variables and base styles (Tailwind handles utilities) |
| `frontend/app.js` | Update stage labels (remove Kimi/Gemini), add Alpine.js data logic |

---

## Deferred Ideas (out of Phase 5 scope)

- Job detail view / click-to-expand row — Phase 6+
- Real-time cost estimate display during pipeline — Phase 6+
- Admin panel UI (create users) — Phase 6+
- Dark/light mode toggle — not aligned with design system, skip entirely
