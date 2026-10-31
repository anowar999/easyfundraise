import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Tier, Workspace
from app.services import crypto

from .conftest import ORIGIN, login, set_tier


def anon() -> TestClient:
    return TestClient(app, headers=ORIGIN)


def test_data_room_magic_link_and_analytics(client):
    client.put("/workspace/profile", json={"company_name": "Room Co", "one_liner": "Rooms for all"})
    room = client.get("/data-room").json()
    assert room["slug"].startswith("room-co") and room["access"] == "magic" and not room["published"]
    assert anon().get(f"/public/rooms/{room['slug']}").status_code == 404  # unpublished
    content = room["content"]
    content["sections"][0]["body"] = "Clinics waste hours"
    client.put("/data-room", json={"published": True, "content": content})
    assert anon().get(f"/public/rooms/{room['slug']}").json()["locked"] is True
    card = client.post("/funnel", json={"name": "Viewer Vic", "firm": "VicVC"}).json()
    link = client.post("/data-room/links", json={"card_id": card["id"]}).json()
    token = link["url"].split("k=")[1]
    v = anon()
    page = v.get(f"/public/rooms/{room['slug']}", params={"k": token}).json()
    assert page["locked"] is False and page["content"]["sections"][0]["body"] == "Clinics waste hours"
    assert page["indexable"] is False  # DR-05
    v.post(f"/public/rooms/{room['slug']}/ping", json={"view_id": page["view_id"], "seconds": 40,
                                                       "sections": {"traction": 30, "team": 10}})
    views = client.get("/data-room/views", params={"card_id": card["id"]}).json()["items"]
    assert views[0]["seconds"] == 40 and views[0]["sections"]["traction"] == 30
    assert any("Viewer Vic" in n["title"] for n in client.get("/notifications").json()["items"])
    # cookie keeps access without the token; revoking the link ends it
    assert v.get(f"/public/rooms/{room['slug']}").json()["locked"] is False
    client.delete(f"/data-room/links/{link['id']}")
    assert v.get(f"/public/rooms/{room['slug']}").json()["locked"] is True
    # version history
    assert len(client.get("/data-room").json()["versions"]) == 1


def test_data_room_password_and_email(client):
    client.put("/workspace/profile", json={"company_name": "Pw Co"})
    slug = client.get("/data-room").json()["slug"]
    client.put("/data-room", json={"published": True, "access": "password", "password": "s3cret!"})
    v = anon()
    assert v.post(f"/public/rooms/{slug}/unlock", json={"password": "nope"}).status_code == 403
    assert v.post(f"/public/rooms/{slug}/unlock", json={"password": "s3cret!"}).status_code == 200
    assert v.get(f"/public/rooms/{slug}").json()["locked"] is False
    client.put("/data-room", json={"access": "email"})
    v2 = anon()
    v2.post(f"/public/rooms/{slug}/unlock", json={"email": "lp@fund.com"})
    assert v2.get(f"/public/rooms/{slug}").json()["locked"] is False


def test_invites_roles_and_seats(client):
    set_tier(client, "pro")  # 3 seats
    r = client.post("/workspace/invites", json={"email": "cofounder@founder.io", "role": "editor"}).json()
    token = r["url"].rsplit("/", 1)[1]
    other = login("cofounder@founder.io")
    assert other.get(f"/invites/{token}").json()["role"] == "editor"
    ws_id = other.post(f"/invites/{token}/accept").json()["workspace_id"]
    members = client.get("/workspace/members").json()["items"]
    assert {m["role"] for m in members} == {"owner", "editor"}
    # viewers can't change things
    viewer_id = next(m["id"] for m in members if m["role"] == "editor")
    client.patch(f"/workspace/members/{viewer_id}", json={"role": "viewer"})
    r = other.post("/funnel", json={"name": "X"}, headers={"x-workspace": ws_id})
    assert r.status_code == 403
    # seat limit (3): owner + member + 1 invite fills it
    client.post("/workspace/invites", json={"email": "third@founder.io"})
    assert client.post("/workspace/invites", json={"email": "fourth@founder.io"}).status_code == 402
    # wrong account can't accept
    t2 = client.post("/workspace/invites", json={"email": "fifth@founder.io"})
    assert t2.status_code == 402


def test_sessions_list_and_revoke(client):
    items = client.get("/auth/sessions").json()["items"]
    assert len(items) == 1 and items[0]["current"]
    client.delete(f"/auth/sessions/{items[0]['id']}")
    assert client.get("/auth/me").status_code == 401


def test_admin_mfa(client, monkeypatch):
    with SessionLocal() as db:
        from app.models import User

        u = db.scalar(select(User).where(User.email.like("test_admin_mfa%")))
        u.is_admin = True
        db.commit()
    monkeypatch.setattr(get_settings(), "admin_mfa", True)
    assert client.get("/admin/overview").json()["code"] == "EF-AUTH-011"
    secret = client.post("/auth/mfa/setup").json()["secret"]
    assert client.post("/auth/mfa/verify", json={"code": "000000"}).status_code == 403
    assert client.post("/auth/mfa/verify", json={"code": crypto.totp(secret)}).status_code == 200
    assert client.get("/admin/overview").status_code == 200


def test_crypto_roundtrip():
    blob = crypto.encrypt("refresh-token")
    assert blob != "refresh-token" and crypto.decrypt(blob) == "refresh-token"
    assert crypto.password_ok("pw", crypto.password_hash("pw")) and not crypto.password_ok("x", crypto.password_hash("pw"))


def test_stripe_webhook_sets_tier(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_test")
    ws_id = client.get("/workspace").json()["id"]
    with SessionLocal() as db:
        db.get(Tier, "starter").stripe_price_monthly = "price_starter_m"
        db.commit()

    def post(ev, secret="whsec_test"):
        body = json.dumps(ev).encode()
        t = str(int(time.time()))
        sig = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
        return anon().post("/billing/webhook", content=body, headers={"stripe-signature": f"t={t},v1={sig}",
                                                                     "content-type": "application/json"})

    sub = {"id": "sub_1", "customer": "cus_1", "status": "active", "metadata": {"workspace_id": ws_id},
           "items": {"data": [{"price": {"id": "price_starter_m", "recurring": {"interval": "month"}},
                               "current_period_end": int(time.time()) + 86400 * 30}]}}
    assert post({"type": "customer.subscription.updated", "data": {"object": sub}}, "wrong").status_code == 400
    assert post({"type": "customer.subscription.updated", "data": {"object": sub}}).status_code == 200
    with SessionLocal() as db:
        assert db.get(Workspace, __import__("uuid").UUID(ws_id)).tier_code == "starter"
    sub["status"] = "canceled"
    post({"type": "customer.subscription.deleted", "data": {"object": sub}})
    assert client.get("/workspace").json()["tier"]["code"] == "trial"
