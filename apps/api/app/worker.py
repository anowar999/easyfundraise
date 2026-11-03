"""Background worker (TZ-03/04, MAIL-03, AGT-02). Run: python -m app.worker

Every minute: fire due reminders, send due emails, prepare call briefs, daily briefs.
Every 5 minutes: poll Gmail threads for replies and bounces.
Jobs are idempotent and safe to run in more than one process (row locks with SKIP LOCKED).
"""

import logging
import time

from .db import SessionLocal
from .routers.notifications import fire_due_reminders
from .services.agent import prepare_call_briefs, send_daily_briefs
from .services.mailer import poll_replies, send_due

log = logging.getLogger("easyfundraise.worker")


def release_stuck_drafts(db) -> int:
    """A background AI draft that never finished (e.g. the API restarted) keeps its template emails."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from .models import Sequence
    n = db.execute(update(Sequence).where(Sequence.engine == "drafting",
                                          Sequence.created_at < datetime.now(UTC) - timedelta(minutes=5))
                   .values(engine="template")).rowcount
    db.commit()
    return n


def tick(n: int) -> None:
    jobs = [("stuck drafts", release_stuck_drafts), ("reminders", fire_due_reminders), ("send", send_due), ("call briefs", prepare_call_briefs),
            ("daily briefs", send_daily_briefs)]
    if n % 5 == 0:
        jobs.append(("replies", poll_replies))
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
        tick(n)
        n += 1
        time.sleep(60)


if __name__ == "__main__":
    main()
