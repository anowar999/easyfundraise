"""§9.5 round updates and §12 investor updates."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..deps import Ctx, ctx
from ..errors import ApiError, not_found
from ..models import Broadcast, Email, FunnelCard, GmailAccount
from ..services import broadcasts as svc
from ..services.entitlements import can

router = APIRouter(prefix="/broadcasts", tags=["broadcasts"])


class Audience(BaseModel):
    stages: list[int] = Field(default_factory=lambda: [2, 7], min_length=2, max_length=2)
    statuses: list[str] = Field(default_factory=lambda: ["Active"])
    exclude_card_ids: list[str] = []  # FOMO-01 "exclude a, b, c"
    card_ids: list[str] = []


class BroadcastIn(BaseModel):
    kind: str = Field(pattern="^(round_update|investor_update)$")
    template: str = Field(max_length=32)
    title: str = Field("", max_length=200)
    inputs: dict = {}
    audience: Audience = Audience()
    follow_up: bool = False


def b_out(b: Broadcast, emails: bool = False) -> dict:
    sent = [e for e in b.emails if e.status == "sent"]
    out = {"id": str(b.id), "kind": b.kind, "template": b.template, "title": b.title, "status": b.status,
           "inputs": b.inputs, "audience": b.audience, "follow_up": b.follow_up, "created_at": b.created_at,
           "recipients": len({e.card_id for e in b.emails}), "sent": len(sent),
           "opened": sum(1 for e in sent if e.opened_at), "replied": sum(1 for e in b.emails if e.replied_at)}
    if emails:
        out["emails"] = [{"id": str(e.id), "card_id": str(e.card_id) if e.card_id else None, "to": e.to_email,
                          "step": e.step, "subject": e.subject, "body": e.body, "status": e.status,
                          "scheduled_for": e.scheduled_for, "sent_at": e.sent_at, "opened": e.open_count,
                          "reply": e.reply_kind} for e in sorted(b.emails, key=lambda e: (e.step, e.to_email))]
    return out


def _gate(c: Ctx, kind: str) -> None:
    if kind == "investor_update" and not can(c.db, c.workspace, "newsletter"):
        raise ApiError(402, "EF-TIER-040", "Investor updates are on the Investor Relations plan", "", {"upgrade": True})
    if kind == "round_update" and not can(c.db, c.workspace, "send"):
        raise ApiError(402, "EF-TIER-030", "Upgrade to send emails", "", {"upgrade": True})


@router.get("")
def list_broadcasts(c: Ctx = Depends(ctx)):
    rows = c.db.scalars(select(Broadcast).where(Broadcast.workspace_id == c.ws_id).order_by(Broadcast.created_at.desc()).limit(50))
    return {"items": [b_out(b) for b in rows], "templates": {"round_update": svc.ROUND_TEMPLATES, "investor_update": svc.IR_TEMPLATES},
            "committed": svc.committed_total(c.db, c.ws_id),
            "nameable": [{"id": str(x.id), "name": x.name, "firm": x.firm} for x in c.db.scalars(select(FunnelCard).where(
                FunnelCard.workspace_id == c.ws_id, FunnelCard.stage >= 8, FunnelCard.shareable,
                FunnelCard.deleted_at.is_(None)))]}


@router.post("/audience")
def preview_audience(body: Audience, c: Ctx = Depends(ctx)):
    cards = svc.audience(c.db, c.ws_id, body.model_dump())
    no_email = c.db.scalar(select(func.count()).select_from(FunnelCard).where(
        FunnelCard.workspace_id == c.ws_id, FunnelCard.deleted_at.is_(None), FunnelCard.email == "",
        FunnelCard.stage >= body.stages[0], FunnelCard.stage <= body.stages[1]))
    return {"count": len(cards), "without_email": no_email,
            "items": [{"id": str(x.id), "name": x.name, "firm": x.firm, "stage": x.stage} for x in cards[:200]]}


@router.post("")
def create(body: BroadcastIn, c: Ctx = Depends(ctx)):
    c.require_editor()
    _gate(c, body.kind)
    templates = svc.ROUND_TEMPLATES if body.kind == "round_update" else svc.IR_TEMPLATES
    if body.template not in templates:
        raise ApiError(422, "EF-BC-001", "Unknown template")
    b = Broadcast(workspace_id=c.ws_id, user_id=c.user.id, kind=body.kind, template=body.template,
                  title=body.title or templates[body.template], inputs=body.inputs, audience=body.audience.model_dump(),
                  follow_up=body.follow_up)
    c.db.add(b)
    c.db.flush()
    try:
        n = svc.build(c.db, c.workspace, c.user, b)
    except svc.Invalid as e:
        c.db.rollback()
        raise ApiError(422, "EF-BC-002", "Check who you're naming", str(e)) from e
    if n == 0:
        c.db.rollback()
        raise ApiError(422, "EF-BC-003", "No recipients", "Nobody in that audience has an email on their funnel card.")
    c.db.commit()
    c.db.refresh(b)
    return b_out(b, True)


def _get(c: Ctx, bid: str) -> Broadcast:
    b = c.db.get(Broadcast, uuid.UUID(bid))
    if b is None or b.workspace_id != c.ws_id:
        raise not_found("Update")
    return b


@router.get("/{bid}")
def get(bid: str, c: Ctx = Depends(ctx)):
    return b_out(_get(c, bid), True)


class EmailPatch(BaseModel):
    subject: str = Field(max_length=200)
    body: str = Field(max_length=8000)


@router.patch("/{bid}/emails/{eid}")
def edit(bid: str, eid: str, body: EmailPatch, c: Ctx = Depends(ctx)):
    c.require_editor()
    b = _get(c, bid)
    em = next((e for e in b.emails if str(e.id) == eid), None)
    if em is None or em.status not in ("draft", "scheduled"):
        raise not_found("Email")
    em.subject, em.body = body.subject.strip(), body.body.strip()
    c.db.commit()
    return {"ok": True}


@router.delete("/{bid}/emails/{eid}")
def remove_recipient(bid: str, eid: str, c: Ctx = Depends(ctx)):
    c.require_editor()
    b = _get(c, bid)
    em = next((e for e in b.emails if str(e.id) == eid), None)
    if em is None or em.status == "sent":
        raise not_found("Email")
    for e in [x for x in b.emails if x.card_id == em.card_id and x.status != "sent"]:
        c.db.delete(e)
    c.db.commit()
    return {"ok": True}


@router.post("/{bid}/approve")
def approve(bid: str, c: Ctx = Depends(ctx)):
    c.require_editor()
    b = _get(c, bid)
    _gate(c, b.kind)
    if b.status != "draft":
        raise ApiError(409, "EF-BC-004", "This update was already scheduled")
    acc = c.db.get(GmailAccount, c.user.id)
    if acc is None or acc.status != "connected":
        raise ApiError(409, "EF-SEQ-007", "Connect Gmail to send", "", {"needs_gmail": True})
    svc.schedule(c.db, b, datetime.now(UTC))
    b.status = "scheduled"
    c.audit("broadcast.approve", str(b.id))
    c.db.commit()
    c.db.refresh(b)
    return b_out(b, True)


@router.post("/{bid}/cancel")
def cancel(bid: str, c: Ctx = Depends(ctx)):
    c.require_editor()
    b = _get(c, bid)
    b.status = "cancelled"
    for e in b.emails:
        if e.status in ("draft", "scheduled"):
            e.status = "cancelled"
    c.db.commit()
    return {"ok": True}


@router.get("/{bid}/engagement")
def engagement(bid: str, c: Ctx = Depends(ctx)):
    """IR-04: who opened, who replied, and who is going quiet."""
    b = _get(c, bid)
    rows = c.db.execute(select(Email, FunnelCard.name).outerjoin(FunnelCard, FunnelCard.id == Email.card_id)
                        .where(Email.broadcast_id == b.id, Email.step == 1)).all()
    return {"items": [{"name": n or e.to_email, "opened": e.open_count, "replied": bool(e.replied_at),
                       "quiet": e.status == "sent" and not e.opened_at} for e, n in rows]}
