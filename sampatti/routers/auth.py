# routers/auth.py (unchanged)
import os
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from ..auth import create_access_token, Token

from ..auth import create_access_token, Token

router = APIRouter(prefix="/auth", tags=["auth"])

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
