"""A round & progress update to every investor already emailed: written (or AI-polished) once, sent as a reply in
each investor's existing Gmail thread at 08:35 their time, never within a day of another email to them."""

import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Broadcast, Email, FunnelCard, Investor, Sequence, User, Workspace
from . import ai
from .outreach import first_name

SEND_AT = time(8, 35)
GAP_DAYS = 3  # moved this far when another email lands within a day
TEMPLATE = "progress"
NO_SEND = ("negative", "opt_out", "bounce")


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def tidy(text: str) -> str:
    """Whitespace and the first capital and full stop; the founder's words are otherwise kept as written."""
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    out = []
    for p in paras:
        p = p[0].upper() + p[1:]
        out.append(p if re.search(r"[.!?:)]$", p) else f"{p}.")
    return "\n\n".join(out)


POLISH_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["text"],
                 "properties": {"text": {"type": "string"}}}


def polish(db: Session, ws: Workspace, text: str) -> tuple[str, str]:
    """AI rewrite into a short, warm investor update. Falls back to tidy() without AI."""
    system = (f"{ai.SAFETY}\n\nYou polish a startup founder's short round & progress update before it goes to investors "
              "they have already emailed. Keep every fact, number and name exactly as given and add none. Plain, warm, "
              "confident; 2-5 short sentences, at most two short paragraphs. No greeting, no sign-off, no subject, no "
              "hype words, no emojis, no markdown. Write in the founder's first person (we / I).")
    out = ai.small_json(db, ws, system, f"The founder's update:\n{text.strip()}", POLISH_SCHEMA, max_tokens=600)
    t = (out or {}).get("text", "").strip()
    return (tidy(t), "ai") if t else (tidy(text), "template")


def body_for(text: str, signature: str, name: str = "") -> str:
    body = f"Hi {first_name(name) if name else '{first name}'},\n\nA quick update from our side.\n\n{tidy(text)}\n\nHappy to share more or find 15 minutes if useful."
    return f"{body}\n\n{signature.strip()}" if signature.strip() else body


def recipients(db: Session, ws_id) -> list[dict]:
    """One row per investor who has been sent at least one outreach email, with the thread to reply in."""
    rows = db.execute(select(Email, Sequence).join(Sequence, Sequence.id == Email.sequence_id).where(
        Email.workspace_id == ws_id, Email.status == "sent").order_by(Email.sent_at)).all()
    by_seq: dict = {}
    for em, s in rows:
        by_seq.setdefault(s.id, (s, []))[1].append(em)
    out, seen = [], set()
    for s, sent in by_seq.values():
        if any(e.reply_kind in NO_SEND or e.bounced_at for e in s.emails):
            continue
        last, first = sent[-1], min(sent, key=lambda e: e.step)
        to = (last.to_email or "").strip().lower()
        if not to or to in seen:
            continue
        seen.add(to)
        card = db.get(FunnelCard, last.card_id) if last.card_id else None
        if card is not None and card.status == "Rejection":
            continue
        inv = db.get(Investor, s.investor_id) if s.investor_id else None
        tz = (card.investor_timezone if card else "") or (inv.timezone if inv else "") or "UTC"
        out.append({"to": last.to_email, "card_id": last.card_id, "name": inv.name if inv else (card.name if card else to),
                    "firm": (inv.current_firm or inv.company) if inv else (card.firm if card else ""), "timezone": tz,
                    "thread": last.gmail_thread_id, "message_id": last.rfc_message_id,
                    "subject": re.sub(r"^\s*re:\s*", "", first.subject, flags=re.I)})
    return out


def _busy_days(db: Session, ws_id, to: str, tz: ZoneInfo, now: datetime) -> set[date]:
    rows = db.execute(select(Email.scheduled_for, Email.sent_at, Email.status).where(
        Email.workspace_id == ws_id, Email.to_email.ilike(to),
        Email.status.in_(["scheduled", "sending", "sent"]))).all()
    days = set()
    for sched, sent_at, status in rows:
        t = sent_at if status == "sent" else sched
        if t and t > now - timedelta(days=2):
            days.add(t.astimezone(tz).date())
    return days


def slot(db: Session, ws_id, to: str, tz_name: str, now: datetime) -> tuple[datetime, bool]:
    """08:35 their time on the next weekday morning; moved 3 days on (and again) while another email to them is
    scheduled or sent within a day of it. Returns (UTC time, moved)."""
    tz = _tz(tz_name)
    local = now.astimezone(tz)
    d = local.date() if local.time() < SEND_AT else local.date() + timedelta(days=1)
    busy = _busy_days(db, ws_id, to, tz, now)
    moved = False
    for _ in range(12):
        while d.weekday() >= 5:  # Saturday / Sunday -> Monday
            d += timedelta(days=1)
        if not busy & {d - timedelta(days=1), d, d + timedelta(days=1)}:
            break
        d += timedelta(days=GAP_DAYS)
        moved = True
    return datetime.combine(d, SEND_AT, tz).astimezone(UTC), moved


def plan(db: Session, ws_id, now: datetime) -> list[dict]:
    out = []
    for r in recipients(db, ws_id):
        at, moved = slot(db, ws_id, r["to"], r["timezone"], now)
        out.append({**r, "scheduled_for": at, "moved": moved})
    return out


def schedule(db: Session, ws: Workspace, user: User, text: str, now: datetime, send_now: bool = False) -> tuple[Broadcast, int]:
    """send_now: everyone straight away (the sender still spaces them out and keeps the daily cap) instead of
    08:35 their time."""
    rows = plan(db, ws.id, now)
    if send_now:
        rows = [{**r, "scheduled_for": now, "moved": False} for r in rows]
    b = Broadcast(workspace_id=ws.id, user_id=user.id, kind="round_update", template=TEMPLATE,
                  title="Round & progress update", inputs={"text": tidy(text)}, audience={"previously_emailed": True},
                  status="scheduled")
    db.add(b)
    db.flush()
    for r in rows:
        body = body_for(text, user.signature or "", r["name"])
        db.add(Email(workspace_id=ws.id, broadcast_id=b.id, card_id=r["card_id"], user_id=user.id, to_email=r["to"],
                     step=1, hook="update", subject=f"Re: {r['subject']}", body=body, status="scheduled",
                     scheduled_for=r["scheduled_for"], gmail_thread_id=r["thread"] or "",
                     rfc_message_id=r["message_id"] or "",
                     facts=[{"text": "Your round & progress update", "source": "written by you"}]))
    return b, len(rows)
