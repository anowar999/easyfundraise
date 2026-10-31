"""§15 Admin Portal API (admin role required; every change is audited, §15.7)."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import admin_user, client_ip
from ..errors import ApiError, not_found
from ..models import (
    AuditLog,
    ConfigKV,
    DataAccessEvent,
    EngTask,
    ErrorRecord,
    FunnelCard,
    Investor,
    RemovalRequest,
    SuppressedInvestor,
    Tier,
    User,
    Workspace,
    WorkspaceMember,
)
from ..services.dataset_import import norm_linkedin

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(admin_user)])

TASK_STATES = ["Idea", "Validated", "Awaiting approval", "Approved", "In development", "In review (QA)",
               "Ready for uat", "UAT verified", "Ready for prod", "Released", "Monitoring", "Done", "Declined",
               "Blocked", "Reopened"]


def audit(db: Session, request: Request, actor: User, action: str, target: str, before=None, after=None):
    db.add(AuditLog(actor_id=actor.id, action=action, target=target, before=before, after=after,
                    ip=client_ip(request)))


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    week = datetime.now(UTC) - timedelta(days=7)
    return {
        "users": db.scalar(select(func.count()).select_from(User)),
        "signups_7d": db.scalar(select(func.count()).select_from(User).where(User.created_at >= week)),
        "workspaces_by_tier": dict(db.execute(select(Workspace.tier_code, func.count()).group_by(Workspace.tier_code)).all()),
        "investors": db.scalar(select(func.count()).select_from(Investor)),
        "investors_enriched": db.scalar(select(func.count()).select_from(Investor).where(Investor.enriched)),
        "funnel_cards": db.scalar(select(func.count()).select_from(FunnelCard).where(FunnelCard.deleted_at.is_(None))),
        "reveals_7d": db.scalar(select(func.count()).select_from(DataAccessEvent).where(
            DataAccessEvent.kind == "reveal", DataAccessEvent.created_at >= week)),
        "searches_7d": db.scalar(select(func.count()).select_from(DataAccessEvent).where(
            DataAccessEvent.kind == "search", DataAccessEvent.created_at >= week)),
        "open_errors": db.scalar(select(func.count()).select_from(ErrorRecord).where(ErrorRecord.status.in_(["new", "triaged"]))),
        "open_removal_requests": db.scalar(select(func.count()).select_from(RemovalRequest).where(RemovalRequest.status == "open")),
        "top_revealers_7d": [{"user": u, "count": n} for u, n in db.execute(
            select(User.email, func.count()).join(DataAccessEvent, DataAccessEvent.user_id == User.id)
            .where(DataAccessEvent.kind == "reveal", DataAccessEvent.created_at >= week)
            .group_by(User.email).order_by(func.count().desc()).limit(5)).all()],
    }


# ---------- users ----------

@router.get("/users")
def users(q: str = "", db: Session = Depends(get_db)):
    stmt = select(User).order_by(User.created_at.desc()).limit(100)
    if q:
        stmt = stmt.where(User.email.ilike(f"%{q}%") | User.name.ilike(f"%{q}%"))
    out = []
    for u in db.scalars(stmt):
        wss = db.execute(select(Workspace).join(WorkspaceMember).where(WorkspaceMember.user_id == u.id)).scalars().all()
        out.append({"id": str(u.id), "email": u.email, "name": u.name, "is_admin": u.is_admin,
                    "suspended": u.suspended_at is not None, "created_at": u.created_at,
                    "workspaces": [{"id": str(w.id), "name": w.name, "tier": w.tier_code,
                                    "trial_ends_at": w.trial_ends_at} for w in wss]})
    return {"items": out}


class UserAction(BaseModel):
    suspended: bool | None = None
    is_admin: bool | None = None
    reason: str = Field("", max_length=500)


@router.patch("/users/{uid}")
def patch_user(uid: str, body: UserAction, request: Request, db: Session = Depends(get_db),
               actor: User = Depends(admin_user)):
    u = db.get(User, uuid.UUID(uid))
    if u is None:
        raise not_found("User")
    before = {"suspended": u.suspended_at is not None, "is_admin": u.is_admin}
    if body.suspended is not None:
        u.suspended_at = datetime.now(UTC) if body.suspended else None
    if body.is_admin is not None:
        if u.id == actor.id and not body.is_admin:
            raise ApiError(409, "EF-ADM-001", "You can't remove your own admin role")
        u.is_admin = body.is_admin
    audit(db, request, actor, "user.update", u.email, before, body.model_dump())
    db.commit()
    return {"ok": True}


class WorkspaceAction(BaseModel):
    tier_code: str | None = None
    extend_trial_days: int | None = Field(None, ge=1, le=90)


@router.patch("/workspaces/{wid}")
def patch_workspace(wid: str, body: WorkspaceAction, request: Request, db: Session = Depends(get_db),
                    actor: User = Depends(admin_user)):
    w = db.get(Workspace, uuid.UUID(wid))
    if w is None:
        raise not_found("Workspace")
    before = {"tier": w.tier_code, "trial_ends_at": str(w.trial_ends_at)}
    if body.tier_code:
        if db.get(Tier, body.tier_code) is None:
            raise ApiError(422, "EF-ADM-002", "Unknown tier")
        w.tier_code = body.tier_code
    if body.extend_trial_days:
        w.trial_ends_at = max(w.trial_ends_at or datetime.now(UTC), datetime.now(UTC)) + timedelta(days=body.extend_trial_days)
    audit(db, request, actor, "workspace.update", str(w.id), before, body.model_dump(exclude_none=True))
    db.commit()
    return {"ok": True}


# ---------- tiers (§15.2) ----------

def t_out(t: Tier) -> dict:
    return {"code": t.code, "name": t.name, "price_monthly": t.price_monthly, "price_annual": t.price_annual,
            "limits": t.limits, "features": t.features, "sort": t.sort, "visible": t.visible, "version": t.version}


@router.get("/tiers")
def tiers(db: Session = Depends(get_db)):
    return {"items": [t_out(t) for t in db.scalars(select(Tier).order_by(Tier.sort))]}


class TierIn(BaseModel):
    name: str = Field(max_length=80)
    price_monthly: int = Field(ge=0)
    price_annual: int = Field(ge=0)
    limits: dict[str, int]
    features: dict[str, bool | str]
    sort: int = 0
    visible: bool = True


@router.put("/tiers/{code}")
def put_tier(code: str, body: TierIn, request: Request, db: Session = Depends(get_db), actor: User = Depends(admin_user)):
    t = db.get(Tier, code)
    before = t_out(t) if t else None
    if t is None:
        t = Tier(code=code[:32], version=0)
        db.add(t)
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    t.version = (t.version or 0) + 1
    audit(db, request, actor, "tier.update", code, before, body.model_dump())
    db.commit()
    return t_out(t)


# ---------- platform config (§15.3) ----------

@router.get("/config")
def get_config(db: Session = Depends(get_db)):
    return {"items": [{"key": c.key, "value": c.value, "version": c.version} for c in db.scalars(select(ConfigKV).order_by(ConfigKV.key))]}


class ConfigIn(BaseModel):
    value: dict


@router.put("/config/{key}")
def put_config(key: str, body: ConfigIn, request: Request, db: Session = Depends(get_db), actor: User = Depends(admin_user)):
    c = db.get(ConfigKV, key)
    before = c.value if c else None
    if c is None:
        c = ConfigKV(key=key[:80], value=body.value, version=1)
        db.add(c)
    else:
        c.value, c.version = body.value, c.version + 1
    audit(db, request, actor, "config.update", key, before, body.value)
    db.commit()
    return {"ok": True}


# ---------- Error Center (§15.6) ----------

@router.get("/errors")
def errors(status: str = "", db: Session = Depends(get_db)):
    stmt = select(ErrorRecord).order_by(ErrorRecord.last_seen.desc()).limit(100)
    if status:
        stmt = stmt.where(ErrorRecord.status == status)
    return {"items": [{"fingerprint": e.fingerprint, "type": e.error_type, "message": e.message, "path": e.path,
                       "count": e.count, "users_affected": len(e.users_affected), "status": e.status, "env": e.env,
                       "first_seen": e.first_seen, "last_seen": e.last_seen, "stack": e.stack,
                       "task_id": str(e.task_id) if e.task_id else None} for e in db.scalars(stmt)]}


class ErrorAction(BaseModel):
    status: str | None = Field(None, pattern="^(new|triaged|task_created|fixed|muted)$")
    create_task: bool = False


@router.patch("/errors/{fp}")
def patch_error(fp: str, body: ErrorAction, request: Request, db: Session = Depends(get_db),
                actor: User = Depends(admin_user)):
    e = db.get(ErrorRecord, fp)
    if e is None:
        raise not_found("Error")
    if body.create_task and e.task_id is None:
        t = EngTask(type="bug", title=f"{e.error_type} at {e.path}", description=f"{e.message}\n\n{e.stack[-2000:]}",
                    source="error", severity="medium", state="Approved")
        db.add(t)
        db.flush()
        e.task_id, e.status = t.id, "task_created"
    if body.status:
        e.status = body.status
    audit(db, request, actor, "error.update", fp, None, body.model_dump())
    db.commit()
    return {"ok": True}


# ---------- Agent Task Dashboard (§16) ----------

def task_out(t: EngTask) -> dict:
    return {"id": str(t.id), "type": t.type, "title": t.title, "description": t.description,
            "requirement_ids": t.requirement_ids, "source": t.source, "severity": t.severity, "priority": t.priority,
            "state": t.state, "pr_urls": t.pr_urls, "created_at": t.created_at, "updated_at": t.updated_at}


@router.get("/tasks")
def tasks(db: Session = Depends(get_db)):
    return {"states": TASK_STATES, "items": [task_out(t) for t in db.scalars(select(EngTask).order_by(EngTask.created_at.desc()).limit(500))]}


class TaskIn(BaseModel):
    title: str | None = Field(None, max_length=300)
    description: str | None = Field(None, max_length=20000)
    type: str | None = Field(None, pattern="^(feature|improvement|bug|debt|seo|ops)$")
    requirement_ids: list[str] | None = None
    priority: str | None = Field(None, pattern="^P[1-4]$")
    severity: str | None = Field(None, pattern="^(low|medium|high)$")
    state: str | None = None
    pr_urls: list[str] | None = None


@router.post("/tasks")
def create_task(body: TaskIn, request: Request, db: Session = Depends(get_db), actor: User = Depends(admin_user)):
    if not body.title:
        raise ApiError(422, "EF-VAL-005", "Title is required")
    t = EngTask(**{k: v for k, v in body.model_dump(exclude_none=True).items()})
    t.state = t.state or "Idea"
    if t.state not in TASK_STATES:
        raise ApiError(422, "EF-VAL-006", "Unknown state")
    db.add(t)
    audit(db, request, actor, "task.create", body.title)
    db.commit()
    return task_out(t)


@router.patch("/tasks/{tid}")
def patch_task(tid: str, body: TaskIn, request: Request, db: Session = Depends(get_db), actor: User = Depends(admin_user)):
    t = db.get(EngTask, uuid.UUID(tid))
    if t is None:
        raise not_found("Task")
    if body.state and body.state not in TASK_STATES:
        raise ApiError(422, "EF-VAL-006", "Unknown state")
    before = task_out(t)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(t, k, v)
    audit(db, request, actor, "task.update", str(t.id), {"state": before["state"]}, body.model_dump(exclude_none=True))
    db.commit()
    return task_out(t)


# ---------- Investor data admin (§15.5, DATA-04) ----------

@router.get("/removal-requests")
def removal_requests(db: Session = Depends(get_db)):
    return {"items": [{"id": str(r.id), "name": r.name, "email": r.email, "linkedin": r.linkedin, "kind": r.kind,
                       "message": r.message, "status": r.status, "created_at": r.created_at}
                      for r in db.scalars(select(RemovalRequest).order_by(RemovalRequest.created_at.desc()).limit(200))]}


class RemovalAction(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    investor_id: str | None = None


@router.post("/removal-requests/{rid}")
def act_removal(rid: str, body: RemovalAction, request: Request, db: Session = Depends(get_db),
                actor: User = Depends(admin_user)):
    r = db.get(RemovalRequest, uuid.UUID(rid))
    if r is None:
        raise not_found("Request")
    if body.action == "approve" and r.kind == "remove":
        if body.investor_id:
            inv = db.get(Investor, uuid.UUID(body.investor_id))
        else:
            conds = [Investor.email == r.email.lower()]
            if r.linkedin.strip("/"):
                conds.append(Investor.linkedin == norm_linkedin(r.linkedin))
            inv = db.scalar(select(Investor).where(or_(*conds)))
        if inv is None:
            raise ApiError(404, "EF-ADM-003", "No matching investor; pass investor_id")
        inv.suppressed = True
        if not db.get(SuppressedInvestor, inv.linkedin):
            db.add(SuppressedInvestor(linkedin=inv.linkedin, reason=f"removal request {r.id}"))
    r.status = "done" if body.action == "approve" else "rejected"
    audit(db, request, actor, "removal." + body.action, str(r.id))
    db.commit()
    return {"ok": True}


@router.get("/investors")
def admin_investors(q: str = "", page: int = Query(1, ge=1), db: Session = Depends(get_db)):
    stmt = select(Investor).order_by(Investor.name).offset((page - 1) * 50).limit(50)
    if q:
        stmt = stmt.where(Investor.name.ilike(f"%{q}%") | Investor.company.ilike(f"%{q}%"))
    return {"items": [{"id": str(i.id), "name": i.name, "company": i.company, "current_firm": i.current_firm,
                       "investor_type": i.investor_type, "seed_fit": i.seed_fit, "enriched": i.enriched,
                       "identity_confidence": i.identity_confidence, "suppressed": i.suppressed,
                       "is_honeypot": i.is_honeypot} for i in db.scalars(stmt)]}


@router.get("/audit")
def audit_log(db: Session = Depends(get_db)):
    rows = db.execute(select(AuditLog, User.email).outerjoin(User, User.id == AuditLog.actor_id)
                      .order_by(AuditLog.created_at.desc()).limit(200)).all()
    return {"items": [{"id": str(a.id), "actor": email, "action": a.action, "target": a.target, "before": a.before,
                       "after": a.after, "ip": a.ip, "created_at": a.created_at} for a, email in rows]}
