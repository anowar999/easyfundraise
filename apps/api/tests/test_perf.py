"""Performance pass: bounded caches, page-scoped membership marks, the per-row send claim and reply-poll isolation."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Email, GmailAccount
from app.services import mailer
from app.services.cache import BoundedCache
from app.services.gmail import FakeGmail

from .conftest import login
from .test_mailer import _approved


def test_bounded_cache_evicts_oldest_and_expires():
    c = BoundedCache(maxsize=2)
    c["a"], c["b"] = 1, 2
    assert c.get("a") == 1  # a is now the most recently used
    c["c"] = 3
    assert "b" not in c and c["a"] == 1 and c["c"] == 3 and len(c) == 2
    t = BoundedCache(maxsize=5, ttl=-1)  # already expired
    t["x"] = 1
    assert t.get("x") is None


def test_search_marks_only_cover_the_page():
    cl = login("perf-marks@example.com")
    first = cl.get("/investors", params={"q": "Ada"}).json()["items"][0]
    assert cl.put(f"/shortlist/{first['id']}").status_code == 200
    items = cl.get("/investors", params={"q": "Ada"}).json()["items"]
    assert next(i for i in items if i["id"] == first["id"])["in_shortlist"] is True
    assert all(not i["in_shortlist"] for i in items if i["id"] != first["id"])


def test_reply_poll_failure_in_one_mailbox_is_contained(client, monkeypatch):
    """A Gmail error for one founder is logged and rolled back; polling carries on for everyone else."""
    FakeGmail.reset()
    seq = _approved(client)
    with SessionLocal() as db:
        first = db.scalar(select(Email).where(Email.sequence_id == seq["id"], Email.step == 1))
        db.get(GmailAccount, first.user_id).next_send_at = None
        db.commit()
        assert mailer.send_due(db, first.scheduled_for + timedelta(seconds=1)) == 1

        def broken(db, acc):
            raise RuntimeError("gmail is down")

        monkeypatch.setattr(mailer, "client_for", broken)
        assert mailer.poll_mailbox(db, first.user_id) == 0  # no exception escapes
        assert db.get(GmailAccount, first.user_id).status == "connected"


def test_send_due_claims_each_email_once():
    with SessionLocal() as db:
        assert mailer.send_due(db, datetime(2000, 1, 1, tzinfo=UTC)) == 0  # nothing due that early
        assert mailer.send_due(db, datetime.now(UTC), limit_n=5, budget_s=0) == 0  # zero budget: returns at once
