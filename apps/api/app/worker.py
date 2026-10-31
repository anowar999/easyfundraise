"""Background worker: fires due reminders every minute (TZ-04). Run: python -m app.worker"""

import logging
import time

from .db import SessionLocal
from .routers.notifications import fire_due_reminders

log = logging.getLogger("easyfundraise.worker")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            with SessionLocal() as db:
                n = fire_due_reminders(db)
                if n:
                    log.info("fired %s reminders", n)
        except Exception:
            log.exception("worker tick failed")
        time.sleep(60)


if __name__ == "__main__":
    main()
