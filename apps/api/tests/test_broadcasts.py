from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Email, GmailAccount
from app.services import mailer
from app.services.gmail import FakeGmail

from .conftest import set_tier


def _setup(client):
    set_tier(client, "top")
    client.put("/workspace/profile", json={"company_name": "DocAI", "round_size": "$1.5M"})
    client.patch("/workspace/me", json={"signature": "Sam"})
    client.get("/gmail/connect", follow_redirects=False)
    lead = client.post("/funnel", json={"name": "Lena Lead", "firm": "LeadVC", "email": "lena@leadvc.com",
                                        "stage": 8, "shareable": True}).json()
    quiet = client.post("/funnel", json={"name": "Nora Noname", "firm": "Shy", "email": "nora@shy.vc", "stage": 9}).json()
    warm = client.post("/funnel", json={"name": "Walt Warm", "firm": "WarmVC", "email": "walt@warm.vc", "stage": 5}).json()
    cool = client.post("/funnel", json={"name": "Cody Cool", "firm": "CoolVC", "email": "cody@cool.vc", "stage": 2}).json()
    client.post("/funnel", json={"name": "No Email", "stage": 3})
    return lead, quiet, warm, cool


def test_round_update_truthful_and_warmest_first(client):
    lead, quiet, warm, cool = _setup(client)
    # naming a committed investor who did not agree to be named is refused (FOMO-01)
    r = client.post("/broadcasts", json={"kind": "round_update", "template": "lead_secured",
                                         "inputs": {"lead_card_ids": [quiet["id"]]}})
    assert r.status_code == 422
    r = client.post("/broadcasts", json={"kind": "round_update", "template": "lead_secured",
                                         "inputs": {"lead_card_ids": [lead["id"]], "amount_committed": "$900K",
                                                    "closing_date": "28 Nov"},
                                         "audience": {"stages": [2, 7], "exclude_card_ids": [cool["id"]]},
                                         "follow_up": True})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["recipients"] == 1  # Walt only: Cody excluded, no-email card skipped, committed stage 8/9 outside 2-7
    body = b["emails"][0]["body"]
    assert "Lena Lead (LeadVC) is leading" in body and "$900K committed of our $1.5M round" in body
    b = client.post(f"/broadcasts/{b['id']}/approve", json={"confirm": True}).json()
    assert b["status"] == "scheduled" and len(b["emails"]) == 2  # + one follow-up


def test_investor_update_needs_ir_tier_and_threads_followup(client):
    lead, *_ = _setup(client)
    set_tier(client, "pro")
    r = client.post("/broadcasts", json={"kind": "investor_update", "template": "monthly",
                                         "audience": {"stages": [8, 9]}})
    assert r.status_code == 402
    set_tier(client, "top")
    b = client.post("/broadcasts", json={"kind": "investor_update", "template": "monthly",
                                         "inputs": {"metrics": [{"label": "MRR", "value": "$42K"}], "wins": ["NHS pilot"]},
                                         "audience": {"stages": [8, 9]}}).json()
    assert b["recipients"] == 2 and "MRR: $42K" in b["emails"][0]["body"]
    client.post(f"/broadcasts/{b['id']}/approve", json={"confirm": True})
    FakeGmail.reset()
    with SessionLocal() as db:
        ems = db.scalars(select(Email).where(Email.broadcast_id == b["id"])).all()
        for em in ems:
            acc = db.get(GmailAccount, em.user_id)
            acc.next_send_at = None
            acc.connected_at = acc.connected_at - timedelta(days=30)
            db.commit()
            mailer.send_due(db, em.scheduled_for + timedelta(seconds=1))
    mine = [m for m in FakeGmail.sent if m["Subject"].startswith("DocAI update")]
    assert len(mine) == 2 and mine[0]["List-Unsubscribe"]  # MAIL-07
