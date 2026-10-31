from .conftest import ORIGIN, login, set_tier


def test_requires_login():
    from fastapi.testclient import TestClient

    from app.main import app

    r = TestClient(app).get("/auth/me")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == "EF-AUTH-001"


def test_signup_creates_trial_workspace(client):
    me = client.get("/auth/me").json()
    assert me["workspaces"][0]["tier"] == "trial"
    ws = client.get("/workspace").json()
    assert ws["tier"]["limits"]["searches_total"] == 10
    assert ws["admin_unlocked"] is False
    assert ws["trial_ends_at"]


def test_trial_ten_searches_then_locked(client):
    for _ in range(10):
        r = client.get("/investors", params={"q": "health"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["contacts_locked"] is True
        assert all("email" not in x and "linkedin" not in x for x in body["items"])  # ASP-01
    r = client.get("/investors", params={"q": "health"})
    assert r.status_code == 402
    assert r.json()["code"] == "EF-LIMIT-001"


def test_browsing_without_criteria_is_free(client):
    for _ in range(5):
        assert client.get("/investors").status_code == 200
    assert client.get("/workspace").json()["usage"]["searches_total"] == 0


def test_trial_cannot_reveal(client):
    inv = client.get("/investors").json()["items"][0]
    r = client.post(f"/investors/{inv['id']}/reveal")
    assert r.status_code == 402


def test_starter_reveal_charges_once(client):
    set_tier(client, "starter")
    inv = next(x for x in client.get("/investors", params={"q": "Ada"}).json()["items"] if x["name"] == "Ada Seed")
    prof = client.get(f"/investors/{inv['id']}").json()
    assert prof["contacts"] is None and prof["revealed"] is False
    r1 = client.post(f"/investors/{inv['id']}/reveal").json()
    assert r1["charged"] is True and r1["contacts"]["email"] == "ada@seedfund.vc"
    r2 = client.post(f"/investors/{inv['id']}/reveal").json()
    assert r2["charged"] is False
    assert client.get("/workspace").json()["usage"]["reveals_month"] == 1
    assert client.get(f"/investors/{inv['id']}").json()["contacts"]["email"] == "ada@seedfund.vc"


def test_honeypot_reveal_suspends(client):
    set_tier(client, "starter")
    hp = next(x for x in client.get("/investors", params={"q": "Honey"}).json()["items"])
    assert client.post(f"/investors/{hp['id']}/reveal").status_code == 403
    assert client.get("/auth/me").status_code == 403


def test_workspace_isolation():
    a, b = login("iso-a@founder.io"), login("iso-b@founder.io")
    card = a.post("/funnel", json={"name": "Private Investor"}).json()
    assert b.get(f"/funnel/{card['id']}").status_code == 404
    assert b.get("/funnel").json()["items"] == []
    assert b.get("/investors", headers={"x-workspace": a.get("/workspace").json()["id"]}).status_code == 403


def test_csrf_blocks_cross_site(client):
    r = client.post("/funnel", json={"name": "x"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    assert ORIGIN  # same-origin requests (fixture default) pass elsewhere


def test_admin_requires_admin(client):
    assert client.get("/admin/overview").status_code == 403


def test_admin_workspace_gets_top_tier_outside_prod(client):
    from sqlalchemy import text

    from app.db import SessionLocal

    email = client.get("/auth/me").json()["email"]
    with SessionLocal() as db:
        db.execute(text("update users set is_admin = true where email = :e"), {"e": email})
        db.commit()
    ws = client.get("/workspace").json()
    assert ws["tier"]["code"] == "top" and ws["admin_unlocked"] is True
    assert client.get("/auth/me").json()["workspaces"][0]["tier"] == "trial"  # billing state is untouched
