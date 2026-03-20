"""
api.py — FastAPI backend for BDDA web interface
Endpoints: /upload, /status/{job_id}, /download/{job_id}

Full pipeline per job:
  Upload ZIP/images → ingest → triage → classify → analyze → report PDF
"""

import asyncio
import json
import os
import shutil
import time
import traceback
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select, update as sa_update

from auth import get_current_user, create_token, verify_password, hash_password
from database import (
    DATA_DIR, JOBS_DIR, init_db, get_db,
    get_job, save_new_job, update_job, set_stage,
    list_jobs_last_30_days, Job,
    get_user_by_username, create_user, _seed_admin_user,
    User,
)

# ─── PATHS ────────────────────────────────────────────────────────────────────

# DATA_DIR and JOBS_DIR imported from database.py
# FRONTEND_DIR is relative to this file
BASE_DIR = Path(__file__).parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

# ─── CONFIG ───────────────────────────────────────────────────────────────────

ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "")

# ─── COST ESTIMATION ──────────────────────────────────────────────────────────

INPUT_PRICE  = 5.0 / 1_000_000   # $ per token, claude-opus-4-6
OUTPUT_PRICE = 25.0 / 1_000_000  # $ per token, claude-opus-4-6


def estimate_cost(image_count: int) -> dict:
    """Conservative pre-run cost estimate before pipeline starts."""
    TOKENS_PER_TILE     = 1600
    TILES_PER_IMAGE     = 4
    TRIAGE_OUT_EST      = 80
    CLASSIFY_IN_EST     = 1600
    CLASSIFY_OUT_EST    = 500
    ANALYZE_IN_EST      = 1600
    ANALYZE_OUT_EST     = 600
    flagged_est         = int(image_count * 0.30)
    critical_est        = int(flagged_est * 0.20)

    triage_in   = image_count * TILES_PER_IMAGE * TOKENS_PER_TILE
    triage_out  = image_count * TRIAGE_OUT_EST
    classify_in = flagged_est * CLASSIFY_IN_EST
    classify_out = flagged_est * CLASSIFY_OUT_EST
    analyze_in  = critical_est * ANALYZE_IN_EST
    analyze_out = critical_est * ANALYZE_OUT_EST

    total_in  = triage_in + classify_in + analyze_in
    total_out = triage_out + classify_out + analyze_out
    total_usd = total_in * INPUT_PRICE + total_out * OUTPUT_PRICE

    return {
        "image_count": image_count,
        "flagged_estimate": flagged_est,
        "critical_estimate": critical_est,
        "estimated_cost_usd": round(total_usd, 2),
        "breakdown": {
            "triage_usd": round(triage_in * INPUT_PRICE + triage_out * OUTPUT_PRICE, 2),
            "classify_usd": round(classify_in * INPUT_PRICE + classify_out * OUTPUT_PRICE, 2),
            "analyze_usd": round(analyze_in * INPUT_PRICE + analyze_out * OUTPUT_PRICE, 2),
        },
    }


# ─── LIFESPAN ─────────────────────────────────────────────────────────────────

INTERRUPTED_STAGES = {"triaging", "classifying", "analyzing", "ingesting", "generating_report", "queued"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — order matters:
    # 1. init_db() creates tables (users + jobs) if they don't exist
    # 2. migrate_schema() adds owner_id column to existing jobs table
    # 3. _seed_admin_user() seeds admin user if users table is empty
    # 4. _mark_interrupted_jobs_failed() recovers in-progress jobs from before restart
    from database import migrate_schema
    init_db()
    migrate_schema()
    _seed_admin_user()
    _mark_interrupted_jobs_failed()
    yield
    # Shutdown — nothing needed


def _mark_interrupted_jobs_failed():
    """On restart, mark any in-progress jobs as failed (per CONTEXT.md Area A)."""
    with get_db() as session:
        stmt = (
            sa_update(Job)
            .where(Job.stage.in_(INTERRUPTED_STAGES))
            .values(
                stage="failed",
                stage_message="Job interrupted by server restart",
            )
        )
        session.execute(stmt)
        session.commit()


# ─── APP SETUP ────────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {".zip", ".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="BDDA — Blade Defect Detection Agent",
    description="AI-powered wind turbine drone inspection analysis",
    version="2.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def attach_new_token_header(request: Request, call_next):
    """Read request.state.new_token (set by get_current_user when <1h remaining)
    and attach it as X-New-Token response header for the frontend to store.
    """
    response = await call_next(request)
    new_token = getattr(request.state, "new_token", None)
    if new_token:
        response.headers["X-New-Token"] = new_token
    return response


ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:8000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["POST", "GET", "DELETE"],
    allow_headers=["*"],
    expose_headers=["X-New-Token"],  # required so browser JS can read this header
)

# ─── DISK SPACE GUARD ─────────────────────────────────────────────────────────


def check_disk_space():
    """Refuse uploads if less than 100MB free on the data disk (per CONTEXT.md Area D)."""
    usage = shutil.disk_usage(DATA_DIR)
    free_mb = usage.free / (1024 * 1024)
    if free_mb < 100:
        raise HTTPException(
            status_code=507,
            detail="Server storage full — please contact the administrator.",
        )


# ─── PIPELINE ─────────────────────────────────────────────────────────────────

def run_pipeline(job_id: str, job_dir: Path, turbine_meta: Dict):
    """Run the full 4-stage pipeline synchronously (called in background thread)."""
    try:
        # Import pipeline modules
        import sys
        sys.path.insert(0, str(BASE_DIR / "backend"))
        from ingest import ingest_turbine_folder, get_all_images_flat
        from triage import triage_batch, save_triage_results
        from classify import classify_batch, save_classify_results, load_critical_findings
        from analyze import analyze_critical_defects, save_analysis_results

        images_dir = job_dir / "images"

        # ── Stage 1: Ingest ──
        set_stage(job_id, "ingesting", "Parsing DJI folder structure...")

        # If the ZIP contained a single top-level wrapper folder (e.g. JAP19_test/),
        # unwrap it so ingest sees the DJI mission folders directly.
        subdirs = [d for d in images_dir.iterdir() if d.is_dir()]
        if len(subdirs) == 1 and not any(images_dir.glob("DJI_*")):
            scan_dir = subdirs[0]
        else:
            scan_dir = images_dir

        result = ingest_turbine_folder(
            scan_dir,
            turbine_id=turbine_meta["turbine_id"],
        )
        images = get_all_images_flat(result)
        update_job(job_id, total_images=len(images))

        # 500-image cap
        IMAGE_CAP = 500
        if len(images) > IMAGE_CAP:
            skipped_count = len(images) - IMAGE_CAP
            images = images[:IMAGE_CAP]
            update_job(job_id, image_cap_warning=f"Capped at {IMAGE_CAP} images. {skipped_count} images skipped.")

        set_stage(job_id, "triaging", f"Screening {len(images)} images for defects...")

        # ── Stage 2: Triage ──
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        cost_limit_usd = float(os.environ.get("COST_LIMIT_USD", "999999"))
        running_cost = 0.0

        if not anthropic_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set — pipeline requires Anthropic API key")

        summary = triage_batch(
            images,
            anthropic_key,
            n_tiles=4,
            location_type=turbine_meta.get("location_type", "onshore"),
            turbine_model=turbine_meta.get("turbine_model", ""),
            inspection_date=turbine_meta.get("inspection_date", ""),
            job_dir=job_dir,
            verbose=False,
        )
        triage_path = job_dir / "triage.json"
        save_triage_results(summary, triage_path)
        triage_cost = summary.triage_cost_usd
        running_cost += triage_cost
        update_job(job_id, flagged_images=summary.flagged_images, triage_cost_usd=triage_cost)

        # Save thumbnail copies of flagged images before deleting originals.
        # These survive for classify stage and PDF report embedding (PDF-03).
        # Max 80 flagged images × ~150KB each = ~12MB — well within 1GB disk budget.
        thumbnails_dir = job_dir / "thumbnails"
        thumbnails_dir.mkdir(exist_ok=True)
        flagged_paths = {str(r.image_path) for r in summary.results if r.has_defect}
        for orig_path_str in flagged_paths:
            orig_path = Path(orig_path_str)
            if orig_path.exists():
                thumb_path = thumbnails_dir / orig_path.name
                try:
                    with Image.open(orig_path) as img:
                        img.thumbnail((1568, 1568), Image.LANCZOS)
                        img.convert("RGB").save(str(thumb_path), "JPEG", quality=85)
                except Exception:
                    # If thumbnail creation fails, copy original (better than nothing)
                    shutil.copy2(str(orig_path), str(thumb_path))

        # Delete uploaded images after triage — they are 15-30MB each and not needed
        images_dir = job_dir / "images"
        if images_dir.exists():
            shutil.rmtree(images_dir)

        # Cost limit check after triage
        if running_cost > cost_limit_usd:
            update_job(job_id, stage="error", stage_message=f"Cost limit exceeded after triage: ${running_cost:.2f} > ${cost_limit_usd:.2f}")
            return

        flagged = [
            {**vars(r), "path": str(r.image_path), "location_type": turbine_meta.get("location_type", "onshore")}
            for r in summary.results if r.has_defect
        ]
        # Update flagged image paths to point to thumbnail copies (originals now deleted).
        # Classify stage and PDF report read from these thumbnail paths.
        for f in flagged:
            orig_name = Path(f["path"]).name
            thumb = thumbnails_dir / orig_name
            if thumb.exists():
                f["path"] = str(thumb)

        set_stage(job_id, "classifying", f"Classifying {len(flagged)} flagged images...")

        # ── Stage 3: Classify ──
        classify_path = job_dir / "classify.json"

        classify_results = classify_batch(
            flagged[:80],  # cap at 80 images
            turbine_meta.get("turbine_model", "Unknown"),
            anthropic_key,
            verbose=False,
        )
        save_classify_results(classify_results, classify_path)
        classify_cost = sum(r.cost_usd for r in classify_results)
        running_cost += classify_cost
        update_job(job_id, critical_findings=sum(1 for r in classify_results if r.has_critical), classify_cost_usd=classify_cost)
        critical_findings = load_critical_findings(classify_path)

        # Cost limit check after classify
        if running_cost > cost_limit_usd:
            update_job(job_id, stage="error", stage_message=f"Cost limit exceeded after classify: ${running_cost:.2f} > ${cost_limit_usd:.2f}")
            return

        set_stage(job_id, "analyzing", f"Deep analysis of {len(critical_findings)} critical findings...")

        # ── Stage 4: Analyze ──
        analyze_path = job_dir / "analyze.json"

        if critical_findings:
            analyses, analyze_cost = analyze_critical_defects(
                critical_findings,
                turbine_meta.get("turbine_model", "Unknown"),
                anthropic_key,
                verbose=False,
            )
            save_analysis_results(analyses, analyze_path)
            running_cost += analyze_cost
            update_job(job_id, analyze_cost_usd=analyze_cost)
        else:
            analyses = []
            analyze_cost = 0.0
            with open(analyze_path, "w") as f:
                json.dump([], f)

        set_stage(job_id, "generating_report", "Building PDF report...")

        # ── Stage 5: Report ──
        from report import build_report_data, generate_pdf_fpdf2, load_classify_json, load_analyze_json, load_triage_json

        classify_data = load_classify_json(classify_path)
        analyze_data = load_analyze_json(analyze_path) if analyze_path.exists() else []
        triage_data = None
        triage_path_json = job_dir / "triage.json"
        if triage_path_json.exists():
            triage_data = load_triage_json(triage_path_json)

        report_data = build_report_data(turbine_meta, triage_data, classify_data, analyze_data)
        pdf_path = job_dir / f"report_{turbine_meta['turbine_id']}.pdf"
        generate_pdf_fpdf2(report_data, pdf_path)

        update_job(
            job_id,
            stage="complete",
            stage_message="Report ready",
            pdf_path=str(pdf_path),
            completed_at=datetime.now(timezone.utc),
            total_cost_usd=round(running_cost, 4),
        )

    except Exception as e:
        tb = traceback.format_exc()
        update_job(
            job_id,
            stage="error",
            stage_message=str(e),
            error_traceback=tb,
            failed_at=datetime.now(timezone.utc),
        )


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def extract_upload(upload_file: UploadFile, dest_dir: Path) -> int:
    """Extract ZIP or save individual files. Returns image count."""
    filename = upload_file.filename or ""
    suffix = Path(filename).suffix
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    content = upload_file.file.read()

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds 500 MB limit")

    if filename.lower().endswith(".zip"):
        zip_path = dest_dir / "upload.zip"
        with open(zip_path, "wb") as f:
            f.write(content)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(dest_dir)
        zip_path.unlink()
        # Count extracted images
        return len(list(dest_dir.rglob("*.jpg")) + list(dest_dir.rglob("*.JPG")) +
                   list(dest_dir.rglob("*.jpeg")) + list(dest_dir.rglob("*.png")))
    else:
        # Single file
        with open(dest_dir / filename, "wb") as f:
            f.write(content)
        return 1


# ─── ENDPOINTS ────────────────────────────────────────────────────────────────

@app.post("/api/estimate")
async def cost_estimate(image_count: int = Form(...)):
    """Return estimated pipeline cost for a given image count before committing to run."""
    if image_count > 500:
        image_count = 500  # cap matches pipeline cap
    return estimate_cost(image_count)


@app.post("/api/auth/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login endpoint. Accepts application/x-www-form-urlencoded (OAuth2 standard).

    Returns {"access_token": JWT, "token_type": "bearer"} on success.
    Returns 401 on wrong credentials.

    Per CONTEXT.md Area D: frontend submits with URLSearchParams (not JSON) to satisfy
    OAuth2PasswordRequestForm's x-www-form-urlencoded content type requirement.
    """
    user = get_user_by_username(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_token(user["username"], user["id"], user["is_admin"])
    return {"access_token": token, "token_type": "bearer"}


@app.post("/api/admin/create-user", status_code=201)
async def admin_create_user(
    username: str = Form(...),
    password: str = Form(...),
    is_admin: bool = Form(False),
    x_admin_secret: Optional[str] = Header(None),
):
    """Create a new inspector account.

    Protected by X-Admin-Secret header (not JWT). CONTEXT.md Area A: admin operates
    via direct API call, not the inspector UI. Caller sends X-Admin-Secret: <value>.
    FastAPI maps hyphenated header name to x_admin_secret (underscore, lowercase).

    Returns 403 if ADMIN_SECRET env var is not set or header value doesn't match.
    Returns 409 if username already exists.
    Returns 201 + {"username": ..., "is_admin": ...} on success.
    """
    if not ADMIN_SECRET or x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        new_user = create_user(
            username=username,
            hashed_password=hash_password(password),
            is_admin=is_admin,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"username": new_user["username"], "is_admin": new_user["is_admin"]}


@app.post("/api/upload")
@limiter.limit("10/hour")
async def upload_inspection(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    turbine_id: str = Form(...),
    site_name: str = Form(...),
    country: str = Form(...),
    turbine_model: str = Form(...),
    inspector_name: str = Form(...),
    inspection_date: str = Form(...),
    hub_height_m: Optional[str] = Form(None),
    rotor_diameter_m: Optional[str] = Form(None),
    blade_length_m: Optional[str] = Form(None),
    weather: Optional[str] = Form(None),
    wind_speed_ms: Optional[str] = Form(None),
    temperature_c: Optional[str] = Form(None),
    visibility_km: Optional[str] = Form(None),
    gps_lat: Optional[str] = Form(None),
    gps_lon: Optional[str] = Form(None),
    drone_model: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    location_type: Optional[str] = Form(None),
    images: UploadFile = File(...),
):
    check_disk_space()

    job_id = str(uuid.uuid4())[:8]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    images_dir = job_dir / "images"

    # Extract uploaded images
    try:
        image_count = extract_upload(images, images_dir)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Upload failed: {e}")

    turbine_meta = {
        "turbine_id": turbine_id,
        "site_name": site_name,
        "country": country,
        "turbine_model": turbine_model,
        "inspector_name": inspector_name,
        "inspection_date": inspection_date,
        "hub_height_m": int(hub_height_m) if hub_height_m else None,
        "rotor_diameter_m": int(rotor_diameter_m) if rotor_diameter_m else None,
        "blade_length_m": int(blade_length_m) if blade_length_m else None,
        "weather": weather or "",
        "wind_speed_ms": float(wind_speed_ms) if wind_speed_ms else None,
        "temperature_c": float(temperature_c) if temperature_c else None,
        "visibility_km": float(visibility_km) if visibility_km else None,
        "gps_lat": float(gps_lat) if gps_lat else None,
        "gps_lon": float(gps_lon) if gps_lon else None,
        "drone_model": drone_model or "DJI Matrice 300 RTK",
        "camera": "DJI Zenmuse P1 45MP",
        "notes": notes or "",
        "company_name": os.environ.get("COMPANY_NAME", "AWID - APAC Wind Inspections Drones"),
        "location_type": location_type if location_type in ("onshore", "offshore") else "onshore",
    }

    save_new_job(
        {
            "job_id": job_id,
            "stage": "queued",
            "stage_message": "Job queued",
            "turbine_meta": turbine_meta,
            "image_count": image_count,
        },
        owner_id=current_user["user_id"],
    )

    # Compute cost estimate before starting
    cost_est = estimate_cost(min(image_count, 500))

    # Run pipeline in background
    background_tasks.add_task(run_pipeline, job_id, job_dir, turbine_meta)

    return {
        "job_id": job_id,
        "image_count": image_count,
        "message": "Pipeline started",
        "cost_estimate": cost_est,
    }


@app.get("/api/status/{job_id}")
@limiter.limit("60/minute")
async def get_status(request: Request, job_id: str, current_user: dict = Depends(get_current_user)):
    state = get_job(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")

    # Ownership enforcement (per CONTEXT.md Area B): admin exempt, inspector must own job
    if not current_user["is_admin"]:
        if state.get("owner_id") != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="Access forbidden")

    # Map stage to progress %
    stage_progress = {
        "queued": 0,
        "ingesting": 10,
        "triaging": 25,
        "classifying": 50,
        "analyzing": 70,
        "generating_report": 85,
        "complete": 100,
        "error": -1,
        "failed": -1,
        "cost_limit_exceeded": -1,
    }

    stage = state.get("stage", "queued")
    return {
        "job_id": job_id,
        "stage": stage,
        "message": state.get("stage_message", ""),
        "progress": stage_progress.get(stage, 0),
        "total_images": state.get("total_images"),
        "flagged_images": state.get("flagged_images"),
        "critical_findings": state.get("critical_findings"),
        "created_at": state.get("created_at"),
        "completed_at": state.get("completed_at"),
        "error": state.get("stage_message") if stage in ("error", "failed") else None,
        "error_traceback": state.get("error_traceback") if stage in ("error", "failed") else None,
        "triage_cost_usd": state.get("triage_cost_usd"),
        "classify_cost_usd": state.get("classify_cost_usd"),
        "analyze_cost_usd": state.get("analyze_cost_usd"),
        "total_cost_usd": state.get("total_cost_usd"),
        "image_cap_warning": state.get("image_cap_warning"),
    }


@app.get("/api/debug/ai")
async def debug_ai():
    """Test Anthropic claude-opus-4-6 vision API — sends a test image, returns raw response."""
    import base64, io
    from PIL import Image as PILImage

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        return {"error": "ANTHROPIC_API_KEY not set"}

    # Create a small 64x64 solid grey test image
    img = PILImage.new("RGB", (64, 64), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=60)
    b64 = base64.b64encode(buf.getvalue()).decode()

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=anthropic_key)
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=100,
            system="You are a test assistant.",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                    {"type": "text", "text": 'Reply ONLY with valid JSON: {"status": "ok", "model": "claude-opus-4-6", "vision": true}'},
                ],
            }],
        )
        raw = response.content[0].text.strip()
        try:
            parsed = json.loads(raw)
            parse_ok = True
        except Exception as pe:
            parsed = None
            parse_ok = str(pe)

        return {
            "model": "claude-opus-4-6",
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "raw_response": raw,
            "parse_ok": parse_ok,
            "parsed": parsed,
        }
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}


@app.get("/api/download/{job_id}")
@limiter.limit("30/hour")
async def download_report(request: Request, job_id: str, current_user: dict = Depends(get_current_user)):
    state = get_job(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")

    if not current_user["is_admin"]:
        if state.get("owner_id") != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="Access forbidden")

    if state.get("stage") != "complete":
        raise HTTPException(status_code=400, detail="Report not ready yet")

    pdf_path = Path(state["pdf_path"])
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")

    turbine_id = state.get("turbine_meta", {}).get("turbine_id", job_id)
    date = state.get("turbine_meta", {}).get("inspection_date", "")
    filename = f"inspection_report_{turbine_id}_{date}.pdf"

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=filename,
    )


@app.get("/api/jobs")
async def list_jobs(current_user: dict = Depends(get_current_user)):
    """List jobs from the last 30 days. Admin sees all; inspector sees own jobs only.

    Per CONTEXT.md Area B: existing jobs with NULL owner_id are visible to admin,
    not to inspectors (SQLAlchemy WHERE owner_id == uuid naturally excludes NULLs).
    """
    if current_user["is_admin"]:
        return list_jobs_last_30_days()          # no filter — admin sees all
    return list_jobs_last_30_days(owner_id=current_user["user_id"])


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str, current_user: dict = Depends(get_current_user)):
    """Delete job — removes SQLite row AND job directory."""
    with get_db() as session:
        job = session.scalars(select(Job).where(Job.job_id == job_id)).first()
        if job:
            if not current_user["is_admin"] and job.owner_id != current_user["user_id"]:
                raise HTTPException(status_code=403, detail="Access forbidden")
            # Remove files first, then DB row
            job_dir = JOBS_DIR / job_id
            if job_dir.exists():
                shutil.rmtree(job_dir)
            session.delete(job)
            session.commit()
    return {"deleted": job_id}


# ─── HEALTH ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    keys = {
        "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "COST_LIMIT_USD": os.environ.get("COST_LIMIT_USD", "not set"),
    }
    return {"status": "ok", "api_keys": keys, "jobs_dir": str(JOBS_DIR), "data_dir": str(DATA_DIR)}


# ─── LOGIN PAGE ───────────────────────────────────────────────────────────────

@app.get("/login")
async def login_page():
    """Serve the login HTML page."""
    login_path = FRONTEND_DIR / "login.html"
    if not login_path.exists():
        raise HTTPException(status_code=404, detail="Login page not found — run Plan 04 first")
    return HTMLResponse(content=login_path.read_text())


# ─── STATIC FILES ────────────────────────────────────────────────────────────

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False)
