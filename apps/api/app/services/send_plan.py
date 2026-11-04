"""The daily allowance: how many NEW investors one sender may email per day (their plan's emails_day, capped at 20
and reduced during Gmail warm-up). Only a first email counts; follow-ups to an investor already emailed never do.

When outreach is scheduled, each investor's email 1 is placed on the first day that still has room, counting what
already went out today and what is already scheduled. Anything over the allowance goes to the next day's send
window, and the founder is told before they confirm. The mailer checks the same allowance again at send time."""

from collections import Counter
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Email, GmailAccount, User, Workspace
from .entitlements import usage
from .mailer import daily_cap, sent_metric, user_day
from .outreach import next_send_slot


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except Exception:
        return ZoneInfo("UTC")


class DayPlanner:
    def __init__(self, db: Session, ws: Workspace, user: User, acc: GmailAccount | None, now: datetime):
        self.user, self.now = user, now
        self.cap = daily_cap(db, ws, acc, now) if acc is not None else 0
        self.today = user_day(user, now)
        self.used_today = usage(db, ws, sent_metric(user.id), self.today)
        self.booked: Counter = Counter({self.today: self.used_today})
        for when in db.scalars(select(Email.scheduled_for).where(
                Email.user_id == user.id, Email.step == 1, Email.status.in_(("scheduled", "sending")),
                Email.sequence_id.is_not(None), Email.scheduled_for.is_not(None))):
            self.booked[user_day(user, max(when, now))] += 1
        self.placed: Counter = Counter()
        self.moved = 0  # first emails pushed to a later day because the allowance was full
        self.left_today = max(self.cap - self.booked[self.today], 0)

    def place(self, tz_name: str, first_at: datetime | None = None) -> datetime:
        """When this investor's email 1 can go: first_at (send now) or their next morning window, moved on a day at
        a time while that day's allowance is full."""
        when = first_at or next_send_slot(self.now, tz_name)
        if self.cap <= 0:
            return when
        tz = _tz(tz_name)
        for k in range(60):
            day = user_day(self.user, when)
            if self.booked[day] < self.cap:
                self.booked[day] += 1
                self.placed[day] += 1
                self.moved += k > 0
                return when
            nxt = datetime.combine(when.astimezone(tz).date() + timedelta(days=1), time(0, 0), tz)
            when = next_send_slot(nxt, tz_name)
        return when

    def summary(self) -> dict:
        """For the confirm screen and the toast: today's allowance and on which days the new first emails land."""
        return {"cap": self.cap, "sent_today": self.used_today, "left_today": self.left_today,
                "days": [{"day": d, "count": n} for d, n in sorted(self.placed.items())], "moved": self.moved}
