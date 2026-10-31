"""Mail on a tracker card: read the latest Gmail thread with the investor, draft an AI update on top of it,
then send it as a reply in that thread (now, or at a set time) from the founder's own Gmail."""

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CardEvent, CompanyProfile, FunnelCard, GmailAccount, Investor, Reveal, Workspace
from . import ai, outreach
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


def msg_out(m: FullMessage, me: str) -> dict:
    return {"id": m.id, "from": m.sender, "to": m.to, "subject": m.subject, "text": m.text[:4000],
            "at": m.at.isoformat() if m.at else None, "mine": me.lower() in m.sender.lower()}


def draft_reply(db: Session, ws: Workspace, card: FunnelCard, thread: list[FullMessage], ask: str) -> dict:
    """An update written on top of the thread. Falls back to a short template without AI."""
    p = db.get(CompanyProfile, ws.id)
    notes = db.scalars(select(CardEvent.body).where(CardEvent.card_id == card.id, CardEvent.kind == "note")
                       .order_by(CardEvent.created_at.desc()).limit(5)).all()
    subject = (thread[-1].subject if thread else "") or f"Update from {(p.company_name if p else '') or 'us'}"
    system = (
        "You write a short email from a founder to an investor, as a reply on top of their existing email thread. "
        "Read the thread and continue it naturally: acknowledge anything the investor asked, then give a concise "
        "update and one clear next step. Under 150 words. Use only facts from the thread, the company profile and "
        "the founder's notes; never invent numbers or names. Open with 'Hi <first name>,'. No signature."
    )
    user = json.dumps({"investor": {"name": card.name, "firm": card.firm, "stage": card.stage},
                       "thread_oldest_first": [{"from": m.sender, "text": m.text[:1500]} for m in thread[-6:]],
                       "company": shareable_profile(p), "founder_notes": notes, "founder_ask": ask[:500],
                       "founder_instructions": instructions(db, ws.id)[:1500]}, default=str)
    out, engine = ai.json_call(db, ws, "draft", system, user, REPLY_SCHEMA, max_tokens=2000)
    if not out:
        out, engine = ai.small_json(db, ws, system, user, REPLY_SCHEMA, max_tokens=1200), "claude"
    if out and out.get("body", "").strip():
        return {"subject": subject, "body": out["body"].strip(), "engine": engine}
    company = (p.company_name if p else "") or "our company"
    traction = (p.traction if p and p.shareable.get("traction", True) else "").rstrip(".")
    lines = [f"Hi {outreach.first_name(card.name)},",
             f"A quick update from {company}." + (f" {traction}." if traction else ""),
             "Would a short call in the next week or two be useful? Happy to send anything you need beforehand."]
    return {"subject": subject, "body": "\n\n".join(lines), "engine": "template"}


def when(send_at: datetime | None, now: datetime) -> datetime:
    return send_at if send_at and send_at > now else now
