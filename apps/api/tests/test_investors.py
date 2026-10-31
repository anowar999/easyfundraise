from .conftest import set_tier


def test_seed_fit_and_decision_maker_derived(client):
    set_tier(client, "pro")
    items = {x["name"]: x for x in client.get("/investors", params={"sector": "Digital Health & HealthTech"}).json()["items"]}
    assert items["Ada Seed"]["seed_fit"] is True and items["Ada Seed"]["is_decision_maker"] is True
    assert items["Bob Buyout"]["seed_fit"] is False and items["Bob Buyout"]["is_decision_maker"] is False
    assert items["Ada Seed"]["verified_recent_deal"] is True
    # DATA-02: unknown activity is never flagged inactive
    assert items["Bob Buyout"]["verified_recent_deal"] is False


def test_fit_ranks_profile_match_first(client):
    set_tier(client, "pro")
    client.put("/workspace/profile", json={"company_name": "DocAI", "one_liner": "AI triage for clinics",
                                           "sectors": ["Digital Health & HealthTech"], "stage": "seed",
                                           "geography": "Europe"})
    rec = client.get("/investors/recommended").json()["items"]
    assert rec[0]["name"] == "Ada Seed"
    assert rec[0]["fit"]["score"] > rec[-1]["fit"]["score"]
    bob = next(x for x in rec if x["name"] == "Bob Buyout")
    assert any("early-stage" in w for w in bob["fit"]["warnings"])


def test_filters(client):
    set_tier(client, "pro")
    r = client.get("/investors", params={"seed_fit": True, "decision_maker": True}).json()
    assert {x["name"] for x in r["items"]} == {"Ada Seed"}


def test_similar_and_company_lookup(client):
    set_tier(client, "pro")
    ada = next(x for x in client.get("/investors", params={"q": "Ada"}).json()["items"])
    sims = client.get(f"/investors/{ada['id']}/similar").json()["items"]
    assert ada["id"] not in [s["id"] for s in sims]
    found = client.get("/investors/lookup/company", params={"name": "Medibot"}).json()
    assert [x["name"] for x in found["investors"]] == ["Ada Seed"]
    assert found["investors"][0]["evidence"]["round"] == "Seed"


def test_exclusion_blocks_drafts(client):
    set_tier(client, "pro")
    client.post("/workspace/exclusions", json={"kind": "domain", "value": "seedfund.vc"})
    ada = next(x for x in client.get("/investors", params={"q": "Ada"}).json()["items"])
    assert client.get(f"/investors/{ada['id']}").json()["excluded"] is True
    assert client.post("/sequences", json={"investor_id": ada["id"]}).status_code == 409


def test_public_removal_request():
    from fastapi.testclient import TestClient

    from app.main import app

    r = TestClient(app).post("/public/investor-requests", json={"name": "Ada Seed", "email": "ada@seedfund.vc"})
    assert r.status_code == 200
