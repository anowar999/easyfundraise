"""Public investor-stats endpoints behind the SEO investor-list pages: aggregates only, never individuals."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_index_counts_segments():
    r = client.get("/public/investor-stats/index")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert set(body["countries"]) == {"all", "angel", "vc", "seed", "pre-seed"}
    assert sum(body["sectors"]["seed"].values()) >= 1


def test_stats_are_aggregates_without_names():
    r = client.get("/public/investor-stats", params={"segment": "seed"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert any(f["count"] >= 1 for f in body["sectors"])
    assert {"countries", "sectors", "firms", "leads", "active_last_12mo"} <= set(body)
    text = r.text
    assert "Ada Seed" not in text and "ada@seedfund.vc" not in text and "linkedin" not in text


def test_unknown_segment_404():
    assert client.get("/public/investor-stats", params={"segment": "nope"}).status_code == 404
