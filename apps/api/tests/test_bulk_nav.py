import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Email, Sequence

from .test_outreach import _ready_to_send


def _two_drafts(client):
    ada = _ready_to_send(client)
    cara = client.get("/investors", params={"q": "Cara"}).json()["items"][0]
    a = client.post("/sequences", json={"investor_id": ada["id"]}).json()
    b = client.post("/sequences", json={"investor_id": cara["id"]}).json()
    return a, b


def _item(client, sid):
    return next(x for x in client.get("/sequences").json()["items"] if x["id"] == sid)


def test_list_has_country_seen_replied_ready(client):
    a, b = _two_drafts(client)
    it = _item(client, a["id"])
    assert {"country", "seen", "replied", "ready", "blocker"} <= it.keys()
    assert isinstance(it["country"], str)
    assert it["ready"] is True and it["blocker"] is None and it["drafting"] is False and it["card_id"] is None
    assert it["seen"] is False and it["replied"] is False
    with SessionLocal() as db:
        e1, e2 = sorted(db.scalars(select(Email).where(Email.sequence_id == uuid.UUID(a["id"]))), key=lambda e: e.step)[:2]
        e1.status, e1.open_count, e1.sent_at = "sent", 2, datetime.now(UTC)
        e2.replied_at, e2.reply_kind = datetime.now(UTC), "auto"  # an auto-reply is not a reply
        db.get(Sequence, uuid.UUID(a["id"])).status = "approved"
        db.commit()
    it = _item(client, a["id"])
    assert it["seen"] is True and it["replied"] is False and it["ready"] is False
    with SessionLocal() as db:
        e2 = db.scalar(select(Email).where(Email.sequence_id == uuid.UUID(a["id"]), Email.step == 2))
        e2.reply_kind = "positive"
        db.commit()
    assert _item(client, a["id"])["replied"] is True


def test_bulk_send_needs_confirm_then_schedules(client):
    a, b = _two_drafts(client)
    r = client.post("/sequences/bulk", json={"action": "send", "ids": [a["id"]]}).json()
    assert r == {"needs_confirm": True, "eligible": 1, "skipped": []}
    assert client.get(f"/sequences/{a['id']}").json()["status"] == "draft"  # nothing changed
    r = client.post("/sequences/bulk", json={"action": "send", "ids": [a["id"]], "confirm": True}).json()
    assert {k: r[k] for k in ("done", "skipped")} == {"done": 1, "skipped": []} and r["allowance"]["cap"]
    s = client.get(f"/sequences/{a['id']}").json()
    assert s["status"] == "approved" and all(e["status"] == "scheduled" for e in s["emails"])
    assert client.get(f"/sequences/{b['id']}").json()["status"] == "draft"  # not ticked
    # sending again skips it with a reason
    r = client.post("/sequences/bulk", json={"action": "send", "ids": [a["id"], b["id"]], "confirm": True}).json()
    assert r["done"] == 1 and [x["id"] for x in r["skipped"]] == [a["id"]] and r["skipped"][0]["reason"]


def test_bulk_regenerate_queues_drafts(client):
    a, b = _two_drafts(client)
    client.post("/sequences/bulk", json={"action": "send", "ids": [b["id"]], "confirm": True})
    r = client.post("/sequences/bulk", json={"action": "regenerate", "ids": [a["id"], b["id"]]}).json()
    assert r["needs_confirm"] and r["eligible"] == 1 and r["skipped"][0]["id"] == b["id"]
    r = client.post("/sequences/bulk", json={"action": "regenerate", "ids": [a["id"], b["id"]], "confirm": True}).json()
    assert r["queued"] == 1 and [x["id"] for x in r["skipped"]] == [b["id"]]
    s = client.get(f"/sequences/{a['id']}").json()  # the background task ran (TestClient runs it after the reply)
    assert s["status"] == "draft" and not s["drafting"] and s["engine"] == "template"
    assert [e["step"] for e in s["emails"]] == [1, 2, 3]


def test_bulk_remove(client):
    a, b = _two_drafts(client)
    other = str(uuid.uuid4())
    r = client.post("/sequences/bulk", json={"action": "remove", "ids": [a["id"], b["id"], other]}).json()
    assert r["needs_confirm"] and r["eligible"] == 2 and r["skipped"][0]["id"] == other
    with SessionLocal() as db:  # b has history: it is stopped, not deleted
        e = db.scalar(select(Email).where(Email.sequence_id == uuid.UUID(b["id"]), Email.step == 1))
        e.status, e.sent_at = "sent", datetime.now(UTC)
        db.commit()
    r = client.post("/sequences/bulk", json={"action": "remove", "ids": [a["id"], b["id"]], "confirm": True}).json()
    assert r == {"done": 2, "kept_history": 1}
    assert client.get(f"/sequences/{a['id']}").status_code == 404
    s = client.get(f"/sequences/{b['id']}").json()
    assert s["status"] == "stopped" and all(e["status"] in ("sent", "cancelled") for e in s["emails"])


def test_bulk_ignores_other_workspaces(client):
    from .conftest import login

    a, _ = _two_drafts(client)
    other = login("bulk-outsider@founder.io")
    r = other.post("/sequences/bulk", json={"action": "remove", "ids": [a["id"]], "confirm": True}).json()
    assert r == {"done": 0, "kept_history": 0}
    assert client.get(f"/sequences/{a['id']}").status_code == 200


def test_nav_counts(client):
    n = client.get("/nav/counts").json()
    assert isinstance(n.pop("company"), str)
    assert n == {"outreach": 0, "tracker": 0, "shortlist": 0, "tasks": 0}
    a, b = _two_drafts(client)
    client.post("/sequences", json={"investor_id": a["investor_id"]})  # same investor twice counts once
    ada = a["investor_id"]
    client.put(f"/shortlist/{ada}")
    card = client.post("/funnel", json={"name": "Nina Nav"}).json()
    client.post("/funnel", json={"name": "Gone Card"})
    client.delete(f"/funnel/{card['id']}")
    client.post("/funnel", json={"name": "Quiet Card", "status": "Inactive"})  # not counted
    client.post("/funnel", json={"name": "Passed Card", "status": "Rejection"})  # not counted
    client.post("/funnel", json={"name": "Ghost Card", "status": "Ghosting"})  # still counted
    t1 = client.post("/tasks", json={"title": "One"}).json()
    client.post("/tasks", json={"title": "Two", "status": "doing"})
    client.post("/tasks", json={"title": "Three"})
    client.patch(f"/tasks/{t1['id']}", json={"status": "done"})
    n = client.get("/nav/counts").json()
    n.pop("company")
    assert n == {"outreach": 2, "tracker": 2, "shortlist": 1, "tasks": 2}
