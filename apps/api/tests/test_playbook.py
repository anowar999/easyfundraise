"""Email playbook: founder's angles for emails 1-3 in a random order per investor, a special line in one email,
quick updates written into unsent emails, and the outreach agent tools."""

import json
import random
from types import SimpleNamespace as NS

from app.services import agent, outreach, playbook

from .conftest import set_tier
from .test_agent import GOOD, _ada, stub  # noqa: F401 - stub is a fixture

PB = {"angles": [
    {"label": "Problem", "message": "230m people ask ChatGPT health questions every week and reach a dead end. "
                                    "DocAI connects them to a real doctor in minutes."},
    {"label": "Traction", "message": "We launch to 1m users with 1,500 doctors, on a model built from 875k consultations."},
    {"label": "Market", "message": "4.6bn people have no access to basic healthcare."}],
    "special_line": "We were selected by EWOR (top 0.1% of founders), 10x more competitive than Y Combinator."}


def _setup(client):
    client.put("/workspace/profile", json={"company_name": "DocAI", "one_liner": "AI triage for clinics",
                                           "sectors": ["Digital Health & HealthTech"]})
    r = client.put("/outreach/playbook", json=PB)
    assert r.status_code == 200, r.text
    return r.json()


def test_counts_are_not_money():
    assert not agent.money_talk(PB["angles"][0]["message"], PB["angles"][1]["message"], PB["angles"][2]["message"])
    assert agent.money_talk("€500k first cheques") and agent.money_talk("a EUR 350K round")


def test_plan_shuffles_angles_and_places_special_line_once():
    pb = {"angles": [{"label": a["label"], "message": a["message"]} for a in PB["angles"]],
          "special_line": PB["special_line"], "shuffle": True, "quick_update": ""}
    orders = set()
    for seed in range(30):
        p = playbook.plan(pb, random.Random(seed))
        orders.add(tuple(p[s]["angle_no"] for s in (1, 2, 3)))
        assert sorted(p[s]["angle_no"] for s in (1, 2, 3)) == [1, 2, 3]
        assert sum(bool(p[s]["special"]) for s in (1, 2, 3)) == 1
    assert len(orders) >= 4  # different investors get different orders
    pb["shuffle"] = False
    assert [playbook.plan(pb)[s]["angle_no"] for s in (1, 2, 3)] == [1, 2, 3]


def test_template_drafts_use_playbook_and_quick_update(client):
    set_tier(client, "pro")
    got = _setup(client)
    assert got["active"] and not got["money_warning"] and got["angles"][2]["label"] == "Market"
    r = client.put("/outreach/quick-update", json={"text": "We just signed our third NHS trust"}).json()
    assert r["quick_update"].startswith("We just signed") and r["changed"] == 0
    seq = client.post("/sequences", json={"investor_id": _ada(client)["id"]}).json()
    emails = seq["emails"]
    assert sorted(e["hook"] for e in emails) == ["playbook-1", "playbook-2", "playbook-3"]
    by_hook = {e["hook"]: e["body"] for e in emails}
    assert "230m people" in by_hook["playbook-1"] and "4.6bn" in by_hook["playbook-3"]
    assert sum("EWOR" in e["body"] for e in emails) == 1
    assert "Quick update: We just signed our third NHS trust." in emails[0]["body"]
    assert all(e["issues"] == [] for e in emails), [e["issues"] for e in emails]
    # A new update replaces the old one in the next unsent email only
    r = client.put("/outreach/quick-update", json={"text": "Pilot live in 4 clinics"}).json()
    assert r["changed"] == 1 and r["unsent"] >= 1
    body = client.get(f"/sequences/{seq['id']}").json()["emails"][0]["body"]
    assert "Pilot live in 4 clinics." in body and "NHS trust" not in body
    assert body.index("Quick update") < body.index("reply 'no'")
    r = client.put("/outreach/quick-update", json={"text": ""}).json()
    assert "Quick update" not in client.get(f"/sequences/{seq['id']}").json()["emails"][0]["body"]


def test_ai_draft_follows_playbook(client, stub):  # noqa: F811
    set_tier(client, "pro")
    _setup(client)
    s = stub([GOOD])
    seq = client.post("/sequences", json={"investor_id": _ada(client)["id"]}).json()
    user = json.loads(s.calls[0]["messages"][0]["content"])
    plan = user["email_plan"]
    assert {plan[k]["label"] for k in plan} == {"Problem", "Traction", "Market"}
    assert sum("special" in plan[k] for k in plan) == 1
    assert "email playbook" in s.calls[0]["system"]
    assert seq["engine"] != "template"
    assert sorted(e["hook"] for e in seq["emails"]) == ["playbook-1", "playbook-2", "playbook-3"]


def test_redraft_unapproved_drafts(client):
    set_tier(client, "pro")
    client.put("/workspace/profile", json={"company_name": "DocAI", "one_liner": "AI triage for clinics"})
    seq = client.post("/sequences", json={"investor_id": _ada(client)["id"]}).json()
    assert not any(e["hook"].startswith("playbook") for e in seq["emails"])
    _setup(client)
    assert client.post("/outreach/playbook/redraft").json()["redrafted"] == 1
    hooks = [e["hook"] for e in client.get(f"/sequences/{seq['id']}").json()["emails"]]
    assert sorted(hooks) == ["playbook-1", "playbook-2", "playbook-3"]


def test_agent_sets_playbook_and_quick_update(client, stub):  # noqa: F811
    set_tier(client, "pro")
    tool = NS(content=[NS(type="tool_use", id="t1", name="set_email_playbook",
                          input={"email1": {"label": "Problem", "message": PB["angles"][0]["message"]},
                                 "special_line": PB["special_line"]}),
                       NS(type="tool_use", id="t2", name="set_quick_update", input={"text": "Signed a 3rd NHS trust"})],
              stop_reason="tool_use", model="claude-opus-5-5", usage=NS(input_tokens=10, output_tokens=5))
    done = NS(content=[NS(type="text", text="Saved.")], stop_reason="end_turn", model="claude-opus-5-5",
              usage=NS(input_tokens=10, output_tokens=5))
    stub([tool, done])
    m = client.post("/agent/chat", json={"text": "Email 1 should be problem focused ..."}).json()
    assert [a["type"] for a in m["actions"]] == ["playbook", "playbook"]
    pb = client.get("/outreach/playbook").json()
    assert pb["angles"][0]["message"].startswith("230m") and "EWOR" in pb["special_line"]
    assert pb["quick_update"] == "Signed a 3rd NHS trust"


def test_agent_without_ai_understands_playbook_lines(client):
    client.post("/agent/chat", json={"text": "Email 2 should be: We launch to 1m users with 1,500 doctors"})
    client.post("/agent/chat", json={"text": "Quick update: We closed a pilot with a London clinic"})
    pb = client.get("/outreach/playbook").json()
    assert pb["angles"][1]["message"] == "We launch to 1m users with 1,500 doctors"
    assert pb["quick_update"] == "We closed a pilot with a London clinic"


def test_lint_ignores_quick_update_words():
    body = "Hi Ada,\n\n" + "word " * 60 + "\n\nOpen to a call?\n\n" + outreach.OPT_OUT
    assert outreach.lint("Hi", body, 3)
    assert not outreach.lint("Hi", playbook.with_update("Hi Ada,\n\nShort.\n\n" + outreach.OPT_OUT, "x " * 40), 3)
