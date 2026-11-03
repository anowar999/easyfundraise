"""The Outreach Agent can work the whole outreach page: results, reading and rewriting one investor's emails,
redrafting, pausing, and offering stop / resume / send all (which the founder confirms)."""

from types import SimpleNamespace as NS

from .conftest import set_tier
from .test_agent import _ada, stub  # noqa: F401 - stub is a fixture


def _turn(*uses):
    return NS(content=[NS(type="tool_use", id=f"t{i}", name=n, input=a) for i, (n, a) in enumerate(uses)],
              stop_reason="tool_use", model="claude-opus-5-5", usage=NS(input_tokens=10, output_tokens=5))


DONE = NS(content=[NS(type="text", text="Done.")], stop_reason="end_turn", model="claude-opus-5-5",
          usage=NS(input_tokens=10, output_tokens=5))


def test_agent_rewrites_reads_and_stops_a_sequence(client, stub):  # noqa: F811
    set_tier(client, "pro")
    seq = client.post("/sequences", json={"investor_id": _ada(client)["id"]}).json()
    stub([_turn(("edit_outreach_email", {"sequence": "Ada", "step": 2, "subject": "A new angle"}),
                ("get_outreach_stats", {}), ("propose_stop_sequence", {"sequence": "Ada"})), DONE])
    m = client.post("/agent/chat", json={"text": "Change Ada's second subject, how am I doing, and stop Ada"}).json()
    assert [a["type"] for a in m["actions"]] == ["outreach", "stop_sequence"]
    assert client.get(f"/sequences/{seq['id']}").json()["emails"][1]["subject"] == "A new angle"
    assert client.get(f"/sequences/{seq['id']}").json()["status"] == "draft"  # stop waits for the tap
    stop = m["actions"][1]
    assert client.post(f"/agent/chat/{m['id']}/actions/{stop['id']}").status_code == 200
    assert client.get(f"/sequences/{seq['id']}").json()["status"] == "stopped"


def test_agent_pauses_and_offers_send_all_without_ai(client):
    client.get("/gmail/connect", follow_redirects=False)  # fake mailbox in tests
    m = client.post("/agent/chat", json={"text": "Pause sending for now"}).json()
    assert m["actions"][0]["type"] == "outreach" and client.get("/gmail").json()["paused_until"]
    m = client.post("/agent/chat", json={"text": "Send all founders"}).json()
    assert m["actions"][0]["href"] == "/app/outreach?send_all=1"  # a button to the confirm screen, never a send
