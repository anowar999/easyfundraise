"""§9.3 Outreach sequences: draft (Claude with a fact pack, or the template engine), edit, regenerate, lint,
approve & schedule, WhatsApp nudge (SEQ-07). Approved emails are queued as `scheduled` in the investor's local
send window; the worker sends them from the founder's Gmail (services/mailer.py)."""

import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..db import SessionLocal
from ..deps import Ctx, ctx
from ..errors import ApiError, not_found
from ..models import CompanyProfile, Email, FunnelCard, GmailAccount, Investor, Reveal, Sequence, User, Workspace
from ..services import agent, ai, mailer, outreach, spam, test_investors
from ..services.entitlements import can, consume, limit
from .investors import _exclusions, auto_reveal, is_excluded

FOLLOW_UP_GAP = timedelta(hours=24)

router = APIRouter(prefix="/sequences", tags=["sequences"])


def s_out(s: Sequence, inv: Investor | None = None, signature: str = "") -> dict:
    return {"id": str(s.id), "investor_id": str(s.investor_id), "status": s.status, "persona": s.persona,
            "engine": s.engine, "drafting": s.engine == DRAFTING, "card_id": str(s.card_id) if s.card_id else None,
            "investor": {"name": inv.name, "firm": inv.current_firm or inv.company} if inv else None,
            "emails": [{"id": str(e.id), "step": e.step, "hook": e.hook, "subject": e.subject, "body": e.body,
                        "facts": e.facts, "status": e.status, "scheduled_for": e.scheduled_for,
                        "sent_at": e.sent_at, "opened": e.open_count, "reply": e.reply_kind, "error": e.error,
                        "issues": outreach.lint(e.subject, e.body, e.step, signature),
                        "spam": spam.score(e.subject, e.body, e.step, inv.name if inv else "")} for e in s.emails]}


class FirstEmail(BaseModel):
    subject: str = Field(max_length=200)
    body: str = Field(max_length=5000)


class DraftIn(BaseModel):
    investor_id: str
    first_email: FirstEmail | None = None  # written on the investor profile; replaces email 1
    persona: str = Field("momentum", pattern="^(momentum|warm-intro|technical-founder|humble-expert)$")


def with_opt_out(body: str, signature: str) -> str:
    """Kept for callers; outreach no longer adds an opt-out line."""
    if not outreach.OPT_OUT or outreach.OPT_OUT in body:
        return body
    sig = signature.strip()
    if sig and body.endswith(sig):
        return f"{body[:-len(sig)].rstrip()}\n\n{outreach.OPT_OUT}\n\n{sig}"
    return f"{body}\n\n{outreach.OPT_OUT}"


DRAFTING = "drafting"  # template emails are in place; the AI versions are being written in the background


def finish_ai_draft(seq_id: uuid.UUID, user_id: uuid.UUID, placed: dict[int, str]) -> None:
    """Writes the AI versions after "add to outreach" has already answered with template drafts. Only emails
    still exactly as placed are replaced, so nothing the founder edited or approved meanwhile is touched."""
    with SessionLocal() as db:
        s = db.get(Sequence, seq_id)
        if s is None or s.engine != DRAFTING:
            return
        engine = "template"
        try:
            ws, inv, user = db.get(Workspace, s.workspace_id), db.get(Investor, s.investor_id), db.get(User, user_id)
            emails, engine = agent.draft_sequence(db, ws, inv, db.get(CompanyProfile, s.workspace_id), s.persona,
                                                  user.signature if user else "")
            db.refresh(s)
            clean = all(not outreach.lint(e["subject"], e["body"], e["step"], user.signature if user else "")
                        for e in emails)
            if s.status in ("draft", "approved") and engine != "template" and clean:
                by_step = {e["step"]: e for e in emails}
                for em in s.emails:  # auto-send may have scheduled them already; swap any not yet sent
                    e = by_step.get(em.step)
                    if e and em.status in ("draft", "scheduled") and em.body == placed.get(em.step):
                        em.hook, em.subject, em.body, em.facts = e["hook"], e["subject"], e["body"], e["facts"]
                        em.pre_update_body = e.get("pre_update_body")
        finally:
            s.engine = engine
            db.commit()


@router.post("")
def draft(body: DraftIn, c: Ctx = Depends(ctx), background: BackgroundTasks = None):
    c.require_editor()
    inv = c.db.get(Investor, uuid.UUID(body.investor_id))
    if not test_investors.visible(inv, c.user.email):
        raise not_found("Investor")
    if is_excluded(inv, _exclusions(c)):  # SEQ-06
        raise ApiError(409, "EF-SEQ-001", "This investor is on your exclusion list")
    if not can(c.db, c.workspace, "send"):  # trial: up to N sample drafts
        consume(c.db, c.workspace, "sample_drafts", "all", limit(c.db, c.workspace, "sample_drafts"))
    prof = c.db.get(CompanyProfile, c.ws_id)
    card = c.db.scalar(select(FunnelCard).where(FunnelCard.workspace_id == c.ws_id, FunnelCard.investor_id == inv.id,
                                                FunnelCard.deleted_at.is_(None)))
    auto = auto_send_on(c.workspace)
    # Answer at once with lint-clean template drafts; the AI versions (10-20s) are written in the background.
    later = background is not None and ai.available()
    emails, engine = agent.draft_sequence(c.db, c.workspace, inv, prof, body.persona, c.user.signature,
                                          use_ai=not later)
    if later:
        engine = DRAFTING
    seq = Sequence(workspace_id=c.ws_id, investor_id=inv.id, card_id=card.id if card else None, persona=body.persona,
                   user_id=c.user.id, engine=engine)
    c.db.add(seq)
    c.db.flush()
    if body.first_email:
        emails[0] = {**emails[0], "subject": body.first_email.subject.strip(),
                     "body": with_opt_out(body.first_email.body.strip(), c.user.signature)}
        outreach.thread_subjects(emails)
    for e in emails:
        c.db.add(Email(workspace_id=c.ws_id, sequence_id=seq.id, user_id=c.user.id, **e))
    if not (card and card.email):
        auto_reveal(c, inv)  # so it's ready to send with no "reveal first" step
    c.db.commit()
    c.db.refresh(seq)
    if later:
        background.add_task(finish_ai_draft, seq.id, c.user.id,
                            {e.step: e.body for e in seq.emails if not (body.first_email and e.step == 1)})
    sent = try_auto_send(c, seq) if auto else None
    return {**s_out(seq, inv, c.user.signature), "auto": sent}


def _get(c: Ctx, sid: str) -> Sequence:
    s = c.db.get(Sequence, uuid.UUID(sid))
    if s is None or s.workspace_id != c.ws_id:
        raise not_found("Sequence")
    return s


@router.get("")
def list_sequences(c: Ctx = Depends(ctx)):
    rows = c.db.execute(select(Sequence, Investor).join(Investor).where(Sequence.workspace_id == c.ws_id)
                        .order_by(Sequence.created_at.desc()).limit(500)).all()
    return {"auto_send": auto_send_on(c.workspace),
            "items": [{"id": str(s.id), "status": s.status, "investor": {"id": str(i.id), "name": i.name,
                       "firm": i.current_firm or i.company}, "created_at": s.created_at,
                       "email": next((e.to_email for e in s.emails if e.to_email), ""),
                       "blocker": blocker(c, s) if s.status == "draft" else None,
                       "sent": sum(e.status == "sent" for e in s.emails),
                       "next_at": min((e.scheduled_for for e in s.emails if e.status == "scheduled"), default=None)}
                      for s, i in rows]}


@router.get("/scheduled")
def scheduled(c: Ctx = Depends(ctx)):
    """Every outreach email waiting to go out, soonest first, with the investor's time zone for local times."""
    rows = c.db.execute(select(Email, Sequence, Investor).join(Sequence, Sequence.id == Email.sequence_id)
                        .join(Investor, Investor.id == Sequence.investor_id)
                        .where(Email.workspace_id == c.ws_id, Email.status == "scheduled", Sequence.status == "approved")
                        .order_by(Email.scheduled_for).limit(300)).all()
    now = datetime.now(UTC)
    sent = {}  # (sequence, step) -> sent_at
    for sid, step, at, subj in c.db.execute(select(Email.sequence_id, Email.step, Email.sent_at, Email.subject).where(
            Email.workspace_id == c.ws_id, Email.sequence_id.is_not(None), Email.status == "sent")).all():
        sent[(sid, step)] = (at, subj)

    def ready(e: Email, s: Sequence) -> tuple[bool, datetime | None]:
        """Send now: email 1 any time; a follow-up once the email before it went out at least a day ago."""
        if e.scheduled_for and e.scheduled_for <= now:
            return False, None  # already on its way
        if e.step == 1:
            return True, None
        prev = sent.get((s.id, e.step - 1))
        if not prev or not prev[0]:
            return False, None
        after = prev[0] + FOLLOW_UP_GAP
        return after <= now, (after if after > now else None)

    def subject(e: Email, s: Sequence) -> str:  # follow-ups go as a reply to email 1
        first = sent.get((s.id, 1))
        if e.step > 1 and first:
            return "Re: " + re.sub(r"^\s*re:\s*", "", first[1], flags=re.I)
        return e.subject

    items = []
    for e, s, inv in rows:
        ok, after = ready(e, s)
        items.append({"email_id": str(e.id), "sequence_id": str(s.id), "kind": "sequence", "step": e.step,
                      "subject": outreach.fill_first_name(subject(e, s), inv.name),
                      "body": outreach.fill_first_name(e.body, inv.name), "to": e.to_email,
                      "spam": spam.score(e.subject, e.body, e.step, inv.name),
                      "scheduled_for": e.scheduled_for, "investor": inv.name,
                      "firm": inv.current_firm or inv.company, "timezone": inv.timezone or "UTC", "can_send_now": ok,
                      "send_now_from": after, "sending": bool(e.scheduled_for and e.scheduled_for <= now)})
    # Round & progress updates waiting to go out (sent as a reply in each investor's thread).
    for e, card in c.db.execute(select(Email, FunnelCard).outerjoin(FunnelCard, FunnelCard.id == Email.card_id).where(
            Email.workspace_id == c.ws_id, Email.status == "scheduled", Email.broadcast_id.is_not(None),
            Email.hook == "update").limit(300)).all():
        items.append({"email_id": str(e.id), "sequence_id": None, "card_id": str(card.id) if card else None,
                      "kind": "update", "step": 0, "subject": e.subject, "body": e.body, "to": e.to_email,
                      "scheduled_for": e.scheduled_for, "investor": card.name if card else e.to_email,
                      "firm": card.firm if card else "", "timezone": (card.investor_timezone if card else "") or "UTC",
                      "can_send_now": not (e.scheduled_for and e.scheduled_for <= now), "send_now_from": None,
                      "sending": bool(e.scheduled_for and e.scheduled_for <= now)})
    items.sort(key=lambda x: x["scheduled_for"] or now)
    return {"items": items}


def _scheduled_email(c: Ctx, eid: str) -> Email:
    try:
        em = c.db.get(Email, uuid.UUID(eid))
    except ValueError:
        em = None
    if em is None or em.workspace_id != c.ws_id:
        raise not_found("Email")
    if em.status != "scheduled":
        raise ApiError(409, "EF-SEQ-011", "This email isn't scheduled", "It may have been sent or cancelled already.")
    if em.scheduled_for and em.scheduled_for <= datetime.now(UTC):
        raise ApiError(409, "EF-SEQ-013", "This email is already on its way", "It goes out within a minute.")
    return em


class SendNowIn(BaseModel):
    anyway: bool = False  # the founder confirmed sending a follow-up within a day of the email before it


def _respace_plan(c: Ctx) -> list[tuple[Email, datetime]]:
    """Follow-ups scheduled later than 3 working days after the email before them (the old 1-week spacing)."""
    out = []
    seqs = c.db.scalars(select(Sequence).where(Sequence.workspace_id == c.ws_id, Sequence.status == "approved")).all()
    for s in seqs:
        inv = c.db.get(Investor, s.investor_id)
        tz = (inv.timezone if inv else "") or "UTC"
        prev = None
        for e in sorted(s.emails, key=lambda e: e.step):
            if e.status == "sent":
                prev = e.sent_at
            elif e.status == "scheduled" and e.step > 1 and prev is not None and e.scheduled_for:
                due = max(outreach.follow_up_slot(prev, tz), datetime.now(UTC))
                if e.scheduled_for - due > timedelta(hours=20):
                    out.append((e, due))
                    prev = due
                else:
                    prev = e.scheduled_for
            elif e.status == "scheduled":
                prev = e.scheduled_for
    return out


class RespaceIn(BaseModel):
    confirm: bool = False


@router.post("/scheduled/respace")
def respace(body: RespaceIn | None = None, c: Ctx = Depends(ctx)):
    """Move follow-ups on the old spacing to 3 working days after the email before them. Without confirm it only
    counts them, so the founder decides."""
    rows = _respace_plan(c)
    if not (body and body.confirm):
        return {"count": len(rows)}
    c.require_editor()
    for e, due in rows:
        e.scheduled_for = due
    c.audit("sequence.respace", str(c.ws_id), after={"emails": len(rows)})
    c.db.commit()
    return {"count": len(rows), "moved": len(rows)}


@router.post("/scheduled/{eid}/send-now")
def scheduled_send_now(eid: str, background: BackgroundTasks, body: SendNowIn | None = None, c: Ctx = Depends(ctx)):
    """Send now from the Scheduled list: an outreach email (same rules as on its sequence) or a progress update."""
    c.require_editor()
    em = _scheduled_email(c, eid)
    if em.sequence_id:
        return send_now(str(em.sequence_id), eid, background, body, c)
    now = datetime.now(UTC)
    em.scheduled_for, em.error = now, ""
    acc = c.db.get(GmailAccount, c.user.id)
    if acc is not None and acc.next_send_at and acc.next_send_at > now:
        acc.next_send_at = now
    c.audit("email.send_now", str(em.id))
    c.db.commit()
    background.add_task(mailer.send_now_one, em.id)  # goes in seconds, not at the next worker tick
    return {"ok": True, "scheduled_for": now}


@router.post("/scheduled/{eid}/cancel")
def scheduled_cancel(eid: str, c: Ctx = Depends(ctx)):
    """Cancel send. Email 1 takes its sequence back to drafts (follow-ups can't go without it; approve again to
    reschedule); a follow-up or a progress update is cancelled on its own."""
    c.require_editor()
    em = _scheduled_email(c, eid)
    s = c.db.get(Sequence, em.sequence_id) if em.sequence_id else None
    if s is not None and em.step == 1:
        for e in s.emails:
            if e.status in ("scheduled", "draft"):
                e.status, e.scheduled_for, e.error = "draft", None, ""
        s.status = "draft"
        result = {"ok": True, "back_to_draft": True, "cancelled": [e.step for e in s.emails if e.status == "draft"]}
    else:
        em.status, em.error = "cancelled", "Cancelled by you"
        result = {"ok": True, "back_to_draft": False, "cancelled": [em.step]}
    c.audit("email.cancel", str(em.id), after=result)
    c.db.commit()
    return result


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
    if em.step == 1:
        outreach.thread_subjects([e for e in s.emails if e.status != "sent"])
    c.db.commit()
    inv = c.db.get(Investor, s.investor_id)
    return {"issues": outreach.lint(em.subject, em.body, em.step, c.user.signature),
            "spam": spam.score(em.subject, em.body, em.step, inv.name if inv else "")}


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
        em.pre_update_body = e.get("pre_update_body")
    s.persona, s.engine = body.persona, engine
    c.db.commit()
    return s_out(s, inv, c.user.signature)


class ApproveIn(BaseModel):
    confirm: bool = False  # the founder saw who, from which mailbox and when, and said yes


def _ready(c: Ctx, s: Sequence, reveal: bool = True) -> tuple[Investor, str, GmailAccount]:
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
    risky = {e.step: r for e in s.emails if e.status in ("draft", "scheduled")
             for r in [spam.score(e.subject, e.body, e.step, inv.name if inv else "")] if r["level"] == "high"}
    if risky:
        step, r = next(iter(risky.items()))
        raise ApiError(422, "EF-SEQ-020", f"Email {step} looks like spam (score {r['score']}/100)",
                       "Fix: " + "; ".join(r["reasons"][:3]), {"spam": {str(k): v for k, v in risky.items()}})
    card = c.db.get(FunnelCard, s.card_id) if s.card_id else None
    to = (card.email if card and card.email else "") or (inv.email if c.db.get(Reveal, (c.ws_id, inv.id)) else "")
    if not to and auto_reveal(c, inv, dry=not reveal):  # uses one contact credit by itself when there are some
        to = inv.email
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
        _ready(c, s, reveal=False)  # a check only: never spends a credit
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
    inv, to, acc = _ready(c, s, reveal=bool(body and body.confirm))
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
            inv, to, acc = _ready(c, s, reveal=bool(body and body.confirm))
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


@router.delete("/{sid}")
def remove(sid: str, c: Ctx = Depends(ctx)):
    """Remove an investor from outreach. Nothing sent yet: the sequence is deleted. Something sent: it stops, unsent
    emails are cancelled and the sent ones stay in Activity."""
    c.require_editor()
    s = _get(c, sid)
    if any(e.status in ("sent", "sending") for e in s.emails):
        s.status = "stopped"
        for e in s.emails:
            if e.status in ("scheduled", "draft"):
                e.status, e.error = "cancelled", "Removed from outreach"
        kept = True
    else:
        c.db.delete(s)
        kept = False
    c.audit("sequence.remove", sid, after={"kept_history": kept})
    c.db.commit()
    return {"ok": True, "kept_history": kept}


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


@router.post("/{sid}/emails/{eid}/send-now")
def send_now(sid: str, eid: str, background: BackgroundTasks, body: SendNowIn | None = None, c: Ctx = Depends(ctx)):
    """Move one scheduled email to now; the sender picks it up within a minute (daily cap and safety checks still
    apply). A follow-up can only go once email 1 has been sent, so it stays in the same thread."""
    c.require_editor()
    s = _get(c, sid)
    em = next((e for e in s.emails if str(e.id) == eid), None)
    if em is None or em.status != "scheduled" or s.status != "approved":
        raise ApiError(409, "EF-SEQ-011", "This email isn't scheduled")
    now = datetime.now(UTC)
    if em.scheduled_for and em.scheduled_for <= now:
        raise ApiError(409, "EF-SEQ-013", "This email is already on its way", "It goes out within a minute.")
    if em.step > 1:
        prev = next((e for e in s.emails if e.step == em.step - 1 and e.status == "sent"), None)
        if prev is None:
            raise ApiError(409, "EF-SEQ-012", f"Email {em.step - 1} hasn't gone out yet",
                           "Follow-ups reply in the same thread, so they go after the email before them.")
        if prev.sent_at and prev.sent_at + FOLLOW_UP_GAP > now and not (body and body.anyway):
            raise ApiError(409, "EF-SEQ-014", "Too soon after the last email",
                           f"A follow-up can go a day after email {prev.step}, so they don't land minutes apart.")
    em.scheduled_for, em.error = now, ""
    acc = c.db.get(GmailAccount, c.user.id)
    if acc is not None and acc.next_send_at and acc.next_send_at > now:  # the founder asked for this one now
        acc.next_send_at = now
    c.audit("sequence.send_now", str(em.id))
    c.db.commit()
    background.add_task(mailer.send_now_one, em.id)  # goes in seconds, not at the next worker tick
    return {"ok": True, "scheduled_for": now}


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
