# Phase 05 Research — Frontend UI
**Generated:** 2026-04-18
**Mode:** ecosystem
**Phase:** 05 — Frontend UI (Tailwind + Alpine.js, Cyber Operator design system)

---

## Standard Stack

### CDN URLs (use exactly these — no build pipeline)

```html
<!-- Tailwind CSS v3 (Play CDN — runtime JIT, full utility set) -->
<script src="https://cdn.tailwindcss.com"></script>

<!-- Alpine.js v3 (core) -->
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>

<!-- Google Fonts (single preconnect + single stylesheet call) -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=JetBrains+Mono:wght@400;700&family=Syne:wght@400;600;700&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
```

**Tailwind Play CDN note:** `cdn.tailwindcss.com` is the Play CDN. It scans the DOM at runtime and generates CSS on the fly. No config file needed. All standard Tailwind v3 utilities available including arbitrary values like `w-[64px]`, `bg-[#050510]`.

**Alpine.js v3 note:** Must load with `defer`. Alpine initializes after DOM is parsed. `x-data`, `x-show`, `x-bind`, `x-on`, `x-transition`, `x-for`, `x-init`, `x-ref`, `x-text` all available in core — no plugins needed for this phase.

### Tailwind config override (inline, in `<script>` after CDN)

```html
<script>
  tailwind.config = {
    theme: {
      extend: {
        colors: {
          bg:      '#050510',
          cyan:    '#00F5FF',
          green:   '#00FF88',
          magenta: '#FF006E',
          amber:   '#FFB800',
          purple:  '#7B2FFF',
        },
        fontFamily: {
          bebas:   ['Bebas Neue', 'sans-serif'],
          mono:    ['JetBrains Mono', 'monospace'],
          syne:    ['Syne', 'sans-serif'],
          dmmono:  ['DM Mono', 'monospace'],
        }
      }
    }
  }
</script>
```

This must appear **after** `<script src="https://cdn.tailwindcss.com">` and **before** `</head>`.

---

## Architecture Patterns

### Pattern 1 — Single Alpine component per page (not global store)

Each page (`index.html`, `login.html`) uses one top-level `x-data` on `<body>` or a wrapping `<div>`. All state lives in one Alpine component object returned from `Alpine.data()` or inline.

```html
<body x-data="app()" x-init="init()">
```

```js
function app() {
  return {
    // Auth state
    token: localStorage.getItem('bdda_token') || null,
    username: localStorage.getItem('bdda_username') || '',

    // Tab navigation
    activeTab: 'new-inspection',  // 'new-inspection' | 'history'

    // Form state
    fileSelected: false,
    fileName: '',
    fileSize: '',
    sections: {
      identity: true,
      details: true,
      environment: true,
      notes: true,
      upload: true,
    },

    // Pipeline state
    jobId: null,
    stage: null,       // matches backend stage string
    progress: 0,
    message: '',
    totalImages: null,
    flaggedImages: null,
    criticalFindings: null,
    isPolling: false,
    downloadUrl: null,
    autoRedirect: false,
    countdown: 3,
    pipelineError: null,

    // History
    jobs: [],
    historyLoaded: false,

    // Methods...
    async init() { ... },
    async login() { ... },
    logout() { ... },
    async submit() { ... },
    async poll() { ... },
    async loadHistory() { ... },
    apiFetch(path, opts) { ... },  // adds Authorization header
  }
}
```

### Pattern 2 — JWT in Alpine via `apiFetch()` wrapper

All API calls go through one helper that reads `localStorage['bdda_token']`, adds `Authorization: Bearer`, and handles 401 (redirect to login):

```js
async apiFetch(path, opts = {}) {
  const token = localStorage.getItem('bdda_token');
  if (!token) { window.location.href = '/login'; return null; }
  const headers = { 'Authorization': `Bearer ${token}`, ...opts.headers };
  const res = await fetch(path, { ...opts, headers });
  // Handle silent token refresh
  const newToken = res.headers.get('X-New-Token');
  if (newToken) localStorage.setItem('bdda_token', newToken);
  if (res.status === 401) { this.logout(); return null; }
  return res;
},
```

### Pattern 3 — Polling with Alpine (setInterval + $data reference)

Do NOT use global `setInterval` with DOM queries. Use an instance method bound to Alpine's `this`:

```js
startPolling(jobId) {
  this.isPolling = true;
  this._pollTimer = setInterval(async () => {
    await this.pollOnce(jobId);
  }, 2000);
  this.pollOnce(jobId);  // immediate first hit
},
stopPolling() {
  clearInterval(this._pollTimer);
  this.isPolling = false;
},
```

The `_pollTimer` is stored directly on `this` (the Alpine reactive proxy). Alpine ignores underscore-prefixed properties for reactivity — they won't trigger re-renders.

### Pattern 4 — Alpine `x-show` with CSS transitions (not Tailwind transition classes)

For expandable form sections, use Alpine's built-in `x-transition` with CSS max-height:

```html
<div x-show="sections.identity" x-transition:enter="transition-expand" x-transition:leave="transition-collapse">
  ...
</div>
```

```css
/* In style.css */
[x-cloak] { display: none !important; }

.transition-expand { transition: max-height 0.3s ease, opacity 0.2s ease; }
.transition-collapse { transition: max-height 0.25s ease, opacity 0.15s ease; }
```

Add `x-cloak` to the `<body>` tag and `[x-cloak] { display: none }` in CSS to prevent FOUC (flash of unstyled content) while Alpine loads.

### Pattern 5 — `x-for` for history table (not innerHTML string building)

Replace the current `innerHTML` string concatenation with Alpine `x-for`:

```html
<template x-for="job in jobs" :key="job.job_id">
  <tr>
    <td x-text="formatDate(job.created_at)"></td>
    <td x-text="job.turbine_id || '—'"></td>
    ...
  </tr>
</template>
```

This is reactive — when `this.jobs` updates, the table re-renders automatically.

### Pattern 6 — Tailwind arbitrary values for Cyber Operator design tokens

Use CSS variables for the design system (in `:root` in `style.css`) AND expose them to Tailwind via the config. Use `bg-[#050510]` or `text-[var(--cyan)]` for one-off values. Prefer CSS variables for anything used more than twice.

### Pattern 7 — Clip-path action buttons (CSS, not Tailwind)

The `action-btn` clip-path style cannot be done with Tailwind utilities. Define in `style.css`:

```css
.action-btn {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  background: var(--cyan);
  color: #050510;
  padding: 0.5rem 1.25rem;
  clip-path: polygon(8px 0%, 100% 0%, calc(100% - 8px) 100%, 0% 100%);
  border: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  transition: opacity 0.15s;
}
.action-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.action-btn:hover:not(:disabled) { opacity: 0.85; }
.action-btn.amber { background: var(--amber); }
.action-btn.sm { font-size: 0.65rem; padding: 0.3rem 0.8rem; }
```

### Pattern 8 — Animated background (CSS only, no JS)

```css
body::before {
  content: '';
  position: fixed;
  inset: 0;
  background:
    radial-gradient(ellipse at 20% 30%, rgba(0,245,255,0.06) 0%, transparent 60%),
    radial-gradient(ellipse at 80% 70%, rgba(123,47,255,0.06) 0%, transparent 60%);
  animation: bgPulse 8s ease-in-out infinite alternate;
  pointer-events: none;
  z-index: 0;
}
body::after {
  content: '';
  position: fixed;
  inset: 0;
  background-image:
    linear-gradient(rgba(0,245,255,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,245,255,0.03) 1px, transparent 1px);
  background-size: 60px 60px;
  pointer-events: none;
  z-index: 0;
}
@keyframes bgPulse {
  from { opacity: 0.6; }
  to { opacity: 1; }
}
```

Scanlines overlay on a dedicated `<div class="scanlines">` element (position:fixed, z-index above bg but below content).

### Pattern 9 — `livePulse` animation for active stage dot and running badge

```css
@keyframes livePulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.5; transform: scale(0.85); }
}
.pulse { animation: livePulse 1.4s ease-in-out infinite; }
```

Apply via Alpine: `:class="{ 'pulse': stage === 'triaging' }"` etc.

---

## Don't Hand-Roll

- **Drag-and-drop file detection:** Use the native `dragover` / `drop` events on the drop zone `<div>` with `e.dataTransfer.files`. Do NOT build a custom file picker component.
- **Form validation:** Use native HTML5 `required` + `type` validation. Do NOT add a custom validation library.
- **Date formatting:** Use `Date.toLocaleDateString('en-GB', { day:'2-digit', month:'short' })` and `.toLocaleTimeString('en-GB', { hour:'2-digit', minute:'2-digit' })`. Do NOT import a date library (no Day.js, no date-fns).
- **CSS animations:** Use `@keyframes` in `style.css`. Do NOT use `animate.css` or GSAP.
- **File size display:** `(bytes / 1024 / 1024).toFixed(1) + ' MB'` inline — do NOT abstract.
- **JWT decode for username:** `JSON.parse(atob(token.split('.')[1]))` — do NOT import `jwt-decode`.
- **Toast/notification system:** Inline Alpine state (`errorMsg`, `successMsg`) displayed with `x-show`. Do NOT pull in a toast library.

---

## Common Pitfalls

### Alpine pitfalls

1. **`x-show` vs `x-if`:** Use `x-show` for elements that toggle frequently (stage dots, section collapse). Use `x-if` only for conditional rendering that never reverses (e.g., only rendering the progress panel after first submit). `x-if` destroys and recreates the DOM; `x-show` just toggles `display`.

2. **Alpine initializes after `DOMContentLoaded`:** If you use `x-init="init()"` with `async init()`, the function fires before font rendering — do not depend on layout measurements in `x-init`.

3. **`x-for` key must be unique:** Use `job_id` not `index` as the `:key`. Using index breaks reactivity when the list updates.

4. **`x-bind:class` with template literals:** Alpine supports `:class="{ 'text-[#00FF88]': isDone, 'text-[#FFB800]': isActive }"`. Do NOT use string concatenation inside `:class`.

5. **`x-transition` + `x-show` + initial hidden:** If `x-show` starts as `false`, add `style="display:none"` to prevent FOUC before Alpine loads. Use `x-cloak` as backup.

6. **Polling memory leak:** Always call `stopPolling()` in `x-init` when navigating away (the page doesn't unmount — it's SPA-like with `x-show`). Use `document.addEventListener('visibilitychange', ...)` to pause polling when the tab is backgrounded.

### Tailwind Play CDN pitfalls

7. **Dynamic class names not detected:** If you build class strings dynamically like `` `text-${color}` ``, Tailwind CDN won't scan them. Use full class names in HTML or use `safelist` in tailwind.config. Prefer inline `style` or CSS variables for dynamic colors.

8. **Tailwind config must come after CDN script:** If `tailwind.config` is set before the CDN loads, the config is ignored.

9. **`@apply` doesn't work in Play CDN:** The CDN does not process `@apply` directives. Write standard CSS in `style.css` instead.

### Auth / API pitfalls

10. **Login form must use `URLSearchParams`, not `FormData` or JSON:** FastAPI `OAuth2PasswordRequestForm` requires `Content-Type: application/x-www-form-urlencoded`. Current `login.html` already does this correctly — preserve it.

11. **Download endpoint requires Bearer token:** `/api/download/{job_id}` needs `Authorization: Bearer`. Setting `downloadBtn.href` directly won't work. Fetch the PDF as a blob and create an object URL, or use a hidden anchor with JS click trigger:

```js
async downloadReport(jobId) {
  const res = await this.apiFetch(`/api/download/${jobId}`);
  if (!res || !res.ok) return;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `inspection_${jobId}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
},
```

12. **`/api/jobs` also requires Bearer:** Current `app.js` calls `fetch('/api/jobs')` without auth headers. This will 401 in production. Must use `apiFetch`.

13. **`/api/status/{job_id}` requires Bearer:** Same issue — must add auth header on every poll call.

14. **Silent token refresh:** After every `apiFetch`, check `res.headers.get('X-New-Token')` and update `localStorage['bdda_token']`. The backend mints a new token when <60 min remain.

### Design system pitfalls

15. **`border-radius > 4px` breaks the aesthetic:** All cards, inputs, buttons use `border-radius: 2px` or `0`. No rounded corners.

16. **No drop shadows — glow only:** Use `box-shadow: 0 0 12px rgba(0,245,255,0.2)` for glow effects. Never `box-shadow: 4px 4px 8px rgba(0,0,0,0.5)`.

17. **Fixed header must be `position: fixed; z-index: 100`:** Content below must have `padding-top: 64px`. Do not use `position: sticky` — it interacts poorly with the CSS grid background.

18. **History tab loads lazily:** Only call `/api/jobs` when the user clicks "HISTORY" tab, not on page load. Add `x-init` on the history tab content: `x-init="if (!historyLoaded) loadHistory()"`.

---

## Code Examples

### Login page Alpine structure

```html
<div x-data="loginApp()" x-init="checkAlreadyLoggedIn()">
  <form @submit.prevent="login()">
    <input x-model="username" type="text" name="username" required autofocus>
    <input x-model="password" type="password" name="password" required>
    <button type="submit" :disabled="loading" class="action-btn">
      <span x-show="!loading">▶ LOGIN</span>
      <span x-show="loading">AUTHENTICATING…</span>
    </button>
    <p x-show="errorMsg" x-text="errorMsg" class="text-[#FF006E] font-mono text-xs mt-2"></p>
  </form>
</div>

<script>
function loginApp() {
  return {
    username: '', password: '', loading: false, errorMsg: '',
    checkAlreadyLoggedIn() {
      if (localStorage.getItem('bdda_token')) {
        const params = new URLSearchParams(window.location.search);
        window.location.href = params.get('next') || '/';
      }
    },
    async login() {
      this.loading = true; this.errorMsg = '';
      try {
        const res = await fetch('/api/auth/token', {
          method: 'POST',
          body: new URLSearchParams({ username: this.username, password: this.password }),
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        });
        if (!res.ok) { this.errorMsg = 'Invalid credentials.'; return; }
        const data = await res.json();
        localStorage.setItem('bdda_token', data.access_token);
        // Store username from JWT payload
        try {
          const payload = JSON.parse(atob(data.access_token.split('.')[1]));
          localStorage.setItem('bdda_username', payload.sub);
        } catch {}
        const params = new URLSearchParams(window.location.search);
        window.location.href = params.get('next') || '/';
      } catch { this.errorMsg = 'Network error.'; }
      finally { this.loading = false; }
    },
  }
}
</script>
```

### Stage dot rendering (Alpine x-for)

```html
<template x-for="(s, i) in stages" :key="s.key">
  <div class="flex items-center gap-3 py-1">
    <div class="w-2 h-2 rounded-full flex-shrink-0"
         :class="{
           'bg-[#00FF88]': isDone(i),
           'bg-[#FFB800] pulse': isActive(i),
           'bg-[#FF006E]': isFailed(i),
           'bg-white/20': isPending(i),
         }">
    </div>
    <span class="font-mono text-xs uppercase tracking-wider"
          :class="{
            'text-[#00FF88]': isDone(i),
            'text-[#FFB800]': isActive(i),
            'text-[#FF006E]': isFailed(i),
            'text-white/30': isPending(i),
          }">
      <span x-text="s.label"></span>
      <span x-show="isDone(i)"> ✓</span>
      <span x-show="isFailed(i)"> ✗</span>
    </span>
  </div>
</template>
```

Stage data (in Alpine component):
```js
stages: [
  { key: 'ingesting',          label: 'INGEST IMAGES' },
  { key: 'triaging',           label: 'TRIAGE — claude-opus-4-6' },
  { key: 'classifying',        label: 'CLASSIFY — claude-opus-4-6' },
  { key: 'analyzing',          label: 'ANALYZE — claude-opus-4-6' },
  { key: 'generating_report',  label: 'BUILD PDF' },
  { key: 'complete',           label: 'COMPLETE' },
],
STAGE_ORDER: ['ingesting','triaging','classifying','analyzing','generating_report','complete'],
isDone(i)    { return this.STAGE_ORDER.indexOf(this.stage) > i; },
isActive(i)  { return this.STAGE_ORDER.indexOf(this.stage) === i && this.stage !== 'error'; },
isFailed(i)  { return this.stage === 'error' && this.STAGE_ORDER.indexOf(this.stage) === i; },
isPending(i) { return this.STAGE_ORDER.indexOf(this.stage) < i; },
```

### Progress bar (Alpine bind:style)

```html
<div class="h-[4px] w-full bg-white/10 relative overflow-hidden">
  <div class="absolute inset-y-0 left-0 transition-all duration-700"
       :style="`width: ${progress}%; background: ${progress === 100 ? 'var(--green)' : 'linear-gradient(90deg, var(--amber), var(--cyan))'}`">
  </div>
</div>
```

### History table row (Alpine x-for)

```html
<tr class="border-b border-white/8 hover:bg-white/[0.02] transition-colors">
  <td class="py-2 px-3 font-mono text-xs text-white/40" x-text="formatDate(job.created_at)"></td>
  <td class="py-2 px-3 font-mono text-xs text-[#00F5FF] uppercase" x-text="job.turbine_id || '—'"></td>
  <td class="py-2 px-3 text-sm" x-text="job.site_name || '—'"></td>
  <td class="py-2 px-3">
    <span class="font-mono text-xs px-2 py-0.5 border"
          :class="{
            'text-[#00FF88] border-[#00FF88]/30 bg-[#00FF88]/10': job.stage === 'complete',
            'text-[#FF006E] border-[#FF006E]/30 bg-[#FF006E]/10': job.stage === 'error',
            'text-[#FFB800] border-[#FFB800]/30 bg-[#FFB800]/10 pulse': job.stage !== 'complete' && job.stage !== 'error',
          }"
          x-text="job.stage === 'complete' ? 'COMPLETE' : job.stage === 'error' ? 'FAILED' : 'RUNNING'">
    </span>
  </td>
  <td class="py-2 px-3 font-mono text-xs" x-text="job.defect_count ?? '—'"></td>
  <td class="py-2 px-3 font-mono text-xs" x-text="job.total_cost_usd ? '$' + job.total_cost_usd : '—'"></td>
  <td class="py-2 px-3">
    <button class="action-btn sm" :disabled="job.stage !== 'complete'"
            @click="downloadReport(job.job_id)"
            x-text="'⬇ PDF'">
    </button>
  </td>
</tr>
```

### Expandable section header

```html
<div class="flex items-center gap-3 cursor-pointer select-none mb-3"
     @click="sections.identity = !sections.identity">
  <div class="h-px flex-1 bg-[#00F5FF]/20"></div>
  <span class="font-mono text-xs text-[#00F5FF]/70 uppercase tracking-widest">TURBINE IDENTITY</span>
  <div class="h-px flex-1 bg-[#00F5FF]/20"></div>
  <span class="font-mono text-xs text-white/30" x-text="sections.identity ? '▼' : '▶'"></span>
</div>
<div x-show="sections.identity" x-transition>
  <!-- fields -->
</div>
```

### File drop zone state

```html
<div class="drop-zone border-2 border-dashed transition-colors"
     :class="fileSelected ? 'border-[#00FF88] bg-[#00FF88]/5' : 'border-white/10 bg-white/3'"
     @dragover.prevent="$el.classList.add('drag-over')"
     @dragleave="$el.classList.remove('drag-over')"
     @drop.prevent="handleDrop($event)">
  <input type="file" name="images" id="fileInput" accept=".zip,.jpg,.jpeg,.png"
         class="absolute inset-0 opacity-0 cursor-pointer"
         @change="handleFileChange($event)">
  <template x-if="!fileSelected">
    <div class="text-center py-8 pointer-events-none">
      <div class="text-2xl mb-2">📁</div>
      <div class="font-mono text-xs text-white/40 uppercase tracking-wider">DROP ZIP OR CLICK TO SELECT</div>
    </div>
  </template>
  <template x-if="fileSelected">
    <div class="flex items-center gap-3 py-4 px-4 pointer-events-none">
      <span class="text-[#00FF88] font-mono text-sm">✓</span>
      <div>
        <div class="font-mono text-sm text-[#00FF88]" x-text="fileName"></div>
        <div class="font-mono text-xs text-white/30" x-text="fileSize"></div>
      </div>
    </div>
  </template>
</div>
```

### Celebration / complete state

```html
<div x-show="stage === 'complete'" x-transition class="mt-4 space-y-3">
  <div class="font-mono text-xs text-[#00FF88] tracking-widest uppercase pulse text-center py-2 border border-[#00FF88]/30 bg-[#00FF88]/10">
    ✓ INSPECTION COMPLETE
  </div>
  <button class="action-btn w-full justify-center" @click="downloadReport(jobId)">
    ⬇ DOWNLOAD REPORT PDF
  </button>
  <label class="flex items-center gap-2 font-mono text-xs text-white/40 cursor-pointer mt-2">
    <input type="checkbox" x-model="autoRedirect" class="accent-[#00F5FF]">
    AUTO-REDIRECT TO HISTORY
  </label>
  <div x-show="autoRedirect" class="font-mono text-xs text-white/30 text-center"
       x-text="'Redirecting in ' + countdown + 's…'">
  </div>
</div>
```

---

## API Response Shape (for Alpine component)

### `GET /api/status/{job_id}`
```json
{
  "job_id": "...",
  "stage": "triaging",
  "message": "Processing images...",
  "progress": 25,
  "total_images": 63,
  "flagged_images": 18,
  "critical_findings": 3,
  "created_at": "2026-04-18T14:30:00",
  "completed_at": null,
  "error": null,
  "triage_cost_usd": "0.42",
  "classify_cost_usd": null,
  "analyze_cost_usd": null,
  "total_cost_usd": null
}
```

Stage values: `queued`, `ingesting`, `triaging`, `classifying`, `analyzing`, `generating_report`, `complete`, `error`, `failed`, `cost_limit_exceeded`

Progress values: `0` (queued), `10` (ingesting), `25` (triaging), `50` (classifying), `70` (analyzing), `85` (generating_report), `100` (complete), `-1` (error/failed)

### `GET /api/jobs`
Array of job objects. Fields available: `job_id`, `stage`, `turbine_id`, `site_name`, `created_at`, `completed_at`, `total_cost_usd`. Field `defect_count` (critical_findings) may be null for non-complete jobs.

---

## File Plan (what gets rewritten)

| File | Strategy |
|------|----------|
| `frontend/login.html` | Full rewrite — Cyber Operator, Alpine.js `loginApp()` |
| `frontend/index.html` | Full rewrite — Cyber Operator layout, Alpine.js `app()` |
| `frontend/style.css` | Full rewrite — CSS variables, keyframes, non-Tailwind classes |
| `frontend/app.js` | Full rewrite — all logic moves into Alpine component functions in `index.html` inline script; `app.js` retained for any global utilities |

**Backend:** No changes. FastAPI serves `frontend/` as static files unchanged.

---

## Confidence Levels

| Claim | Confidence | Source |
|-------|-----------|--------|
| Tailwind Play CDN URL `cdn.tailwindcss.com` | High | Official Tailwind docs |
| Alpine v3 CDN must use `defer` | High | Official Alpine docs |
| `@apply` not supported in Play CDN | High | Official Tailwind Play CDN docs |
| Dynamic class strings not scanned by Play CDN | High | Known Tailwind CDN limitation |
| `URLSearchParams` required for FastAPI OAuth2 form | High | Verified in existing `login.html` + backend code |
| Download endpoint needs blob fetch workaround | High | Backend uses `Depends(get_current_user)` on `/api/download` — direct `<a href>` won't have auth header |
| `/api/jobs` and `/api/status` also need Bearer | High | Verified in `api.py` — both use `Depends(get_current_user)` |
| Alpine underscore properties non-reactive | High | Alpine v3 docs |
| `x-cloak` prevents FOUC | High | Alpine docs |
