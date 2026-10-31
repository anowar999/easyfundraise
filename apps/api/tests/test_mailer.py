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
    r = client.post(f"/sequences/{seq['id']}/approve", json={"confirm": True})
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


def test_card_mail_reads_latest_thread_and_replies_in_it(client):
    FakeGmail.reset()
    seq = _approved(client)
    [first, *_] = _send_all(seq["id"])
    with SessionLocal() as db:
        me = db.get(GmailAccount, first.user_id).email
    FakeGmail.inbound(first.gmail_thread_id, "Ada <ada@seedfund.vc>", "Thanks Sam, what's your current MRR?\n\n"
                      "On Tue, Sam wrote:\n> earlier text", {"message-id": "<ada-1@seedfund.vc>", "subject": "Re: hi",
                                                            "to": me, "cc": "Bo <bo@seedfund.vc>"})
    cid = seq["card_id"]
    m = client.get(f"/funnel/{cid}/mail").json()
    assert m["connected"] and m["to"] == "ada@seedfund.vc"
    assert m["thread_id"] == first.gmail_thread_id and m["reply_to"] == "<ada-1@seedfund.vc>"
    assert m["thread"][-1]["text"] == "Thanks Sam, what's your current MRR?"  # quoted history stripped
    d = client.post(f"/funnel/{cid}/mail/draft", json={"ask": "share the new pilot"}).json()
    assert d["body"].startswith("Hi Ada,") and d["subject"] and "\n\nBest,\n" in d["body"]
    assert m["reply_all"] == {"to": ["ada@seedfund.vc"], "cc": ["bo@seedfund.vc"]} and m["subject"] == "Re: hi"
    r = client.post(f"/funnel/{cid}/mail/send", json={"body": d["body"], "add_signature": True,
                                                       "thread_id": m["thread_id"], "reply_to": m["reply_to"]}).json()
    assert r["status"] == "sent", r
    sent = FakeGmail.sent[-1]
    assert sent["In-Reply-To"] == "<ada-1@seedfund.vc>" and sent.get_body(preferencelist=("plain",)).get_content().rstrip().endswith("Sam")
    assert sent["Subject"] == "Re: hi" and sent["To"] == "ada@seedfund.vc" and sent["Cc"] == "bo@seedfund.vc"
    assert FakeGmail.threads[first.gmail_thread_id][-1].headers["to"] == "ada@seedfund.vc"
    events = client.get(f"/funnel/{cid}").json()["events"]
    assert any(e["kind"] == "email" and e["body"].startswith("Email sent:") for e in events)
    # Check email: Ada's reply and a mail the founder sent from Gmail directly land on the timeline, once
    FakeGmail.inbound("t_direct", me, "Sharing the deck as promised.", {"to": "ada@seedfund.vc", "subject": "Deck"})
    assert client.post(f"/funnel/{cid}/mail/sync").json()["new"] == 2
    assert client.post(f"/funnel/{cid}/mail/sync").json()["new"] == 0
    events = client.get(f"/funnel/{cid}").json()["events"]
    assert any(e["kind"] == "reply" and "MRR" in e["body"] for e in events)
    assert any(e["kind"] == "email" and e["body"].startswith("Email sent: Deck") for e in events)
    # their newest reply gives a timeline: the card gets a follow-up date and reminder, quoted history dropped
    FakeGmail.inbound("t_direct", "Ada <ada@seedfund.vc>", "Thanks for the nudge. The team will update you next week. "
                      "Best On Sat, 31 Oct 2026 at 01:15, Sam wrote", {"to": me, "subject": "Re: Deck"})
    assert client.post(f"/funnel/{cid}/mail/sync").json()["new"] == 1
    card = client.get(f"/funnel/{cid}").json()
    assert card["next_contact_date"] and card["events"]
    latest = next(e for e in card["events"] if e["kind"] == "reply" and "nudge" in e["body"])
    assert latest["body"].endswith("next week.") and latest["meta"]["follow_up"] == card["next_contact_date"]
    later = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    r = client.post(f"/funnel/{cid}/mail/send", json={"subject": "Later", "body": "Hi Ada,\n\nLater.", "send_at": later,
                                                       "add_signature": False}).json()
    assert r["status"] == "scheduled" and r["sent_at"] is None


def test_send_safety_burst_pause_and_editor_check(client):
    from app.models import ConfigKV, Notification, WorkspaceMember

    FakeGmail.reset()
    seq = _approved(client)
    cid = seq["card_id"]
    with SessionLocal() as db:
        row = db.get(ConfigKV, "sending")
        old = dict(row.value) if row else None
        db.merge(ConfigKV(key="sending", value={**(old or {}), "burst_max": 2, "burst_window_minutes": 10,
                                                "max_recipients": 10}, version=1))
        db.commit()
    try:
        send = lambda: client.post(f"/funnel/{cid}/mail/send", json={"subject": "Hi", "body": "Hi Ada"})  # noqa: E731
        assert send().json()["status"] == "sent"
        assert send().json()["status"] == "sent"
        r = send()  # a third within 10 minutes trips the burst guard
        assert r.status_code == 429 and r.json()["paused"]
        g = client.get("/gmail").json()
        assert g["paused_until"] and "Paused" in g["paused_reason"]
        assert send().status_code == 423  # stays paused
        with SessionLocal() as db:
            assert db.scalar(select(Notification).where(Notification.kind == "send_paused")) is not None
        assert client.post("/gmail/resume").json()["paused_until"] is None

        # paused by the user: a scheduled email waits instead of going out
        assert client.post("/gmail/pause").json()["paused_until"]
        with SessionLocal() as db:
            em = db.scalar(select(Email).where(Email.sequence_id == seq["id"], Email.step == 1))
            mailer.send_due(db, em.scheduled_for + timedelta(seconds=1))
            db.refresh(em)
            assert em.status == "scheduled" and "Paused by you" in em.error
        client.post("/gmail/resume")

        # a teammate demoted to viewer can't have their scheduled emails sent
        with SessionLocal() as db:
            em = db.scalar(select(Email).where(Email.sequence_id == seq["id"], Email.step == 1))
            m = db.get(WorkspaceMember, (em.workspace_id, em.user_id))
            m.role = "viewer"
            db.get(GmailAccount, em.user_id).next_send_at = None
            db.commit()
            mailer.send_due(db, em.scheduled_for + timedelta(seconds=1))
            db.refresh(em)
            assert em.status == "cancelled" and "no longer an editor" in em.error
            m.role = "owner"
            db.commit()
    finally:
        with SessionLocal() as db:
            if old is None:
                db.delete(db.get(ConfigKV, "sending"))
            else:
                db.get(ConfigKV, "sending").value = old
            db.commit()


def test_follow_up_date_and_quote_stripping():
    from datetime import date

    from app.services.gmail import strip_quoted
    from app.services.notes import follow_up_date

    sat = date(2026, 10, 31)
    assert follow_up_date("The team is looking into it and will update you next week.", sat) == date(2026, 11, 5)
    assert follow_up_date("Let me get back to you", sat) == date(2026, 11, 7)
    assert follow_up_date("We'll pass on this one, not a fit", sat) is None
    assert follow_up_date("Great, thanks!", sat) is None
    assert strip_quoted("Will update you next week. Best On Sat, 31 Oct 2026 at 01:15, Anow") == \
        "Will update you next week."
