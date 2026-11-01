"""Mail on a tracker card: read the latest Gmail thread with the investor, draft an AI update on top of it,
then send it as a reply in that thread (now, or at a set time) from the founder's own Gmail."""

import json
import re
from datetime import UTC, datetime
from email.utils import getaddresses

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CardEvent, CompanyProfile, Email, FunnelCard, GmailAccount, Investor, Reveal, Workspace
from . import ai, follow_up, outreach
from .agent import instructions, shareable_profile
from .gmail import FullMessage, client_for

REPLY_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["subject", "body"],
                "properties": {"subject": {"type": "string"}, "body": {"type": "string"}}}


def address(db: Session, ws_id, card: FunnelCard) -> str:
    """The investor's email: the card's, else the database's when this workspace revealed it."""
    if card.email:
        return card.email
    if card.investor_id and db.get(Reveal, (ws_id, card.investor_id)):
        inv = db.get(Investor, card.investor_id)
        return inv.email if inv else ""
    return ""


def latest_thread(db: Session, acc: GmailAccount, addr: str) -> list[FullMessage]:
    gm = client_for(db, acc)
    tid = gm.latest_thread_with(addr)
    return gm.thread_full(tid) if tid else []


def reply_all(thread: list[FullMessage], me: str, investor: str) -> dict:
    """Recipients and subject exactly as Gmail's Reply all on the latest message: answering someone else goes to
    the sender with everyone else copied; answering my own message goes to the same people again."""
    if not thread:
        return {"to": [investor] if investor else [], "cc": [], "subject": ""}
    last, me = thread[-1], me.lower()

    def addrs(*headers: str) -> list[str]:
        return [a for _, a in getaddresses(list(headers)) if "@" in a]

    sender = (addrs(last.sender) or [""])[0]
    if me and sender.lower() == me:
        to, cc = addrs(last.to), addrs(last.cc)
    else:
        to, cc = [sender], addrs(last.to, last.cc)
    seen, out_to, out_cc = {me, ""}, [], []
    for a, bucket in [(x, out_to) for x in to] + [(x, out_cc) for x in cc]:
        if a.lower() not in seen:
            seen.add(a.lower())
            bucket.append(a)
    if not out_to and investor:  # a note to myself in the thread: still reply to the investor
        out_to = [investor]
    # the investor first, so exclusions and bounces key off them
    out_to.sort(key=lambda a: a.lower() != investor.lower())
    subject = re.sub(r"^\s*((re|fwd?)\s*:\s*)+", "", last.subject or thread[0].subject, flags=re.I).strip()
    return {"to": out_to, "cc": out_cc, "subject": f"Re: {subject}" if subject else ""}


def sync(db: Session, card: FunnelCard, acc: GmailAccount, addr: str) -> int:
    """Logs on the card any Gmail message to or from the investor that isn't on its timeline yet: their emails as
    replies, the founder's (sent from Gmail directly) as emails. Returns how many were added."""
    msgs = client_for(db, acc).messages_with(addr)
    if not msgs:
        return 0
    known = {str((e.meta or {}).get("gmail_id")) for e in db.scalars(
        select(CardEvent).where(CardEvent.card_id == card.id, CardEvent.kind.in_(["reply", "email"])))}
    known |= set(db.scalars(select(Email.gmail_message_id).where(  # sent from the app: already logged by the mailer
        Email.workspace_id == card.workspace_id, Email.gmail_message_id.in_([m.id for m in msgs]))))
    me, added, newest_in = acc.email.lower(), 0, None
    for m in msgs:
        if m.id in known:
            continue
        mine = bool(me) and me in m.sender.lower()
        text = m.text.strip()[:1500]
        if mine:
            body, kind = f"Email sent: {m.subject}\n\n{text}", "email"
            if m.at and (not card.last_contacted_at or m.at > card.last_contacted_at):
                card.last_contacted_at = m.at
        else:
            body, kind = text[:500] or m.subject, "reply"
        ev = CardEvent(workspace_id=card.workspace_id, card_id=card.id, kind=kind, body=body,
                       meta={"gmail_id": m.id, "from": m.sender, "subject": m.subject, "synced": True})
        if m.at:
            ev.created_at = m.at  # the timeline shows it when it happened, not when it was found
        db.add(ev)
        added += 1
        if kind == "reply":
            newest_in = (m, ev)
    if newest_in is not None and newest_in[0] is msgs[-1]:
        # their new message is the latest word in the conversation: chase when they said they'd come back
        if d := follow_up.from_reply(db, card, acc.user_id, newest_in[0].text, datetime.now(UTC)):
            newest_in[1].meta = {**newest_in[1].meta, "follow_up": d.isoformat()}
    return added


def msg_out(m: FullMessage, me: str) -> dict:
    return {"id": m.id, "from": m.sender, "to": m.to, "cc": m.cc, "subject": m.subject, "text": m.text[:4000],
            "at": m.at.isoformat() if m.at else None, "mine": me.lower() in m.sender.lower()}


def sign_off(body: str, founder: str) -> str:
    """Ends the draft with 'Best,' and the founder's first name, unless the draft already closes itself."""
    body = body.rstrip()
    if re.search(r"\n\s*(best|thanks|cheers|regards|kind regards|best regards|warm regards)[,!.]?\s*(\n.*)?$",
                 body[-80:], re.I):
        return body
    name = founder.split()[0] if founder.strip() else ""
    return f"{body}\n\nBest,\n{name}".rstrip()


def draft_reply(db: Session, ws: Workspace, card: FunnelCard, thread: list[FullMessage], ask: str,
                founder: str = "") -> dict:
    """An update written on top of the thread. Falls back to a short template without AI."""
    p = db.get(CompanyProfile, ws.id)
    notes = db.scalars(select(CardEvent.body).where(CardEvent.card_id == card.id, CardEvent.kind == "note")
                       .order_by(CardEvent.created_at.desc()).limit(5)).all()
    subject = (thread[-1].subject if thread else "") or f"Update from {(p.company_name if p else '') or 'us'}"
    system = (
        "You write a short email from a founder to an investor, as a reply on top of their existing email thread. "
        "Read the thread and continue it naturally: acknowledge anything the investor asked, then give a concise "
        "update and one clear next step. Under 150 words. Use only facts from the thread, the company profile and "
        "the founder's notes; never invent numbers or names. Don't bring up investing, the round or their ticket size "
        "unless the investor asked about it in the thread. Open with 'Hi <first name>,'. No sign-off or signature."
    )
    user = json.dumps({"investor": {"name": card.name, "firm": card.firm, "stage": card.stage},
                       "thread_oldest_first": [{"from": m.sender, "text": m.text[:1500]} for m in thread[-6:]],
                       "company": shareable_profile(p), "founder_notes": notes, "founder_ask": ask[:500],
                       "founder_instructions": instructions(db, ws.id)[:1500]}, default=str)
    out, engine = ai.json_call(db, ws, "draft", system, user, REPLY_SCHEMA, max_tokens=2000)
    if not out:
        out, engine = ai.small_json(db, ws, system, user, REPLY_SCHEMA, max_tokens=1200), "claude"
    if out and out.get("body", "").strip():
        return {"subject": subject, "body": sign_off(out["body"], founder), "engine": engine}
    company = (p.company_name if p else "") or "our company"
    traction = (p.traction if p and p.shareable.get("traction", True) else "").rstrip(".")
    lines = [f"Hi {outreach.first_name(card.name)},",
             f"A quick update from {company}." + (f" {traction}." if traction else ""),
             "Would a short call in the next week or two be useful? Happy to send anything you need beforehand."]
    return {"subject": subject, "body": sign_off("\n\n".join(lines), founder), "engine": "template"}


def when(send_at: datetime | None, now: datetime) -> datetime:
    return send_at if send_at and send_at > now else now
