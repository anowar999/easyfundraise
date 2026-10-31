"""Send pipeline, threading, tracking and reply automations against the fake Gmail mailbox."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Email, Exclusion, FunnelCard, GmailAccount, Sequence
from app.services import mailer
from app.services.gmail import FakeGmail

from .conftest import set_tier


def _approved(client):
    set_tier(client, "pro")
    client.put("/workspace/profile", json={"company_name": "DocAI", "one_liner": "AI triage for clinics",
                                           "sectors": ["Digital Health & HealthTech"], "stage": "seed"})
    client.patch("/workspace/me", json={"signature": "Sam"})
    ada = client.get("/investors", params={"q": "Ada"}).json()["items"][0]
    client.post(f"/investors/{ada['id']}/reveal")
    client.get("/gmail/connect", follow_redirects=False)
    seq = client.post("/sequences", json={"investor_id": ada["id"]}).json()
    r = client.post(f"/sequences/{seq['id']}/approve")
    assert r.status_code == 200, r.text
    with SessionLocal() as db:  # warm-up ramp would cap a brand-new account at 5/day; age it
        acc = db.get(GmailAccount, db.scalar(select(Sequence.user_id).where(Sequence.id == r.json()["id"])))
        acc.connected_at = datetime.now(UTC) - timedelta(days=30)
        db.commit()
    return r.json()


def _send_all(seq_id: str) -> list[Email]:
    """Runs the sender forward in time until every email of the sequence went out."""
    with SessionLocal() as db:
        ems = db.scalars(select(Email).where(Email.sequence_id == seq_id).order_by(Email.step)).all()
        for em in ems:
            when = em.scheduled_for + timedelta(seconds=1)
            acc = db.get(GmailAccount, em.user_id)
            acc.next_send_at = None
            db.commit()
            mailer.send_due(db, when)
        return db.scalars(select(Email).where(Email.sequence_id == seq_id).order_by(Email.step)).all()


def test_sends_thread_and_track(client):
    FakeGmail.reset()
    seq = _approved(client)
    ems = _send_all(seq["id"])
    assert [e.status for e in ems] == ["sent", "sent", "sent"]
    assert len({e.gmail_thread_id for e in ems}) == 1  # MAIL-02: one thread
    mine = {m["Message-ID"]: m for m in FakeGmail.sent}
    m1, m2 = mine[ems[0].rfc_message_id], mine[ems[1].rfc_message_id]
    assert m2["In-Reply-To"] == m1["Message-ID"] and m2["Subject"].startswith("Re: ")
    assert "/t/o/" in m1.get_body(preferencelist=("html",)).get_content()  # TRK-01 pixel
    assert m1.get_body(preferencelist=("plain",)).get_content().startswith("Hi Ada")  # plain text first
    # open pixel: immediate fetch ignored, later fetch counted
    tok = ems[0].open_token
    with SessionLocal() as db:
        e = db.get(Email, ems[0].id)
        e.sent_at = datetime.now(UTC) - timedelta(minutes=5)
        db.commit()
    r = client.get(f"/t/o/{tok}.gif")
    assert r.status_code == 200 and r.headers["content-type"] == "image/gif"
    stats = client.get("/outreach/stats").json()
    assert stats["total"]["sent"] == 3 and stats["total"]["opened"] == 1


def test_positive_reply_stops_sequence_and_moves_card(client):
    FakeGmail.reset()
    seq = _approved(client)
    with SessionLocal() as db:
        first = db.scalar(select(Email).where(Email.sequence_id == seq["id"], Email.step == 1))
        db.get(GmailAccount, first.user_id).next_send_at = None
        db.commit()
        mailer.send_due(db, first.scheduled_for + timedelta(seconds=1))
        db.refresh(first)
        FakeGmail.inbound(first.gmail_thread_id, "Ada <ada@seedfund.vc>", "Interested, please send the deck over.")
        assert mailer.poll_replies(db) == 1
        assert mailer.poll_replies(db) == 0  # idempotent
        s = db.get(Sequence, first.sequence_id)
        assert s.status == "replied"
        assert {e.status for e in s.emails if e.step > 1} == {"cancelled"}
        card = db.get(FunnelCard, s.card_id)
        assert card.stage == 5  # deck requested → 05
    notes = client.get("/notifications").json()["items"]
    assert any("interested" in n["title"] for n in notes)


def test_opt_out_and_bounce_exclude(client):
    FakeGmail.reset()
    seq = _approved(client)
    with SessionLocal() as db:
        first = db.scalar(select(Email).where(Email.sequence_id == seq["id"], Email.step == 1))
        db.get(GmailAccount, first.user_id).next_send_at = None
        db.commit()
        mailer.send_due(db, first.scheduled_for + timedelta(seconds=1))
        db.refresh(first)
        FakeGmail.inbound(first.gmail_thread_id, "ada@seedfund.vc", "no")
        mailer.poll_replies(db)
        ex = db.scalars(select(Exclusion).where(Exclusion.workspace_id == first.workspace_id)).all()
        assert [(x.value, x.reason) for x in ex] == [("ada@seedfund.vc", "opt_out")]


def test_classifier_rules():
    def k(text, sender="x@y.com", headers=None):
        return mailer.classify(None, None, text, headers or {}, sender)["kind"]

    assert k("Mail delivery failed", "MAILER-DAEMON@googlemail.com") == "bounce"
    assert k("I'm out of the office until Monday") == "auto"
    assert k("Thanks, but this is not a fit for us") == "negative"
    assert k("Happy to chat next week") == "positive"
    assert k("Unsubscribe") == "opt_out"


def test_daily_cap_and_warmup(client):
    FakeGmail.reset()
    seq = _approved(client)
    with SessionLocal() as db:
        first = db.scalar(select(Email).where(Email.sequence_id == seq["id"], Email.step == 1))
        acc = db.get(GmailAccount, first.user_id)
        from app.models import Workspace

        ws = db.get(Workspace, first.workspace_id)
        now = datetime.now(UTC)
        acc.connected_at = now
        assert mailer.daily_cap(db, ws, acc, now) == 5  # warm-up starts at 5/day
        acc.connected_at = now - timedelta(days=5)
        assert 5 < mailer.daily_cap(db, ws, acc, now) < 20
        acc.connected_at = now - timedelta(days=11)
        assert mailer.daily_cap(db, ws, acc, now) == 20


def test_role_address_skipped(client):
    FakeGmail.reset()
    seq = _approved(client)
    with SessionLocal() as db:
        first = db.scalar(select(Email).where(Email.sequence_id == seq["id"], Email.step == 1))
        first.to_email = "info@seedfund.vc"
        db.get(GmailAccount, first.user_id).next_send_at = None
        db.commit()
        mailer.send_due(db, first.scheduled_for + timedelta(seconds=1))
        db.refresh(first)
        assert first.status == "cancelled" and "Role address" in first.error
