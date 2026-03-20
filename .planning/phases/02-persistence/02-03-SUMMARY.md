---
phase: 02-persistence
plan: "03"
subsystem: deploy-config
tags: [render, persistent-disk, env-vars, cleanup]
dependency_graph:
  requires: []
  provides: [render-persistent-disk-config, cost-limit-env-var]
  affects: [render.yaml]
tech_stack:
  added: []
  patterns: [render-persistent-disk, mount-path-convention]
key_files:
  created: []
  modified:
    - render.yaml
key_decisions:
  - "Persistent disk: 1GB at /data, name bdda-data — matches DATA_DIR default in database.py"
  - "GOOGLE_API_KEY and KIMI_API_KEY removed from render.yaml (Phase 1 cleanup)"
  - "COST_LIMIT_USD added to render.yaml env vars (was missing despite Phase 1 implementing it)"
  - "Prominent comment block added: paid Starter tier required ($7/month) for persistent disk"
metrics:
  duration: "2 minutes"
  completed: "2026-03-06T01:50:00Z"
  tasks_completed: 1
  tasks_total: 1
  files_modified: 1
---

# Phase 2 Plan 3: render.yaml Persistent Disk Config Summary

**One-liner:** Added Render Persistent Disk block (1GB at /data), removed stale GOOGLE_API_KEY and KIMI_API_KEY, added COST_LIMIT_USD, and surfaced the paid-tier requirement as an explicit comment block.

---

## What Was Built

Updated `render.yaml` with three targeted changes completing PERS-04:

### 1. Persistent Disk Block

Added `disk:` block under the web service definition:

```yaml
disk:
  name: bdda-data
  mountPath: /data
  sizeGB: 1
```

The `mountPath: /data` matches exactly the `DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))` default in `database.py`. No `DATA_DIR` env var is needed in render.yaml — the default is correct.

### 2. Env Var Cleanup

- Removed `GOOGLE_API_KEY` — removed from pipeline in Phase 1 (Plan 01-04)
- Removed `KIMI_API_KEY` — removed from pipeline in Phase 1 (Plan 01-04)
- Added `COST_LIMIT_USD` — implemented in Phase 1 but accidentally omitted from render.yaml

### 3. Paid-Tier Comment Block

Added a 8-line comment at the top of the file:

```
# IMPORTANT: Persistent disk requires a paid web service instance.
# Minimum: Starter tier ($7/month). Free tier has ephemeral filesystem — data
# is wiped on every restart/redeploy. Upgrade the web service to Starter or
# higher before deploying with this disk config.
# Disk cost: $0.25/GB/month ($0.25/month for 1GB).
# Total cost with Starter tier: ~$7.25/month.
# Zero-downtime deploys are NOT available when a persistent disk is attached
# (Render limitation). Brief downtime during redeploy is expected and acceptable.
```

---

## Verification Results

All verification checks passed:

```
grep -n "mountPath\|sizeGB\|bdda-data" render.yaml
# 19:      name: bdda-data
# 20:      mountPath: /data
# 21:      sizeGB: 1

grep -n "GOOGLE_API_KEY\|KIMI_API_KEY" render.yaml || echo "Stale keys removed — OK"
# Stale keys removed — OK

grep -n "COST_LIMIT_USD" render.yaml
# 25:      - key: COST_LIMIT_USD

grep -n "ANTHROPIC_API_KEY" render.yaml
# 23:      - key: ANTHROPIC_API_KEY

python3 text checks passed
```

---

## Deviations from Plan

None — plan executed exactly as written. The new render.yaml content matched the template provided in the plan verbatim.

---

## Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Update render.yaml with persistent disk config | 33ce8ff | render.yaml |

---

## Self-Check: PASSED

- [x] `render.yaml` exists and contains `mountPath: /data`
- [x] `render.yaml` contains `sizeGB: 1`
- [x] `render.yaml` contains `bdda-data` disk name
- [x] `GOOGLE_API_KEY` not in render.yaml
- [x] `KIMI_API_KEY` not in render.yaml
- [x] `COST_LIMIT_USD` present in render.yaml
- [x] `ANTHROPIC_API_KEY` retained in render.yaml
- [x] Paid-tier comment block visible at top of file
- [x] Commit `33ce8ff` present in git log
