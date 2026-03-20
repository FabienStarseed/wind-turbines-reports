"""
tests/test_api.py — BDDA API smoke tests
Run: pytest tests/ -v
"""

import io
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("BDDA_API_KEY", "testkey")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:8000")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api import app
    return TestClient(app, raise_server_exceptions=True)


VALID_KEY = {"X-API-Key": "testkey"}


# ─── Health (public) ─────────────────────────────────────────────────────────

def test_health_public(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ─── Config (authenticated) ───────────────────────────────────────────────────

def test_config_no_key_rejected(client):
    r = client.get("/api/config")
    assert r.status_code == 401

def test_config_wrong_key_rejected(client):
    r = client.get("/api/config", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401

def test_config_valid_key(client):
    r = client.get("/api/config", headers=VALID_KEY)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "api_keys" in data


# ─── Upload (authenticated) ───────────────────────────────────────────────────

def test_upload_no_key_rejected(client):
    r = client.post("/api/upload")
    assert r.status_code == 401

def test_upload_bad_extension(client):
    r = client.post(
        "/api/upload",
        headers=VALID_KEY,
        data={
            "turbine_id": "T1", "site_name": "Site", "country": "Japan",
            "turbine_model": "Vestas", "inspector_name": "Test",
            "inspection_date": "2026-01-01",
        },
        files={"images": ("bad.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400
    assert "Unsupported file type" in r.json()["detail"]


# ─── Jobs (authenticated) ─────────────────────────────────────────────────────

def test_jobs_no_key_rejected(client):
    r = client.get("/api/jobs")
    assert r.status_code == 401

def test_jobs_valid_key(client):
    r = client.get("/api/jobs", headers=VALID_KEY)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ─── Status (authenticated) ───────────────────────────────────────────────────

def test_status_no_key_rejected(client):
    r = client.get("/api/status/fakejob")
    assert r.status_code == 401

def test_status_unknown_job(client):
    r = client.get("/api/status/doesnotexist", headers=VALID_KEY)
    assert r.status_code == 404


# ─── Download (authenticated) ─────────────────────────────────────────────────

def test_download_no_key_rejected(client):
    r = client.get("/api/download/fakejob")
    assert r.status_code == 401

def test_download_unknown_job(client):
    r = client.get("/api/download/doesnotexist", headers=VALID_KEY)
    assert r.status_code == 404
