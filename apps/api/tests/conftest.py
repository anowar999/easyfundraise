import os

os.environ.setdefault("EF_DATABASE_URL", "postgresql+psycopg://ef:ef@localhost:5432/easyfundraise_test")
os.environ["EF_ENV"] = "dev"
os.environ["EF_DEV_LOGIN"] = "true"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Investor  # noqa: E402
from app.seed import seed  # noqa: E402
from app.services.dataset_import import apply_enrichment  # noqa: E402

ORIGIN = {"origin": "http://testserver"}


@pytest.fixture(scope="session", autouse=True)
def schema():
    with engine.begin() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
        seed_investors(db)
    yield


def seed_investors(db):
    a = Investor(linkedin="https://linkedin.com/in/ada", name="Ada Seed", title="General Partner", company="Seedcamp-ish",
                 industries=["Digital Health & HealthTech", "Artificial Intelligence"], location="London, England, United Kingdom",
                 timezone="Europe/London", email="ada@seedfund.vc", stages_src="Seed")
    apply_enrichment(a, {"current_firm": "Ada Fund", "firm_type": "seed VC", "role_at_firm": "General Partner",
                         "identity_confidence": "high", "focus_sectors": "digital health; AI", "focus_stages": "pre-seed; seed",
                         "geography_focus": "Europe", "investment_thesis": "Backs clinician-led health AI. Early.",
                         "active_last_12mo": "yes", "notable_portfolio": ["Healthly", "Medibot"],
                         "personalization_hooks": ["Writes about clinical AI safety"], "sources": ["https://example.com/ada"],
                         "recent_investments_12mo": [{"company": "Medibot", "date": "2026-05", "round": "Seed", "role": "lead",
                                                      "source_url": "https://example.com/medibot"}]})
    b = Investor(linkedin="https://linkedin.com/in/bob", name="Bob Buyout", title="CFO", company="Big PE",
                 industries=["Digital Health & HealthTech"], location="New York, New York, United States",
                 timezone="America/New_York", email="bob@bigpe.com")
    apply_enrichment(b, {"current_firm": "Big PE", "firm_type": "PE firm", "role_at_firm": "CFO",
                         "identity_confidence": "high", "focus_stages": "buyout"})
    c = Investor(linkedin="https://linkedin.com/in/cara", name="Cara Angel", title="Angel Investor", company="Self",
                 industries=["Artificial Intelligence", "FinTech"], location="Berlin, Germany", email="cara@example.com")
    hp = Investor(linkedin="https://linkedin.com/in/hp-1", name="Honey Pot", company="Northfield", industries=["FinTech"],
                  email="hp@northfield.vc", is_honeypot=True)
    db.add_all([a, b, c, hp])
    db.commit()


def login(email: str) -> TestClient:
    c = TestClient(app, headers=ORIGIN)
    r = c.post("/auth/dev-login", json={"email": email, "name": email.split("@")[0].title(), "timezone": "Europe/London"})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def client(request):
    return login(f"{request.node.name[:40].replace('[', '').replace(']', '')}@founder.io")


def set_tier(client: TestClient, tier: str):
    with SessionLocal() as db:
        db.execute(text("update workspaces set tier_code=:t where id=:w"), {"t": tier, "w": client.get("/workspace").json()["id"]})
        db.commit()
