from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.services import outreach
from app.services.notes import find_date, parse_note

from .conftest import set_tier


def test_sequence_draft_limits_and_lint(client):
    set_tier(client, "pro")
    client.put("/workspace/profile", json={"company_name": "DocAI", "one_liner": "AI triage for clinics",
                                           "sectors": ["Digital Health & HealthTech"], "stage": "seed",
                                           "traction": "40 clinics live, 12% MoM growth"})
    ada = next(x for x in client.get("/investors", params={"q": "Ada"}).json()["items"])
    seq = client.post("/sequences", json={"investor_id": ada["id"]}).json()
    emails = seq["emails"]
    assert [e["step"] for e in emails] == [1, 2, 3]
    assert len({e["hook"] for e in emails}) == 3  # different hook family each email
    for e in emails:
        assert outreach.words(e["body"]) <= outreach.LIMITS[e["step"]]
        assert e["issues"] == []
    assert "Medibot" in emails[0]["body"]  # grounded in a stored, sourced deal
    assert emails[0]["facts"][0]["source"].startswith("https://")
    # Approve requires a signature (AUTH-05)
    r = client.post(f"/sequences/{seq['id']}/approve", json={"confirm": True})
    assert r.status_code == 409 and r.json()["needs_signature"]
    client.patch("/workspace/me", json={"signature": "Sam\nDocAI"})
    r = client.post(f"/sequences/{seq['id']}/approve", json={"confirm": True})
    # adding to outreach revealed the contact by itself (one credit), so no "reveal first" step
    assert client.get("/workspace").json()["usage"]["reveals_month"] == 1
    r = client.post(f"/sequences/{seq['id']}/approve", json={"confirm": True})
    assert r.status_code == 409 and r.json()["needs_gmail"]
    client.get("/gmail/connect", follow_redirects=False)  # fake mailbox in tests
    # Nothing is scheduled until the founder confirms the sender, recipient and send times
    r = client.post(f"/sequences/{seq['id']}/approve")
    assert r.status_code == 409 and r.json()["needs_confirm"]
    preview = r.json()["preview"]
    assert preview["to"] == "ada@seedfund.vc" and preview["from"] and len(preview["emails"]) == 3
    assert client.get(f"/sequences/{seq['id']}").json()["status"] == "draft"
    assert all(e["status"] == "draft" for e in client.get(f"/sequences/{seq['id']}").json()["emails"])
    r = client.post(f"/sequences/{seq['id']}/approve", json={"confirm": True}).json()
    assert r["status"] == "approved"
    london = [datetime.fromisoformat(e["scheduled_for"]).astimezone(ZoneInfo("Europe/London")) for e in r["emails"]]
    assert all(d.weekday() in (1, 2, 3) for d in london)
    assert london[0] < london[1] < london[2]


def test_trial_can_draft_three_samples(client):
    ada = next(x for x in client.get("/investors").json()["items"] if x["name"] == "Ada Seed")
    for _ in range(3):
        assert client.post("/sequences", json={"investor_id": ada["id"]}).status_code == 200
    assert client.post("/sequences", json={"investor_id": ada["id"]}).status_code == 402


def test_lint_catches_spam():
    issues = outreach.lint("URGENT OFFER", "Click here! bit.ly/x http://a http://b", 1)
    assert any("Spam" in i for i in issues) and any("shortener" in i for i in issues)
    assert any("one link" in i for i in issues)


def test_send_slot_is_in_investor_window():
    fri_evening = datetime(2026, 10, 30, 20, 0, tzinfo=UTC)
    slot = outreach.next_send_slot(fri_evening, "America/New_York").astimezone(ZoneInfo("America/New_York"))
    assert slot.weekday() == 1 and slot.hour == 8 and slot.minute == 30


def test_note_dates():
    from datetime import date

    today = date(2026, 10, 30)  # Friday
    assert find_date("follow up tomorrow", today) == date(2026, 10, 31)
    assert find_date("call on Thursday", today) == date(2026, 11, 5)
    assert find_date("not now, Q2", today) == date(2027, 4, 1)
    assert find_date("meeting 23/10", today) == date(2027, 10, 23)
    assert find_date("ping in 2 weeks", today) == date(2026, 11, 13)
    p = parse_note("They passed, not a fit", today)
    assert p["suggestions"][0]["value"] == "Rejection"


def test_nudge(client):
    card = client.post("/funnel", json={"name": "Nina Nudge"}).json()
    n = client.get(f"/sequences/nudge/{card['id']}").json()
    assert n["whatsapp"].startswith("Hi Nina") and len(n["whatsapp"].split()) <= 40


def _ready_to_send(client):
    set_tier(client, "pro")
    client.put("/workspace/profile", json={"company_name": "DocAI", "one_liner": "AI triage for clinics",
                                           "sectors": ["Digital Health & HealthTech"], "stage": "seed",
                                           "traction": "40 clinics live, 12% MoM growth"})
    client.patch("/workspace/me", json={"signature": "Sam\nDocAI"})
    client.get("/gmail/connect", follow_redirects=False)
    return client.get("/investors", params={"q": "Ada"}).json()["items"][0]


def test_send_all_reports_then_schedules_ready_drafts(client):
    ada = _ready_to_send(client)
    seq = client.post("/sequences", json={"investor_id": ada["id"]}).json()
    assert seq["auto"] is None  # auto-send is off unless the founder turns it on
    lst = client.get("/sequences").json()
    assert lst["auto_send"] is False and lst["items"][0]["blocker"] is None  # contact revealed automatically
    r = client.post("/sequences/send-all").json()
    assert [x["name"] for x in r["ready"]] == [ada["name"]] and r["from"]
    assert client.get(f"/sequences/{seq['id']}").json()["status"] == "draft"  # preview changes nothing
    assert client.post("/sequences/send-all", json={"confirm": True}).json() == {"scheduled": 1, "skipped": []}
    s = client.get(f"/sequences/{seq['id']}").json()
    assert s["status"] == "approved" and all(e["status"] == "scheduled" for e in s["emails"])


def test_auto_send_schedules_new_outreach(client):
    ada = _ready_to_send(client)
    client.post(f"/investors/{ada['id']}/reveal")
    client.patch("/workspace", json={"auto_send": True})
    assert client.get("/workspace").json()["auto_send"] is True
    seq = client.post("/sequences", json={"investor_id": ada["id"]}).json()
    assert seq["auto"] == {"scheduled": True, "reason": ""}
    assert client.get(f"/sequences/{seq['id']}").json()["status"] == "approved"


def test_write_email_then_send_it_through_outreach(client):
    ada = _ready_to_send(client)
    e = client.post(f"/investors/{ada['id']}/write-email", json={"angle": "our clinic traction"}).json()
    assert e["subject"] and e["subjects"][0] == e["subject"]
    assert e["body"].startswith("Hi Ada,") and e["body"].endswith("Sam\nDocAI")
    assert "reply 'no'" not in e["body"].lower()  # copy-to-Gmail version has no opt-out line
    assert e["to"] == ""  # not revealed yet
    seq = client.post("/sequences", json={"investor_id": ada["id"],
                                          "first_email": {"subject": "My own subject", "body": e["body"]}}).json()
    first = seq["emails"][0]
    assert first["subject"] == "My own subject" and first["issues"] == []
    assert first["body"].endswith("Sam\nDocAI") and "reply 'no'" not in first["body"].lower()


def _later(seq_id: str) -> None:
    """Move a just-approved sequence's send times a day on: inside a send window email 1 is due at once."""
    import uuid
    from datetime import timedelta

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Email
    with SessionLocal() as db:
        for e in db.scalars(select(Email).where(Email.sequence_id == uuid.UUID(seq_id))):
            if e.scheduled_for:
                e.scheduled_for += timedelta(days=1)
        db.commit()


def test_upcoming_scheduled_and_send_now(client):
    ada = _ready_to_send(client)
    seq = client.post("/sequences", json={"investor_id": ada["id"]}).json()
    assert client.post(f"/sequences/{seq['id']}/approve", json={"confirm": True}).status_code == 200
    _later(seq["id"])
    up = client.get("/sequences/scheduled").json()["items"]
    mine = [x for x in up if x["sequence_id"] == seq["id"]]
    assert [x["step"] for x in mine] == [1, 2, 3] and mine[0]["can_send_now"] and not mine[1]["can_send_now"]
    assert mine[1]["subject"] == f"Re: {mine[0]['subject']}"
    r = client.post(f"/sequences/{seq['id']}/emails/{mine[1]['email_id']}/send-now")
    assert r.status_code == 409  # follow-ups wait for email 1
    r = client.post(f"/sequences/{seq['id']}/emails/{mine[0]['email_id']}/send-now").json()
    assert r["ok"]
    again = client.post(f"/sequences/{seq['id']}/emails/{mine[0]['email_id']}/send-now")
    assert again.status_code == 409  # no double send
    assert client.get(f"/sequences/{seq['id']}").json()["emails"][0]["status"] == "sent"  # sent at once, not next tick
    from datetime import UTC, datetime

    from app.db import SessionLocal
    from app.services import mailer
    with SessionLocal() as db:
        mailer.send_due(db, datetime.now(UTC))
    e1 = client.get(f"/sequences/{seq['id']}").json()["emails"][0]
    assert e1["status"] == "sent"
    two = next(x for x in client.get("/sequences/scheduled").json()["items"] if x["email_id"] == mine[1]["email_id"])
    assert not two["can_send_now"] and two["send_now_from"]  # a day after email 1, never minutes apart
    assert client.post(f"/sequences/{seq['id']}/emails/{mine[1]['email_id']}/send-now").status_code == 409

    # Round & progress update to everyone already emailed: a reply in their thread, kept clear of other emails.
    text = "we closed our first 500k and signed two hospitals"
    pv = client.post("/outreach/progress-update/preview", json={"text": text}).json()
    assert pv["count"] == 1 and pv["recipients"][0]["moved"]  # email 1 went today, so not tomorrow
    assert pv["sample"]["subject"] == f"Re: {e1['subject']}" and "We closed our first 500k" in pv["sample"]["body"]
    assert pv["sample"]["body"].startswith("Hi Ada,")
    when = datetime.fromisoformat(pv["recipients"][0]["scheduled_for"].replace("Z", "+00:00"))
    local = when.astimezone(ZoneInfo(pv["recipients"][0]["timezone"]))
    assert (local.hour, local.minute) == (8, 35) and local.weekday() < 5
    assert (local.date() - datetime.now(UTC).astimezone(local.tzinfo).date()).days >= 2
    pol = client.post("/outreach/progress-update/polish", json={"text": text}).json()
    assert pol["text"].startswith("We closed")  # no AI in tests: tidied, facts kept
    assert client.post("/outreach/progress-update/schedule", json={"text": text}).json()["scheduled"] == 1
    ups = [x for x in client.get("/sequences/scheduled").json()["items"] if x["kind"] == "update"]
    assert len(ups) == 1 and ups[0]["subject"] == f"Re: {e1['subject']}"
    from sqlalchemy import select

    from app.models import Email, GmailAccount
    with SessionLocal() as db:
        import uuid
        upd = db.get(Email, uuid.UUID(ups[0]["email_id"]))
        upd.scheduled_for = datetime.now(UTC)
        for acc in db.scalars(select(GmailAccount)):
            acc.next_send_at = None
        db.commit()
        mailer.send_due(db, datetime.now(UTC))
        db.refresh(upd)
        sent1 = db.scalar(select(Email).where(Email.sequence_id == uuid.UUID(seq["id"]), Email.step == 1))
        assert upd.status == "sent" and upd.gmail_thread_id == sent1.gmail_thread_id  # same Gmail thread
    r = client.post(f"/sequences/scheduled/{mine[1]['email_id']}/send-now", json={"anyway": True})
    assert r.status_code == 200  # the founder confirmed "Send anyway" within the day


def test_scheduled_preview_send_now_and_cancel(client):
    ada = _ready_to_send(client)
    seq = client.post("/sequences", json={"investor_id": ada["id"]}).json()
    client.post(f"/sequences/{seq['id']}/approve", json={"confirm": True})
    _later(seq["id"])
    mine = [x for x in client.get("/sequences/scheduled").json()["items"] if x["sequence_id"] == seq["id"]]
    assert mine[0]["body"].startswith("Hi Ada") and "{first name}" not in mine[0]["body"]  # preview, name filled
    r = client.post(f"/sequences/scheduled/{mine[2]['email_id']}/cancel").json()  # one follow-up
    assert r == {"ok": True, "back_to_draft": False, "cancelled": [3]}
    assert client.post(f"/sequences/scheduled/{mine[2]['email_id']}/cancel").status_code == 409
    r = client.post(f"/sequences/scheduled/{mine[0]['email_id']}/cancel").json()  # email 1: back to drafts
    assert r["back_to_draft"]
    s = client.get(f"/sequences/{seq['id']}").json()
    assert s["status"] == "draft" and s["emails"][0]["status"] == "draft" and s["emails"][1]["status"] == "draft"
    assert not [x for x in client.get("/sequences/scheduled").json()["items"] if x["sequence_id"] == seq["id"]]
    client.post(f"/sequences/{seq['id']}/approve", json={"confirm": True})  # approve again to reschedule
    _later(seq["id"])
    first = next(x for x in client.get("/sequences/scheduled").json()["items"] if x["sequence_id"] == seq["id"])
    assert client.post(f"/sequences/scheduled/{first['email_id']}/send-now").json()["ok"]
    assert client.post(f"/sequences/scheduled/{first['email_id']}/cancel").status_code == 409  # on its way
