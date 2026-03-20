# Phase 3: Auth — Research

**Researched:** 2026-03-06
**Domain:** FastAPI JWT authentication, SQLAlchemy schema migration, Render.com deployment
**Confidence:** HIGH (official docs + PyPI verified for all core packages)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Area A — Inspector Account Setup**
- Admin (Fabien) creates all accounts manually via `POST /api/admin/create-user`
- Admin account bootstrapped at startup via `ADMIN_SECRET` env var
- No self-registration — inspectors invited/created by admin
- `POST /api/admin/create-user` protected by a separate `ADMIN_SECRET` header (not JWT)
- Inspector credentials: `username` + `password` (bcrypt-hashed in DB)
- On first deploy, seed ONE admin user if no users exist (username=`admin`, password from `ADMIN_PASSWORD` env var)
- User ORM locked fields: `id` (UUID), `username` (unique), `hashed_password`, `is_admin` (bool), `created_at`

**Area B — Job Visibility & Ownership**
- Inspectors see only their own jobs; admin (`is_admin=True`) sees all jobs
- `Job` table gets a `owner_id` FK → `User.id` (nullable — existing jobs have NULL, admin sees them)
- `GET /api/jobs`: admin → all jobs (last 30 days); inspector → only own jobs
- `POST /api/upload` assigns `owner_id = current_user.id`
- Ownership enforcement on `GET /api/status/{job_id}`, `GET /api/download/{job_id}`, `DELETE /api/jobs/{job_id}` (403 if not owner, admin exempt)

**Area C — Token & Session Behaviour**
- JWT lifetime: 8 hours
- Silent refresh: issue new JWT when token has <1 hour remaining, returned in `X-New-Token` response header
- Token payload: `{ "sub": username, "user_id": uuid, "is_admin": bool, "exp": unix_ts }`
- Token storage: `localStorage`
- Expired token → 401, frontend redirects to `/login`
- No explicit refresh endpoint

**Area D — Login Page & Redirect Flow**
- `/login` is a simple HTML page (functional but unstyled — Phase 5 will redesign)
- On success → redirect to `/`
- Unauthenticated → redirect to `/login?next=<original_url>`
- After login → redirect to `next` param if present, else `/`
- Login HTML scope: username + password form, submit → `POST /api/auth/token`, store JWT, redirect

**New endpoints:**
- `POST /api/auth/token` — public, returns JWT
- `POST /api/admin/create-user` — protected by `ADMIN_SECRET` header
- `GET /login` — public, HTML page

**Endpoints to protect with JWT:**
- `POST /api/upload`, `GET /api/status/{job_id}`, `GET /api/download/{job_id}`, `DELETE /api/jobs/{job_id}`, `GET /api/jobs`

**Endpoints remaining public:**
- `POST /api/estimate`, `GET /api/health`, `GET /api/debug/ai`

**New env vars:** `SECRET_KEY` (required), `ADMIN_SECRET` (required), `ADMIN_USERNAME` (optional, default: `admin`), `ADMIN_PASSWORD` (optional, default: `changeme` — warn if unchanged)

### Claude's Discretion
- N/A (all decisions locked)

### Deferred Ideas (OUT OF SCOPE)
- Styled login page → Phase 5
- Password reset flow → not needed
- Multi-tenant org structure → not needed
- OAuth / SSO → not needed
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUTH-01 | Inspector can log in with username + password | `/api/auth/token` endpoint using OAuth2PasswordRequestForm, verified against User table with pwdlib |
| AUTH-02 | JWT token issued on login (8-hour session) | PyJWT 2.11.0 `jwt.encode()` with `exp` claim set to `now + 8h` |
| AUTH-03 | All upload/status/download endpoints require valid token | `Depends(get_current_user)` injected into each protected endpoint; 401 on missing/invalid/expired token |
| AUTH-04 | Admin can create new inspector accounts via protected endpoint | `POST /api/admin/create-user` checks `X-Admin-Secret` header against `ADMIN_SECRET` env var |
| AUTH-05 | Each job linked to the inspector who created it | `owner_id` FK column added to `jobs` table via startup migration; assigned at `save_new_job()` time |
</phase_requirements>

---

## Summary

Phase 3 adds JWT-based authentication to the BDDA FastAPI backend. The implementation is straightforward: PyJWT for token encoding/decoding, pwdlib[bcrypt] for password hashing, FastAPI's built-in OAuth2PasswordBearer for token extraction, and a raw SQL migration to add `owner_id` to the existing `jobs` table without Alembic.

The two critical gotchas for this stack are: (1) `python-jose` is abandoned — use `PyJWT` instead; (2) `passlib` is abandoned — use `pwdlib[bcrypt]` instead. Both are now reflected in FastAPI's official documentation. The SQLite schema migration requires a `PRAGMA table_info()` check because Render's SQLite (3.27.2) does not support `ADD COLUMN IF NOT EXISTS` (that requires 3.37.0+).

The silent token refresh (returning `X-New-Token` on responses) requires two things: (a) the refresh logic runs in the `get_current_user` dependency and attaches the new token to the request state, and (b) a middleware reads the request state and sets the response header — with the header added to `expose_headers` in the CORS config so browsers can read it.

**Primary recommendation:** Use PyJWT 2.11.0 + pwdlib[bcrypt] 0.3.0. Wire auth as a FastAPI dependency chain. Migrate schema via a raw SQL helper called inside `lifespan()` before `init_db()`.

---

## Standard Stack

### Core Auth Packages

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `PyJWT` | 2.11.0 (Jan 2026) | JWT encode/decode | Official FastAPI recommendation (replaced abandoned python-jose); actively maintained; simple API |
| `pwdlib[bcrypt]` | 0.3.0 (Oct 2025) | Password hashing | Official FastAPI replacement for abandoned passlib; Python 3.10+ native; supports bcrypt backend |
| `python-multipart` | already in requirements | Form data parsing for login | Required by FastAPI's OAuth2PasswordRequestForm; already installed |

### Packages to NOT Use (Abandoned)

| Library | Status | Replace With |
|---------|--------|-------------|
| `python-jose` | Abandoned ~3 years ago; no releases; security risk | `PyJWT` |
| `passlib` | Abandoned; incompatible with bcrypt 4.x+; breaks on Python 3.13+ | `pwdlib[bcrypt]` |

### No Additional Framework Needed

- No `fastapi-users` — overkill for a single-admin, small-team tool
- No `fastapi-jwt-auth` — adds complexity; core PyJWT is sufficient
- No `authlib` — OAuth2/OpenID scope beyond requirements

### Installation

```bash
pip install "PyJWT==2.11.0" "pwdlib[bcrypt]==0.3.0"
```

Add to `requirements.txt`:
```
PyJWT==2.11.0
pwdlib[bcrypt]==0.3.0
```

---

## Architecture Patterns

### Recommended File Layout

```
backend/
├── api.py              # existing — add new endpoints + protect existing
├── auth.py             # NEW — JWT utilities, password helpers, get_current_user
├── database.py         # existing — add User model, migrate_schema(), update save_new_job()
├── triage.py           # existing — unchanged
├── classify.py         # existing — unchanged
├── analyze.py          # existing — unchanged
├── taxonomy.py         # existing — unchanged
```

All auth logic goes in `auth.py`. Keep `database.py` for ORM models and CRUD only. Keep `api.py` thin — it wires together endpoints.

### Pattern 1: User ORM Model (in database.py)

```python
# Source: SQLAlchemy 2.0 DeclarativeBase pattern (already used in project)
import uuid as _uuid
from sqlalchemy import Column, String, Boolean, DateTime, func
from sqlalchemy.dialects.sqlite import TEXT  # UUID stored as TEXT in SQLite

class User(Base):
    __tablename__ = "users"

    id            = Column(String(36), primary_key=True, default=lambda: str(_uuid.uuid4()))
    username      = Column(String(64), unique=True, nullable=False, index=True)
    hashed_password = Column(Text, nullable=False)
    is_admin      = Column(Boolean, default=False, nullable=False)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
```

Note: Use `String(36)` for UUID in SQLite — SQLAlchemy's `Uuid` type maps to native UUID on Postgres but falls back to string on SQLite. Explicit `String(36)` is clearer for a SQLite-only project.

### Pattern 2: Schema Migration Without Alembic (in database.py)

SQLite 3.27.2 (Render's version) does NOT support `ADD COLUMN IF NOT EXISTS`. Use PRAGMA check:

```python
def migrate_schema(connection):
    """Add owner_id to jobs table if it doesn't already exist.

    Render runs SQLite 3.27.2 — no IF NOT EXISTS support on ADD COLUMN.
    Use PRAGMA table_info() to check first.
    """
    cursor = connection.cursor()
    # Check existing columns in jobs table
    cursor.execute("PRAGMA table_info(jobs)")
    columns = {row[1] for row in cursor.fetchall()}
    if "owner_id" not in columns:
        cursor.execute("ALTER TABLE jobs ADD COLUMN owner_id VARCHAR(36) REFERENCES users(id)")
        connection.commit()
    cursor.close()
```

Call this in `lifespan()` AFTER `init_db()`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()                    # create tables (User + Job)
    with engine.connect() as conn:
        migrate_schema(conn.connection.dbapi_connection)
    _seed_admin_user()           # seed admin if no users exist
    _mark_interrupted_jobs_failed()
    yield
```

Important: `init_db()` with `create_all()` creates `User` table and `jobs` table if they don't exist. The `migrate_schema()` only patches the existing `jobs` table. Order matters.

### Pattern 3: JWT Utilities (in auth.py)

```python
# Source: FastAPI official docs https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
import os
from datetime import datetime, timedelta, timezone
import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

SECRET_KEY = os.environ.get("SECRET_KEY", "")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 8
TOKEN_REFRESH_THRESHOLD_MINUTES = 60  # issue new token if <1h remaining

password_hash = PasswordHash.recommended()  # uses Argon2 by default with pwdlib[argon2]
# For bcrypt backend: PasswordHash((BcryptHasher(),))

def hash_password(plain: str) -> str:
    return password_hash.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return password_hash.verify(plain, hashed)

def create_token(username: str, user_id: str, is_admin: bool) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": username,
        "user_id": user_id,
        "is_admin": is_admin,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    """Raises jwt.exceptions.InvalidTokenError (includes ExpiredSignatureError) on failure."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
```

Note: `pwdlib[bcrypt]` vs `pwdlib[argon2]` — both are supported. The locked decision says "bcrypt-hashed in DB" (CONTEXT.md Area A), so use bcrypt. Install `pwdlib[bcrypt]` not `pwdlib[argon2]`.

### Pattern 4: get_current_user Dependency (in auth.py)

```python
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme)
) -> dict:
    """Extract and validate JWT. Attaches refresh token to request.state if needed."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
    except InvalidTokenError:
        raise credentials_exception

    username = payload.get("sub")
    user_id = payload.get("user_id")
    is_admin = payload.get("is_admin", False)
    if not username or not user_id:
        raise credentials_exception

    # Silent refresh: if token expires in <1h, mint a new one
    exp = payload.get("exp")
    if exp:
        remaining = datetime.fromtimestamp(exp, tz=timezone.utc) - datetime.now(timezone.utc)
        if remaining < timedelta(minutes=TOKEN_REFRESH_THRESHOLD_MINUTES):
            new_token = create_token(username, user_id, is_admin)
            request.state.new_token = new_token  # picked up by middleware

    return {"username": username, "user_id": user_id, "is_admin": is_admin}
```

### Pattern 5: Silent Refresh Middleware (in api.py)

```python
# MUST be added BEFORE CORSMiddleware to ensure header is present before CORS processing
@app.middleware("http")
async def attach_new_token_header(request: Request, call_next):
    response = await call_next(request)
    new_token = getattr(request.state, "new_token", None)
    if new_token:
        response.headers["X-New-Token"] = new_token
    return response
```

And update CORSMiddleware to expose the header:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-New-Token"],   # ADD THIS
)
```

**CRITICAL ORDER**: FastAPI middleware is applied in reverse registration order. Register the `attach_new_token_header` middleware AFTER CORSMiddleware in code (so it runs first on request, last on response — actually the reverse applies to middleware wrapping). The safe rule: add `expose_headers` to CORSMiddleware config and the `X-New-Token` header will pass through regardless of order.

### Pattern 6: Login Endpoint (in api.py)

```python
from fastapi.security import OAuth2PasswordRequestForm

@app.post("/api/auth/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login endpoint — accepts application/x-www-form-urlencoded (OAuth2 standard)."""
    user = get_user_by_username(form_data.username)  # CRUD from database.py
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_token(user["username"], user["id"], user["is_admin"])
    return {"access_token": token, "token_type": "bearer"}
```

Note: `OAuth2PasswordRequestForm` expects `Content-Type: application/x-www-form-urlencoded` — the login HTML form must NOT use `application/json`. Use a plain HTML `<form>` or `fetch()` with `FormData`.

### Pattern 7: Protecting Endpoints

```python
# Protected endpoint — simple injection
@app.post("/api/upload")
async def upload_inspection(
    current_user: dict = Depends(get_current_user),
    # ... other params
):
    # current_user is {"username": ..., "user_id": ..., "is_admin": ...}
    owner_id = current_user["user_id"]
```

```python
# Ownership check pattern
@app.get("/api/status/{job_id}")
async def get_status(job_id: str, current_user: dict = Depends(get_current_user)):
    state = get_job(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")

    # Ownership enforcement
    if not current_user["is_admin"]:
        if state.get("owner_id") != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="Access forbidden")

    # ... rest of response
```

### Pattern 8: Admin-Secret Protected Endpoint

```python
from fastapi import Header

ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "")

@app.post("/api/admin/create-user")
async def create_user(
    username: str = Form(...),
    password: str = Form(...),
    is_admin: bool = Form(False),
    x_admin_secret: Optional[str] = Header(None),
):
    if not ADMIN_SECRET or x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    # create user...
```

Note: FastAPI automatically converts the `X-Admin-Secret` header to the `x_admin_secret` parameter (hyphen → underscore, lowercase). The caller sends the header as `X-Admin-Secret: <value>`.

### Pattern 9: Admin Auto-Seed (in lifespan)

```python
def _seed_admin_user():
    """Seed admin user on first deploy if no users exist."""
    admin_username = os.environ.get("ADMIN_USERNAME", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD", "changeme")

    if admin_password == "changeme":
        import logging
        logging.warning("ADMIN_PASSWORD is set to default 'changeme' — change it in production!")

    with get_db() as session:
        existing = session.scalars(select(User)).first()
        if existing is None:
            admin = User(
                id=str(uuid.uuid4()),
                username=admin_username,
                hashed_password=hash_password(admin_password),
                is_admin=True,
            )
            session.add(admin)
            session.commit()
```

### Pattern 10: Login HTML Page

Serve as a FastAPI endpoint returning `HTMLResponse`:

```python
from fastapi.responses import HTMLResponse

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    # Return self-contained HTML string or read from templates/login.html
    return HTMLResponse(content=LOGIN_HTML)
```

The login HTML must:
- Submit to `POST /api/auth/token` as `application/x-www-form-urlencoded` (form fields: `username`, `password`)
- On success: store token in `localStorage`, redirect to `/` (or `?next=` param)
- On failure: show inline error message

```javascript
// Fetch pattern for login form
const formData = new FormData(form);
const resp = await fetch('/api/auth/token', {
    method: 'POST',
    body: new URLSearchParams(formData),  // converts to x-www-form-urlencoded
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
});
```

### Anti-Patterns to Avoid

- **Using python-jose**: Abandoned; do NOT use even if tutorials suggest it
- **Using passlib**: Abandoned; breaks with bcrypt 4.x+; do NOT use
- **Storing owner_id as Integer FK**: CONTEXT.md specifies UUID string — use `String(36)` FK
- **JWT in sessionStorage or cookies**: CONTEXT.md specifies `localStorage` — use that
- **Using Depends(get_db) for auth endpoint alongside sync SQLAlchemy**: The existing codebase uses context manager pattern (`with get_db() as session`), not the `Depends(get_db)` yield pattern — stay consistent with this project's convention
- **Registering auth endpoints after StaticFiles mount**: The static file mount (`app.mount("/", ...)`) must be LAST — all API routes must be registered before it. Adding new auth routes before the static mount is critical.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JWT encode/decode | Custom base64+hmac | `PyJWT` | Handles exp, iat, algorithm selection, timing attack resistance |
| Password hashing | Custom SHA/MD5 | `pwdlib[bcrypt]` | Bcrypt work factor, salt, future algorithm migration |
| Bearer token extraction | Manual `Authorization` header parsing | `OAuth2PasswordBearer` | Handles "Bearer " prefix stripping, returns 401 automatically if missing |
| Form data parsing | Manual request body reading | `OAuth2PasswordRequestForm` | Standard OAuth2 form fields, auto-validated by FastAPI |

---

## Common Pitfalls

### Pitfall 1: Static Mount Overrides API Routes

**What goes wrong:** The existing `app.mount("/", StaticFiles(...), html=True)` catches ALL requests that don't match API routes. If a new route is registered AFTER the mount, FastAPI never reaches it.

**Why it happens:** `mount()` acts as a catch-all wildcard. FastAPI routes are checked in registration order.

**How to avoid:** Register `/login` route and all auth routes BEFORE `app.mount("/", ...)`. The mount must remain the last line of route registration.

**Warning signs:** 404 or wrong response for `/login`, or getting the frontend HTML when hitting `/api/auth/token`.

### Pitfall 2: CORSMiddleware Blocks X-New-Token Header

**What goes wrong:** Frontend JavaScript can't read the `X-New-Token` response header despite it being set.

**Why it happens:** Browsers block access to custom response headers unless explicitly listed in `expose_headers` in the CORS config.

**How to avoid:** Add `expose_headers=["X-New-Token"]` to `CORSMiddleware`.

**Warning signs:** `response.headers.get('X-New-Token')` returns `null` in browser JS even though the header shows in DevTools Network tab.

### Pitfall 3: SQLite ADD COLUMN IF NOT EXISTS Not Supported on Render

**What goes wrong:** `ALTER TABLE jobs ADD COLUMN IF NOT EXISTS owner_id ...` raises `OperationalError` on Render.

**Why it happens:** Render's native environment uses SQLite 3.27.2; `IF NOT EXISTS` support for `ADD COLUMN` requires SQLite 3.37.0+.

**How to avoid:** Use `PRAGMA table_info(jobs)` to check if the column exists before running `ALTER TABLE`.

**Warning signs:** Deploy works locally (newer SQLite) but fails on Render at startup.

### Pitfall 4: OAuth2PasswordRequestForm Requires Form Encoding

**What goes wrong:** Login returns 422 Unprocessable Entity when posting JSON.

**Why it happens:** `OAuth2PasswordRequestForm` expects `application/x-www-form-urlencoded`, not `application/json`.

**How to avoid:** The login HTML form must use `new URLSearchParams(formData)` as the body, not `JSON.stringify()`. Set `Content-Type: application/x-www-form-urlencoded`.

**Warning signs:** 422 error with "value is not a valid string" in the response.

### Pitfall 5: Existing Jobs with NULL owner_id

**What goes wrong:** Inspector can't see any pre-Phase-3 jobs; admin can see them but inspectors get confused.

**Why it happens:** `owner_id` is nullable (by design) — existing jobs were created before auth existed.

**How to avoid:** This is the intended behavior (CONTEXT.md Area B). The filter query must handle NULL explicitly:
```python
# Inspector filter: owner_id == current_user.id (NULL rows excluded)
where(Job.owner_id == current_user["user_id"])
# Admin filter: no filter (sees everything including NULL owner_id rows)
```

**Warning signs:** Inspector sees all jobs (forgot WHERE clause) or admin can't see old jobs (accidentally filtered NULLs).

### Pitfall 6: SECRET_KEY Empty in Dev

**What goes wrong:** JWT operations silently use an empty key, producing tokens that appear valid but are insecure.

**How to avoid:** At startup, log a warning if `SECRET_KEY` is empty or shorter than 32 characters. In `auth.py`:
```python
if not SECRET_KEY or len(SECRET_KEY) < 32:
    import logging
    logging.warning("SECRET_KEY is not set or too short — JWT tokens are insecure!")
```

**Warning signs:** All JWTs are accepted even after rotating the key (sign/verify always succeeds against empty string).

### Pitfall 7: Sync SQLAlchemy + Depends(get_db) Deadlock

**What goes wrong:** Under load, requests deadlock because sync DB sessions block thread pool workers, preventing other sessions from releasing connections.

**Why it happens:** The existing project uses context manager pattern (`with get_db() as session`) deliberately. The `Depends(get_db)` yield pattern with sync SQLAlchemy can deadlock.

**How to avoid:** For auth endpoints, keep the same `with get_db() as session` pattern used everywhere else in this codebase. Do not introduce `Depends(get_db)` yield pattern.

---

## Code Examples

### Full get_current_user with silent refresh
```python
# Source: FastAPI docs pattern adapted for this project
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme)
) -> dict:
    try:
        payload = decode_token(token)
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    user_id = payload.get("user_id")
    is_admin = payload.get("is_admin", False)

    if not username or not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # Silent refresh if <1h remaining
    exp = payload.get("exp")
    if exp:
        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
        remaining = exp_dt - datetime.now(timezone.utc)
        if remaining < timedelta(minutes=60):
            request.state.new_token = create_token(username, user_id, is_admin)

    return {"username": username, "user_id": user_id, "is_admin": is_admin}
```

### PRAGMA migration check
```python
def _column_exists(conn, table: str, column: str) -> bool:
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cursor.fetchall()}
    cursor.close()
    return column in cols

def migrate_schema():
    with engine.connect() as conn:
        raw = conn.connection.dbapi_connection
        if not _column_exists(raw, "jobs", "owner_id"):
            raw.execute("ALTER TABLE jobs ADD COLUMN owner_id VARCHAR(36) REFERENCES users(id)")
            raw.commit()
```

### Frontend localStorage token pattern
```javascript
// Store on login
localStorage.setItem('bdda_token', data.access_token);

// Send on every request
const token = localStorage.getItem('bdda_token');
const resp = await fetch('/api/jobs', {
    headers: { 'Authorization': `Bearer ${token}` }
});

// Check for silent refresh
const newToken = resp.headers.get('X-New-Token');
if (newToken) localStorage.setItem('bdda_token', newToken);

// Handle 401
if (resp.status === 401) {
    localStorage.removeItem('bdda_token');
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `python-jose` for JWT | `PyJWT` | 2024 (FastAPI docs updated PR #11589) | Drop python-jose entirely; PyJWT has simpler API |
| `passlib[bcrypt]` | `pwdlib[bcrypt]` | 2024-2025 (FastAPI docs updated) | passlib breaks on Python 3.13+; pwdlib is the official successor |
| `@app.on_event("startup")` | `lifespan` context manager | FastAPI 0.95.0 (2023) | Already used in this project's api.py — continue using it |
| `session.query()` ORM style | `select()` + `session.scalars()` | SQLAlchemy 2.0 (2023) | Already used in this project — continue with this pattern |

**Deprecated/outdated:**
- `python-jose`: Last release ~3 years ago; security library with no active maintenance is unacceptable
- `passlib`: AttributeError with bcrypt 4.x; Python 3.13 crypt module removal breaks it
- `@app.on_event("startup")`: Functional but deprecated; project already uses `lifespan`

---

## Open Questions

1. **pwdlib bcrypt vs argon2 backend**
   - What we know: CONTEXT.md says "bcrypt-hashed in DB"; pwdlib supports both
   - What's unclear: `PasswordHash.recommended()` defaults to argon2, not bcrypt. To get bcrypt, import explicitly: `from pwdlib.hashers.bcrypt import BcryptHasher; PasswordHash((BcryptHasher(),))`
   - Recommendation: Use bcrypt as locked in CONTEXT.md. The install is `pwdlib[bcrypt]`. Be explicit in code.

2. **Render SQLite 3.27.2 confirmation**
   - What we know: Multiple Render community posts confirm 3.27.2; Render hasn't upgraded native SQLite as of late 2023
   - What's unclear: Whether Render has upgraded since (they mentioned "working on it")
   - Recommendation: Write the PRAGMA-based migration defensively regardless. If Render upgraded, `PRAGMA table_info()` still works fine on any SQLite version.

3. **Middleware ordering for X-New-Token**
   - What we know: FastAPI ASGI middleware is applied in reverse order of `add_middleware()` calls
   - What's unclear: Exact interaction with the `@app.middleware("http")` decorator approach
   - Recommendation: Add `expose_headers=["X-New-Token"]` to CORSMiddleware and test in browser DevTools to confirm header is readable. The implementation is correct regardless of middleware order — the header is set on the response object directly.

---

## Env Vars — Render Configuration

Add these to `render.yaml` under the service's `envVars`:

```yaml
- key: SECRET_KEY
  sync: false          # Prompted in Dashboard on first deploy; never committed to git
- key: ADMIN_SECRET
  sync: false          # Same — set manually in Render Dashboard
- key: ADMIN_USERNAME
  value: admin         # Non-secret, safe to commit
- key: ADMIN_PASSWORD
  sync: false          # Secret — set in Dashboard
```

**Generate SECRET_KEY locally:**
```bash
openssl rand -hex 32
# Example output: a3f2b1c9d8e7f6054321abcdef123456fedcba9876543210a1b2c3d4e5f60789
```

**Render env var notes:**
- No size limitations for string env vars on any tier (only secret files capped at 1MB)
- `sync: false` env vars are set once in Dashboard; Blueprint updates do NOT overwrite them
- Environment variables are available immediately at runtime — no restart needed after Dashboard update
- Free tier and paid tier have identical env var behavior

---

## Sources

### Primary (HIGH confidence)
- FastAPI official docs — https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/ — JWT + password hashing patterns; confirmed PyJWT + pwdlib as current recommendations
- PyJWT PyPI — https://pypi.org/project/PyJWT/ — Version 2.11.0 (Jan 2026), Python 3.9+ compatible
- pwdlib PyPI — https://pypi.org/project/pwdlib/ — Version 0.3.0 (Oct 2025), Python 3.10+ compatible
- FastAPI official docs — https://fastapi.tiangolo.com/tutorial/middleware/ — Middleware response header pattern
- FastAPI official docs — https://fastapi.tiangolo.com/tutorial/cors/ — expose_headers configuration
- Render Docs — https://render.com/docs/configure-environment-variables — sync: false env var pattern

### Secondary (MEDIUM confidence)
- GitHub discussion fastapi/fastapi #11345 — Confirmed FastAPI team switched from python-jose to PyJWT (PR #11589 merged)
- GitHub discussion fastapi/fastapi #11773 — Confirmed passlib deprecated, pwdlib recommended as replacement
- Render community forum — https://community.render.com/t/any-chance-of-choosing-or-upgrading-the-sqlite3-version/17282 — Render SQLite 3.27.2 confirmed; IF NOT EXISTS not available

### Tertiary (LOW confidence)
- Render community SQLite posts from 2023 — SQLite version may have been updated since; verify at runtime with `import sqlite3; sqlite3.sqlite_version`

---

## Metadata

**Confidence breakdown:**
- Standard stack (PyJWT + pwdlib): HIGH — verified against official FastAPI docs and PyPI release dates
- Architecture patterns: HIGH — based on FastAPI official docs patterns
- SQLite migration: HIGH — PRAGMA table_info() is valid on all SQLite versions including 3.27.2
- Render env vars: HIGH — official Render docs confirmed
- Render SQLite version: MEDIUM — community posts from 2023; may be outdated

**Research date:** 2026-03-06
**Valid until:** 2026-06-06 (90 days — FastAPI and PyJWT are stable; pwdlib is newer but unlikely to change API)
