from datetime import date, timedelta

from .conftest import set_tier


def test_card_crud_move_and_events(client):
    a = client.post("/funnel", json={"name": "Jane VC", "firm": "Fund", "priority": "P1"}).json()
    b = client.post("/funnel", json={"name": "Jim VC"}).json()
    assert a["stage"] == 1 and a["stage_label"] == "01 Not started"
    moved = client.post(f"/funnel/{b['id']}/move", json={"stage": 3}).json()
    assert moved["stage"] == 3
    client.post(f"/funnel/{a['id']}/move", json={"stage": 3, "before_id": b["id"]})
    col = [x["name"] for x in client.get("/funnel", params={"stage": 3}).json()["items"]]
    assert col == ["Jane VC", "Jim VC"]
    detail = client.get(f"/funnel/{a['id']}").json()
    assert any(e["kind"] == "stage" for e in detail["events"])
    assert client.patch(f"/funnel/{a['id']}", json={"status": "Nope"}).status_code == 422
    client.delete(f"/funnel/{b['id']}")
    assert len(client.get("/funnel").json()["items"]) == 1


def test_add_database_investor_once(client):
    set_tier(client, "pro")
    ada = next(x for x in client.get("/investors", params={"q": "Ada"}).json()["items"])
    c1 = client.post("/funnel", json={"investor_id": ada["id"]}).json()
    c2 = client.post("/funnel", json={"investor_id": ada["id"]}).json()
    assert c1["id"] == c2["id"] and c1["firm"] == "Ada Fund" and c1["source"] == "Database"


def test_note_creates_reminder_and_suggestions(client):
    card = client.post("/funnel", json={"name": "Note Person"}).json()
    r = client.post(f"/funnel/{card['id']}/notes", json={"body": "Asked for the deck, follow up tomorrow. Intro via Sam Lee"}).json()
    assert r["reminder_date"]
    fields = {s["field"] for s in r["suggestions"]}
    assert {"stage", "referrer"} <= fields
    detail = client.get(f"/funnel/{card['id']}").json()
    assert detail["next_contact_date"] and detail["reminders"]


def test_due_reminder_becomes_notification(client):
    card = client.post("/funnel", json={"name": "Overdue Olga"}).json()
    client.patch(f"/funnel/{card['id']}", json={"next_contact_date": (date.today() - timedelta(days=1)).isoformat()})
    n = client.get("/notifications").json()
    assert n["unread"] >= 1 and any("Overdue Olga" in x["title"] for x in n["items"])
    home = client.get("/home").json()
    assert any(x["name"] == "Overdue Olga" for x in home["due"])
    client.post("/notifications/read")
    assert client.get("/notifications").json()["unread"] == 0


def test_export_is_own_data_and_watermarked(client):
    client.post("/funnel", json={"name": "Export Me", "email": "e@x.com"})
    r = client.get("/funnel/export/csv")
    assert r.status_code == 200 and "Export Me" in r.text and "exported by EasyFundraise workspace" in r.text


def test_star_and_stale(client):
    card = client.post("/funnel", json={"name": "Grace Hopper", "firm": "Navy Ventures"}).json()
    assert card["starred"] is False and card["stale"] is False and card["days_since_update"] == 0
    r = client.patch(f"/funnel/{card['id']}", json={"starred": True, "star_reason": "Can lead"}).json()
    assert r["starred"] and r["star_reason"] == "Can lead"
    assert any(e["body"] == "Starred: Can lead" for e in client.get(f"/funnel/{card['id']}").json()["events"])


def test_card_summary_follows_up_on_notes(client):
    card = client.post("/funnel", json={"name": "Grace Hopper", "firm": "Navy Ventures"}).json()
    s = client.get(f"/funnel/{card['id']}/summary").json()
    assert "not contacted yet" in s["headline"] and s["engine"] == "rules"
    client.post(f"/funnel/{card['id']}/notes", json={"body": "Waiting for our deck"})
    s = client.get(f"/funnel/{card['id']}/summary").json()
    assert "Waiting for our deck" in s["headline"] and "Did you send it" in s["next_step"]


def test_card_summary_waits_after_a_sent_note_or_scheduled_email(client):
    from datetime import UTC, datetime, timedelta

    from app.db import SessionLocal
    from app.models import Email, FunnelCard

    card = client.post("/funnel", json={"name": "Ada Byron", "firm": "Engine Capital"}).json()
    client.post(f"/funnel/{card['id']}/notes", json={"body": "Deck sent on 31/01"})
    s = client.get(f"/funnel/{card['id']}/summary").json()
    assert "not contacted" not in s["headline"] and "Waiting on their reply" in s["next_step"]
    with SessionLocal() as db:
        c = db.get(FunnelCard, card["id"])
        db.add(Email(workspace_id=c.workspace_id, card_id=c.id, to_email="ada@engine.vc", step=1, hook="reply",
                     subject="Re: deck", body="Hi", status="scheduled",
                     scheduled_for=datetime.now(UTC) + timedelta(minutes=5)))
        db.commit()
    s = client.get(f"/funnel/{card['id']}/summary").json()
    assert "scheduled" in s["headline"] and "Wait for their reply" in s["next_step"]
