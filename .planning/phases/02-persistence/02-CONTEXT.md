---
phase: 02-persistence
created: 2026-03-05
status: ready-for-planning
areas_discussed:
  - job-history-behaviour
  - file-storage-layout
  - render-disk-sizing
---

# Phase 2 Context — Persistence

Decisions gathered from user discussion. Downstream agents (researcher, planner) must follow these exactly — do not re-ask.

---

## Area A: Job history behaviour

### Locked decisions
- **Retention window**: Show jobs from the **last 30 days** only. Jobs older than 30 days are not shown in history (but their records stay in SQLite — just filtered from the UI query).
- **Interrupted jobs**: If a job was in-progress (stage = "triaging", "classifying", "analyzing") when Render restarted, mark it as **stage = "failed"** with `stage_message = "Job interrupted by server restart"` on startup. Do not silently drop them.
- **Manual delete**: Users can delete a job from history. Deleting removes the SQLite row AND all files in `/data/jobs/{job_id}/`. This is the same as the "files expired" cleanup flow.
- **Scale**: ~50 jobs/month expected. No pagination required in Phase 2. Simple list is fine.

### Implementation notes
- On app startup, scan SQLite for jobs with stage not in ("complete", "error", "failed") and update them to stage="failed" with the restart message.
- The `/api/jobs` endpoint filters by `created_at >= now - 30 days`.
- DELETE endpoint removes DB row + job directory recursively.

---

## Area B: File storage layout & cleanup

### Locked decisions
- **Raw uploaded images**: **Deleted immediately** after the triage stage completes. Do not keep originals — they are 15-30MB each (DJI P1) and would exhaust disk quickly.
- **Intermediate AI outputs** (triage.json, classify.json, analyze.json): **Kept permanently** alongside the PDF. User can delete via the manual delete button.
- **PDF report**: **Kept permanently**, re-downloadable at any time via `/api/download/{job_id}`.
- **Files expired state**: If a job's files are deleted (manual delete), the job row is also deleted from SQLite. It disappears from history. If files are missing but the row exists (edge case), show status as `"files_expired"`.

### Storage layout
```
/data/
├── bdda.db                          # SQLite database
└── jobs/
    └── {job_id}/
        ├── triage.json              # Kept
        ├── classify.json            # Kept
        ├── analyze.json             # Kept
        ├── report.pdf               # Kept — re-downloadable
        └── errors.json              # Kept (if any)
        # NOTE: uploaded images deleted after triage completes
```

### Implementation notes
- After `save_triage_results()` succeeds in `run_pipeline()`, delete all image files from the upload staging area.
- The job directory at `/data/jobs/{job_id}/` is created at job start and persists until manual delete.
- `/api/download/{job_id}` serves `report.pdf` from `/data/jobs/{job_id}/report.pdf`.

---

## Area D: Render Persistent Disk

### Locked decisions
- **Disk size**: Start at **1GB** ($1/month). Upgrade to larger size when going live with clients. No migration needed — Render allows online resize.
- **Render instance tier**: Stay on free tier for now (spins down after 15min inactivity, ~30s cold start). Upgrade to paid instance later — that's a separate decision from the disk.
- **Mount path**: `/data` (Render standard). SQLite at `/data/bdda.db`, jobs at `/data/jobs/`.
- **Disk full behaviour**: **Refuse new jobs** with HTTP 507 (Insufficient Storage) and a clear message: "Server storage full — please contact the administrator." Do NOT auto-delete old jobs silently.
- **Local dev fallback**: When `RENDER_PERSISTENT_DISK` env var is not set (local dev), use `./data/` relative to the backend directory. This avoids breaking local development.

### render.yaml disk config
```yaml
services:
  - type: web
    name: bdda
    disk:
      name: bdda-data
      mountPath: /data
      sizeGB: 1
```

### Implementation notes
- `DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))` — override with `DATA_DIR=./data` in local `.env`.
- Check available disk space before accepting an upload: `shutil.disk_usage(DATA_DIR).free`. If < 100MB free, return 507.
- SQLAlchemy with sync SQLite driver (`sqlite:///...`) — no async driver needed for Phase 2, consistent with project pattern (sync + SQLite per CLAUDE.md).

---

## Deferred ideas (do not implement in Phase 2)
- **Automatic cleanup of jobs older than 30 days from disk** — noted, deferred to a later phase or maintenance script
- **External storage (S3, R2, Cloudflare)** — noted for future scale; start with Render disk
- **Disk usage dashboard** — deferred to Phase 5 UI
- **Email notifications on job complete** — deferred

---

## Migration strategy (in-memory → SQLite)

- **Clean break**: No backward compatibility with the in-memory `_jobs` dict. Phase 2 replaces it entirely.
- On first deploy with persistent disk, existing in-memory jobs are lost (expected — they don't survive restarts anyway).
- The `_jobs: Dict[str, dict]` global in `api.py` is removed entirely and replaced with SQLAlchemy calls.
- No data migration script needed — starting fresh is the correct approach.
