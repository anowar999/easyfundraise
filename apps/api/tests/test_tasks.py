from datetime import date, timedelta


def test_founder_tasks_board(client):
    today = date.today()
    a = client.post("/tasks", json={"title": "Finish deck", "priority": 1, "deadline": today.isoformat()}).json()
    b = client.post("/tasks", json={"title": "Call lawyer", "priority": 2, "owner": "Sam", "depends_on": "Term sheet",
                                    "follow_ups": [(today + timedelta(days=3)).isoformat(), today.isoformat()]}).json()
    c = client.post("/tasks", json={"title": "Fix pricing page", "priority": 3, "urgent": True}).json()
    client.post("/tasks", json={"title": "Low thing", "priority": 3})
    assert a["due_today"] and b["due_today"] and b["next_follow_up"] == today.isoformat()
    assert client.post("/tasks", json={"title": "  "}).status_code == 422

    board = client.get("/tasks").json()
    assert [t["title"] for t in board["top"]] == ["Fix pricing page", "Finish deck", "Call lawyer"]  # urgent first
    assert [t["title"] for t in board["urgent"]] == ["Fix pricing page"] and board["due_today"] == 2

    r = client.patch(f"/tasks/{a['id']}", json={"status": "doing", "progress": 40}).json()
    assert r["status"] == "doing" and r["progress"] == 40
    r = client.patch(f"/tasks/{c['id']}", json={"status": "done"}).json()
    assert r["progress"] == 100 and r["urgent"] is False and r["done_at"]
    r = client.patch(f"/tasks/{a['id']}", json={"progress": 100}).json()
    assert r["status"] == "done"  # 100% moves it to Done

    client.patch(f"/tasks/{b['id']}", json={"status": "archived"})
    assert "Call lawyer" not in [t["title"] for t in client.get("/tasks").json()["items"]]
    assert [t["title"] for t in client.get("/tasks", params={"archived": True}).json()["items"]] == ["Call lawyer"]
    assert client.patch(f"/tasks/{b['id']}", json={"status": "nope"}).status_code == 422
    assert client.delete(f"/tasks/{b['id']}").json()["ok"]
