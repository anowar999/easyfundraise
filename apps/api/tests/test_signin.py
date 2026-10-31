"""Email sign-in links, safe redirects and the welcome step for new users."""

import time
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import app
from app.routers.auth import safe_next
from app.services.account_mail import read_sign_in_token, sign_in_token


def test_token_round_trip_and_expiry():
    assert read_sign_in_token(sign_in_token("A@Example.com")) == "a@example.com"
    assert read_sign_in_token(sign_in_token("a@example.com", now=time.time() - 3600)) is None
    tok = sign_in_token("a@example.com")
    assert read_sign_in_token(tok[:-2] + "xx") is None
    assert read_sign_in_token("garbage") is None


def test_safe_next():
    assert safe_next("/app/funnel") == "/app/funnel"
    for bad in ("https://evil.com", "//evil.com", "/\\\\evil.com", ""):
        assert safe_next(bad) == "/app"


def test_email_link_signs_in_and_new_user_goes_to_welcome():
    c = TestClient(app)
    r = c.post("/auth/email/start", json={"email": "linkuser@founder.io", "next": "/app/funnel"},
               headers={"origin": "http://testserver"})
    assert r.status_code == 200 and r.json()["sent"] is False  # dev without SMTP returns the link
    q = parse_qs(urlparse(r.json()["dev_link"]).query)
    r = c.get("/auth/email/verify", params={"token": q["token"][0], "next": q["next"][0]}, follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/welcome?next=" in r.headers["location"] and "%2Fapp%2Ffunnel" in r.headers["location"]
    assert c.get("/auth/me").json()["email"] == "linkuser@founder.io"
    # second sign-in: existing user goes straight to next
    r = c.get("/auth/email/verify", params={"token": sign_in_token("linkuser@founder.io"), "next": "/app"},
              follow_redirects=False)
    assert r.headers["location"].endswith("/app")


def test_expired_link_returns_to_login():
    c = TestClient(app)
    r = c.get("/auth/email/verify", params={"token": "nope.nope"}, follow_redirects=False)
    assert "/login?error=expired" in r.headers["location"]
