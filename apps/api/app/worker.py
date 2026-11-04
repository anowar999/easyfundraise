"""Background worker (TZ-03/04, MAIL-03, AGT-02). Run: python -m app.worker

Every minute: fire due reminders, send due emails, prepare call briefs, daily briefs.
Every 5 minutes: poll Gmail threads for replies and bounces (many mailboxes in parallel).
Every hour: purge old rate-limit windows and expired sessions.
Sending and reminders use row locks with SKIP LOCKED, so a second worker process can share that load.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, update

from .config import get_settings
from .db import SessionLocal
from .models import AuthSession, RateLimit, Sequence
from .routers.notifications import fire_due_reminders
from .services.agent import prepare_call_briefs, send_daily_briefs
from .services.mailer import mailboxes_to_poll, poll_mailbox, send_due

log = logging.getLogger("easyfundraise.worker")

TICK_S = 60
SEND_BUDGET_S = 45  # keep sending through a backlog for most of the minute, then let the other jobs run


def release_stuck_drafts(db) -> int:
    """A background AI draft that never finished (e.g. the API restarted) keeps its template emails."""
    n = db.execute(update(Sequence).where(Sequence.engine == "drafting",
                                          Sequence.created_at < datetime.now(UTC) - timedelta(minutes=5))
                   .values(engine="template")).rowcount
    db.commit()
    return n


def send(db) -> int:
    """Drains the due queue (not just a fixed 50 a minute), so morning send windows don't build a backlog."""
    return send_due(db, limit_n=5000, budget_s=SEND_BUDGET_S)


def _poll_one(user_id) -> int:
    with SessionLocal() as db:
        return poll_mailbox(db, user_id)


def poll_all_replies(db) -> int:
    """Each mailbox is a few Gmail API calls; checking them side by side keeps a full pass well inside 5 minutes
    as the number of connected founders grows."""
    ids = mailboxes_to_poll(db)
    db.close()
    if not ids:
        return 0
    with ThreadPoolExecutor(max_workers=max(1, get_settings().worker_poll_threads)) as pool:
        return sum(pool.map(_poll_one, ids))


def cleanup(db) -> int:
    """Rate-limit windows are only read for their own minute/hour; sessions past expiry can never be used again."""
    now = datetime.now(UTC)
    n = db.execute(delete(RateLimit).where(RateLimit.window_start < now - timedelta(days=2))).rowcount
    n += db.execute(delete(AuthSession).where(AuthSession.expires_at < now - timedelta(days=1))).rowcount
    db.commit()
    return n


def tick(n: int) -> None:
    jobs = [("stuck drafts", release_stuck_drafts), ("reminders", fire_due_reminders), ("send", send),
            ("call briefs", prepare_call_briefs), ("daily briefs", send_daily_briefs)]
    if n % 5 == 0:
        jobs.append(("replies", poll_all_replies))
    if n % 60 == 0:
        jobs.append(("cleanup", cleanup))
    for name, fn in jobs:
        try:
            with SessionLocal() as db:
                done = fn(db)
                if done:
                    log.info("%s: %s", name, done)
        except Exception:
            log.exception("%s failed", name)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    n = 0
    while True:
        started = time.monotonic()
        tick(n)
        n += 1
        # Fixed cadence: a slow tick doesn't push every later run back by its own length
        time.sleep(max(1.0, TICK_S - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
