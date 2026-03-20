# Codebase Concerns

**Analysis Date:** 2026-03-03

---

## In-Memory Job State (Partial Persistence Risk)

**Job state in `_jobs` dict:**
- Files: `backend/api.py` lines 53, 56–79
- Issue: `_jobs: Dict[str, Dict]` is an in-process Python dict. On Render's free tier, the process restarts when the service spins down after inactivity (typically 15 minutes). The in-memory cache is cleared.
- Mitigation in place: `get_job()` falls back to reading `jobs/<id>/state.json` from disk, so jobs that completed before spin-down can be recovered — but only if the disk is still there.
- Remaining risk: Any job that was in-progress when the process died (stage: `triaging`, `classifying`, etc.) will be stuck in that stage forever in the state.json. There is no recovery path: the background thread is gone, the state file says "triaging", and polling will return that stale state indefinitely.
- Fix approach: Add a startup scan that marks any non-terminal `state.json` as `error` with message "Server restarted during processing". Alternatively add a proper job queue (Celery, ARQ, or similar).

---

## Render Free Tier: Ephemeral Disk and Spin-Down

**Deployment config:**
- File: `render.yaml`
- Issue 1 — Spin-down: Render free web services stop after ~15 minutes of inactivity. Cold start takes 30–60 seconds. A pipeline that was running when the service span down is silently killed.
- Issue 2 — Ephemeral disk: Render free tier has no persistent disk. The `jobs/` directory (uploaded images, triage/classify/analyze JSON, generated PDFs) lives on the container's ephemeral filesystem. Every new deploy wipes all jobs and reports. Users cannot retrieve a PDF after a redeploy.
- Issue 3 — No disk size guard: Large ZIP uploads accumulate in `jobs/` with no cleanup. A few large turbine inspection sets (500 images × ~15 MB each ≈ 7.5 GB) would fill the container and crash the process.
- Fix approach: Use an object storage bucket (S3/R2/GCS) for uploaded images and generated PDFs. Store job metadata in a persistent database (PostgreSQL, Redis). Add a periodic cleanup job for old `jobs/` directories.

---

## No Authentication or Authorization

**Upload and status endpoints:**
- Files: `backend/api.py` lines 286–491
- Issue: All endpoints (`/api/upload`, `/api/status/{job_id}`, `/api/download/{job_id}`, `/api/jobs`, `/api/debug/kimi`) are publicly accessible with no authentication.
- `/api/upload` allows any anonymous user to trigger a full AI pipeline run, burning API credits (Kimi, Gemini, Claude) at ~$11.50 per turbine job.
- `/api/jobs` lists all jobs ever run, exposing client turbine IDs and inspection metadata to anyone who queries the endpoint.
- `/api/debug/kimi` is a live diagnostic endpoint that reveals whether a Kimi API key is configured and makes a real API call — left open in production.
- CORS is set to `allow_origins=["*"]` (`api.py` line 37), which allows any web origin to call the API.
- Fix approach: Add API key authentication (header-based) as a minimum. Restrict CORS to known origins. Remove or protect `/api/debug/kimi` behind an admin check. Rate-limit `/api/upload` per IP.

---

## No Job Queue — Background Tasks Can Pile Up

**Pipeline execution:**
- Files: `backend/api.py` line 351
- Issue: FastAPI's `BackgroundTasks` runs pipeline stages in a thread pool with no concurrency limit. Each job runs `run_pipeline()` which is synchronous and CPU/IO-bound (image tiling, multiple sequential API calls). If multiple jobs are submitted simultaneously, they all run concurrently in threads.
- A single job on 500 images can take 20–40+ minutes (500 images × 0.5s delay = 4+ minutes for triage alone, plus classify at 2s/image × 80 images = 2.7 minutes). Multiple concurrent jobs multiply this.
- There is no max job limit, no queue depth limit, and no way to cancel a running job.
- Fix approach: Use a proper task queue (Celery with Redis, ARQ, or RQ). Limit concurrent pipeline runs to 1–2. Expose a cancel endpoint.

---

## API Rate Limits and Sequential Processing

**Triage (Kimi) — `backend/triage.py`:**
- Issue: `triage_batch()` processes images sequentially with a fixed `delay_between_calls=0.5` seconds. For 500 images, this is at minimum 250 seconds of deliberate sleep alone, not counting API latency. There is no dynamic rate limit handling — if Kimi returns a 429, the retry logic uses a fixed `time.sleep(2 ** attempt)` up to `2^2 = 4` seconds, which may not be sufficient for Kimi quota windows.
- Each image sends 8 tiles as inline base64 in a single request, which is large. 500 images × 8 tiles is 4,000 tile uploads.

**Classify (Gemini) — `backend/classify.py`:**
- Issue: `classify_batch()` processes images sequentially at `delay_between_calls=2.0` seconds. The batch is hard-capped at 80 images in `api.py` line 171. On a 429 from Gemini, the backoff is `time.sleep(30)` (line 203), which is a single flat delay with no exponential growth and no jitter — risky under sustained quota pressure.
- Each classification call loads the full raw JPEG into memory and sends it as base64 (`classify.py` lines 147–149). A 45MP DJI P1 image can be 20–40 MB. Holding 80 images' worth of data in memory during a batch is a significant memory load.

**Analyze (Claude) — `backend/analyze.py`:**
- Issue: `analyze_critical_defects()` uses `delay_between_calls=3.0` seconds. The `anthropic.RateLimitError` handler in `call_claude_analyze()` sleeps a flat 30 seconds (line 187) and does not retry — it falls through to the next `attempt` iteration but the retry loop has already exited if it was on the last attempt.

**Fix approach:** Implement async/concurrent calls with a semaphore to limit parallelism (e.g., `asyncio.Semaphore(5)`). Use true exponential backoff with jitter for all three providers. Consider streaming or chunked processing to reduce peak memory use.

---

## PDF Generation: xhtml2pdf Limitations

**Report generation:**
- Files: `backend/report.py` lines 302–331
- Issue: The primary PDF renderer is `xhtml2pdf` (pure Python, no system deps). xhtml2pdf has known significant CSS limitations compared to WeasyPrint: no CSS flexbox, no CSS grid, limited float support, no `@page` margin boxes, no CSS counters. Complex multi-page reports with the current styling may render poorly — misaligned tables, broken page breaks, missing styles.
- WeasyPrint (the higher-quality fallback) requires system GTK/Pango/Cairo libraries which are not available on Render free tier without a custom Docker image. The `render.yaml` uses the default Python runtime with no system package installation step, so WeasyPrint will always fail on Render even if imported.
- The `requirements.txt` pins `python-bidi==0.4.2` specifically because `0.5+` requires a Rust build — this is a fragile dependency workaround that may break as the package evolves.
- Fix approach: Either invest in making WeasyPrint work (custom Dockerfile with `apt-get install libpango1.0-dev`) or accept xhtml2pdf and redesign the report template to avoid unsupported CSS features. Consider headless Chromium (Playwright/Puppeteer) for highest-fidelity PDF output.

---

## Error Recovery: No Mid-Pipeline Resume

**Pipeline stages:**
- Files: `backend/api.py` lines 88–256
- Issue: The pipeline is a single long try/except block. If any stage fails, the entire job moves to `stage="error"`. There is no checkpoint or resume mechanism. A failure at Stage 4 (report generation) after spending $11 on API calls produces no recoverable output.
- Specific fragile points:
  - If triage succeeds but `triage.json` is written and the process is killed before classify starts, a restart cannot resume from the classify stage.
  - If classify partially completes (e.g., 40/80 images) before a crash, `classify.json` is only written after the full batch completes (`save_classify_results` is called once at the end of `classify_batch`). Partial results are lost.
  - The analyze stage writes `analyze.json` the same way — atomic at the end.
- Fix approach: Write intermediate results to disk after each image (not batch). Add a `resume_pipeline()` function that reads existing stage files and skips completed stages.

---

## Image Storage: Ephemeral Disk, No Cleanup

**File handling:**
- Files: `backend/api.py` lines 261–281, 44–48
- Issue: Uploaded ZIPs are extracted to `jobs/<job_id>/images/` on the local filesystem. Original ZIPs are deleted after extraction (`zip_path.unlink()`, line 273), but all extracted images remain permanently until the job is deleted via `DELETE /api/jobs/{job_id}`.
- There is no automatic cleanup of old jobs. No TTL, no cron, no disk usage monitoring.
- The upload endpoint reads the entire file into memory (`content = upload_file.file.read()`, line 265) before writing to disk. A 500-image ZIP could easily be 500 MB–2 GB, held entirely in memory during upload.
- There is no upload size limit enforced in the API. FastAPI's default is unlimited. An attacker or accidental oversized upload could OOM the process.
- Fix approach: Add `max_upload_size` middleware. Stream the upload to disk instead of reading into memory. Add a job TTL (e.g., 7 days) with a background cleanup task. Move images to object storage post-extraction.

---

## No Job History Persistence

**Job listing:**
- Files: `backend/api.py` lines 465–482
- Issue: `/api/jobs` reads `jobs/*/state.json` files directly from disk and returns the last 20 by file modification time. On Render, every deploy wipes the filesystem, so all job history is lost on each deploy. There is no database, no audit log, no way to retrieve historical reports.
- Turbine inspection reports have long-term archival value (regulatory requirements, maintenance records). Storing them only on ephemeral disk is not appropriate for production use.
- Fix approach: Store job metadata in PostgreSQL (Render offers a free PostgreSQL addon). Store generated PDFs in object storage. Use the database for job history queries.

---

## No Retry Logic for Failed Pipeline Stages

**Error handling:**
- Files: `backend/api.py` lines 248–256
- Issue: When the pipeline catches an exception, it sets `stage="error"` and saves the traceback. There is no automatic retry, no partial-success handling, and no way for a user to re-trigger a failed job.
- If the failure was transient (network timeout, rate limit), the user must re-upload the entire ZIP and restart from scratch.
- Fix approach: Add a `POST /api/jobs/{job_id}/retry` endpoint that reads the existing stage files and re-runs from the failed stage. This is only viable after fixing the mid-pipeline resume concern above.

---

## Hard-Coded Caps Without User Feedback

**Image processing limits:**
- Files: `backend/api.py` lines 128, 171
- Issue: When `KIMI_API_KEY` is absent, triage is skipped and only the first 50 images are treated as flagged (`images[:50]`). When classify runs, it hard-caps at 80 images (`flagged[:80]`). These caps are silent — the API response and job status do not communicate that images were dropped.
- A user who uploads 300 flagged images will receive a report covering only 80 of them with no warning. This could result in critical defects being missed in uninspected images.
- Fix approach: Expose `images_skipped` and `classify_cap_applied` fields in the job status response. Surface this information clearly in the report.

---

## Debug Endpoint Left Open in Production

**Kimi debug endpoint:**
- Files: `backend/api.py` lines 390–439
- Issue: `GET /api/debug/kimi` makes a live Kimi API call and returns the full raw API response, parse status, and error tracebacks in a public JSON endpoint. It reveals: whether `KIMI_API_KEY` is configured, the exact model name in use, and detailed error messages if the key is invalid.
- This endpoint was added for deployment debugging and was never removed or restricted.
- Fix approach: Remove from production or guard with an internal-only token check.

---

## Dependencies at Risk

**`python-bidi==0.4.2`:**
- Files: `requirements.txt` line 20
- Risk: Pinned to a specific old version to avoid a Rust build requirement in `0.5+`. The upstream package `python-bidi` continues evolving. This pin may become incompatible with future Python versions or security patches may require upgrading past `0.4.2`.
- Impact: Breaks PDF generation if the pin ever becomes incompatible.
- Migration plan: Either vendor the `0.4.2` wheel directly or set up a custom build environment that supports Rust (which would also unblock WeasyPrint).

**`google-generativeai>=0.8.0`:**
- Risk: The `google-generativeai` package has been deprecated in favor of `google-genai` (the new unified SDK). The `>=0.8.0` range may pull in a version that produces deprecation warnings or behaves differently than tested. Gemini model names (currently `gemini-2.5-pro-preview-06-05` in `classify.py` line 128) are preview models that expire on short notice.
- Fix approach: Pin the Gemini model name to a stable GA model. Monitor Google's deprecation notices for the SDK.

---

## Test Coverage Gaps

**No tests detected:**
- No test files found in the repository (`*.test.py`, `test_*.py`, `tests/` directory).
- The entire pipeline — triage, classify, analyze, report generation — has zero automated test coverage.
- Risk: Any refactor or dependency update can silently break the pipeline. The only validation is a manual end-to-end run.
- Priority: High — especially for `report.py`'s `build_report_data()` logic which contains non-trivial data assembly, and for the JSON parse/clean logic in all three API clients which has demonstrated fragility (markdown fence stripping, non-object response handling).
- Fix approach: Add unit tests for `build_report_data()`, the triage/classify/analyze JSON parsing functions, and the `extract_upload()` helper. Add an integration test using the `make_sample_*` fixtures already defined in `report.py`.

---

*Concerns audit: 2026-03-03*
