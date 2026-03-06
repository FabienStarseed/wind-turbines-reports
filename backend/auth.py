"""
auth.py — JWT token utilities and password hashing for BDDA.

Libraries (per RESEARCH.md):
- PyJWT 2.11.0: JWT encode/decode (NOT python-jose — abandoned)
- pwdlib[bcrypt] 0.3.0: password hashing (NOT passlib — breaks with bcrypt 4.x+)

CRITICAL: Use PasswordHash((BcryptHasher(),)) — NOT PasswordHash.recommended()
which defaults to Argon2. CONTEXT.md Area A locks bcrypt as the hash algorithm.
"""
import logging
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

# ── CONSTANTS ─────────────────────────────────────────────────────────────────

SECRET_KEY = os.environ.get("SECRET_KEY", "")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 8           # per CONTEXT.md Area C
TOKEN_REFRESH_THRESHOLD_MINUTES = 60  # silent refresh when <1h remaining

# Warn at module load if SECRET_KEY is missing or too short
if not SECRET_KEY or len(SECRET_KEY) < 32:
    logging.warning(
        "SECRET_KEY is not set or shorter than 32 characters — JWT tokens are insecure! "
        "Set SECRET_KEY env var to a 32-byte hex string: openssl rand -hex 32"
    )

# ── PASSWORD HASHING ──────────────────────────────────────────────────────────
# Use BcryptHasher explicitly — PasswordHash.recommended() defaults to Argon2
# which requires the argon2-cffi extra, not the bcrypt extra.

password_hash = PasswordHash((BcryptHasher(),))


def hash_password(plain: str) -> str:
    """Hash a plain-text password with bcrypt. Returns the hashed string."""
    return password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash. Returns True if match."""
    return password_hash.verify(plain, hashed)


# ── JWT UTILITIES ─────────────────────────────────────────────────────────────

def create_token(username: str, user_id: str, is_admin: bool) -> str:
    """Issue a signed JWT with 8-hour expiry.

    Payload (per CONTEXT.md Area C):
      sub      — username (standard JWT subject claim)
      user_id  — UUID string from User.id
      is_admin — bool
      exp      — expiry timestamp (UTC)
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": username,
        "user_id": user_id,
        "is_admin": is_admin,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises jwt.exceptions.InvalidTokenError on failure.

    InvalidTokenError covers ExpiredSignatureError, DecodeError, InvalidSignatureError, etc.
    Caller (get_current_user) catches this and raises HTTP 401.
    """
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# ── FASTAPI DEPENDENCY ────────────────────────────────────────────────────────

# tokenUrl tells the OpenAPI UI where to get tokens (also used by OAuth2 flow).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
) -> dict:
    """FastAPI dependency: validates JWT and returns user context dict.

    Returns: {"username": str, "user_id": str, "is_admin": bool}

    Silent refresh (per CONTEXT.md Area C): if the token has less than 60 minutes
    remaining, a new token is minted and attached to request.state.new_token.
    The attach_new_token_header middleware in api.py reads this and sets
    the X-New-Token response header so the frontend can silently update its copy.

    Raises HTTP 401 on missing, expired, or invalid token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(token)
    except InvalidTokenError:
        raise credentials_exception

    username: str = payload.get("sub", "")
    user_id: str = payload.get("user_id", "")
    is_admin: bool = payload.get("is_admin", False)

    if not username or not user_id:
        raise credentials_exception

    # Silent refresh: mint new token if less than 60 minutes remain
    exp = payload.get("exp")
    if exp:
        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
        remaining = exp_dt - datetime.now(timezone.utc)
        if remaining < timedelta(minutes=TOKEN_REFRESH_THRESHOLD_MINUTES):
            request.state.new_token = create_token(username, user_id, is_admin)

    return {"username": username, "user_id": user_id, "is_admin": is_admin}
