from fastapi.testclient import TestClient

from app.main import app

from .conftest import ORIGIN, login

PW = "Blue-harbour-42"


def fresh():
    return TestClient(app, headers=ORIGIN)


def pw_login(c, email, pw=PW):
    """Password step, then the emailed code (returned as dev_code because tests have no SMTP)."""
    r = c.post("/auth/password/login", json={"email": email, "password": pw})
    if r.status_code != 200:
        return r
    assert r.json()["code_required"] is True
    return c.post("/auth/password/verify", json={"email": email, "code": r.json()["dev_code"]})


def test_set_password_then_sign_in_with_it():
    c = login("pw-founder@example.com")
    me = c.get("/auth/me").json()
    assert me["has_password"] is False
    r = c.post("/auth/password", json={"password": PW})
    assert r.status_code == 200, r.text
    assert c.get("/auth/me").json()["has_password"] is True

    other = fresh()
    r = other.post("/auth/password/login", json={"email": "PW-Founder@example.com", "password": PW})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "pw••••••••@example.com"
    assert other.get("/auth/me").status_code == 401  # the password alone does not sign you in
    r = other.post("/auth/password/verify", json={"email": "pw-founder@example.com", "code": r.json()["dev_code"]})
    assert r.status_code == 200, r.text
    assert r.json()["next"].startswith("/app")
    assert other.get("/auth/me").json()["email"] == "pw-founder@example.com"


def test_wrong_password_and_unknown_email_look_the_same():
    login("pw-wrong@example.com").post("/auth/password", json={"password": PW})
    a = fresh().post("/auth/password/login", json={"email": "pw-wrong@example.com", "password": "nope-nope-nope"})
    b = fresh().post("/auth/password/login", json={"email": "nobody-here@example.com", "password": PW})
    assert a.status_code == b.status_code == 401
    assert a.json()["code"] == b.json()["code"] == "EF-AUTH-062"


def test_google_only_user_cannot_sign_in_with_password():
    login("pw-google@example.com")
    r = fresh().post("/auth/password/login", json={"email": "pw-google@example.com", "password": PW})
    assert r.status_code == 401


def test_weak_passwords_rejected():
    c = login("pw-weak@example.com")
    for bad in ["short", "password123", "pw-weak@example.com", "aaaaaaaaaaaa"]:
        r = c.post("/auth/password", json={"password": bad})
        assert r.status_code == 422, bad


def test_change_needs_current_password_and_signs_out_other_devices():
    a = login("pw-change@example.com")
    a.post("/auth/password", json={"password": PW})
    b = fresh()
    assert pw_login(b, "pw-change@example.com").status_code == 200
    assert a.post("/auth/password", json={"password": "Green-meadow-77"}).status_code == 403
    r = a.post("/auth/password", json={"password": "Green-meadow-77", "current_password": PW})
    assert r.status_code == 200, r.text
    assert a.get("/auth/me").status_code == 200  # this device stays signed in
    assert b.get("/auth/me").status_code == 401  # the other one is signed out
    assert fresh().post("/auth/password/login", json={"email": "pw-change@example.com", "password": PW}).status_code == 401


def test_remove_password():
    c = login("pw-remove@example.com")
    c.post("/auth/password", json={"password": PW})
    assert c.delete("/auth/password").status_code == 200
    assert fresh().post("/auth/password/login", json={"email": "pw-remove@example.com", "password": PW}).status_code == 401


def test_code_is_single_use_and_burns_after_five_wrong_tries():
    login("pw-code@example.com").post("/auth/password", json={"password": PW})
    c = fresh()
    code = c.post("/auth/password/login", json={"email": "pw-code@example.com", "password": PW}).json()["dev_code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert c.post("/auth/password/verify", json={"email": "pw-code@example.com", "code": wrong}).status_code == 401
    r = c.post("/auth/password/verify", json={"email": "pw-code@example.com", "code": code})
    assert r.status_code == 401 and r.json()["code"] == "EF-AUTH-063"

    code = c.post("/auth/password/login", json={"email": "pw-code@example.com", "password": PW}).json()["dev_code"]
    assert c.post("/auth/password/verify", json={"email": "pw-code@example.com", "code": code}).status_code == 200
    assert fresh().post("/auth/password/verify", json={"email": "pw-code@example.com", "code": code}).status_code == 401


def test_expired_code_rejected():
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import User

    login("pw-exp@example.com").post("/auth/password", json={"password": PW})
    c = fresh()
    code = c.post("/auth/password/login", json={"email": "pw-exp@example.com", "password": PW}).json()["dev_code"]
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == "pw-exp@example.com"))
        u.login_code_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert c.post("/auth/password/verify", json={"email": "pw-exp@example.com", "code": code}).status_code == 401
