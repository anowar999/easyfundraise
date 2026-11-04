"""Investor list > select > Add to outreach (schedule / send now / drafts), and the audit trail of consent."""

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditLog, Sequence

from .conftest import set_tier


def _setup(client):
    set_tier(client, "pro")
    client.put("/workspace/profile", json={"company_name": "DocAI", "one_liner": "AI triage for clinics",
                                           "sectors": ["Digital Health & HealthTech"], "stage": "seed"})
    client.patch("/workspace/me", json={"signature": "Sam"})
    client.get("/gmail/connect", follow_redirects=False)
    return [i["id"] for i in client.get("/investors", params={"q": "a"}).json()["items"]][:3]


def test_bulk_add_confirm_then_schedule_and_audit(client):
    ids = _setup(client)
    pre = client.post("/sequences/bulk-add", json={"investor_ids": ids, "action": "window"}).json()
    assert pre["needs_confirm"] and pre["count"] + len(pre["skipped"]) == len(ids) and pre["terms"]
    ws = client.get("/workspace").json()["id"]
    with SessionLocal() as db:  # the confirm screen creates nothing
        assert not db.scalars(select(Sequence).where(Sequence.workspace_id == ws)).all()
    r = client.post("/sequences/bulk-add", json={"investor_ids": ids, "action": "window", "confirm": True})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["scheduled"] + len(out["drafts"]) + len(out["skipped"]) == len(ids) and out["scheduled"] >= 1
    with SessionLocal() as db:
        seqs = db.scalars(select(Sequence).where(Sequence.workspace_id == ws)).all()
        assert any(s.status == "approved" and all(e.scheduled_for for e in s.emails) for s in seqs)
        bulk = db.scalars(select(AuditLog).where(AuditLog.action == "sequence.bulk_add")).all()[-1]
        assert bulk.after["confirmed"] is True and bulk.after["agreed_to"] and bulk.after["scheduled"]
        assert db.scalars(select(AuditLog).where(AuditLog.action == "sequence.approve",
                                                 AuditLog.target == str(seqs[0].id) if seqs[0].status == "approved"
                                                 else AuditLog.target == str(seqs[-1].id))).first().after["to"]
        assert db.scalars(select(AuditLog).where(AuditLog.action == "POST /sequences/bulk-add")).first()
    again = client.post("/sequences/bulk-add", json={"investor_ids": ids, "action": "draft"}).json()
    assert again["skipped"] and all(s["reason"] == "Already in your outreach list" for s in again["skipped"][:1])


def test_bulk_add_drafts_need_no_confirm(client):
    set_tier(client, "pro")
    ids = [i["id"] for i in client.get("/investors", params={"q": "e"}).json()["items"]][:2]
    r = client.post("/sequences/bulk-add", json={"investor_ids": ids, "action": "draft"}).json()
    assert "needs_confirm" not in r and len(r["drafts"]) + len(r["skipped"]) == len(ids)
