# auth.py (drop-in replacement)
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

# === Config ===
SECRET_KEY = os.getenv("JWT_SECRET") or os.getenv("SECRET_KEY") or ""
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

# Back-compat toggles (all optional; keep them unset in prod if you want strict auth)
LEGACY_ALLOW_NOAUTH = os.getenv("LEGACY_ALLOW_NOAUTH", "false").lower() == "true"
# Comma-separated list of allowed path prefixes, e.g. "/user/send_,/user/generate_"
LEGACY_PATH_PREFIXES: List[str] = [p.strip() for p in os.getenv("LEGACY_PATH_PREFIXES", "").split(",") if p.strip()]
# Comma-separated list of exact IPs allowed (e.g. cron hosts); keep empty to allow none
LEGACY_IP_ALLOWLIST: List[str] = [ip.strip() for ip in os.getenv("LEGACY_IP_ALLOWLIST", "").split(",") if ip.strip()]

if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET (or SECRET_KEY) must be set")

# OAuth2 password flow so Swagger shows the login UI.
# auto_error=False lets us handle the “no token provided” case for legacy callers.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    now = datetime.now(timezone.utc)
    exp = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = {**data, "exp": int(exp.timestamp())}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

def _legacy_allowed(request: Request) -> bool:
    if not LEGACY_ALLOW_NOAUTH:
        return False
    # Path prefix check (restrict legacy to specific endpoints)
    if LEGACY_PATH_PREFIXES:
        path_ok = any(request.url.path.startswith(p) for p in LEGACY_PATH_PREFIXES)
        if not path_ok:
            return False
    # IP allowlist check (exact match; keep empty to skip)
    if LEGACY_IP_ALLOWLIST:
        client_ip = (request.client.host if request.client else None)
        if client_ip not in LEGACY_IP_ALLOWLIST:
            return False
    return True

async def get_current_user(request: Request, token: Optional[str] = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    Backward-compatible auth:
    - If Bearer token present -> enforce JWT.
    - If missing -> allow only if LEGACY_* env rules permit; otherwise 401.
    """
    if token:
        return decode_token(token)

    if _legacy_allowed(request):
        # Minimal pseudo-user for legacy calls; downstream code can read `sub`.
        return {"sub": "legacy", "auth": "legacy"}

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)
