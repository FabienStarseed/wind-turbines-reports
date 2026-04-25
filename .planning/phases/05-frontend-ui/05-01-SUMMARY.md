---
plan: 05-01
status: complete
---

# Summary 05-01 — Login Page Rewrite

## Done

- `frontend/login.html` fully rewritten — old vanilla-JS form replaced with Alpine.js `loginApp()` component
- Cyber Operator design system applied: `#050510` bg, cyan/purple/green/magenta CSS custom vars
- Fonts loaded via Google Fonts CDN: Bebas Neue, JetBrains Mono, Syne, DM Mono
- Tailwind Play CDN + inline `tailwind.config` override with full color/font palette
- Alpine.js v3 deferred from jsDelivr CDN
- AWID branding: "AWID" in Bebas Neue with cyan→purple gradient text, subtitle "APAC WIND INSPECTIONS DRONES" in JetBrains Mono muted
- Animated background: radial gradient pulse layer + 60px cyan grid drift + scanline overlay (all `position:fixed`, `z-index:0/1`)
- `action-btn` with `clip-path: polygon(8px 0%, 100% 0%, calc(100% - 8px) 100%, 0% 100%)` on submit button
- `cyber-input` class: dark semi-transparent bg, `rgba(255,255,255,0.08)` border, cyan focus glow
- `cyber-card` with glass backdrop-filter and cyan glow border via `::before` pseudo-element
- No border-radius > 4px anywhere (inputs/card: 2px)
- No white backgrounds, no drop shadows

## Auth logic

- `checkAlreadyLoggedIn()` runs on `x-init` — redirects to `?next=` or `/` if token present
- Form uses `@submit.prevent="login()"` — no vanilla event listeners
- Submits via `URLSearchParams` + `application/x-www-form-urlencoded` (FastAPI OAuth2 requirement)
- On success: stores `access_token` → `localStorage['bdda_token']`, decodes JWT payload `.sub` → `localStorage['bdda_username']`
- On fail: magenta `#FF006E` error message via `x-show="errorMsg"`
- Button shows "AUTHENTICATING…" (`x-show="loading"`) during fetch, disabled while loading

## Verification checklist

- [x] `login.html` has no syntax errors
- [x] Background is `#050510` with grid + gradient + scanlines
- [x] AWID logo in Bebas Neue with cyan-purple gradient
- [x] Magenta error message on bad credentials (`errorMsg` binding)
- [x] JWT stored + username decoded on success
- [x] Button loading state implemented
- [x] No white backgrounds, no border-radius > 4px
- [x] `max-w-sm` card centered, usable at 768px+
