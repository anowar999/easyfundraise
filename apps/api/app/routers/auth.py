"""AUTH-01/02/07: Google sign-in (openid email profile only at signup), sessions, dev login."""

import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import create_session, current_user, destroy_session
from ..errors import ApiError
from ..models import User, Workspace, WorkspaceMember
from ..services.entitlements import limit

router = APIRouter(prefix="/auth", tags=["auth"])
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
DISPOSABLE = {"mailinator.com", "10minutemail.com", "guerrillamail.com", "tempmail.com", "yopmail.com"}


def upsert_user(db: Session, email: str, name: str, picture: str = "", sub: str | None = None,
                tz: str = "UTC") -> User:
    email = email.lower()
    if email.split("@")[-1] in DISPOSABLE:  # ASP-09
        raise ApiError(403, "EF-AUTH-030", "Disposable email domains are not allowed")
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, name=name or email.split("@")[0], picture=picture, google_sub=sub, timezone=tz)
        db.add(user)
        db.flush()
        ws = Workspace(name=f"{user.name.split()[0]}'s raise", tier_code="trial")
        db.add(ws)
        db.flush()
        days = limit(db, ws, "trial_days") or 14
        ws.trial_ends_at = datetime.now(UTC) + timedelta(days=days)
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    else:
        user.name, user.picture = name or user.name, picture or user.picture
        user.google_sub = user.google_sub or sub
    if email in get_settings().admin_email_set:
        user.is_admin = True
    db.commit()
    return user


@router.get("/config")
def auth_config():
    s = get_settings()
    return {"google": bool(s.google_client_id), "dev_login": s.dev_login_enabled}


@router.get("/google/start")
def google_start(request: Request):
    s = get_settings()
    if not s.google_client_id:
        raise ApiError(503, "EF-AUTH-040", "Google sign-in is not configured")
    state = secrets.token_urlsafe(24)
    params = dict(client_id=s.google_client_id, response_type="code", scope="openid email profile",
                  redirect_uri=f"{s.web_origin}/api/auth/google/callback", state=state, prompt="select_account")
    resp = RedirectResponse(f"{GOOGLE_AUTH}?{urlencode(params)}")
    resp.set_cookie("ef_oauth_state", state, max_age=600, httponly=True, samesite="lax", secure=s.env != "dev")
    return resp


@router.get("/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", db: Session = Depends(get_db)):
    s = get_settings()
    if not code or not state or state != request.cookies.get("ef_oauth_state"):
        raise ApiError(400, "EF-AUTH-041", "Sign-in failed", "Invalid OAuth state. Please try again.")
    with httpx.Client(timeout=10) as c:
        tok = c.post(GOOGLE_TOKEN, data=dict(code=code, client_id=s.google_client_id,
                                             client_secret=s.google_client_secret, grant_type="authorization_code",
                                             redirect_uri=f"{s.web_origin}/api/auth/google/callback"))
        if tok.status_code != 200:
            raise ApiError(400, "EF-AUTH-042", "Sign-in failed", "Google rejected the sign-in code.")
        info = c.get(GOOGLE_USERINFO, headers={"Authorization": f"Bearer {tok.json()['access_token']}"}).json()
    if not info.get("email_verified"):
        raise ApiError(403, "EF-AUTH-043", "Google email is not verified")
    user = upsert_user(db, info["email"], info.get("name", ""), info.get("picture", ""), info.get("sub"))
    resp = RedirectResponse(f"{s.web_origin}/app")
    resp.delete_cookie("ef_oauth_state")
    create_session(db, resp, user, request.headers.get("user-agent", ""))
    return resp


class DevLogin(BaseModel):
    email: EmailStr
    name: str = ""
    timezone: str = "UTC"


@router.post("/dev-login")
def dev_login(body: DevLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    if not get_settings().dev_login_enabled:
        raise ApiError(404, "EF-NF-001", "Not found")
    user = upsert_user(db, body.email, body.name, tz=body.timezone)
    create_session(db, response, user, request.headers.get("user-agent", ""))
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    destroy_session(db, request, response)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Workspace, WorkspaceMember.role).join(WorkspaceMember)
                      .where(WorkspaceMember.user_id == user.id).order_by(Workspace.created_at)).all()
    return {
        "id": str(user.id), "email": user.email, "name": user.name, "picture": user.picture,
        "timezone": user.timezone, "is_admin": user.is_admin, "signature": user.signature,
        "workspaces": [{"id": str(w.id), "name": w.name, "role": r, "tier": w.tier_code} for w, r in rows],
    }
