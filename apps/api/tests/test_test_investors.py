"""Test investors: everyone sees them in dev/UAT; on live (or EF_LIVE_RULES) only the listed test accounts do."""

import json

import pytest
from sqlalchemy import delete

from app.config import get_settings
from app.db import SessionLocal
from app.models import Investor
from app.services import test_investors

from .conftest import login, set_tier

RECORDS = [
    {"name": "Tessa Testwell", "email": "tessa@example.test", "title": "General Partner", "firm": "Testbed VC",
     "location": "London, England, United Kingdom", "industries": ["FinTech", "SaaS & Enterprise"],
     "check_size": "$50k-$2m", "thesis": "Test thesis.", "geography": "UK; Europe"},
    {"name": "Theo Trial", "email": "theo@example.test", "title": "Partner", "firm": "Testbed VC",
     "location": "New York, New York, United States", "industries": ["FinTech"], "check_size": "$10k-$1m"},
]


@pytest.fixture
def seeded(tmp_path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps(RECORDS))
    with SessionLocal() as db:
        assert len(test_investors.load(db, f)) == 2
        assert len(test_investors.load(db, f)) == 2  # re-runnable: refreshes, no duplicates
        assert db.query(Investor).filter(Investor.is_test).count() == 2
    yield
    with SessionLocal() as db:
        db.execute(delete(Investor).where(Investor.is_test))
        db.commit()


def _search(c, q="Testbed"):
    return [i["name"] for i in c.get("/investors", params={"q": q}).json()["items"]]


def test_dev_everyone_sees_test_investors(client, seeded):
    items = client.get("/investors", params={"q": "Testbed"}).json()["items"]
    assert {i["name"] for i in items} == {"Tessa Testwell", "Theo Trial"} and all(i["is_test"] for i in items)
    tessa = next(i for i in items if i["name"] == "Tessa Testwell")
    p = client.get(f"/investors/{tessa['id']}").json()
    assert p["typical_check_size"] == "$50k-$2m" and p["country"] == "United Kingdom" and p["identity_confidence"] == "high"


def test_live_only_test_accounts_see_them(seeded, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "live_rules", True)
    monkeypatch.setattr(s, "test_investor_users", "tester@doctra.io")
    other, tester = login("someone@founder.io"), login("tester@doctra.io")
    assert _search(other) == [] and len(_search(tester)) == 2
    tid = tester.get("/investors", params={"q": "Testbed"}).json()["items"][0]["id"]
    assert other.get(f"/investors/{tid}").status_code == 404
    assert other.post("/sequences", json={"investor_id": tid}).status_code == 404
    set_tier(tester, "pro")
    r = tester.post(f"/investors/{tid}/reveal").json()
    assert r["contacts"] and r["charged"]
    assert tester.post("/sequences", json={"investor_id": tid}).status_code == 200


def test_test_reveal_uses_no_credit(client, seeded):
    set_tier(client, "starter")
    tid = client.get("/investors", params={"q": "Testbed"}).json()["items"][0]["id"]
    r = client.post(f"/investors/{tid}/reveal").json()
    assert r["contacts"]["email"].endswith("@example.test")
    assert client.get("/workspace").json()["usage"].get("reveals_month", 0) == 0
