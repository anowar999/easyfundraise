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


def test_chat_tools_preview_then_apply(client, stub):
    set_tier(client, "pro")
    card = client.post("/funnel", json={"name": "Jane Doe", "firm": "Acme VC"}).json()
    tool = NS(content=[NS(type="text", text="Let me check."),
                       NS(type="tool_use", id="tu1", name="propose_move", input={"card_id": "Jane", "stage": 4})],
              stop_reason="tool_use", model="claude-opus-5-5", usage=NS(input_tokens=10, output_tokens=5))
    done = NS(content=[NS(type="text", text="I proposed moving Jane to first call.")], stop_reason="end_turn",
              model="claude-opus-5-5", usage=NS(input_tokens=10, output_tokens=5))
    stub([tool, done])
    m = client.post("/agent/chat", json={"text": "I have a call with Jane on Thursday"}).json()
    assert m["text"].startswith("I proposed")
    act = m["actions"][0]
    assert act["state"] == "pending" and act["type"] == "move"  # no silent writes (AGT-05)
    assert client.get(f"/funnel/{card['id']}").json()["stage"] == 1
    r = client.post(f"/agent/chat/{m['id']}/actions/{act['id']}").json()
    assert r["ok"] and client.get(f"/funnel/{card['id']}").json()["stage"] == 4
    assert client.post(f"/agent/chat/{m['id']}/actions/{act['id']}").status_code == 409


def test_chat_without_ai_handles_reminders_and_memory(client):
    m = client.post("/agent/chat", json={"text": "remind me to email Jane tomorrow"}).json()
    assert m["actions"][0]["type"] == "reminder"
    client.post("/agent/chat", json={"text": "remember we closed a pilot with NHS Trust"})
    assert any("NHS" in x["text"] for x in client.get("/agent/memory").json()["items"])


def test_meeting_brief_template(client):
    set_tier(client, "pro")
    ada = _ada(client)
    card = client.post("/funnel", json={"name": "Ada Seed", "investor_id": ada["id"]}).json()
    b = client.post(f"/agent/briefs/{card['id']}").json()["brief"]
    assert b["engine"] == "template"
    assert "General Partner" in b["content"]["who"]
    assert any("Medibot" in x for x in b["content"]["recent"])
    assert client.get(f"/agent/briefs/{card['id']}").json()["brief"]["id"] == b["id"]
