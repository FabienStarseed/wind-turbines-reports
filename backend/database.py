"""
database.py — SQLAlchemy 2.0 sync session, Job model, and CRUD helpers.
Replaces the in-memory _jobs dict and state.json filesystem pattern.
"""
import json
import os
import uuid as _uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator, List, Optional

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, create_engine, event, func, select, update
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# ── DATA_DIR ──────────────────────────────────────────────────────────────────
# Pitfall 6: DATA_DIR must exist before engine creation — mkdir at import time.
# Production: /data (Render Persistent Disk mount path)
# Local dev: override with DATA_DIR=./data env var (avoids touching /data locally)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR = DATA_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "bdda.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

# ── ENGINE ────────────────────────────────────────────────────────────────────
# Pitfall 2: check_same_thread=False is mandatory — FastAPI runs the background
# pipeline in a thread pool; SQLite's default single-thread check would fail.

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


# Pitfall 3: WAL mode prevents status polling from blocking during pipeline writes.
# Default rollback journal acquires exclusive write lock — WAL allows concurrent readers.
@event.listens_for(engine, "connect")
def set_sqlite_pragmas(dbapi_connection, connection_record):
    """Enable WAL mode so reads don't block background pipeline writes."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


# ── SESSION FACTORY ───────────────────────────────────────────────────────────

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager that yields a session and closes it on exit.

    Pitfall 4: Does NOT auto-commit — each write operation must call
    session.commit() explicitly. Only closes in finally to guarantee cleanup.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ── MODEL ─────────────────────────────────────────────────────────────────────
# State of the Art: DeclarativeBase class syntax (SQLAlchemy 2.0).
# NOT the legacy declarative_base() from sqlalchemy.ext.declarative.

class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    job_id            = Column(String(8), unique=True, nullable=False, index=True)
    stage             = Column(String(32), nullable=False, default="queued")
    stage_message     = Column(Text, default="")
    # Pitfall 5: turbine_meta stored as Text with explicit json.dumps/loads.
    # SQLite JSON column support varies by version; Text is explicit and portable.
    turbine_meta_json = Column(Text, default="{}")
    image_count       = Column(Integer, default=0)
    total_images      = Column(Integer, nullable=True)
    flagged_images    = Column(Integer, nullable=True)
    critical_findings = Column(Integer, nullable=True)
    pdf_path          = Column(Text, nullable=True)
    # Anti-pattern: storing floats in Float column causes SQLite precision issues.
    # Use Text (string) for all cost values to avoid rounding artifacts.
    triage_cost_usd   = Column(Text, nullable=True)
    classify_cost_usd = Column(Text, nullable=True)
    analyze_cost_usd  = Column(Text, nullable=True)
    total_cost_usd    = Column(Text, nullable=True)
    image_cap_warning = Column(Text, nullable=True)
    error_traceback   = Column(Text, nullable=True)
    owner_id          = Column(String(36), nullable=True)
    created_at        = Column(DateTime(timezone=True), server_default=func.now())
    updated_at        = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at      = Column(DateTime(timezone=True), nullable=True)
    failed_at         = Column(DateTime(timezone=True), nullable=True)


class User(Base):
    __tablename__ = "users"

    id               = Column(String(36), primary_key=True, default=lambda: str(_uuid.uuid4()))
    username         = Column(String(64), unique=True, nullable=False, index=True)
    hashed_password  = Column(Text, nullable=False)
    is_admin         = Column(Boolean, default=False, nullable=False)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())


def init_db():
    """Create all tables if they don't exist. Idempotent — safe to call on every startup."""
    Base.metadata.create_all(bind=engine)


def migrate_schema():
    """Add owner_id column to jobs table if it doesn't already exist.

    Render uses SQLite 3.27.2 — ADD COLUMN IF NOT EXISTS requires SQLite 3.37.0+.
    Use PRAGMA table_info() check instead (works on all SQLite versions).
    """
    with engine.connect() as conn:
        raw = conn.connection.dbapi_connection
        cursor = raw.cursor()
        cursor.execute("PRAGMA table_info(jobs)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        cursor.close()
        if "owner_id" not in existing_columns:
            raw.execute("ALTER TABLE jobs ADD COLUMN owner_id VARCHAR(36) REFERENCES users(id)")
            raw.commit()


def _seed_admin_user():
    """Seed admin user on first deploy if no users exist.

    Reads ADMIN_USERNAME (default: 'admin') and ADMIN_PASSWORD (default: 'changeme').
    Logs a warning if ADMIN_PASSWORD is still the default — insecure in production.
    Called from lifespan() in api.py after init_db() and migrate_schema().
    """
    import logging
    from auth import hash_password  # imported here to avoid circular import at module level

    admin_username = os.environ.get("ADMIN_USERNAME", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD", "changeme")

    if admin_password == "changeme":
        logging.warning("ADMIN_PASSWORD is set to default 'changeme' — change it in production!")

    with get_db() as session:
        existing = session.scalars(select(User)).first()
        if existing is None:
            admin = User(
                id=str(_uuid.uuid4()),
                username=admin_username,
                hashed_password=hash_password(admin_password),
                is_admin=True,
            )
            session.add(admin)
            session.commit()
            logging.info(f"Seeded admin user: {admin_username}")


# ── CRUD HELPERS ──────────────────────────────────────────────────────────────
# Use SQLAlchemy 2.0 select() style throughout.
# State of the Art: select(Model) + session.scalars() — NOT the legacy session.query() API.

def _job_to_dict(job: Job) -> dict:
    """Convert a Job ORM row to the dict shape api.py expects.

    - turbine_meta_json: deserialized from JSON string back to dict
    - cost fields (Text): converted back to float (or None if not set)
    - datetime fields: converted to ISO 8601 string (or None if not set)
    """
    return {
        "job_id": job.job_id,
        "stage": job.stage,
        "stage_message": job.stage_message,
        "turbine_meta": json.loads(job.turbine_meta_json or "{}"),
        "image_count": job.image_count,
        "total_images": job.total_images,
        "flagged_images": job.flagged_images,
        "critical_findings": job.critical_findings,
        "pdf_path": job.pdf_path,
        "triage_cost_usd": float(job.triage_cost_usd) if job.triage_cost_usd else None,
        "classify_cost_usd": float(job.classify_cost_usd) if job.classify_cost_usd else None,
        "analyze_cost_usd": float(job.analyze_cost_usd) if job.analyze_cost_usd else None,
        "total_cost_usd": float(job.total_cost_usd) if job.total_cost_usd else None,
        "image_cap_warning": job.image_cap_warning,
        "error_traceback": job.error_traceback,
        "owner_id": job.owner_id,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "failed_at": job.failed_at.isoformat() if job.failed_at else None,
    }


def get_job(job_id: str) -> Optional[dict]:
    """Fetch a single job by job_id. Returns dict or None."""
    with get_db() as session:
        job = session.scalars(select(Job).where(Job.job_id == job_id)).first()
        return _job_to_dict(job) if job else None


def save_new_job(state: dict, owner_id: Optional[str] = None):
    """Insert a new Job row from the initial state dict passed at job creation.

    Called once at upload time. turbine_meta dict is serialized to JSON string.
    owner_id is set to the uploading user's UUID (None for legacy jobs created before auth).
    """
    with get_db() as session:
        job = Job(
            job_id=state["job_id"],
            stage=state.get("stage", "queued"),
            stage_message=state.get("stage_message", ""),
            turbine_meta_json=json.dumps(state.get("turbine_meta", {})),
            image_count=state.get("image_count", 0),
            owner_id=owner_id,
        )
        session.add(job)
        session.commit()


def update_job(job_id: str, **kwargs):
    """Update specific fields on a job row using SQLAlchemy 2.0 update() statement.

    Cost fields (any key ending in _usd) are automatically converted to str for
    storage in Text columns, matching the anti-pattern avoidance for float precision.
    """
    # Only map known column names — ignore unknown kwargs silently
    COST_FIELDS = {"triage_cost_usd", "classify_cost_usd", "analyze_cost_usd", "total_cost_usd"}
    COLUMN_NAMES = {
        "stage", "stage_message", "total_images", "flagged_images", "critical_findings",
        "pdf_path", "triage_cost_usd", "classify_cost_usd", "analyze_cost_usd",
        "total_cost_usd", "image_cap_warning", "error_traceback", "completed_at", "failed_at",
        "owner_id",
    }
    values = {}
    for key, value in kwargs.items():
        if key not in COLUMN_NAMES:
            continue
        # Store cost floats as strings to avoid SQLite float precision issues
        if key in COST_FIELDS and value is not None:
            value = str(value)
        values[key] = value

    if not values:
        return

    with get_db() as session:
        session.execute(
            update(Job).where(Job.job_id == job_id).values(**values)
        )
        session.commit()


def set_stage(job_id: str, stage: str, message: str = ""):
    """Convenience wrapper: update stage and stage_message in one call."""
    update_job(job_id, stage=stage, stage_message=message)


def list_jobs_last_30_days(owner_id: Optional[str] = None) -> List[dict]:
    """Return jobs created in the last 30 days, ordered by created_at descending.

    Returns list of dicts with: job_id, stage, created_at, completed_at, turbine_meta, owner_id.
    Used by /api/jobs endpoint. No pagination needed at ~50 jobs/month scale.

    owner_id filter: when provided, returns only jobs belonging to that user
    (inspector view). When None, returns all jobs including NULL owner_id rows
    (admin view).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    with get_db() as session:
        stmt = select(Job).where(Job.created_at >= cutoff)
        if owner_id is not None:
            # Inspector filter: only their jobs (NULL owner_id rows excluded naturally)
            stmt = stmt.where(Job.owner_id == owner_id)
        # Admin: no additional filter — sees all jobs including NULL owner_id rows
        stmt = stmt.order_by(Job.created_at.desc())
        jobs = session.scalars(stmt).all()
        return [
            {
                "job_id": j.job_id,
                "stage": j.stage,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                "turbine_meta": json.loads(j.turbine_meta_json or "{}"),
                "owner_id": j.owner_id,
            }
            for j in jobs
        ]


# ── USER CRUD ──────────────────────────────────────────────────────────────────

def get_user_by_username(username: str) -> Optional[dict]:
    """Fetch user by username. Returns dict with id, username, hashed_password, is_admin — or None."""
    with get_db() as session:
        user = session.scalars(select(User).where(User.username == username)).first()
        if not user:
            return None
        return {
            "id": user.id,
            "username": user.username,
            "hashed_password": user.hashed_password,
            "is_admin": user.is_admin,
        }


def create_user(username: str, hashed_password: str, is_admin: bool = False) -> dict:
    """Insert a new user. Raises ValueError if username already exists."""
    with get_db() as session:
        existing = session.scalars(select(User).where(User.username == username)).first()
        if existing:
            raise ValueError(f"Username '{username}' already exists")
        user = User(
            id=str(_uuid.uuid4()),
            username=username,
            hashed_password=hashed_password,
            is_admin=is_admin,
        )
        session.add(user)
        session.commit()
        return {"id": user.id, "username": user.username, "is_admin": user.is_admin}
