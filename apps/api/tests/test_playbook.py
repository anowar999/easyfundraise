"""Email playbook: email 1-3 built the founder's way (about them + building, problem, market), what we're looking
for, strengths placed once per investor, round/progress updates as the next follow-up, AI fill from the founder's
own deck, a 3-email preview, and the outreach agent tools."""

import json
import random
from types import SimpleNamespace as NS

from app.services import agent, playbook

from .conftest import set_tier
from .test_agent import GOOD, _ada, stub  # noqa: F401 - stub is a fixture

PB = {"emails": [
    {"focus": "What we're building", "message": "LedgerLoop closes the books in one day for SaaS finance teams."},
    {"focus": "The problem we solve", "message": "Finance teams lose 9 days every month reconciling usage billing."},
    {"focus": "Market opportunity and traction", "message": "40 SaaS customers today and 3x usage since January."}],
    "ask": "We're raising $750k pre-seed and looking for an angel with finance operator experience.",
    "strengths": ["Our team has worked together for 5 years.", "We were selected for a top European founder program."]}

PROFILE = {"company_name": "LedgerLoop", "one_liner": "Month-end close in one day for SaaS finance teams",
           "sectors": ["Digital Health & HealthTech"], "stage": "pre-seed", "round_size": "$750k",
           "traction": "40 SaaS customers"}


def _setup(client, pb=PB):
    client.put("/workspace/profile", json=PROFILE)
    r = client.put("/outreach/playbook", json=pb)
    assert r.status_code == 200, r.text
    return r.json()


def test_money_rules_allow_our_raise_not_their_money():
    assert not agent.money_talk(PB["ask"], "230m people, 875k consultations", "we talk to investors weekly")
    assert agent.money_talk("This fits your ticket range") and agent.money_talk("a great investment")
    assert agent.money_talk("your typical cheque") and agent.money_talk("at a $5m valuation")


def test_plan_places_each_strength_once():
    pb = {**playbook.merge(playbook.get(NS(email_playbook={})), PB["emails"], PB["ask"], PB["strengths"])}
    for seed in range(20):
        p = playbook.plan(pb, random.Random(seed))
        placed = [s for step in (1, 2, 3) for s in p[step]["strengths"]]
        assert sorted(placed) == sorted(PB["strengths"])
        assert p[1]["structure"].startswith("About them") and p["ask"] == PB["ask"]


def test_template_drafts_follow_the_shape(client):
    set_tier(client, "pro")
    got = _setup(client)
    assert got["saved_at"] and not got["money_warning"] and got["emails"][2]["focus"].startswith("Market")
    seq = client.post("/sequences", json={"investor_id": _ada(client)["id"]}).json()
    e1, e2, e3 = (e["body"] for e in seq["emails"])
    assert "Medibot" in e1 and "closes the books in one day" in e1 and "$750k pre-seed" in e1  # about them, building, ask
    assert "9 days" in e2 and "Medibot" not in e2 and "$750k" in e2  # the problem replaces the synergy
    assert "40 SaaS customers" in e3 and "$750k" in e3
    assert sum("5 years" in b for b in (e1, e2, e3)) == 1 and sum("founder program" in b for b in (e1, e2, e3)) == 1
    assert [e["hook"] for e in seq["emails"]] == ["playbook-1", "playbook-2", "playbook-3"]
    assert all(e["issues"] == [] for e in seq["emails"]), [e["issues"] for e in seq["emails"]]


def test_update_becomes_the_next_follow_up_and_clears_back(client):
    set_tier(client, "pro")
    _setup(client)
    seq = client.post("/sequences", json={"investor_id": _ada(client)["id"]}).json()
    before = seq["emails"][1]["body"]
    r = client.put("/outreach/quick-update", json={"text": "We just closed half the round with two angels"}).json()
    assert r["changed"] == 1 and r["update"].startswith("We just closed") and r["unsent"] >= 1
    e = client.get(f"/sequences/{seq['id']}").json()["emails"]
    assert e[1]["body"].startswith("Hi Ada,\n\nWe just closed half the round with two angels.")
    assert "$750k pre-seed" in e[1]["body"] and "20-minute call" in e[1]["body"] and "9 days" not in e[1]["body"]
    assert e[0]["body"] == seq["emails"][0]["body"] and e[2]["body"] == seq["emails"][2]["body"]
    assert e[1]["issues"] == []
    new = client.post("/sequences", json={"investor_id": _ada(client)["id"]}).json()  # new drafts carry it too
    assert "half the round" in new["emails"][1]["body"]
    client.put("/outreach/quick-update", json={"text": ""})
    assert client.get(f"/sequences/{seq['id']}").json()["emails"][1]["body"] == before


def test_ai_draft_follows_the_plan(client, stub):  # noqa: F811
    set_tier(client, "pro")
    _setup(client)
    s = stub([GOOD])
    seq = client.post("/sequences", json={"investor_id": _ada(client)["id"]}).json()
    user = json.loads(s.calls[0]["messages"][0]["content"])
    assert user["what_were_looking_for"] == PB["ask"]
    plan = user["email_plan"]
    assert plan["1"]["shape"].startswith("About them") and plan["2"]["main_focus"] == "The problem we solve"
    assert sum(len(plan[k].get("include_strengths", [])) for k in plan) == 2
    assert "Email 2 (a follow-up" in s.calls[0]["system"]
    assert seq["engine"] != "template" and [e["hook"] for e in seq["emails"]] == ["playbook-1", "playbook-2", "playbook-3"]


def test_preview_shows_three_emails_without_saving(client):
    set_tier(client, "pro")
    client.put("/workspace/profile", json=PROFILE)
    client.put(f"/shortlist/{_ada(client)['id']}")
    draft = {**PB, "ask": "We're raising $1m seed."}
    r = client.post("/outreach/playbook/preview", json=draft).json()
    assert r["investor"]["name"] and len(r["emails"]) == 3 and "$1m seed" in r["emails"][0]["body"]
    assert client.get("/outreach/playbook").json()["saved_at"] is None  # nothing saved
    assert client.get("/sequences").json()["items"] == []  # nothing drafted
    other = client.post("/outreach/playbook/preview", json={**draft, "skip": [r["investor"]["id"]]}).json()
    assert other["investor"]["id"] != r["investor"]["id"]


def test_redraft_unapproved_drafts(client):
    set_tier(client, "pro")
    client.put("/workspace/profile", json=PROFILE)
    seq = client.post("/sequences", json={"investor_id": _ada(client)["id"]}).json()
    assert "9 days" not in seq["emails"][1]["body"]
    _setup(client)
    assert client.post("/outreach/playbook/redraft").json()["redrafted"] == 1
    assert "9 days" in client.get(f"/sequences/{seq['id']}").json()["emails"][1]["body"]


def test_agent_sets_playbook_and_update(client, stub):  # noqa: F811
    set_tier(client, "pro")
    tool = NS(content=[NS(type="tool_use", id="t1", name="set_email_playbook",
                          input={"email2": {"focus": "The problem", "message": PB["emails"][1]["message"]},
                                 "add_strength": "Selected by a top founder program"}),
                       NS(type="tool_use", id="t2", name="set_quick_update", input={"text": "Half the round is committed"})],
              stop_reason="tool_use", model="claude-opus-5-5", usage=NS(input_tokens=10, output_tokens=5))
    done = NS(content=[NS(type="text", text="Saved.")], stop_reason="end_turn", model="claude-opus-5-5",
              usage=NS(input_tokens=10, output_tokens=5))
    stub([tool, done])
    m = client.post("/agent/chat", json={"text": "Email 2 should be about the problem ..."}).json()
    assert [a["type"] for a in m["actions"]] == ["playbook", "playbook"]
    pb = client.get("/outreach/playbook").json()
    assert pb["emails"][1] == {"focus": "The problem", "message": PB["emails"][1]["message"]}
    assert pb["strengths"] == ["Selected by a top founder program"] and pb["update"] == "Half the round is committed"


def test_agent_without_ai_understands_playbook_lines(client):
    client.post("/agent/chat", json={"text": "Email 2 should focus on the problem we solve: Teams lose 9 days a month"})
    client.post("/agent/chat", json={"text": "Add a strength: We have worked together for 5 years"})
    client.post("/agent/chat", json={"text": "Round update: We closed our first $300k"})
    pb = client.get("/outreach/playbook").json()
    assert pb["emails"][1] == {"focus": "the problem we solve", "message": "Teams lose 9 days a month"}
    assert pb["strengths"] == ["We have worked together for 5 years"] and pb["update"] == "We closed our first $300k"


def test_fill_comes_from_this_founders_deck(client, stub):  # noqa: F811
    s = client.post("/outreach/playbook/fill", json={}).json()  # no profile: blanks, nobody else's facts
    assert s["source"] == "generic" and all(e["message"] == "" for e in s["emails"]) and s["ask"] == ""
    assert [p.get("send", False) for p in s["prompts"]] == [False, False, False, True]
    client.put("/workspace/profile", json=PROFILE)
    s = client.post("/outreach/playbook/fill", json={}).json()  # no AI: from the profile
    assert s["source"] == "profile" and "LedgerLoop" in s["emails"][0]["message"] and s["ask"] == "We're raising $750k pre-seed."
    set_tier(client, "pro")
    deck = {"messages": ["We close the books in a day.", "Teams lose 9 days a month.", "A $40bn market, 40 customers."],
            "ask": "We're raising $750k pre-seed.", "strengths": ["Team of 5 years."],
            "update_example": "We just signed our 41st customer."}
    st = stub([deck])
    client.put("/workspace/profile", json={**PROFILE, "business_model": "SaaS subscription"})  # profile changed: re-pick
    s = client.post("/outreach/playbook/fill", json={"focuses": ["What we're building", "Customer pain", "Market"]}).json()
    assert s["source"] == "deck" and s["emails"][1] == {"focus": "Customer pain", "message": "Teams lose 9 days a month."}
    assert s["strengths"] == ["Team of 5 years."] and len(st.calls) == 1
    assert "Customer pain" in json.loads(st.calls[0]["messages"][0]["content"])["focuses"]
    again = client.post("/outreach/playbook/fill", json={"focuses": ["What we're building", "Customer pain", "Market"]})
    assert again.json()["source"] == "deck" and len(st.calls) == 1  # cached


def test_fill_reads_the_data_room_sections(client, stub):  # noqa: F811
    client.put("/workspace/profile", json=PROFILE)
    room = client.get("/data-room").json()
    secs = room["content"]["sections"]
    text = {"problem": "Finance teams lose 9 days every month reconciling usage billing. It costs them a hire.",
            "solution": "LedgerLoop matches every invoice to usage automatically.",
            "market": "SaaS finance software is a $40bn market.", "traction": "40 SaaS customers and 3x usage since January."}
    for s in secs:
        if s["type"] in text:
            s["body"] = text[s["type"]]
    assert client.put("/data-room", json={"content": {**room["content"], "sections": secs}}).status_code == 200
    s = client.post("/outreach/playbook/fill", json={}).json()  # no AI: straight from the room, by focus
    assert s["source"] == "data room"
    e1, e2, e3 = (e["message"] for e in s["emails"])
    assert e1.startswith("LedgerLoop matches every invoice") and "Month-end close" not in e2
    assert e2.startswith("Finance teams lose 9 days") and "$40bn" in e3 and "40 SaaS customers" in e3
    swapped = client.post("/outreach/playbook/fill", json={"focuses": ["The problem", "Our solution", "Traction"]}).json()
    assert swapped["emails"][0]["message"].startswith("Finance teams") and swapped["emails"][2]["message"].startswith("40 SaaS")
    # With AI: the room goes in, mapped per focus, and refresh re-reads instead of using the cache
    set_tier(client, "pro")
    out = {"messages": ["We match invoices to usage.", "Teams lose 9 days a month.", "$40bn market, 40 customers."],
           "ask": "We're raising $750k pre-seed.", "strengths": [], "update_example": ""}
    st = stub([out, out])
    client.post("/outreach/playbook/fill", json={})
    client.post("/outreach/playbook/fill", json={})  # cached
    assert len(st.calls) == 1
    sent = json.loads(st.calls[0]["messages"][0]["content"])
    assert sent["data_room"]["problem"].startswith("Finance teams") and sent["focus_sources"]["The problem we solve"] == ["problem"]
    r = client.post("/outreach/playbook/fill", json={"refresh": True}).json()
    assert len(st.calls) == 2 and r["source"] == "data room"
