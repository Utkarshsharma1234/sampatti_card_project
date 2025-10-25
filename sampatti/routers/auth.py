# routers/auth.py (unchanged)
import os
from datetime import timedelta
import time
import requests
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from ..auth import create_access_token, Token

from ..auth import create_access_token, Token

router = APIRouter(prefix="/auth", tags=["auth"])

# Configure via env
API_BASE = os.getenv("API_BASE", "https://conv.sampatticards.com")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SERVICE_TOKEN = os.getenv("SERVICE_TOKEN")  # optional pre-generated JWT

# Internal cache
_TOKEN: Optional[str] = None
_EXP: float = 0  # epoch seconds

@router.get("/login", response_class=HTMLResponse)
def login_form():
    # Optional: a simple HTML form so you can open /auth/login in a browser.
    # For Swagger-based login, use /docs instead.
    return """
<!doctype html>
<html>
  <body>
    <h3>Login (manual test)</h3>
    <form method="post" action="/auth/login">
      <label>Username: <input name="username" /></label><br/>
      <label>Password: <input name="password" type="password" /></label><br/>
      <button type="submit">Login</button>
    </form>
    <p>Tip: For the Swagger “Authorize” flow, go to <a href="/docs">/docs</a>.</p>
  </body>
</html>
    """

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    POST only. Swagger's Authorize uses this endpoint.
    Requires ADMIN_USERNAME and ADMIN_PASSWORD in env.
    """
    admin_user = os.getenv("ADMIN_USERNAME")
    admin_pass = os.getenv("ADMIN_PASSWORD")

    if not admin_user or not admin_pass:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Admin credentials not configured")

    if form_data.username != admin_user or form_data.password != admin_pass:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Incorrect username or password")

    access_token = create_access_token({"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}

def _login_and_get_token() -> str:
    """Login via /auth/login and return access token."""
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        raise RuntimeError("ADMIN_USERNAME/ADMIN_PASSWORD not set for auth_session")
    r = requests.post(
        f"{API_BASE}/auth/login",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    return data["access_token"]

def _current_token() -> str:
    """Return a valid token (SERVICE_TOKEN if provided, else cached login token)."""
    global _TOKEN, _EXP
    # Prefer SERVICE_TOKEN if you set it
    if SERVICE_TOKEN:
        return SERVICE_TOKEN

    now = time.time()
    if _TOKEN and now < _EXP - 30:  # reuse until ~30s before expiry
        return _TOKEN

    _TOKEN = _login_and_get_token()
    # Default API expiry is 60 mins; refresh slightly early
    _EXP = now + 55 * 60
    return _TOKEN

def get_auth_headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Return Authorization header dict that you can pass to requests.* calls.
    Usage: requests.get(url, headers=get_auth_headers(), ...)
    """
    hdrs = {"Authorization": f"Bearer {_current_token()}"}
    if extra:
        hdrs.update(extra)
    return hdrs

def authed_get(path_or_url: str, *, params=None, headers=None, timeout=30, absolute=False, **kw):
    """
    Convenience wrapper around requests.get with Authorization.
    - path_or_url: "/user/check_worker" or full URL
    - absolute=False means we join with API_BASE
    Retries once on 401 by refreshing token.
    """
    url = path_or_url if (absolute or path_or_url.startswith("http")) else f"{API_BASE}{path_or_url}"
    hdrs = get_auth_headers(headers or {})
    resp = requests.get(url, params=params, headers=hdrs, timeout=timeout, **kw)
    if resp.status_code == 401 and not SERVICE_TOKEN:
        # token might have expired; refresh and retry once
        # force refresh by zeroing the cache
        global _TOKEN, _EXP
        _TOKEN, _EXP = None, 0
        hdrs = get_auth_headers(headers or {})
        resp = requests.get(url, params=params, headers=hdrs, timeout=timeout, **kw)
    resp.raise_for_status()
    return resp

def authed_post(path_or_url: str, *, json=None, data=None, params=None, headers=None, timeout=30, absolute=False, **kw):
    """
    Convenience wrapper around requests.post with Authorization.
    Retries once on 401 by refreshing token.
    """
    url = path_or_url if (absolute or path_or_url.startswith("http")) else f"{API_BASE}{path_or_url}"
    hdrs = get_auth_headers(headers or {})
    resp = requests.post(url, json=json, data=data, params=params, headers=hdrs, timeout=timeout, **kw)
    if resp.status_code == 401 and not SERVICE_TOKEN:
        global _TOKEN, _EXP
        _TOKEN, _EXP = None, 0
        hdrs = get_auth_headers(headers or {})
        resp = requests.post(url, json=json, data=data, params=params, headers=hdrs, timeout=timeout, **kw)
    resp.raise_for_status()
    return resp

