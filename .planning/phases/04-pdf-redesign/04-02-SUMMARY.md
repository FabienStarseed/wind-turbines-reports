---
phase: 04-pdf-redesign
plan: 02
subsystem: api
tags: [pillow, image-processing, pipeline, thumbnails, pdf]

requires:
  - phase: 04-01
    provides: fpdf2 foundation, font assets, BDDAReport class skeleton

provides:
  - Thumbnail copies of flagged defect images saved in job_dir/thumbnails/ (1568px JPEG, quality=85)
  - Classify stage receives thumbnail paths — originals no longer referenced
  - PDF report (Plan 03) can embed defect images from thumbnail paths

affects:
  - 04-03-pdf-generation (reads image paths from classify.json — must see thumbnail paths)
  - backend/classify.py (reads from flagged["path"] — now points to thumbnails/)
  - backend/report.py (PDF-03 image embedding reads classify.json image_path values)

tech-stack:
  added: []
  patterns:
    - "Thumbnail-before-delete: save compressed copies before shutil.rmtree, rewrite paths in-flight"
    - "Fallback copy: if PIL thumbnail fails, shutil.copy2 original as safety net"

key-files:
  created: []
  modified:
    - backend/api.py

key-decisions:
  - "Thumbnail at 1568px max edge (matches Anthropic vision limit used by classify.py already)"
  - "JPEG quality=85 for thumbnails — balances PDF image quality vs disk footprint (~150KB each)"
  - "Set-based deduplication of flagged_paths avoids saving duplicates if same image flagged twice"
  - "Path rewriting done in-place on flagged list before classify_batch — classify.json records thumbnail paths"
  - "Thumbnail dir uses exist_ok=True — safe on retry if pipeline partially ran"

patterns-established:
  - "Thumbnail-before-delete pattern: create thumbnails_dir, save copies, delete originals, rewrite paths — all within run_pipeline() before classify stage"

requirements-completed:
  - PDF-03

duration: 5min
completed: 2026-03-08
---

# Phase 4 Plan 02: Image Pipeline Fix Summary

**Thumbnail copies of all flagged defect images saved to job_dir/thumbnails/ before raw image deletion, with path rewriting ensuring classify.json records thumbnail paths for PDF-03 embedding.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-08T03:42:13Z
- **Completed:** 2026-03-08T03:47:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Added `from PIL import Image` at module level in api.py (previously only used locally in debug_ai())
- Created thumbnail saving block: iterates flagged image paths, opens with PIL, resizes to 1568px max edge, saves as JPEG quality=85 to job_dir/thumbnails/
- Fallback: if PIL thumbnail creation fails for any image, copies the original file as-is
- Rewrites flagged list path entries to point at thumbnail copies immediately after saving them
- Classify stage and PDF report now receive valid file paths — defect images survive the pipeline

## Task Commits

Each task was committed atomically:

1. **Task 1: Save thumbnail copies of flagged images before deletion and fix classify paths** - `b79181e` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `backend/api.py` - Added PIL import, thumbnail saving block, path rewriting in run_pipeline()

## Decisions Made
- Thumbnail size: 1568px max edge — this already matches `classify.py`'s `load_and_resize_image()` limit so classify reads the thumbnail at a size it would have resized to anyway, no quality loss.
- JPEG quality=85 — same as classify.py's load_and_resize_image() default; consistent across pipeline.
- Thumbnail saving uses set-based deduplication (`flagged_paths = {str(r.image_path) for r in ...}`) to avoid saving the same file twice if a path appears in multiple triage results.
- Path rewriting loop placed immediately after flagged list construction, before the `classify_batch()` call, so the cap (`flagged[:80]`) already uses thumbnail paths.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan 02 fix is a prerequisite for Plan 03 (PDF defect pages with embedded images)
- classify.json will now record `image_path` values pointing to `job_dir/thumbnails/` which exist on disk
- Report.py Plan 03 can safely call `Path(image_path).exists()` and get `True` for defect images
- Concern: `debug_ai()` function still has `from PIL import Image as PILImage` locally — redundant but harmless (not in scope to clean up)

## Self-Check: PASSED

- FOUND: .planning/phases/04-pdf-redesign/04-02-SUMMARY.md
- FOUND: backend/api.py
- FOUND commit: b79181e

---
*Phase: 04-pdf-redesign*
*Completed: 2026-03-08*
