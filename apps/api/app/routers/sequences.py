"""§9.3 Outreach sequences: draft (template engine), edit, lint, approve & schedule, WhatsApp nudge (SEQ-07).

Sending through Gmail (MAIL-01/02) is not wired yet: approved emails are queued as `scheduled` with the slot
computed in the investor's timezone; the Gmail sender worker picks them up once Gmail OAuth is connected.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..deps import Ctx, ctx
from ..errors import ApiError, not_found
from ..models import AgentInstruction, CompanyProfile, Email, FunnelCard, Investor, Sequence
from ..services import outreach
from ..services.entitlements import can, consume, limit
from .investors import _exclusions, is_excluded

router = APIRouter(prefix="/sequences", tags=["sequences"])


def s_out(s: Sequence, inv: Investor | None = None, signature: str = "") -> dict:
    return {"id": str(s.id), "investor_id": str(s.investor_id), "status": s.status, "persona": s.persona,
            "investor": {"name": inv.name, "firm": inv.current_firm or inv.company} if inv else None,
            "emails": [{"id": str(e.id), "step": e.step, "hook": e.hook, "subject": e.subject, "body": e.body,
                        "facts": e.facts, "status": e.status, "scheduled_for": e.scheduled_for,
                        "issues": outreach.lint(e.subject, e.body, e.step, signature)} for e in s.emails]}


class DraftIn(BaseModel):
    investor_id: str
    persona: str = Field("momentum", pattern="^(momentum|warm-intro|technical-founder|humble-expert)$")


@router.post("")
def draft(body: DraftIn, c: Ctx = Depends(ctx)):
    c.require_editor()
    inv = c.db.get(Investor, uuid.UUID(body.investor_id))
    if inv is None or inv.suppressed:
        raise not_found("Investor")
    if is_excluded(inv, _exclusions(c)):  # SEQ-06
        raise ApiError(409, "EF-SEQ-001", "This investor is on your exclusion list")
    if not can(c.db, c.workspace, "send"):  # trial: up to N sample drafts
        consume(c.db, c.workspace, "sample_drafts", "all", limit(c.db, c.workspace, "sample_drafts"))
    prof = c.db.get(CompanyProfile, c.ws_id)
    instr = c.db.scalar(select(AgentInstruction.text).where(AgentInstruction.workspace_id == c.ws_id)
                        .order_by(AgentInstruction.version.desc())) or ""
    card = c.db.scalar(select(FunnelCard).where(FunnelCard.workspace_id == c.ws_id, FunnelCard.investor_id == inv.id,
                                                FunnelCard.deleted_at.is_(None)))
    seq = Sequence(workspace_id=c.ws_id, investor_id=inv.id, card_id=card.id if card else None, persona=body.persona)
    c.db.add(seq)
    c.db.flush()
    for e in outreach.draft_sequence(inv, prof, body.persona, instr, c.user.signature):
        c.db.add(Email(workspace_id=c.ws_id, sequence_id=seq.id, **e))
    c.db.commit()
    c.db.refresh(seq)
    return s_out(seq, inv, c.user.signature)


def _get(c: Ctx, sid: str) -> Sequence:
    s = c.db.get(Sequence, uuid.UUID(sid))
    if s is None or s.workspace_id != c.ws_id:
        raise not_found("Sequence")
    return s


@router.get("")
def list_sequences(c: Ctx = Depends(ctx)):
    rows = c.db.execute(select(Sequence, Investor).join(Investor).where(Sequence.workspace_id == c.ws_id)
                        .order_by(Sequence.created_at.desc()).limit(100)).all()
    return {"items": [{"id": str(s.id), "status": s.status, "investor": {"id": str(i.id), "name": i.name,
                       "firm": i.current_firm or i.company}, "created_at": s.created_at} for s, i in rows]}


@router.get("/{sid}")
def get_sequence(sid: str, c: Ctx = Depends(ctx)):
    s = _get(c, sid)
    return s_out(s, c.db.get(Investor, s.investor_id), c.user.signature)


class EmailPatch(BaseModel):
    subject: str = Field(max_length=200)
    body: str = Field(max_length=5000)


@router.patch("/{sid}/emails/{eid}")
def edit_email(sid: str, eid: str, body: EmailPatch, c: Ctx = Depends(ctx)):
    c.require_editor()
    s = _get(c, sid)
    em = next((e for e in s.emails if str(e.id) == eid), None)
    if em is None:
        raise not_found("Email")
    if em.status == "sent":
        raise ApiError(409, "EF-SEQ-002", "This email was already sent")
    em.subject, em.body = body.subject.strip(), body.body.strip()
    c.db.commit()
    return {"issues": outreach.lint(em.subject, em.body, em.step, c.user.signature)}


@router.post("/{sid}/approve")
def approve(sid: str, c: Ctx = Depends(ctx)):
    """SEQ-05: Approve & schedule. Lint must pass; slots land in the investor's local send window."""
    c.require_editor()
    s = _get(c, sid)
    if not can(c.db, c.workspace, "send"):
        raise ApiError(402, "EF-TIER-030", "Upgrade to send emails", "Trial accounts can draft but not send.",
                       {"upgrade": True})
    if not c.user.signature.strip():  # AUTH-05
        raise ApiError(409, "EF-SEQ-003", "Set your email signature first", "", {"needs_signature": True})
    problems = {e.step: outreach.lint(e.subject, e.body, e.step, c.user.signature) for e in s.emails}
    if any(problems.values()):
        raise ApiError(422, "EF-SEQ-004", "Fix the highlighted issues before scheduling", "",
                       {"issues": {str(k): v for k, v in problems.items() if v}})
    inv = c.db.get(Investor, s.investor_id)
    outreach.schedule(s.emails, datetime.now(UTC), inv.timezone)
    s.status = "approved"
    if s.card_id is None:
        card = FunnelCard(workspace_id=c.ws_id, investor_id=inv.id, name=inv.name, firm=inv.current_firm or inv.company,
                          source="Database", stage=1, tags=[], investor_timezone=inv.timezone)
        c.db.add(card)
        c.db.flush()
        s.card_id = card.id
    c.db.commit()
    return s_out(s, inv, c.user.signature)


@router.post("/{sid}/stop")
def stop(sid: str, c: Ctx = Depends(ctx)):
    s = _get(c, sid)
    s.status = "stopped"
    for e in s.emails:
        if e.status == "scheduled":
            e.status = "cancelled"
    c.db.commit()
    return {"ok": True}


@router.get("/nudge/{card_id}")
def nudge(card_id: str, c: Ctx = Depends(ctx)):
    """SEQ-07: ≤40-word WhatsApp-style nudge + LinkedIn DM variant for the founder to copy-send."""
    card = c.db.get(FunnelCard, uuid.UUID(card_id))
    if card is None or card.workspace_id != c.ws_id:
        raise not_found("Card")
    prof = c.db.get(CompanyProfile, c.ws_id)
    company = (prof.company_name if prof else "") or "our company"
    fn = outreach.first_name(card.name)
    traction = (prof.traction if prof and prof.shareable.get("traction", True) else "").rstrip(".")
    wa = f"Hi {fn}, quick one from {company}. " + (f"{traction}. " if traction else "") + \
        "Would you have 15 min this week to pick up where we left off?"
    li = f"Hi {fn}, following up on {company}. " + (f"Since we spoke: {traction}. " if traction else "") + \
        "Happy to send a 2-min update or find a slot for a quick call."
    return {"whatsapp": " ".join(wa.split()[:40]), "linkedin": " ".join(li.split()[:60])}
