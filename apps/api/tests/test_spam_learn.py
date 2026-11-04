"""Spam score, sending-domain check, learning from results, and removing an investor from outreach."""

from datetime import UTC, datetime
from types import SimpleNamespace as NS

from app.services import learn, spam

from .test_outreach import _ready_to_send

CLEAN = ("Hi {first name},\n\nWe help clinics triage patients with AI. 40 clinics are live and we grow 12% a month. "
         "Given your health portfolio, I thought it was worth a note. Would a 15 minute call next week be useful?\n\nSam")


def test_spam_score_levels():
    good = spam.score("DocAI x Seedfund", CLEAN, 1, "Ada")
    assert good["level"] == "good" and good["score"] < spam.WARN
    bad = spam.score("RE: URGENT!!! Guaranteed returns", "Click here to act now!!! http://bit.ly/x http://1.2.3.4/y", 1)
    assert bad["level"] == "high" and any("Spam-trigger" in r for r in bad["reasons"])
    assert any("pretends to be a reply" in r for r in bad["reasons"])


def test_domain_auth_gmail_is_handled_by_google():
    r = spam.domain_auth("founder@gmail.com")
    assert r["ok"] and r["managed"] and [c["name"] for c in r["checks"]] == ["SPF", "DKIM", "DMARC"]


def test_learning_picks_a_clear_winner_only():
    def em(subject, replied):
        return NS(subject=subject, step=1, hook="", replied_at=datetime.now(UTC) if replied else None,
                  reply_kind="positive" if replied else "", open_count=0)

    assert learn.style("Ada, meet DocAI") == "name-first" and learn.style("Re: DocAI x Seedfund") == "x-firm"
    groups = {"x-firm": [em("A x B", i < 3) for i in range(6)], "intro": [em("Intro: A", i < 1) for i in range(6)]}
    k, s, lift = learn._best(groups, opens=False)
    assert k == "x-firm" and s["replied"] == 3 and lift == 3
    even = {"x-firm": [em("A x B", i < 1) for i in range(6)], "intro": [em("Intro: A", i < 1) for i in range(6)]}
    assert learn._best(even, opens=False) is None  # no clear winner, no change
    assert learn._best({"x-firm": groups["x-firm"]}, opens=False) is None  # nothing to compare with


def test_insights_wait_for_enough_data(client):
    _ready_to_send(client)
    r = client.get("/outreach/insights").json()
    assert r["enough"] is False and r["findings"] == [] and r["need"] == learn.MIN_TOTAL


def test_spammy_email_blocks_scheduling_and_remove_from_outreach(client):
    ada = _ready_to_send(client)
    seq = client.post("/sequences", json={"investor_id": ada["id"]}).json()
    assert all("spam" in e for e in seq["emails"])
    e1 = seq["emails"][0]
    r = client.patch(f"/sequences/{seq['id']}/emails/{e1['id']}",
                     json={"subject": "Fwd: deal", "body": "Hi Ada, our deck is at http://1.2.3.4/a for you. Sam"}).json()
    assert r["spam"]["level"] == "high"
    r = client.post(f"/sequences/{seq['id']}/approve", json={"confirm": True})
    assert r.status_code == 422 and "spam" in r.json()["title"].lower()
    # Remove from outreach: nothing sent, so the sequence goes completely and the investor can be added again.
    assert client.delete(f"/sequences/{seq['id']}").json() == {"ok": True, "kept_history": False}
    assert client.get(f"/sequences/{seq['id']}").status_code == 404
    assert all(x["id"] != seq["id"] for x in client.get("/sequences").json()["items"])


def test_usd_and_no_link_lines_in_follow_ups(client):
    from app.services.outreach import for_send, usd

    assert usd("Raising $1.5M at a $10m cap; $40k MRR") == "Raising USD 1.5M at a USD 10m cap; USD 40k MRR"
    body = ("Hi Ada,\n\nWe now have $40k MRR. Our data room: https://dr.example.com/x if useful.\n\n"
            "Sam\nCEO, DocAI\nhttps://docai.example.com\nlinkedin.com/in/sam")
    two = for_send(body, 2)
    assert "USD 40k" in two and "https://dr.example.com/x" in two  # links in a sentence stay
    assert "docai.example.com" not in two and "linkedin" not in two and two.endswith("CEO, DocAI")
    assert "linkedin.com/in/sam" in for_send(body, 1)  # email 1 keeps the signature links
    seq = client.post("/sequences", json={"investor_id": _ready_to_send(client)["id"]}).json()
    assert all("$" not in e["body"] for e in seq["emails"])
