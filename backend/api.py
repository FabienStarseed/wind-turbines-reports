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
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm

from auth import create_token, get_current_user, hash_password, verify_password
from database import get_user_by_username, create_user as db_create_user, init_db

# ─── APP SETUP ────────────────────────────────────────────────────────────────

# Init DB + seed admin on startup
init_db()

app = FastAPI(
    title="BDDA — Blade Defect Detection Agent",
    description="AI-powered wind turbine drone inspection analysis",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── PATHS ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
JOBS_DIR = BASE_DIR / "jobs"
FRONTEND_DIR = BASE_DIR / "frontend"
TEMPLATES_DIR = BASE_DIR / "templates"
JOBS_DIR.mkdir(exist_ok=True)

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


# ─── JOB STATE ────────────────────────────────────────────────────────────────

# In-memory job registry (survives within a process; jobs re-read from disk on restart)
_jobs: Dict[str, Dict] = {}


def get_job(job_id: str) -> Optional[Dict]:
    if job_id in _jobs:
        return _jobs[job_id]
    # Try loading from disk
    state_file = JOBS_DIR / job_id / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            _jobs[job_id] = json.load(f)
        return _jobs[job_id]
    return None


def save_job(job_id: str, state: Dict):
    _jobs[job_id] = state
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(exist_ok=True)
    with open(job_dir / "state.json", "w") as f:
        json.dump(state, f, indent=2, default=str)


def update_job(job_id: str, **kwargs):
    state = get_job(job_id) or {}
    state.update(kwargs)
    save_job(job_id, state)


def set_stage(job_id: str, stage: str, message: str = ""):
    update_job(job_id, stage=stage, stage_message=message, updated_at=datetime.now().isoformat())


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
        from report import build_report, make_sample_turbine_meta

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

        # Cost limit check after triage
        if running_cost > cost_limit_usd:
            update_job(job_id, stage="error", stage_message=f"Cost limit exceeded after triage: ${running_cost:.2f} > ${cost_limit_usd:.2f}")
            return

        flagged = [
            {**vars(r), "path": str(r.image_path), "location_type": turbine_meta.get("location_type", "onshore")}
            for r in summary.results if r.has_defect
        ]

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
        triage_json = job_dir / "triage.json" if (job_dir / "triage.json").exists() else None
        pdf_path = job_dir / f"report_{turbine_meta['turbine_id']}.pdf"

        from report import build_report
        build_report(
            turbine_meta=turbine_meta,
            classify_json_path=classify_path,
            output_pdf_path=pdf_path,
            triage_json_path=triage_json,
            analyze_json_path=analyze_path,
            templates_dir=TEMPLATES_DIR,
            save_html=True,
            verbose=False,
        )

        update_job(
            job_id,
            stage="complete",
            stage_message="Report ready",
            pdf_path=str(pdf_path),
            completed_at=datetime.now().isoformat(),
            total_cost_usd=round(running_cost, 4),
        )

    except Exception as e:
        tb = traceback.format_exc()
        update_job(
            job_id,
            stage="error",
            stage_message=str(e),
            error_traceback=tb,
            failed_at=datetime.now().isoformat(),
        )


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def extract_upload(upload_file: UploadFile, dest_dir: Path) -> int:
    """Extract ZIP or save individual files. Returns image count."""
    filename = upload_file.filename or ""
    dest_dir.mkdir(parents=True, exist_ok=True)
    content = upload_file.file.read()

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


# ─── AUTH ENDPOINTS ───────────────────────────────────────────────────────────

@app.post("/api/auth/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Issue JWT token. Accepts OAuth2 form (username + password)."""
    user = get_user_by_username(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(user["username"], str(user["id"]), user["is_admin"])
    return {"access_token": token, "token_type": "bearer"}


@app.post("/api/admin/create-user")
async def admin_create_user(
    payload: dict,
    request: Request,
):
    """Create inspector account. Requires X-Admin-Secret header."""
    admin_secret = os.environ.get("ADMIN_SECRET", "")
    if not admin_secret or request.headers.get("X-Admin-Secret") != admin_secret:
        raise HTTPException(status_code=403, detail="Forbidden")
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    is_admin = payload.get("is_admin", False)
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")
    if get_user_by_username(username):
        raise HTTPException(status_code=409, detail="User already exists")
    user = db_create_user(username, hash_password(password), is_admin=is_admin)
    return {"created": user["username"], "is_admin": user["is_admin"]}


# ─── ENDPOINTS ────────────────────────────────────────────────────────────────

@app.post("/api/estimate")
async def cost_estimate(image_count: int = Form(...)):
    """Return estimated pipeline cost for a given image count before committing to run."""
    if image_count > 500:
        image_count = 500  # cap matches pipeline cap
    return estimate_cost(image_count)


@app.post("/api/upload")
async def upload_inspection(
    background_tasks: BackgroundTasks,
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
        "company_name": os.environ.get("COMPANY_NAME", "DroneWind Asia"),
        "location_type": location_type if location_type in ("onshore", "offshore") else "onshore",
    }

    save_job(job_id, {
        "job_id": job_id,
        "stage": "queued",
        "stage_message": "Job queued",
        "turbine_meta": turbine_meta,
        "image_count": image_count,
        "created_at": datetime.now().isoformat(),
    })

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
async def get_status(job_id: str):
    state = get_job(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")

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
        "error": state.get("stage_message") if stage == "error" else None,
        "error_traceback": state.get("error_traceback") if stage == "error" else None,
        "triage_cost_usd": state.get("triage_cost_usd"),
        "classify_cost_usd": state.get("classify_cost_usd"),
        "analyze_cost_usd": state.get("analyze_cost_usd"),
        "total_cost_usd": state.get("total_cost_usd"),
        "image_cap_warning": state.get("image_cap_warning"),
    }


@app.get("/api/blademap/{job_id}")
async def get_blademap(job_id: str, token: str = None):
    """Return per-blade zone grid data for the Cyber Operator blade defect map UI."""
    state = get_job(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")

    classify_path = JOBS_DIR / job_id / "classify.json"
    if not classify_path.exists():
        return {"blades": {}, "ready": False}

    with open(classify_path) as f:
        classify_data = json.load(f)

    ZONES     = ["LE", "TE", "PS", "SS"]
    POSITIONS = ["Root", "Mid", "Tip"]

    blades: dict = {}
    for img in classify_data:
        blade = str(img.get("blade", "1"))
        if blade not in blades:
            blades[blade] = {
                "blade": blade,
                "total_defects": 0,
                "max_category": 0,
                "grid": {}
            }
        b = blades[blade]
        b["total_defects"] += len(img.get("defects", []))
        b["max_category"] = max(b["max_category"], img.get("max_category", 0))

        for defect in img.get("defects", []):
            zone = defect.get("zone", "LE")
            pos  = defect.get("position", "Root")
            # Normalize position: Transition → Mid
            if pos == "Transition":
                pos = "Mid"
            key  = f"{zone}/{pos}"
            if key not in b["grid"]:
                b["grid"][key] = {"zone": zone, "position": pos, "count": 0, "worst_cat": 0, "defect_types": []}
            cell = b["grid"][key]
            cell["count"] += 1
            cell["worst_cat"] = max(cell["worst_cat"], defect.get("iec_category", 0))
            dn = defect.get("defect_name", "")
            if dn and dn not in cell["defect_types"]:
                cell["defect_types"].append(dn)

    # Fill in empty cells so frontend always gets a complete 4×3 grid
    for blade, b in blades.items():
        for z in ZONES:
            for p in POSITIONS:
                key = f"{z}/{p}"
                if key not in b["grid"]:
                    b["grid"][key] = {"zone": z, "position": p, "count": 0, "worst_cat": 0, "defect_types": []}

    return {
        "ready": True,
        "blades": blades,
        "turbine_id": state.get("turbine_id", ""),
        "site_name": state.get("site_name", ""),
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
async def download_report(job_id: str):
    state = get_job(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")
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
async def list_jobs():
    """List recent jobs (last 20)."""
    jobs = []
    for state_file in sorted(JOBS_DIR.glob("*/state.json"), reverse=True)[:20]:
        try:
            with open(state_file) as f:
                state = json.load(f)
            jobs.append({
                "job_id": state["job_id"],
                "turbine_id": state.get("turbine_meta", {}).get("turbine_id"),
                "stage": state.get("stage"),
                "created_at": state.get("created_at"),
                "completed_at": state.get("completed_at"),
            })
        except Exception:
            pass
    return jobs


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    job_dir = JOBS_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
    _jobs.pop(job_id, None)
    return {"deleted": job_id}


# ─── HEALTH ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    keys = {
        "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "COST_LIMIT_USD": os.environ.get("COST_LIMIT_USD", "not set"),
    }
    return {"status": "ok", "api_keys": keys, "jobs_dir": str(JOBS_DIR)}


# ─── STATIC FILES ────────────────────────────────────────────────────────────

@app.get("/login", include_in_schema=False)
async def login_page():
    from fastapi.responses import HTMLResponse
    return HTMLResponse('<script>window.location.replace("/")</script>', headers={"Cache-Control": "no-store"})


@app.get("/", include_in_schema=False)
async def index_page():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False)
