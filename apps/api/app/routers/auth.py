"""AUTH-01/02/07: Google sign-in (with optional Gmail consent in the same step), email sign-in links,
sessions, dev login."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlencode

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import COOKIE, _hash, client_ip, create_session, current_user, destroy_session
from ..errors import ApiError
from ..models import AuthSession, GmailAccount, User, Workspace, WorkspaceMember
from ..services.account_mail import read_sign_in_token, send_sign_in_link, sign_in_token, smtp_ready
from ..services.crypto import decrypt, encrypt, totp_ok, totp_secret
from ..services.entitlements import limit, rate_limit
from ..services.gmail import SCOPES, store_tokens

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


def safe_next(path: str, default: str = "/app") -> str:
    """Only same-site paths, so a crafted link can't bounce a signed-in user to another site."""
    return path if path.startswith("/") and not path.startswith("//") and "\\" not in path else default


def after_sign_in(db: Session, user: User, is_new: bool, next: str) -> str:
    """New users without Gmail go to the welcome step that asks for send permission."""
    if is_new and db.get(GmailAccount, user.id) is None:
        return f"/welcome?next={quote(next, safe='')}"
    return next


def is_new_user(db: Session, email: str) -> bool:
    return db.scalar(select(User.id).where(User.email == email.lower())) is None


@router.get("/config")
def auth_config():
    s = get_settings()
    return {"google": bool(s.google_client_id), "dev_login": s.dev_login_enabled,
            "email_link": smtp_ready() or not s.is_prod, "gmail_fake": s.gmail_fake}


@router.get("/google/start")
def google_start(request: Request, gmail: bool = True, next: str = "/app"):
    """AUTH-01/02: sign in with Google. With gmail=1 the same consent screen also asks to send from Gmail
    (and read replies to stop follow-ups); the user can untick those and connect later."""
    s = get_settings()
    if not s.google_client_id:
        raise ApiError(503, "EF-AUTH-040", "Google sign-in is not configured")
    state = secrets.token_urlsafe(24)
    params = dict(client_id=s.google_client_id, response_type="code", scope="openid email profile",
                  redirect_uri=f"{s.web_origin}/api/auth/google/callback", state=state, prompt="select_account")
    if gmail and not s.gmail_fake:
        params.update(scope=f"openid email profile {SCOPES}", access_type="offline", include_granted_scopes="true",
                      prompt="consent select_account")
    resp = RedirectResponse(f"{GOOGLE_AUTH}?{urlencode(params)}")
    secure = s.env != "dev"
    resp.set_cookie("ef_oauth_state", state, max_age=600, httponly=True, samesite="lax", secure=secure)
    resp.set_cookie("ef_oauth_next", safe_next(next), max_age=600, httponly=True, samesite="lax", secure=secure)
    return resp


@router.get("/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    s = get_settings()
    if error:  # the user pressed Cancel on Google's screen
        return RedirectResponse(f"{s.web_origin}/login?error=cancelled")
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
    is_new = is_new_user(db, info["email"])
    user = upsert_user(db, info["email"], info.get("name", ""), info.get("picture", ""), info.get("sub"))
    j = tok.json()
    if "gmail.send" in j.get("scope", ""):
        store_tokens(db, user.id, user.email, j)
        db.commit()
    resp = RedirectResponse(f"{s.web_origin}{after_sign_in(db, user, is_new, safe_next(request.cookies.get('ef_oauth_next', '')))}")
    resp.delete_cookie("ef_oauth_state")
    resp.delete_cookie("ef_oauth_next")
    create_session(db, resp, user, request.headers.get("user-agent", ""), client_ip(request))
    return resp


class EmailStart(BaseModel):
    email: EmailStr
    next: str = "/app"


@router.post("/email/start")
def email_start(body: EmailStart, request: Request, db: Session = Depends(get_db)):
    """Passwordless sign-in: email a link that works for 15 minutes. Without SMTP (dev only) the link is returned."""
    s = get_settings()
    rate_limit(db, f"signin-ip:{client_ip(request)}", 10, 600)
    rate_limit(db, f"signin-email:{body.email.lower()}", 5, 600)
    if body.email.split("@")[-1].lower() in DISPOSABLE:
        raise ApiError(403, "EF-AUTH-030", "Disposable email domains are not allowed")
    link = (f"{s.web_origin}/api/auth/email/verify?"
            f"{urlencode({'token': sign_in_token(body.email), 'next': safe_next(body.next)})}")
    if smtp_ready():
        try:
            send_sign_in_link(body.email, link)
        except OSError as e:
            raise ApiError(502, "EF-AUTH-051", "We couldn't send the email", "Please try again in a minute.") from e
        return {"sent": True}
    if s.is_prod:
        raise ApiError(503, "EF-AUTH-050", "Email sign-in is not configured")
    return {"sent": False, "dev_link": link}


@router.get("/email/verify")
def email_verify(request: Request, token: str = "", next: str = "/app", db: Session = Depends(get_db)):
    s = get_settings()
    email = read_sign_in_token(token)
    if not email:
        return RedirectResponse(f"{s.web_origin}/login?error=expired")
    is_new = is_new_user(db, email)
    user = upsert_user(db, email, "")
    resp = RedirectResponse(f"{s.web_origin}{after_sign_in(db, user, is_new, safe_next(next))}")
    create_session(db, resp, user, request.headers.get("user-agent", ""), client_ip(request))
    return resp


class DevLogin(BaseModel):
    email: EmailStr
    name: str = ""
    timezone: str = "UTC"
    next: str = "/app"


@router.post("/dev-login")
def dev_login(body: DevLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    if not get_settings().dev_login_enabled:
        raise ApiError(404, "EF-NF-001", "Not found")
    is_new = is_new_user(db, body.email)
    user = upsert_user(db, body.email, body.name, tz=body.timezone)
    create_session(db, response, user, request.headers.get("user-agent", ""), client_ip(request))
    return {"ok": True, "next": after_sign_in(db, user, is_new, safe_next(body.next))}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    destroy_session(db, request, response)
    return {"ok": True}


@router.get("/sessions")
def sessions(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """AUTH-07 device list."""
    mine = _hash(request.cookies.get(COOKIE, ""))
    rows = db.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.expires_at > datetime.now(UTC))
                      .order_by(AuthSession.created_at.desc())).all()
    return {"items": [{"id": str(s.id), "device": s.user_agent[:160], "ip": s.ip, "created_at": s.created_at,
                       "last_seen_at": s.last_seen_at, "current": s.token_hash == mine} for s in rows]}


@router.delete("/sessions/{sid}")
def revoke_session(sid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = db.get(AuthSession, uuid.UUID(sid))
    if s is None or s.user_id != user.id:
        raise ApiError(404, "EF-NF-001", "Not found")
    db.delete(s)
    db.commit()
    return {"ok": True}


# ---- AUTH-08 admin MFA (TOTP) ----


@router.post("/mfa/setup")
def mfa_setup(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.is_admin:
        raise ApiError(403, "EF-AUTH-010", "Admin only")
    if user.totp_secret_enc:
        raise ApiError(409, "EF-AUTH-050", "Two-factor is already set up")
    secret = totp_secret()
    user.totp_secret_enc = encrypt(f"pending:{secret}")
    db.commit()
    return {"secret": secret, "otpauth": f"otpauth://totp/EasyFundraise:{user.email}?secret={secret}&issuer=EasyFundraise"}


class MfaIn(BaseModel):
    code: str


@router.post("/mfa/verify")
def mfa_verify(body: MfaIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rate_limit(db, f"mfa:{user.id}", 6, 300)
    raw = decrypt(user.totp_secret_enc) if user.totp_secret_enc else ""
    secret = raw.removeprefix("pending:")
    if not secret or not totp_ok(secret, body.code):
        raise ApiError(403, "EF-AUTH-051", "That code didn't work")
    if raw.startswith("pending:"):
        user.totp_secret_enc = encrypt(secret)
    sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == _hash(request.cookies.get(COOKIE, ""))))
    if sess:
        sess.mfa_at = datetime.now(UTC)
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Workspace, WorkspaceMember.role).join(WorkspaceMember)
                      .where(WorkspaceMember.user_id == user.id).order_by(Workspace.created_at)).all()
    return {
        "id": str(user.id), "email": user.email, "name": user.name, "picture": user.picture,
        "timezone": user.timezone, "is_admin": user.is_admin, "signature": user.signature,
        "notify_prefs": user.notify_prefs or {}, "mfa_enabled": bool(user.totp_secret_enc)
        and not decrypt(user.totp_secret_enc).startswith("pending:"),
        "mfa_required": user.is_admin and get_settings().admin_mfa_required,
        "workspaces": [{"id": str(w.id), "name": w.name, "role": r, "tier": w.tier_code} for w, r in rows],
    }
