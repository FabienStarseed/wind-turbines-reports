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

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, BackgroundTasks, Security, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ─── APP SETUP ────────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="BDDA — Blade Defect Detection Agent",
    description="AI-powered wind turbine drone inspection analysis",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:8000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["POST", "GET", "DELETE"],
    allow_headers=["*"],
)

# ─── AUTH ─────────────────────────────────────────────────────────────────────

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=True)

ALLOWED_EXTENSIONS = {".zip", ".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


def verify_api_key(api_key: str = Security(_API_KEY_HEADER)):
    expected = os.environ.get("BDDA_API_KEY", "")
    if not expected or api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key

# ─── PATHS ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
JOBS_DIR = BASE_DIR / "jobs"
FRONTEND_DIR = BASE_DIR / "frontend"
TEMPLATES_DIR = BASE_DIR / "templates"
JOBS_DIR.mkdir(exist_ok=True)

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
        set_stage(job_id, "triaging", f"Screening {len(images)} images for defects...")

        # ── Stage 2: Triage ──
        kimi_key = os.environ.get("KIMI_API_KEY", "")
        if not kimi_key:
            # Skip triage if no API key — treat all images as flagged
            flagged = [{"path": str(img["path"]), "turbine_id": img["turbine_id"],
                        "blade": img["blade"], "zone": img["zone"], "position": img["position"],
                        "mission_folder": img["mission_folder"], "has_defect": True,
                        "defect_hint": "Triage skipped (no KIMI_API_KEY)"} for img in images[:50]]
            update_job(job_id, flagged_images=len(flagged))
        else:
            from triage import triage_batch
            summary = triage_batch(images, kimi_key, verbose=False)
            triage_path = job_dir / "triage.json"
            save_triage_results(summary, triage_path)
            flagged = [
                {**vars(r), "path": str(r.image_path)}
                for r in summary.results if r.has_defect
            ]
            update_job(job_id, flagged_images=len(flagged))

        set_stage(job_id, "classifying", f"Classifying {len(flagged)} flagged images...")

        # ── Stage 3: Classify ──
        google_key = os.environ.get("GOOGLE_API_KEY", "")
        classify_path = job_dir / "classify.json"

        if not google_key:
            # Generate minimal classify JSON from flagged images
            dummy_classify = [
                {
                    "image_path": img["path"],
                    "turbine_id": turbine_meta["turbine_id"],
                    "blade": img.get("blade", "A"),
                    "zone": img.get("zone", "LE"),
                    "position": img.get("position", "Mid"),
                    "mission_folder": img.get("mission_folder", ""),
                    "image_quality": "good",
                    "image_notes": "Classification skipped (no GOOGLE_API_KEY)",
                    "error": None,
                    "max_category": 0,
                    "defects": [],
                }
                for img in flagged[:20]
            ]
            with open(classify_path, "w") as f:
                json.dump(dummy_classify, f)
            critical_findings = []
        else:
            from classify import classify_batch, save_classify_results, load_critical_findings
            classify_results = classify_batch(
                flagged[:80],  # cap at 80 images
                turbine_meta.get("turbine_model", "Unknown"),
                google_key,
                verbose=False,
            )
            save_classify_results(classify_results, classify_path)
            critical_findings = load_critical_findings(classify_path)
            update_job(job_id, critical_findings=len(critical_findings))

        set_stage(job_id, "analyzing", f"Deep analysis of {len(critical_findings)} critical findings...")

        # ── Stage 4: Analyze ──
        analyze_path = job_dir / "analyze.json"
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")

        if not anthropic_key or not critical_findings:
            analyze_data = []
            with open(analyze_path, "w") as f:
                json.dump(analyze_data, f)
        else:
            from analyze import analyze_critical_defects, save_analysis_results
            analyses = analyze_critical_defects(
                critical_findings,
                turbine_meta.get("turbine_model", "Unknown"),
                anthropic_key,
                verbose=False,
            )
            save_analysis_results(analyses, analyze_path)
            analyze_data = [
                {
                    "defect_name": a.defect_name,
                    "category": a.category,
                    "turbine_id": a.turbine_id,
                    "blade": a.blade,
                    "zone": a.zone,
                    "position": a.position,
                    "root_cause": a.root_cause,
                    "failure_risk": a.failure_risk,
                    "vestas_standard": a.vestas_standard,
                    "recommended_action": a.recommended_action,
                    "repair_timeframe": a.repair_timeframe,
                    "estimated_cost_usd": a.estimated_cost_usd,
                    "engineer_review_required": a.engineer_review_required,
                    "engineer_review_reason": a.engineer_review_reason,
                    "analysis_confidence": a.analysis_confidence,
                    "additional_notes": a.additional_notes,
                    "error": a.error,
                }
                for a in analyses
            ]

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
    suffix = Path(filename).suffix
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

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

@app.post("/api/upload")
@limiter.limit("10/hour")
async def upload_inspection(
    request: Request,
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
    images: UploadFile = File(...),
    _: str = Depends(verify_api_key),
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
    }

    save_job(job_id, {
        "job_id": job_id,
        "stage": "queued",
        "stage_message": "Job queued",
        "turbine_meta": turbine_meta,
        "image_count": image_count,
        "created_at": datetime.now().isoformat(),
    })

    # Run pipeline in background
    background_tasks.add_task(run_pipeline, job_id, job_dir, turbine_meta)

    return {"job_id": job_id, "image_count": image_count, "message": "Pipeline started"}


@app.get("/api/status/{job_id}")
@limiter.limit("60/minute")
async def get_status(request: Request, job_id: str, _: str = Depends(verify_api_key)):
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
    }


@app.get("/api/debug/kimi")
@limiter.limit("5/hour")
async def debug_kimi(request: Request, _: str = Depends(verify_api_key)):
    """Test Kimi API directly — returns raw response for diagnosis."""
    import base64, io, re
    from PIL import Image as PILImage

    kimi_key = os.environ.get("KIMI_API_KEY", "")
    if not kimi_key:
        return {"error": "KIMI_API_KEY not set"}

    # Create a tiny 64x64 solid grey test image
    img = PILImage.new("RGB", (64, 64), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=60)
    b64 = base64.b64encode(buf.getvalue()).decode()

    try:
        from openai import OpenAI
        client = OpenAI(api_key=kimi_key, base_url="https://api.moonshot.cn/v1")

        # Test 1: vision-preview model with image
        response = client.chat.completions.create(
            model="moonshot-v1-8k-vision-preview",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": 'Reply ONLY with valid JSON: {"has_defect": false, "confidence": 0.1, "defect_hint": null}'},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]}],
            max_tokens=300,
            temperature=0.1,
        )
        raw = response.choices[0].message.content
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned, flags=re.MULTILINE).strip()
        try:
            parsed = json.loads(cleaned)
            parse_ok = True
        except Exception as pe:
            parsed = None
            parse_ok = str(pe)

        return {
            "model": "moonshot-v1-8k-vision-preview",
            "raw_response": repr(raw),
            "cleaned": repr(cleaned),
            "parse_ok": parse_ok,
            "parsed": parsed,
        }
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}


@app.get("/api/download/{job_id}")
@limiter.limit("30/hour")
async def download_report(request: Request, job_id: str, _: str = Depends(verify_api_key)):
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
@limiter.limit("30/minute")
async def list_jobs(request: Request, _: str = Depends(verify_api_key)):
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
@limiter.limit("20/hour")
async def delete_job(request: Request, job_id: str, _: str = Depends(verify_api_key)):
    job_dir = JOBS_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
    _jobs.pop(job_id, None)
    return {"deleted": job_id}


# ─── HEALTH ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health(_: str = Depends(verify_api_key)):
    keys = {
        "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "GOOGLE_API_KEY": bool(os.environ.get("GOOGLE_API_KEY")),
        "KIMI_API_KEY": bool(os.environ.get("KIMI_API_KEY")),
    }
    return {"status": "ok", "api_keys": keys}


# ─── STATIC FILES ────────────────────────────────────────────────────────────

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False)
