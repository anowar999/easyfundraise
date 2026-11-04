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
    scores = [s["fit"]["score"] for s in sims]
    assert scores == sorted(scores, reverse=True)  # best match first
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


def test_facets_hide_empty_options(client):
    f = client.get("/investors/facets").json()
    assert all(x["count"] > 0 for x in f["stages"] + f["investor_types"] + f["sectors"])
    assert "series b" not in [s["value"] for s in f["stages"]]  # no fixture investor backs Series B


def test_keyword_search_parse():
    from app.services.search_parse import keyword_parse

    sectors = ["Digital Health & HealthTech", "Healthcare & Biotech", "FinTech", "SaaS & Enterprise"]
    out = keyword_parse("angels actively investing in healthcare in the UK, 500k cheques", sectors,
                        ["United Kingdom", "Germany"])
    assert out["investor_type"] == ["angel", "syndicate"]
    assert set(out["sector"]) == {"Digital Health & HealthTech", "Healthcare & Biotech"}
    assert out["country"] == "United Kingdom" and out["active"] is True
    assert out["check_min"] == 200_000 and out["check_max"] == 1_250_000
    assert keyword_parse("Sequoia", sectors, [])["q"] == "Sequoia"


def test_ai_search_endpoint_falls_back_to_keywords(client):
    r = client.post("/investors/ai-search", json={"q": "seed VCs in digital health"}).json()
    assert r["engine"] == "keywords" and r["stage"] == "seed" and "vc" in r["investor_type"]


def test_shortlist_then_tracker(client):
    ada = next(x for x in client.get("/investors").json()["items"] if x["name"] == "Ada Seed")
    assert client.put(f"/shortlist/{ada['id']}").json()["count"] == 1
    items = client.get("/shortlist").json()["items"]
    assert items[0]["id"] == ada["id"] and items[0]["in_shortlist"]
    assert "email" not in items[0]  # list-safe card
    assert client.post("/shortlist/to-tracker", json={"investor_ids": [ada["id"]]}).json() == {"added": 1, "count": 0}
    assert any(c["investor_id"] == ada["id"] for c in client.get("/funnel").json()["items"])


def test_research_without_key_is_explained(client):
    ada = next(x for x in client.get("/investors").json()["items"] if x["name"] == "Ada Seed")
    assert client.get(f"/investors/{ada['id']}/research").json() == {"research": None, "available": False}
    r = client.post(f"/investors/{ada['id']}/research")
    assert r.status_code == 503 and r.json()["code"] == "EF-AI-010"


def test_cheque_size_filter(client):
    from sqlalchemy import text

    from app.db import SessionLocal

    with SessionLocal() as db:
        db.execute(text("update investors set check_size_src = '$500K' where name = 'Ada Seed'"))
        db.commit()
    names = [x["name"] for x in client.get("/investors", params={"check_min": 200000, "check_max": 1250000}).json()["items"]]
    assert "Ada Seed" in names
    names = [x["name"] for x in client.get("/investors", params={"check_min": 2000000}).json()["items"]]
    assert "Ada Seed" not in names


def test_search_pages_ten_at_a_time_and_trial_stops_at_cap(client):
    from app.db import SessionLocal
    from app.models import Investor

    with SessionLocal() as db:
        for i in range(30):
            db.add(Investor(name=f"Pager Person {i:02d}", linkedin=f"https://linkedin.com/in/pager{i}", investor_type="angel", source="test", industries=["Paging"]))
        db.commit()
    r1 = client.get("/investors", params={"sector": "Paging"}).json()
    assert r1["page_size"] == 10 and len(r1["items"]) == 10 and r1["total"] == 25 and r1["all_total"] == 30
    r3 = client.get("/investors", params={"sector": "Paging", "page": 3}).json()
    assert len(r3["items"]) == 5  # trial cap is 25
    assert client.get("/investors", params={"sector": "Paging", "page": 4}).status_code == 402
    assert {x["id"] for x in r1["items"]}.isdisjoint({x["id"] for x in r3["items"]})


def test_add_to_outreach_from_list_marks_the_row(client):
    set_tier(client, "pro")
    ada = next(x for x in client.get("/investors", params={"q": "Ada"}).json()["items"])
    assert ada["in_outreach"] is False
    assert client.post("/sequences", json={"investor_id": ada["id"]}).status_code == 200
    again = next(x for x in client.get("/investors", params={"q": "Ada"}).json()["items"])
    assert again["in_outreach"] is True and again["in_funnel"] is False


def test_ticket_size_and_type_on_lists(client):
    from sqlalchemy import text

    from app.db import SessionLocal
    from app.services.ticket import parse

    assert parse("$50K-$2M") == {"min": 50_000, "max": 2_000_000, "currency": "USD"}
    assert parse("up to €1m") == {"min": None, "max": 1_000_000, "currency": "EUR"}
    assert parse("$250K+")["max"] is None and parse("unknown (Round Funded lists $2M)") is None
    with SessionLocal() as db:
        db.execute(text("update investors set typical_check_size = '$50K-$2M (firm site)', check_size_src = '$500K' "
                        "where name = 'Ada Seed'"))
        db.execute(text("update investors set typical_check_size = 'unknown', check_size_src = '$2M' "
                        "where name = 'Bob Buyout'"))
        db.commit()
    items = {x["name"]: x for x in client.get("/investors").json()["items"]}
    ada, bob = items["Ada Seed"], items["Bob Buyout"]
    assert (ada["ticket_min"], ada["ticket_max"], ada["ticket_currency"], ada["ticket_source"]) == (
        50_000, 2_000_000, "USD", "research")
    assert ada["investor_type"] and ada["investor_type_label"]
    assert bob["ticket_min"] is None and bob["ticket_source"] is None  # researched as unknown: no unreliable fallback
    client.put(f"/shortlist/{ada['id']}")
    assert client.get("/shortlist").json()["items"][0]["ticket_max"] == 2_000_000
    client.post("/funnel", json={"investor_id": ada["id"]})
    card = next(c for c in client.get("/funnel").json()["items"] if c["investor_id"] == ada["id"])
    assert card["investor_type"] and (card["ticket_min"], card["ticket_source"]) == (50_000, "research")
    client.patch(f"/funnel/{card['id']}", json={"ticket_size": "$100k"})
    card = client.get(f"/funnel/{card['id']}").json()
    assert (card["ticket_min"], card["ticket_max"], card["ticket_source"]) == (100_000, 100_000, "tracker")


def test_recently_viewed_profiles(client):
    assert client.get("/investors/recent").json() == {"items": []}
    items = client.get("/investors").json()["items"]
    a, b = items[0], items[1]
    for x in (a, b, a):
        client.get(f"/investors/{x['id']}")
    got = client.get("/investors/recent").json()["items"]
    assert [x["id"] for x in got] == [a["id"], b["id"]]  # newest first, one each
    assert got[0]["name"] == a["name"] and "viewed_at" in got[0]
