"""The Raise Agent on the investor tracker without an AI key: numbered cards, filtered views, follow-ups, notes."""

from datetime import date, timedelta

from .conftest import login


def make(who):
    c = login(f"tracker-{who}@example.com")
    a = c.post("/funnel", json={"name": "Paul Bartley", "firm": "Bartley Capital"}).json()
    b = c.post("/funnel", json={"name": "Nina Late", "firm": "Late Fund",
                                "next_contact_date": str(date.today() - timedelta(days=3))}).json()
    g = c.post("/funnel", json={"name": "Gary Ghost", "firm": "Quiet VC", "status": "Ghosting"}).json()
    return c, a, b, g


def ask(c, text):
    r = c.post("/agent/chat", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_cards_are_numbered_per_workspace_and_searchable():
    c, a, b, g = make("t1")
    assert (a["number"], b["number"], g["number"]) == (1, 2, 3)
    assert [x["name"] for x in c.get("/funnel", params={"q": "#2"}).json()["items"]] == ["Nina Late"]
    other = login("tracker-other@example.com")
    assert other.post("/funnel", json={"name": "Someone"}).json()["number"] == 1


def test_show_only_active_and_overdue():
    c, a, b, g = make("t2")
    m = ask(c, "show me only list of active investors")
    act = m["actions"][0]
    assert act["type"] == "tracker_filter" and act["args"]["statuses"] == ["Active"]
    assert "#1 Paul Bartley" in m["text"] and "Gary Ghost" not in m["text"]
    assert act["href"].startswith("/app/funnel?agent=")

    m = ask(c, "Or show me which ones are overdue")
    assert m["actions"][0]["args"] == {"overdue": True}
    assert "#2 Nina Late" in m["text"] and "Paul" not in m["text"]


def test_follow_up_by_number_and_note_by_name():
    c, a, *_ = make("t3")
    m = ask(c, "update tracker 1 set a follow up date 02/Nov")
    card = c.get(f"/funnel/{a['id']}").json()
    nov2 = date(date.today().year + (1 if date.today() > date(date.today().year, 11, 2) else 0), 11, 2)
    assert str(card["next_contact_date"]) == str(nov2), m["text"]

    note = "Need to ask Ben for broker engagement letter with 4% converted to equity"
    m = ask(c, f'add note on Paul Bartley "{note}"')
    assert m["text"].startswith("Added the note to #1 Paul Bartley")
    events = c.get(f"/funnel/{a['id']}").json()["events"]
    assert any(e["kind"] == "note" and e["body"] == note for e in events)


def test_status_change_by_number():
    c, a, *_ = make("t4")
    ask(c, "mark #1 as ghosting and P1")
    card = c.get(f"/funnel/{a['id']}").json()
    assert card["status"] == "Ghosting" and card["priority"] == "P1"
