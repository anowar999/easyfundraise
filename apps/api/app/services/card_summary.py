"""Top-of-card summary for the founder: where this investor stands and the one next step, from the card,
its notes, emails and reminders. Small model when available, plain rules otherwise."""

import json
import re
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import STAGES, CardEvent, FunnelCard, Workspace
from . import ai

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["headline", "next_step"],
          "properties": {"headline": {"type": "string"}, "next_step": {"type": "string"}}}
_cache: dict[tuple, dict] = {}  # (card id, last change) -> summary; a new note or edit makes a new key

ASKED_FOR = re.compile(r"\b(deck|data ?room|numbers|metrics|financials|model|one[- ]pager|intro|references?|"
                       r"follow[- ]?up|send|share)\b", re.I)
SENT = re.compile(r"\b(sent|shared|emailed|forwarded)\b", re.I)  # the note itself says it went out


def _days(d: datetime | None, now: datetime) -> int | None:
    return (now - d).days if d else None


def rules(card: FunnelCard, events: list[CardEvent], now: datetime) -> dict:
    stage = STAGES[card.stage - 1].split(" ", 1)[-1]
    last = _days(card.last_contacted_at, now)
    notes = [e for e in events if e.kind == "note"]
    reply = next((e for e in events if e.kind == "reply"), None)
    sent_after_note = notes and any(e.kind == "email" and e.created_at > notes[0].created_at for e in events)
    when = "never contacted" if last is None else "last contact today" if last == 0 else f"last contact {last} day{'s' * (last != 1)} ago"
    head = f"{stage} · {when}."
    if card.status == "Rejection":
        return {"headline": f"They passed ({when}).", "next_step": "Log why they passed if you haven't, and ask if they'd intro a better-fit investor."}
    if card.status == "Inactive":
        return {"headline": f"Marked inactive · {when}.", "next_step": "Nothing to do unless they come back. Reactivate the card if they do."}
    if reply and (not card.last_contacted_at or reply.created_at > card.last_contacted_at):
        days = _days(reply.created_at, now) or 0
        return {"headline": f"They replied {'today' if not days else f'{days} days ago'}: “{reply.body[:120]}”",
                "next_step": "Reply to keep the momentum. Use Email to answer in the same thread."}
    if card.call_at and card.call_at > now:
        return {"headline": f"{head} Call booked for {card.call_at:%a %d %b, %H:%M}.",
                "next_step": "Prep your brief and send any material they asked for before the call."}
    done = notes and any(SENT.search(n.body) for n in notes
                         if n.created_at >= notes[0].created_at - timedelta(days=1))
    if notes and ASKED_FOR.search(notes[0].body) and not sent_after_note and not done:
        return {"headline": f"{head} Your last note says: “{notes[0].body[:140]}”",
                "next_step": "Did you send it? If so, mark as contacted; if not, send it now."}
    if card.next_contact_date and card.next_contact_date < date.today():
        return {"headline": f"{head} Follow-up was due {card.next_contact_date:%d %b}.", "next_step": "Time to follow up."}
    if card.next_contact_date == date.today():
        return {"headline": head, "next_step": "Follow up today."}
    if last is None:
        return {"headline": f"{stage} · not contacted yet.", "next_step": "Send a short, personalised intro email."}
    if last >= 7:
        return {"headline": head, "next_step": "Time to follow up with a short update."}
    return {"headline": head, "next_step": f"Set a next contact date{' for next week' if last <= 3 else ''} so it doesn't go quiet."}


def summary(db: Session, ws: Workspace, card: FunnelCard) -> dict:
    events = db.scalars(select(CardEvent).where(CardEvent.card_id == card.id)
                        .order_by(CardEvent.created_at.desc()).limit(15)).all()
    key = (card.id, card.updated_at, events[0].created_at if events else None)
    if key in _cache:
        return _cache[key]
    now = datetime.now(UTC)
    base = rules(card, events, now)
    system = ("You brief a startup founder on one investor in their fundraise. Give a one-sentence headline of where "
              "things stand (stage, last contact, anything outstanding) and the single most useful next step. Be "
              "specific and short; quote the founder's own note when it shows something outstanding (e.g. a deck they "
              "promised). Use only the facts given. No greetings.")
    facts = {"investor": card.name, "firm": card.firm, "stage": STAGES[card.stage - 1], "status": card.status,
             "priority": card.priority, "today": str(date.today()),
             "days_since_last_contact": _days(card.last_contacted_at, now),
             "next_contact_date": str(card.next_contact_date or ""), "call_at": str(card.call_at or ""),
             "recent_activity_newest_first": [{"kind": e.kind, "text": e.body[:300], "days_ago": _days(e.created_at, now)}
                                              for e in events[:10]],
             "rule_based_suggestion": base}
    out = ai.small_json(db, ws, system, json.dumps(facts, default=str), SCHEMA, max_tokens=400)
    res = {**(out if out and out.get("headline") and out.get("next_step") else base), "engine": "claude" if out else "rules"}
    _cache[key] = res
    return res
