"""Request context: authenticated user, active workspace, audit + data-access logging."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .errors import ApiError
from .models import AuditLog, AuthSession, DataAccessEvent, User, Workspace, WorkspaceMember

COOKIE = "ef_session"


def now() -> datetime:
    return datetime.now(UTC)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, response: Response, user: User, user_agent: str = "", ip: str = "") -> None:
    """AUTH-07: opaque token in an httpOnly, SameSite=Lax cookie; only its hash is stored."""
    s = get_settings()
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=_hash(token), user_id=user.id, user_agent=user_agent[:500], ip=ip[:64],
                       expires_at=now() + timedelta(days=s.session_days)))
    db.commit()
    response.set_cookie(COOKIE, token, max_age=s.session_days * 86400, httponly=True, samesite="lax",
                        secure=s.env != "dev", path="/")


def destroy_session(db: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == _hash(token)))
        if sess:
            db.delete(sess)
            db.commit()
    response.delete_cookie(COOKIE, path="/")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE)
    if not token:
        raise ApiError(401, "EF-AUTH-001", "Not signed in")
    sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == _hash(token)))
    if sess is None or sess.expires_at < now():
        raise ApiError(401, "EF-AUTH-002", "Session expired")
    if sess.user.suspended_at:
        raise ApiError(403, "EF-AUTH-003", "Account suspended")
    # 30-day rolling session; last-seen for the device list (written at most every 10 minutes)
    if sess.expires_at - now() < timedelta(days=get_settings().session_days - 1) or not sess.last_seen_at \
            or sess.last_seen_at < now() - timedelta(minutes=10):
        sess.expires_at = now() + timedelta(days=get_settings().session_days)
        sess.last_seen_at = now()
        db.commit()
    request.state.user_email = sess.user.email
    request.state.session = sess
    return sess.user


def admin_user(request: Request, user: User = Depends(current_user)) -> User:
    """AUTH-08: admins need a TOTP check on this session (12h) when MFA is required."""
    if not user.is_admin:
        raise ApiError(403, "EF-AUTH-010", "Admin only")
    if get_settings().admin_mfa_required:
        sess = request.state.session
        if not sess.mfa_at or sess.mfa_at < now() - timedelta(hours=12):
            raise ApiError(401, "EF-AUTH-011", "Two-factor check required", "", {"mfa": True})
    return user


@dataclass
class Ctx:
    db: Session
    user: User
    workspace: Workspace
    role: str
    ip: str

    @property
    def ws_id(self) -> uuid.UUID:
        return self.workspace.id

    def require_editor(self) -> None:
        if self.role == "viewer":
            raise ApiError(403, "EF-AUTH-020", "Viewers cannot make changes")

    def access(self, kind: str, investor_id: uuid.UUID | None = None, **meta) -> None:
        self.db.add(DataAccessEvent(workspace_id=self.ws_id, user_id=self.user.id, kind=kind,
                                    investor_id=investor_id, meta=meta, ip=self.ip))

    def audit(self, action: str, target: str = "", before: dict | None = None, after: dict | None = None):
        self.db.add(AuditLog(actor_id=self.user.id, action=action, target=target, before=before, after=after,
                             ip=self.ip))


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else ""))[:64]


def ctx(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Ctx:
    """Resolves the active workspace from the X-Workspace header (or the user's first one)."""
    wanted = request.headers.get("x-workspace")
    q = select(Workspace, WorkspaceMember.role).join(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
    if wanted:
        try:
            q = q.where(Workspace.id == uuid.UUID(wanted))
        except ValueError as e:
            raise ApiError(400, "EF-WS-002", "Invalid workspace id") from e
    row = db.execute(q.order_by(Workspace.created_at)).first()
    if row is None:
        raise ApiError(403, "EF-WS-001", "No access to this workspace")
    return Ctx(db=db, user=user, workspace=row[0], role=row[1], ip=client_ip(request))
