"""§9.3 Outreach sequences: draft (Claude with a fact pack, or the template engine), edit, regenerate, lint,
approve & schedule, WhatsApp nudge (SEQ-07). Approved emails are queued as `scheduled` in the investor's local
send window; the worker sends them from the founder's Gmail (services/mailer.py)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..deps import Ctx, ctx
from ..errors import ApiError, not_found
from ..models import CompanyProfile, Email, FunnelCard, GmailAccount, Investor, Reveal, Sequence
from ..services import agent, outreach
from ..services.entitlements import can, consume, limit
from .investors import _exclusions, is_excluded

router = APIRouter(prefix="/sequences", tags=["sequences"])


def s_out(s: Sequence, inv: Investor | None = None, signature: str = "") -> dict:
    return {"id": str(s.id), "investor_id": str(s.investor_id), "status": s.status, "persona": s.persona,
            "engine": s.engine, "card_id": str(s.card_id) if s.card_id else None,
            "investor": {"name": inv.name, "firm": inv.current_firm or inv.company} if inv else None,
            "emails": [{"id": str(e.id), "step": e.step, "hook": e.hook, "subject": e.subject, "body": e.body,
                        "facts": e.facts, "status": e.status, "scheduled_for": e.scheduled_for,
                        "sent_at": e.sent_at, "opened": e.open_count, "reply": e.reply_kind, "error": e.error,
                        "issues": outreach.lint(e.subject, e.body, e.step, signature)} for e in s.emails]}


class FirstEmail(BaseModel):
    subject: str = Field(max_length=200)
    body: str = Field(max_length=5000)


class DraftIn(BaseModel):
    investor_id: str
    first_email: FirstEmail | None = None  # written on the investor profile; replaces email 1
    persona: str = Field("momentum", pattern="^(momentum|warm-intro|technical-founder|humble-expert)$")


def with_opt_out(body: str, signature: str) -> str:
    """Emails sent through outreach carry the opt-out line, just above the signature."""
    if "Missing opt-out line." not in outreach.lint("", body, 1):
        return body
    sig = signature.strip()
    if sig and body.endswith(sig):
        return f"{body[:-len(sig)].rstrip()}\n\n{outreach.OPT_OUT}\n\n{sig}"
    return f"{body}\n\n{outreach.OPT_OUT}"


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
    card = c.db.scalar(select(FunnelCard).where(FunnelCard.workspace_id == c.ws_id, FunnelCard.investor_id == inv.id,
                                                FunnelCard.deleted_at.is_(None)))
    emails, engine = agent.draft_sequence(c.db, c.workspace, inv, prof, body.persona, c.user.signature)
    seq = Sequence(workspace_id=c.ws_id, investor_id=inv.id, card_id=card.id if card else None, persona=body.persona,
                   user_id=c.user.id, engine=engine)
    c.db.add(seq)
    c.db.flush()
    if body.first_email:
        emails[0] = {**emails[0], "subject": body.first_email.subject.strip(),
                     "body": with_opt_out(body.first_email.body.strip(), c.user.signature)}
    for e in emails:
        c.db.add(Email(workspace_id=c.ws_id, sequence_id=seq.id, user_id=c.user.id, **e))
    c.db.commit()
    c.db.refresh(seq)
    auto = try_auto_send(c, seq) if auto_send_on(c.workspace) else None
    return {**s_out(seq, inv, c.user.signature), "auto": auto}


def _get(c: Ctx, sid: str) -> Sequence:
    s = c.db.get(Sequence, uuid.UUID(sid))
    if s is None or s.workspace_id != c.ws_id:
        raise not_found("Sequence")
    return s


@router.get("")
def list_sequences(c: Ctx = Depends(ctx)):
    rows = c.db.execute(select(Sequence, Investor).join(Investor).where(Sequence.workspace_id == c.ws_id)
                        .order_by(Sequence.created_at.desc()).limit(100)).all()
    return {"auto_send": auto_send_on(c.workspace),
            "items": [{"id": str(s.id), "status": s.status, "investor": {"id": str(i.id), "name": i.name,
                       "firm": i.current_firm or i.company}, "created_at": s.created_at,
                       "blocker": blocker(c, s) if s.status == "draft" else None,
                       "sent": sum(e.status == "sent" for e in s.emails),
                       "next_at": min((e.scheduled_for for e in s.emails if e.status == "scheduled"), default=None)}
                      for s, i in rows]}


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


class RegenIn(BaseModel):
    persona: str = Field("momentum", pattern="^(momentum|warm-intro|technical-founder|humble-expert)$")


@router.post("/{sid}/regenerate")
def regenerate(sid: str, body: RegenIn, c: Ctx = Depends(ctx)):
    """SEQ-05 "Change the approach": redraft unsent emails with another persona."""
    c.require_editor()
    s = _get(c, sid)
    if s.status != "draft":
        raise ApiError(409, "EF-SEQ-006", "Only drafts can be regenerated")
    inv = c.db.get(Investor, s.investor_id)
    emails, engine = agent.draft_sequence(c.db, c.workspace, inv, c.db.get(CompanyProfile, c.ws_id), body.persona,
                                          c.user.signature)
    by_step = {e["step"]: e for e in emails}
    for em in s.emails:
        e = by_step[em.step]
        em.hook, em.subject, em.body, em.facts = e["hook"], e["subject"], e["body"], e["facts"]
    s.persona, s.engine = body.persona, engine
    c.db.commit()
    return s_out(s, inv, c.user.signature)


class ApproveIn(BaseModel):
    confirm: bool = False  # the founder saw who, from which mailbox and when, and said yes


def _ready(c: Ctx, s: Sequence) -> tuple[Investor, str, GmailAccount]:
    """Everything that must hold before a sequence may be scheduled. Raises the ApiError that names the blocker."""
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
    card = c.db.get(FunnelCard, s.card_id) if s.card_id else None
    to = (card.email if card and card.email else "") or (inv.email if c.db.get(Reveal, (c.ws_id, inv.id)) else "")
    if not to:
        raise ApiError(409, "EF-SEQ-005", "Reveal this investor's email first",
                       "Reveal the contact on their profile (uses one credit) or add an email on their investor tracker card.",
                       {"needs_reveal": True})
    acc = c.db.get(GmailAccount, c.user.id)
    if acc is None or acc.status != "connected":
        raise ApiError(409, "EF-SEQ-007", "Connect Gmail to send", "Emails go out from your own Gmail.",
                       {"needs_gmail": True})
    return inv, to, acc


def blocker(c: Ctx, s: Sequence) -> str | None:
    """Why this draft can't be scheduled yet, in plain words (None when it's ready)."""
    try:
        _ready(c, s)
    except ApiError as e:
        return e.title
    return None


def _schedule(c: Ctx, s: Sequence, inv: Investor, to: str) -> None:
    s.status, s.user_id = "approved", c.user.id
    if s.card_id is None:
        card = FunnelCard(workspace_id=c.ws_id, investor_id=inv.id, name=inv.name, firm=inv.current_firm or inv.company,
                          source="Database", stage=1, tags=[], investor_timezone=inv.timezone)
        c.db.add(card)
        c.db.flush()
        s.card_id = card.id
    for em in s.emails:
        em.to_email, em.card_id, em.user_id = to, s.card_id, c.user.id
    c.audit("sequence.approve", str(s.id))


def auto_send_on(ws) -> bool:
    """Auto-send is opt-in: a missing key means off (unlike the §10.4 automations)."""
    return (ws.automations or {}).get("auto_send") is True


def try_auto_send(c: Ctx, s: Sequence) -> dict:
    """Workspace has auto-send on: schedule a fresh draft straight away when nothing blocks it."""
    try:
        inv, to, _ = _ready(c, s)
    except ApiError as e:
        return {"scheduled": False, "reason": e.title}
    outreach.schedule(s.emails, datetime.now(UTC), inv.timezone)
    _schedule(c, s, inv, to)
    c.db.commit()
    return {"scheduled": True, "reason": ""}


@router.post("/{sid}/approve")
def approve(sid: str, body: ApproveIn | None = None, c: Ctx = Depends(ctx)):
    """SEQ-05: Approve & schedule. Lint must pass; slots land in the investor's local send window.
    Without confirm=true nothing is scheduled: the reply (409 needs_confirm) carries the exact sender, recipient
    and send times so the founder confirms before anything can go out from their Gmail."""
    c.require_editor()
    s = _get(c, sid)
    inv, to, acc = _ready(c, s)
    outreach.schedule(s.emails, datetime.now(UTC), inv.timezone)
    if not (body and body.confirm):
        preview = {"from": acc.email, "to": to, "investor": inv.name, "timezone": inv.timezone,
                   "emails": [{"step": e.step, "subject": e.subject, "scheduled_for": e.scheduled_for.isoformat()}
                              for e in sorted(s.emails, key=lambda e: e.step)]}
        c.db.rollback()
        raise ApiError(409, "EF-SEQ-010", "Confirm sending", "", {"needs_confirm": True, "preview": preview})
    _schedule(c, s, inv, to)
    c.db.commit()
    return s_out(s, inv, c.user.signature)


@router.post("/send-all")
def send_all(body: ApproveIn | None = None, c: Ctx = Depends(ctx)):
    """Approve every draft on the outreach list in one go. Without confirm=true this only reports who is ready,
    who is blocked and from which mailbox, so the founder confirms before anything is scheduled."""
    c.require_editor()
    drafts = c.db.scalars(select(Sequence).where(Sequence.workspace_id == c.ws_id, Sequence.status == "draft")
                          .order_by(Sequence.created_at)).all()
    ready, skipped, sender = [], [], ""
    for s in drafts:
        try:
            inv, to, acc = _ready(c, s)
        except ApiError as e:
            skipped.append({"id": str(s.id), "name": c.db.get(Investor, s.investor_id).name, "reason": e.title})
            continue
        sender = acc.email
        ready.append((s, inv, to))
    if not (body and body.confirm):
        return {"needs_confirm": True, "from": sender, "skipped": skipped,
                "ready": [{"id": str(s.id), "name": inv.name, "to": to} for s, inv, to in ready]}
    now = datetime.now(UTC)
    for s, inv, to in ready:
        outreach.schedule(s.emails, now, inv.timezone)
        _schedule(c, s, inv, to)
    c.db.commit()
    return {"scheduled": len(ready), "skipped": skipped}


@router.post("/{sid}/stop")
def stop(sid: str, c: Ctx = Depends(ctx)):
    c.require_editor()
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
