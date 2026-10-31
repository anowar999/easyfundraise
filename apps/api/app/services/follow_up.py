"""After an investor replies with a timeline ("we'll update you next week"), set the card's next contact date and
a follow-up reminder so the founder chases at the right time without having to remember."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FunnelCard, Reminder, User
from .notes import follow_up_date


def from_reply(db: Session, card: FunnelCard, user_id, text: str, now: datetime) -> date | None:
    user = db.get(User, user_id) if user_id else None
    try:
        tz = ZoneInfo((user.timezone if user else "") or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    d = follow_up_date(text, now.astimezone(tz).date())
    if d is None or user is None:
        return None
    card.next_contact_date = d
    for r in db.scalars(select(Reminder).where(Reminder.card_id == card.id, Reminder.done_at.is_(None),
                                               Reminder.notified_at.is_(None))):
        db.delete(r)
    quote = " ".join(text.split())[:90]
    db.add(Reminder(workspace_id=card.workspace_id, user_id=user.id, card_id=card.id,
                    title=f"Follow up with {card.name}: they said “{quote}”",
                    due_at=datetime.combine(d, time(9, 0), tz)))
    return d


def label(d: date) -> str:
    return f"{d:%a %d %b}" + ("" if d - date.today() < timedelta(days=300) else f" {d:%Y}")
