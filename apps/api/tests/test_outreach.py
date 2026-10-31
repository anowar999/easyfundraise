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
    assert r.status_code == 409 and r.json()["needs_reveal"]  # sending needs the contact (ASP-01 credit)
    client.post(f"/investors/{seq['investor_id']}/reveal")
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
    assert any("opt-out" in i for i in issues) and any("one link" in i for i in issues)


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
