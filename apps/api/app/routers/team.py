"""AUTH-06 workspaces and collaborators (owner / editor / viewer), invites, seat and workspace limits."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import Ctx, ctx, current_user
from ..errors import ApiError, not_found
from ..models import Invite, User, Workspace, WorkspaceMember
from ..services.entitlements import limit

router = APIRouter(tags=["team"])


def _owner(c: Ctx) -> None:
    if c.role != "owner":
        raise ApiError(403, "EF-AUTH-021", "Only the workspace owner can do that")


def _h(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


@router.get("/workspace/members")
def members(c: Ctx = Depends(ctx)):
    rows = c.db.execute(select(User, WorkspaceMember.role).join(WorkspaceMember, WorkspaceMember.user_id == User.id)
                        .where(WorkspaceMember.workspace_id == c.ws_id).order_by(WorkspaceMember.created_at)).all()
    invites = c.db.scalars(select(Invite).where(Invite.workspace_id == c.ws_id, Invite.accepted_at.is_(None),
                                                Invite.expires_at > datetime.now(UTC)))
    return {"items": [{"id": str(u.id), "name": u.name, "email": u.email, "role": r, "you": u.id == c.user.id} for u, r in rows],
            "invites": [{"id": str(i.id), "email": i.email, "role": i.role, "expires_at": i.expires_at} for i in invites],
            "seats": limit(c.db, c.workspace, "seats")}


class InviteIn(BaseModel):
    email: EmailStr
    role: str = Field("editor", pattern="^(editor|viewer)$")


@router.post("/workspace/invites")
def invite(body: InviteIn, c: Ctx = Depends(ctx)):
    _owner(c)
    seats = limit(c.db, c.workspace, "seats")
    used = c.db.scalar(select(func.count()).select_from(WorkspaceMember).where(WorkspaceMember.workspace_id == c.ws_id))
    pending = c.db.scalar(select(func.count()).select_from(Invite).where(
        Invite.workspace_id == c.ws_id, Invite.accepted_at.is_(None), Invite.expires_at > datetime.now(UTC)))
    if seats is not None and used + pending >= seats:
        raise ApiError(402, "EF-LIMIT-003", "No seats left on your plan", f"Your plan includes {seats} seat(s).",
                       {"upgrade": True})
    token = secrets.token_urlsafe(24)
    inv = Invite(workspace_id=c.ws_id, email=body.email.lower(), role=body.role, token_hash=_h(token),
                 invited_by=c.user.id, expires_at=datetime.now(UTC) + timedelta(days=7))
    c.db.add(inv)
    c.audit("member.invite", body.email.lower(), after={"role": body.role})
    c.db.commit()
    # Transactional email (Resend) is not wired: the owner shares the link.
    return {"id": str(inv.id), "url": f"{get_settings().web_origin}/invite/{token}"}


@router.delete("/workspace/invites/{iid}")
def cancel_invite(iid: str, c: Ctx = Depends(ctx)):
    _owner(c)
    inv = c.db.get(Invite, uuid.UUID(iid))
    if inv is None or inv.workspace_id != c.ws_id:
        raise not_found("Invite")
    c.db.delete(inv)
    c.db.commit()
    return {"ok": True}


@router.get("/invites/{token}")
def invite_info(token: str, db: Session = Depends(get_db)):
    inv = db.scalar(select(Invite).where(Invite.token_hash == _h(token)))
    if inv is None or inv.accepted_at or inv.expires_at < datetime.now(UTC):
        raise not_found("Invite")
    ws = db.get(Workspace, inv.workspace_id)
    return {"workspace": ws.name, "role": inv.role, "email": inv.email}


@router.post("/invites/{token}/accept")
def accept(token: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inv = db.scalar(select(Invite).where(Invite.token_hash == _h(token)))
    if inv is None or inv.accepted_at or inv.expires_at < datetime.now(UTC):
        raise not_found("Invite")
    if inv.email != user.email.lower():
        raise ApiError(403, "EF-AUTH-022", "This invite is for another email", f"Sign in as {inv.email} to accept.")
    if db.get(WorkspaceMember, (inv.workspace_id, user.id)) is None:
        db.add(WorkspaceMember(workspace_id=inv.workspace_id, user_id=user.id, role=inv.role))
    inv.accepted_at = datetime.now(UTC)
    db.commit()
    return {"workspace_id": str(inv.workspace_id)}


class RoleIn(BaseModel):
    role: str = Field(pattern="^(editor|viewer)$")


@router.patch("/workspace/members/{uid}")
def set_role(uid: str, body: RoleIn, c: Ctx = Depends(ctx)):
    _owner(c)
    m = c.db.get(WorkspaceMember, (c.ws_id, uuid.UUID(uid)))
    if m is None or m.role == "owner":
        raise not_found("Member")
    m.role = body.role
    c.audit("member.role", uid, after={"role": body.role})
    c.db.commit()
    return {"ok": True}


@router.delete("/workspace/members/{uid}")
def remove(uid: str, c: Ctx = Depends(ctx)):
    m = c.db.get(WorkspaceMember, (c.ws_id, uuid.UUID(uid)))
    if m is None:
        raise not_found("Member")
    if m.user_id != c.user.id:
        _owner(c)
    if m.role == "owner":
        raise ApiError(409, "EF-WS-010", "The owner can't be removed")
    c.db.delete(m)
    c.audit("member.remove", uid)
    c.db.commit()
    return {"ok": True}


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@router.post("/workspaces")
def create_workspace(body: WorkspaceIn, c: Ctx = Depends(ctx)):
    """AUTH-06: one workspace per raise/company; the limit comes from the current workspace's plan."""
    owned = c.db.scalar(select(func.count()).select_from(WorkspaceMember).where(
        WorkspaceMember.user_id == c.user.id, WorkspaceMember.role == "owner"))
    cap = limit(c.db, c.workspace, "workspaces")
    if cap is not None and owned >= cap:
        raise ApiError(402, "EF-LIMIT-004", "Workspace limit reached", f"Your plan allows {cap} workspace(s).",
                       {"upgrade": True})
    ws = Workspace(name=body.name.strip(), tier_code=c.workspace.tier_code, trial_ends_at=c.workspace.trial_ends_at)
    c.db.add(ws)
    c.db.flush()
    c.db.add(WorkspaceMember(workspace_id=ws.id, user_id=c.user.id, role="owner"))
    c.db.commit()
    return {"id": str(ws.id)}
