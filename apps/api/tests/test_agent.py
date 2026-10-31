"""AI layer with a stub Anthropic client: grounded drafts, fallbacks, chat tools with previewed actions."""

import json
from types import SimpleNamespace as NS

import pytest

from app.services import ai

from .conftest import set_tier


class Stub:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.beta = NS(messages=NS(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        r = self.replies.pop(0)
        if isinstance(r, NS):
            return r
        return NS(content=[NS(type="text", text=json.dumps(r))], stop_reason="end_turn", model=kw["model"],
                  usage=NS(input_tokens=100, output_tokens=50, cache_creation_input_tokens=0))


@pytest.fixture
def stub(monkeypatch):
    holder = {}

    def use(replies):
        holder["s"] = Stub(replies)
        monkeypatch.setattr(ai, "available", lambda: True)
        monkeypatch.setattr(ai, "client", lambda: holder["s"])
        return holder["s"]

    return use


def _ada(client):
    return client.get("/investors", params={"q": "Ada"}).json()["items"][0]


GOOD = {"emails": [
    {"step": 1, "hook": "portfolio-adjacent", "subject": "DocAI and Medibot",
     "body": "Hi Ada,\n\nYou led Medibot's seed and write about clinical AI safety. DocAI triages clinic patients with "
             "clinician oversight.\n\nOpen to 20 minutes next week?", "fact_ids": ["f3", "f5"]},
    {"step": 2, "hook": "insight-first", "subject": "One thing we learned",
     "body": "Hi Ada,\n\nClinics adopt triage when it saves nurses time, not when it is clever. Worth a look at the deck?",
     "fact_ids": ["f2"]},
    {"step": 3, "hook": "ask-for-advice", "subject": "Closing the loop",
     "body": "Hi Ada,\n\nLast note. If it isn't a fit, who should I talk to?", "fact_ids": ["f1"]},
]}


def test_ai_draft_is_grounded_and_routed(client, stub):
    set_tier(client, "pro")
    client.put("/workspace/profile", json={"company_name": "DocAI", "one_liner": "AI triage for clinics",
                                           "sectors": ["Digital Health & HealthTech"]})
    s = stub([GOOD])
    seq = client.post("/sequences", json={"investor_id": _ada(client)["id"]}).json()
    assert seq["engine"] == "claude-opus-5-5"
    call = s.calls[0]
    assert call["output_config"]["format"]["type"] == "json_schema"  # structured output
    assert call["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in call["betas"]
    assert "never invent" in call["system"]
    e1 = seq["emails"][0]
    assert "reply 'no'" in e1["body"] and e1["issues"] == []  # opt-out appended, lint clean
    assert any("Medibot" in f["text"] for f in e1["facts"])  # cited facts come from the fact pack


def test_ai_draft_falls_back_when_lint_fails(client, stub):
    set_tier(client, "pro")
    bad = json.loads(json.dumps(GOOD))
    bad["emails"][0]["body"] = "Hi Ada,\n\nClick here for a guaranteed return!!!"
    stub([bad])
    seq = client.post("/sequences", json={"investor_id": _ada(client)["id"]}).json()
    assert seq["engine"] == "template"


def test_template_tier_never_calls_model(client, stub):
    s = stub([])
    set_tier(client, "trial")
    client.post("/sequences", json={"investor_id": _ada(client)["id"]})
    assert s.calls == []


def test_refusal_falls_back(client, stub):
    set_tier(client, "pro")
    stub([NS(content=[], stop_reason="refusal", model="claude-opus-5-5", usage=NS(input_tokens=1, output_tokens=0))])
    assert client.post("/sequences", json={"investor_id": _ada(client)["id"]}).json()["engine"] == "template"


def test_chat_tools_change_tracker_by_number(client, stub):
    set_tier(client, "pro")
    card = client.post("/funnel", json={"name": "Jane Doe", "firm": "Acme VC"}).json()
    tool = NS(content=[NS(type="text", text="On it."),
                       NS(type="tool_use", id="tu1", name="update_card",
                          input={"card": f"#{card['number']}", "stage": 4, "next_contact": "2026-11-02"})],
              stop_reason="tool_use", model="claude-opus-5-5", usage=NS(input_tokens=10, output_tokens=5))
    done = NS(content=[NS(type="text", text="Moved Jane to first call.")], stop_reason="end_turn",
              model="claude-opus-5-5", usage=NS(input_tokens=10, output_tokens=5))
    stub([tool, done])
    m = client.post("/agent/chat", json={"text": f"I have a call with #{card['number']} on Thursday"}).json()
    assert m["actions"][0]["type"] == "card" and m["actions"][0]["state"] == "applied"
    got = client.get(f"/funnel/{card['id']}").json()
    assert got["stage"] == 4 and str(got["next_contact_date"]) == "2026-11-02"


def test_chat_without_ai_handles_reminders_and_memory(client):
    m = client.post("/agent/chat", json={"text": "remind me to email Jane tomorrow"}).json()
    assert m["actions"][0]["type"] == "reminder"
    client.post("/agent/chat", json={"text": "remember we closed a pilot with NHS Trust"})
    assert any("NHS" in x["text"] for x in client.get("/agent/memory").json()["items"])
    roles = [x["role"] for x in client.get("/agent/chat").json()["items"]]
    assert roles == ["user", "assistant", "user", "assistant"]  # each question shows above its answer


def test_meeting_brief_template(client):
    set_tier(client, "pro")
    ada = _ada(client)
    card = client.post("/funnel", json={"name": "Ada Seed", "investor_id": ada["id"]}).json()
    b = client.post(f"/agent/briefs/{card['id']}").json()["brief"]
    assert b["engine"] == "template"
    assert "General Partner" in b["content"]["who"]
    assert any("Medibot" in x for x in b["content"]["recent"])
    assert client.get(f"/agent/briefs/{card['id']}").json()["brief"]["id"] == b["id"]


def _tool(name, args, tid="t1"):
    return NS(content=[NS(type="tool_use", id=tid, name=name, input=args)], stop_reason="tool_use",
              model="claude-haiku-5-5", usage=NS(input_tokens=10, output_tokens=5))


def _say(text):
    return NS(content=[NS(type="text", text=text)], stop_reason="end_turn", model="claude-haiku-5-5",
              usage=NS(input_tokens=10, output_tokens=5))


def test_raise_agent_works_on_trial_and_changes_settings(client, stub):
    s = stub([_tool("update_profile", {"looking_for": "Angels with clinical networks", "round_size": "$1M"}),
              _tool("update_settings", {"signature": "Sam\nDocAI", "timezone": "Europe/London"}, "t2"),
              _tool("update_data_room_section", {"section": "why_now", "body": "NHS mandates digital triage by 2027."},
                    "t3"),
              _say("Done: profile, signature and your data room's Why now are updated.")])
    m = client.post("/agent/chat", json={"text": "Update my settings: raising $1M from angels with clinical "
                                                 "networks, signature Sam / DocAI, London time, and add why now"}).json()
    assert s.calls[0]["model"] == "claude-haiku-5-5"  # trial plan still gets the agent
    assert {a["type"] for a in m["actions"]} == {"profile", "settings", "data_room"}
    assert all(a["state"] == "applied" for a in m["actions"])
    prof = client.get("/workspace/profile").json()
    assert prof["round_size"] == "$1M" and "clinical" in prof["looking_for"]
    me = client.get("/auth/me").json()
    assert me.get("signature", "Sam\nDocAI") == "Sam\nDocAI"
    secs = {x["id"]: x for x in client.get("/data-room").json()["content"]["sections"]}
    assert secs["why_now"]["body"].startswith("NHS")


def test_agent_email_asks_which_contact_and_never_sends(client, stub, monkeypatch):
    set_tier(client, "pro")
    ada = _ada(client)
    client.post("/funnel", json={"name": "Ada Seed", "investor_id": ada["id"]})
    client.post("/funnel", json={"name": "Ada Lovelace", "firm": "Engines"})
    stub([_tool("find_contact", {"name": "Ada"}), _say("Two Adas: Ada Seed (SeedFund) and Ada Lovelace. Which one?")])
    m = client.post("/agent/chat", json={"text": "Send an email to Ada"}).json()
    assert "Which" in m["text"] and m["actions"] == []
    stub([_tool("propose_email", {"investor_id": ada["id"]}), _say("Tap to draft; you'll confirm before sending.")])
    m = client.post("/agent/chat", json={"text": "Ada Seed"}).json()
    act = m["actions"][0]
    assert act["type"] == "sequence" and act["state"] == "pending"
    monkeypatch.setattr(ai, "available", lambda: False)  # template drafts
    r = client.post(f"/agent/chat/{m['id']}/actions/{act['id']}").json()
    seq = client.get(f"/sequences/{r['sequence_id']}").json()
    assert seq["status"] == "draft" and all(e["status"] == "draft" for e in seq["emails"])


def test_agent_without_ai_answers_common_asks(client):
    m = client.post("/agent/chat", json={"text": "Is my data room complete?"}).json()
    assert "% complete" in m["text"] and any(a["type"] == "link" for a in m["actions"])
    client.post("/funnel", json={"name": "Zed One", "firm": "A"})
    client.post("/funnel", json={"name": "Zed Two", "firm": "B"})
    m = client.post("/agent/chat", json={"text": "send an email to zed"}).json()
    assert m["text"].startswith("Which one?") and "Zed Two" in m["text"]


def test_agent_reads_calendar_meetings(client, stub):
    from datetime import UTC, datetime, timedelta

    card = client.post("/funnel", json={"name": "Jane Doe", "firm": "Acme VC"}).json()
    client.patch(f"/funnel/{card['id']}", json={"call_at": (datetime.now(UTC) + timedelta(days=2)).isoformat()})
    s = stub([_tool("calendar_events", {"raise_only": True}), _say("ok")])
    client.post("/agent/chat", json={"text": "Any investor meetings this week?"})
    assert "isn't connected" in s.calls[1]["messages"][-2]["content"][0]["content"]
    client.get("/gmail/connect", params={"calendar": True}, follow_redirects=False)
    assert client.get("/gmail").json()["calendar"] is True
    s = stub([_tool("calendar_events", {"raise_only": True}), _say("You meet Jane Doe from Acme VC on ...")])
    client.post("/agent/chat", json={"text": "Any investor meetings this week?"})
    result = s.calls[1]["messages"][-2]["content"][0]["content"]
    ev = json.loads(result)
    assert ev[0]["raise_related"] and ev[0]["tracker_card"]["name"] == "Jane Doe"
