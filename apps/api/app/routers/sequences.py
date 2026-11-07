"""§9.3 Outreach sequences: draft (Claude with a fact pack, or the template engine), edit, regenerate, lint,
approve & schedule, WhatsApp nudge (SEQ-07). Approved emails are queued as `scheduled` in the investor's local
send window; the worker sends them from the founder's Gmail (services/mailer.py)."""

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..db import SessionLocal
from ..deps import Ctx, ctx
from ..errors import ApiError, not_found
from ..models import AuditLog, CompanyProfile, Email, FunnelCard, GmailAccount, Investor, Reveal, Sequence, User, Workspace
from ..services import agent, ai, mailer, outreach, send_plan, spam, test_investors, tracker_link
from ..services.entitlements import can, consume, limit
from .investors import _exclusions, auto_reveal, is_excluded

FOLLOW_UP_GAP = timedelta(hours=24)
log = logging.getLogger(__name__)

router = APIRouter(prefix="/sequences", tags=["sequences"])


def s_out(s: Sequence, inv: Investor | None = None, signature: str = "") -> dict:
    def shown(e: Email) -> str:  # what will actually go: USD not $, no link lines in follow-ups
        return e.body if e.status in ("sent", "sending") else outreach.for_send(e.body, e.step)

    return {"id": str(s.id), "investor_id": str(s.investor_id), "status": s.status, "persona": s.persona,
            "engine": s.engine, "drafting": s.engine == DRAFTING, "card_id": str(s.card_id) if s.card_id else None,
            "investor": {"name": inv.name, "firm": inv.current_firm or inv.company} if inv else None,
            "emails": [{"id": str(e.id), "step": e.step, "hook": e.hook, "subject": e.subject, "body": shown(e),
                        "facts": e.facts, "status": e.status, "scheduled_for": e.scheduled_for,
                        "sent_at": e.sent_at, "opened": e.open_count, "reply": e.reply_kind, "error": e.error,
                        "issues": outreach.lint(e.subject, shown(e), e.step, signature),
                        "spam": spam.score(e.subject, shown(e), e.step, inv.name if inv else "")} for e in s.emails]}


class FirstEmail(BaseModel):
    subject: str = Field(max_length=200)
    body: str = Field(max_length=5000)


class DraftIn(BaseModel):
    investor_id: str
    first_email: FirstEmail | None = None  # written on the investor profile; replaces email 1
    persona: str = Field("momentum", pattern="^(momentum|warm-intro|technical-founder|humble-expert)$")
    hold: bool = False  # the quick preview: draft only, even with auto-send on; the founder decides in the sheet
    readd: bool = False  # yes, add them again although they were removed from outreach a moment ago


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
        # Send now was pressed while this was being written: send email 1 the moment it's ready (or queue it behind
        # the one before it), instead of waiting for the worker's next pass
        if s.status == "approved":
            first = next((e for e in s.emails if e.step == 1 and e.status == "scheduled"), None)
            if first is not None and first.scheduled_for and first.scheduled_for <= datetime.now(UTC) + timedelta(seconds=40):
                first.scheduled_for = min(first.scheduled_for, datetime.now(UTC))
                db.commit()
                mailer.send_now_one(first.id)


def _addable(c: Ctx, inv: Investor | None, excl=None) -> Investor:
    """Raises the reason this investor can't be added to outreach."""
    if not test_investors.visible(inv, c.user.email):
        raise not_found("Investor")
    if is_excluded(inv, excl if excl is not None else _exclusions(c)):  # SEQ-06
        raise ApiError(409, "EF-SEQ-001", "This investor is on your exclusion list")
    return inv


def _new_sequence(c: Ctx, inv: Investor, persona: str, later: bool, first_email: "FirstEmail | None" = None):
    """Creates the draft sequence (template emails, AI later when `later`) and commits. Returns (seq, placed)."""
    if not can(c.db, c.workspace, "send"):  # trial: up to N sample drafts
        consume(c.db, c.workspace, "sample_drafts", "all", limit(c.db, c.workspace, "sample_drafts"))
    prof = c.db.get(CompanyProfile, c.ws_id)
    card = c.db.scalar(select(FunnelCard).where(FunnelCard.workspace_id == c.ws_id, FunnelCard.investor_id == inv.id,
                                                FunnelCard.deleted_at.is_(None)))
    emails, engine = agent.draft_sequence(c.db, c.workspace, inv, prof, persona, c.user.signature, use_ai=not later)
    if later:
        engine = DRAFTING
    seq = Sequence(workspace_id=c.ws_id, investor_id=inv.id, card_id=card.id if card else None, persona=persona,
                   user_id=c.user.id, engine=engine)
    c.db.add(seq)
    c.db.flush()
    if first_email:
        emails[0] = {**emails[0], "subject": first_email.subject.strip(),
                     "body": with_opt_out(first_email.body.strip(), c.user.signature)}
        outreach.thread_subjects(emails)
    for e in emails:
        c.db.add(Email(workspace_id=c.ws_id, sequence_id=seq.id, user_id=c.user.id, **e))
    if not (card and card.email):
        auto_reveal(c, inv)  # so it's ready to send with no "reveal first" step
    c.audit("sequence.create", str(seq.id), after={"investor_id": str(inv.id), "investor": inv.name})
    c.db.commit()
    c.db.refresh(seq)
    placed = {e.step: e.body for e in seq.emails if not (first_email and e.step == 1)}
    return seq, placed


@router.post("")
def draft(body: DraftIn, c: Ctx = Depends(ctx), background: BackgroundTasks = None):
    c.require_editor()
    inv = _addable(c, c.db.get(Investor, uuid.UUID(body.investor_id)))
    if not body.readd and (gone := c.db.scalar(select(AuditLog.created_at).where(
            AuditLog.actor_id == c.user.id, AuditLog.action == "sequence.remove",
            AuditLog.after["investor_id"].astext == str(inv.id),
            AuditLog.created_at > datetime.now(UTC) - timedelta(minutes=30)).order_by(AuditLog.created_at.desc()).limit(1))):
        mins = max(int((datetime.now(UTC) - gone).total_seconds() // 60), 0)
        raise ApiError(409, "EF-SEQ-031", f"You removed {inv.name} from outreach {'just now' if mins < 1 else f'{mins} min ago'}",
                       "Add them again?", {"needs_readd": True})
    auto = auto_send_on(c.workspace)
    # Answer at once with lint-clean template drafts; the AI versions (10-20s) are written in the background.
    later = background is not None and ai.available()
    seq, placed = _new_sequence(c, inv, body.persona, later, body.first_email)
    if later:
        background.add_task(finish_ai_draft, seq.id, c.user.id, placed)
    sent = try_auto_send(c, seq) if auto and not body.hold else None
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
    cards = dict(c.db.execute(select(FunnelCard.investor_id, FunnelCard.id).where(  # who's in the tracker
        FunnelCard.workspace_id == c.ws_id, FunnelCard.investor_id.is_not(None), FunnelCard.deleted_at.is_(None))).all())
    items = []
    for s, i in rows:
        why = blocker(c, s) if s.status == "draft" else None
        items.append({"id": str(s.id), "status": s.status, "investor": {"id": str(i.id), "name": i.name,
                      "firm": i.current_firm or i.company}, "created_at": s.created_at,
                      "country": i.country or "",
                      "email": next((e.to_email for e in s.emails if e.to_email), ""),
                      "blocker": why, "ready": s.status == "draft" and why is None and s.engine != DRAFTING,
                      "drafting": s.engine == DRAFTING,
                      "card_id": str(cards[i.id]) if i.id in cards else None,
                      "seen": any(e.status == "sent" and (e.open_count or 0) > 0 for e in s.emails),
                      "replied": any(e.replied_at is not None and e.reply_kind not in ("bounce", "auto")
                                     for e in s.emails),
                      "reply": max(((e.replied_at, e.reply_kind) for e in s.emails
                                    if e.replied_at and e.reply_kind not in ("bounce", "auto")), default=(None, ""))[1],
                      "paused": sum(e.status == "paused" for e in s.emails),
                      "bounced": any(e.bounced_at is not None for e in s.emails),
                      # why the next email moved (allowance, per-firm limit, pacing...), shown under the row
                      "note": next((e.error for e in sorted(s.emails, key=lambda e: e.step)
                                    if e.status == "scheduled" and e.error), ""),
                      "sent": sum(e.status == "sent" for e in s.emails),
                      "next_at": min((e.scheduled_for for e in s.emails if e.status == "scheduled"), default=None)})
    return {"auto_send": auto_send_on(c.workspace), "auto_send_when": auto_send_when(c.workspace), "items": items}


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
                      "body": outreach.fill_first_name(outreach.for_send(e.body, e.step), inv.name), "to": e.to_email,
                      "spam": spam.score(e.subject, outreach.for_send(e.body, e.step), e.step, inv.name),
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
    """Follow-ups scheduled later than 2 working days after the email before them (the old 1-week spacing)."""
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
    """Move follow-ups on the old spacing to 2 working days after the email before them. Without confirm it only
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


class BulkIn(BaseModel):
    action: str = Field(pattern="^(send|regenerate|remove)$")
    ids: list[str] = Field(max_length=500)
    confirm: bool = False


@router.post("/bulk")
def bulk(body: BulkIn, background: BackgroundTasks, c: Ctx = Depends(ctx)):
    """Send, regenerate or remove the ticked sequences. Without confirm=true it only reports how many qualify and
    which are skipped (and why); nothing changes. Regenerate is queued: the AI redrafts in the background."""
    c.require_editor()
    wanted = []
    for x in dict.fromkeys(body.ids):
        try:
            wanted.append(uuid.UUID(x))
        except ValueError:
            pass
    rows = c.db.execute(select(Sequence, Investor).join(Investor).where(
        Sequence.workspace_id == c.ws_id, Sequence.id.in_(wanted)).order_by(Sequence.created_at)).all() if wanted else []
    found = {s.id for s, _ in rows}
    skipped = [{"id": str(x), "name": "", "reason": "Not found"} for x in wanted if x not in found]
    eligible: list[tuple] = []
    for s, inv in rows:
        if body.action == "remove":
            eligible.append((s, inv, ""))
            continue
        if s.status != "draft":
            why = "Already scheduled or sent" if body.action == "send" else "Only drafts can be regenerated"
            skipped.append({"id": str(s.id), "name": inv.name, "reason": why})
            continue
        if body.action == "send":
            try:
                inv, to, _ = _ready(c, s, reveal=body.confirm)
            except ApiError as e:
                skipped.append({"id": str(s.id), "name": inv.name, "reason": e.title})
                continue
            eligible.append((s, inv, to))
        else:
            eligible.append((s, inv, ""))
    if not body.confirm:
        c.db.rollback()
        return {"needs_confirm": True, "eligible": len(eligible), "skipped": skipped}
    ids = [str(s.id) for s, _, _ in eligible]
    if body.action == "send":
        now = datetime.now(UTC)
        plan = _planner(c, now)
        for s, inv, to in eligible:
            outreach.schedule(s.emails, now, inv.timezone, first_at=plan.place(inv.timezone))
            _schedule(c, s, inv, to, {"via": "outreach_bulk_send", "when": "window", "confirmed": True})
        c.audit("sequence.bulk_send", str(c.ws_id), after={"ids": ids})
        c.db.commit()
        return {"done": len(eligible), "skipped": skipped, "allowance": plan.summary()}
    if body.action == "regenerate":
        for s, _, _ in eligible:
            s.engine = DRAFTING  # the list shows them as being redrafted until the background task finishes
        c.audit("sequence.bulk_regenerate", str(c.ws_id), after={"ids": ids})
        c.db.commit()
        background.add_task(bulk_redraft, [s.id for s, _, _ in eligible], c.user.id)
        return {"queued": len(eligible), "skipped": skipped}
    kept = sum(remove_one(c, s) for s, _, _ in eligible)
    c.audit("sequence.bulk_remove", str(c.ws_id), after={"ids": ids, "kept_history": kept})
    c.db.commit()
    return {"done": len(eligible), "kept_history": kept}


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


PERSONAS = ("momentum", "warm-intro", "technical-founder", "humble-expert")


def redraft(db, ws: Workspace, s: Sequence, persona: str, signature: str) -> Investor:
    """Redraft every email of a draft sequence with this persona (Claude or the template engine). No commit."""
    inv = db.get(Investor, s.investor_id)
    emails, engine = agent.draft_sequence(db, ws, inv, db.get(CompanyProfile, s.workspace_id), persona, signature)
    by_step = {e["step"]: e for e in emails}
    for em in s.emails:
        e = by_step[em.step]
        em.hook, em.subject, em.body, em.facts = e["hook"], e["subject"], e["body"], e["facts"]
        em.pre_update_body = e.get("pre_update_body")
    s.persona, s.engine = persona, engine
    return inv


def bulk_redraft(seq_ids: list[uuid.UUID], user_id: uuid.UUID) -> None:
    """Background half of bulk regenerate: redraft each still-draft sequence with its own persona. One failing
    sequence is logged and skipped; the rest still get redrafted."""
    with SessionLocal() as db:
        user = db.get(User, user_id)
        signature = user.signature if user else ""
        for sid in seq_ids:
            try:
                s = db.get(Sequence, sid)
                if s is None:
                    continue
                if s.status != "draft":  # sent or removed meanwhile: don't leave it looking "rewriting"
                    if s.engine == DRAFTING:
                        s.engine = "template"
                        db.commit()
                    continue
                persona = s.persona if s.persona in PERSONAS else "momentum"
                redraft(db, db.get(Workspace, s.workspace_id), s, persona, signature)
                db.commit()
            except Exception:
                log.exception("bulk regenerate failed for sequence %s", sid)
                db.rollback()
                s = db.get(Sequence, sid)
                if s is not None and s.engine == DRAFTING:
                    s.engine = "template"
                    db.commit()


@router.post("/{sid}/regenerate")
def regenerate(sid: str, body: RegenIn, c: Ctx = Depends(ctx)):
    """SEQ-05 "Change the approach": redraft unsent emails with another persona."""
    c.require_editor()
    s = _get(c, sid)
    if s.status != "draft":
        raise ApiError(409, "EF-SEQ-006", "Only drafts can be regenerated")
    inv = redraft(c.db, c.workspace, s, body.persona, c.user.signature)
    c.db.commit()
    return s_out(s, inv, c.user.signature)


class ApproveIn(BaseModel):
    confirm: bool = False  # the founder saw who, from which mailbox and when, and said yes
    first_at: str = Field("window", pattern="^(window|now)$")  # email 1 in their morning send window, or straight away


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


def _planner(c: Ctx, now: datetime) -> send_plan.DayPlanner:
    return send_plan.DayPlanner(c.db, c.workspace, c.user, c.db.get(GmailAccount, c.user.id), now)


def blocker(c: Ctx, s: Sequence) -> str | None:
    """Why this draft can't be scheduled yet, in plain words (None when it's ready)."""
    try:
        _ready(c, s, reveal=False)  # a check only: never spends a credit
    except ApiError as e:
        return e.title
    return None


def _schedule(c: Ctx, s: Sequence, inv: Investor, to: str, how: dict | None = None) -> None:
    s.status, s.user_id = "approved", c.user.id
    if s.card_id is None:  # already in the tracker: log there. Otherwise they join it on "Add to tracker" or a positive reply
        card = tracker_link.card_of(c.db, c.ws_id, inv.id)
        s.card_id = card.id if card else None
    for em in s.emails:
        em.to_email, em.card_id, em.user_id = to, s.card_id, c.user.id
    # The record of consent: who approved sending what, to whom, when, from where (shown in Admin > Audit log)
    c.audit("sequence.approve", str(s.id), after={
        "investor": inv.name, "to": to, **(how or {}),
        "emails": [{"step": e.step, "subject": e.subject, "scheduled_for": e.scheduled_for.isoformat()
                    if e.scheduled_for else None} for e in sorted(s.emails, key=lambda e: e.step)]})


def auto_send_when(ws) -> str:
    """'window' (default): email 1 in the investor's next local morning send window. 'now': as soon as added."""
    return "now" if (ws.automations or {}).get("auto_send_when") == "now" else "window"


def auto_send_on(ws) -> bool:
    """Auto-send is opt-in: a missing key means off (unlike the §10.4 automations)."""
    return (ws.automations or {}).get("auto_send") is True


def try_auto_send(c: Ctx, s: Sequence) -> dict:
    """Workspace has auto-send on: schedule a fresh draft straight away when nothing blocks it."""
    try:
        inv, to, _ = _ready(c, s)
    except ApiError as e:
        return {"scheduled": False, "reason": e.title}
    now = datetime.now(UTC)
    # "As soon as added": a couple of minutes' grace so the AI version (written in the background) goes, not the
    # template; the mailer still spaces sends out and keeps the daily limit. Otherwise their morning send window.
    first_at = now if auto_send_when(c.workspace) == "now" else None  # the mailer waits for the AI version
    outreach.schedule(s.emails, now, inv.timezone, first_at=_planner(c, now).place(inv.timezone, first_at))
    _schedule(c, s, inv, to, {"via": "auto_send_setting", "when": "now" if first_at else "window"})
    c.db.commit()
    return {"scheduled": True, "reason": "", "when": "now" if first_at else "window"}


@router.post("/{sid}/approve")
def approve(sid: str, body: ApproveIn | None = None, c: Ctx = Depends(ctx)):
    """SEQ-05: Approve & schedule. Lint must pass; slots land in the investor's local send window.
    Without confirm=true nothing is scheduled: the reply (409 needs_confirm) carries the exact sender, recipient
    and send times so the founder confirms before anything can go out from their Gmail."""
    c.require_editor()
    s = _get(c, sid)
    inv, to, acc = _ready(c, s, reveal=bool(body and body.confirm))
    now = datetime.now(UTC)
    plan = _planner(c, now)
    outreach.schedule(s.emails, now, inv.timezone, first_at=plan.place(
        inv.timezone,
        # "now": a short grace, longer while the AI version is still being written so that one goes
        # "now" means now: if the AI version is still being written the mailer holds it and finish_ai_draft sends it
        now if body and body.first_at == "now" else None))
    if not (body and body.confirm):
        preview = {"from": acc.email, "to": to, "investor": inv.name, "timezone": inv.timezone,
                   "allowance": plan.summary(),
                   "emails": [{"step": e.step, "subject": e.subject, "scheduled_for": e.scheduled_for.isoformat()}
                              for e in sorted(s.emails, key=lambda e: e.step)]}
        c.db.rollback()
        raise ApiError(409, "EF-SEQ-010", "Confirm sending", "", {"needs_confirm": True, "preview": preview})
    _schedule(c, s, inv, to, {"via": "approve", "when": body.first_at, "confirmed": True, "from": acc.email})
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
    plan = _planner(c, now)
    for s, inv, to in ready:
        outreach.schedule(s.emails, now, inv.timezone, first_at=plan.place(inv.timezone))
        _schedule(c, s, inv, to, {"via": "send_all", "when": "window", "confirmed": True})
    c.db.commit()
    return {"scheduled": len(ready), "skipped": skipped, "allowance": plan.summary()}


class BulkAddIn(BaseModel):
    investor_ids: list[str] = Field(min_length=1, max_length=50)
    action: str = Field(pattern="^(window|now|draft)$")  # schedule for their morning, send now, or keep as drafts
    confirm: bool = False  # the founder read the confirm screen and ticked "I agree"
    persona: str = Field("momentum", pattern="^(momentum|warm-intro|technical-founder|humble-expert)$")


def finish_ai_drafts(jobs: list[tuple[uuid.UUID, uuid.UUID, dict]]) -> None:
    """Personalise several sequences at once (a few in parallel) so a bulk add doesn't take one minute per investor."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=4) as pool:
        for f in [pool.submit(finish_ai_draft, *j) for j in jobs]:
            try:
                f.result()
            except Exception:
                log.exception("bulk AI draft failed")


@router.post("/bulk-add")
def bulk_add(body: BulkAddIn, request: Request, c: Ctx = Depends(ctx), background: BackgroundTasks = None):
    """Investor list > select > Add to outreach: AI-personalised 3-email sequences for each, then scheduled for
    their morning, sent now, or kept as drafts. Scheduling or sending needs confirm=true; without it the reply is
    the confirm screen (who, from which mailbox, who is skipped and why) and nothing is created. The founder's
    acceptance is written to the audit log with what they agreed to."""
    c.require_editor()
    sending = body.action != "draft"
    acc = c.db.get(GmailAccount, c.user.id)
    if sending:
        if not can(c.db, c.workspace, "send"):
            raise ApiError(402, "EF-TIER-030", "Upgrade to send emails", "Trial accounts can draft but not send.",
                           {"upgrade": True})
        if not c.user.signature.strip():
            raise ApiError(409, "EF-SEQ-003", "Set your email signature first", "", {"needs_signature": True})
        if acc is None or acc.status != "connected":
            raise ApiError(409, "EF-SEQ-007", "Connect Gmail to send", "Emails go out from your own Gmail.",
                           {"needs_gmail": True})
    ids = []
    for x in dict.fromkeys(body.investor_ids):
        try:
            ids.append(uuid.UUID(x))
        except ValueError:
            pass
    invs = {i.id: i for i in c.db.scalars(select(Investor).where(Investor.id.in_(ids)))} if ids else {}
    have = set(c.db.scalars(select(Sequence.investor_id).where(Sequence.workspace_id == c.ws_id,
                                                                Sequence.status != "stopped",
                                                                Sequence.investor_id.in_(ids)))) if ids else set()
    excl = _exclusions(c)
    ok, skipped = [], []
    for i in ids:
        inv = invs.get(i)
        if i in have:
            skipped.append({"id": str(i), "name": inv.name if inv else "", "reason": "Already in your outreach list"})
            continue
        try:
            ok.append(_addable(c, inv, excl))
        except ApiError as e:
            skipped.append({"id": str(i), "name": inv.name if inv else "", "reason": e.title})
    plan = {"action": body.action, "from": acc.email if acc else "", "count": len(ok),
            "investors": [{"id": str(i.id), "name": i.name, "firm": i.current_firm or i.company} for i in ok],
            "skipped": skipped, "terms": BULK_TERMS.get(body.action, "")}
    now = datetime.now(UTC)
    planner = _planner(c, now)
    if sending and not body.confirm:
        sim = _planner(c, now)  # where each first email would land, within the daily allowance
        for inv in ok:
            sim.place(inv.timezone, now if body.action == "now" else None)
        return {"needs_confirm": True, **plan, "allowance": sim.summary()}
    later = background is not None and ai.available()
    done, drafts, failed, jobs = [], [], [], []
    for inv in ok:
        try:
            seq, placed = _new_sequence(c, inv, body.persona, later)
        except ApiError as e:
            c.db.rollback()
            failed.append({"id": str(inv.id), "name": inv.name, "reason": e.title})
            continue
        if later:
            jobs.append((seq.id, c.user.id, placed))
        if not sending:
            drafts.append({"id": str(seq.id), "name": inv.name})
            continue
        try:
            inv, to, _ = _ready(c, seq)
        except ApiError as e:  # stays in outreach as a draft, with the reason
            drafts.append({"id": str(seq.id), "name": inv.name, "reason": e.title})
            continue
        # "now": 90s grace so the AI-personalised version goes; the mailer spaces sends and keeps the daily limit
        outreach.schedule(seq.emails, now, inv.timezone, first_at=planner.place(
            inv.timezone, now if body.action == "now" else None))
        _schedule(c, seq, inv, to, {"via": "investor_list_bulk", "when": body.action, "confirmed": True,
                                    "from": acc.email})
        c.db.commit()
        done.append({"id": str(seq.id), "name": inv.name})
    c.audit("sequence.bulk_add", str(c.ws_id), after={
        "action": body.action, "confirmed": bool(body.confirm), "from": acc.email if acc else "",
        "agreed_to": BULK_TERMS[body.action] if sending else "", "user_agent": request.headers.get("user-agent", "")[:300],
        "scheduled": done, "drafts": drafts, "skipped": skipped + failed})
    c.db.commit()
    if jobs:
        background.add_task(finish_ai_drafts, jobs)
    return {"scheduled": len(done), "drafts": drafts, "skipped": skipped + failed, "action": body.action,
            "allowance": planner.summary()}


BULK_TERMS = {  # what the confirm screen says; stored with the acceptance in the audit log
    "window": "AI personalises 3 emails per investor and schedules them from my Gmail: email 1 in each investor's "
              "local morning, follow-ups 2 working days apart, stopping on any reply.",
    "now": "AI personalises 3 emails per investor and sends email 1 from my Gmail within a few minutes; follow-ups "
           "2 working days apart, stopping on any reply.",
}


class FollowUpsIn(BaseModel):
    action: str = Field(pattern="^(resume|send_now|cancel)$")


@router.post("/{sid}/followups")
def followups(sid: str, body: FollowUpsIn, c: Ctx = Depends(ctx), background: BackgroundTasks = None):
    """Follow-ups paused by a reply: resume them (next one 2 working days from now, then spaced as usual), send
    the next one now, or cancel them. Resuming or sending is the founder's explicit choice, recorded in the log."""
    c.require_editor()
    s = _get(c, sid)
    held = sorted((e for e in s.emails if e.status == "paused"), key=lambda e: e.step)
    if not held:
        raise ApiError(409, "EF-SEQ-030", "No paused follow-ups", "This investor has no follow-ups waiting.")
    inv = c.db.get(Investor, s.investor_id)
    if body.action == "cancel":
        for e in held:
            e.status, e.error = "cancelled", "Cancelled after their reply"
        c.audit("sequence.followups_cancel", str(s.id), after={"investor": inv.name, "steps": [e.step for e in held]})
        c.db.commit()
        return s_out(s, inv, c.user.signature)
    acc = c.db.get(GmailAccount, c.user.id)
    if acc is None or acc.status != "connected":
        raise ApiError(409, "EF-SEQ-007", "Connect Gmail to send", "Emails go out from your own Gmail.", {"needs_gmail": True})
    now = datetime.now(UTC)
    tz = inv.timezone if inv else "UTC"
    prev = None
    for e in held:
        e.scheduled_for = (now if body.action == "send_now" and prev is None
                           else outreach.follow_up_slot(prev or now, tz))
        e.status, e.error = "scheduled", ""
        prev = e.scheduled_for
    s.status = "approved"  # updated_at moves past the reply, so the mailer's stop-on-reply lets these go
    c.audit("sequence.followups_" + body.action, str(s.id), after={
        "investor": inv.name, "confirmed": True,
        "emails": [{"step": e.step, "scheduled_for": e.scheduled_for.isoformat()} for e in held]})
    c.db.commit()
    if body.action == "send_now" and background is not None:
        background.add_task(mailer.send_now_one, held[0].id)  # goes in seconds, not at the next worker tick
    return s_out(s, inv, c.user.signature)


@router.delete("/{sid}")
def remove(sid: str, c: Ctx = Depends(ctx)):
    """Remove an investor from outreach. Nothing sent yet: the sequence is deleted. Something sent: it stops, unsent
    emails are cancelled and the sent ones stay in Activity."""
    c.require_editor()
    kept = remove_one(c, _get(c, sid))
    c.db.commit()
    return {"ok": True, "kept_history": kept}


def remove_one(c: Ctx, s: Sequence) -> bool:
    """DELETE /{sid} without the commit. Returns True when sent history was kept (stopped, not deleted)."""
    sid = str(s.id)
    if any(e.status in ("sent", "sending") for e in s.emails):
        s.status = "stopped"
        for e in s.emails:
            if e.status in ("scheduled", "draft"):
                e.status, e.error = "cancelled", "Removed from outreach"
        kept = True
    else:
        c.db.delete(s)
        kept = False
    # Their pending progress updates go too: removing someone from outreach means nothing more goes to them
    inv = c.db.get(Investor, s.investor_id)
    to = {e.to_email.lower() for e in s.emails if e.to_email} | ({inv.email.lower()} if inv and inv.email else set())
    cond = Email.card_id == s.card_id if s.card_id else None
    if to:
        cond = func.lower(Email.to_email).in_(to) if cond is None else cond | func.lower(Email.to_email).in_(to)
    updates = c.db.scalars(select(Email).where(Email.workspace_id == c.ws_id, Email.broadcast_id.is_not(None),
                                               Email.status == "scheduled", cond)).all() if cond is not None else []
    for e in updates:
        e.status, e.error = "cancelled", "Removed from outreach"
    c.audit("sequence.remove", sid, after={"kept_history": kept, "investor_id": str(s.investor_id),
                                           "investor": inv.name if inv else "", "updates_cancelled": len(updates)})
    return kept


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
