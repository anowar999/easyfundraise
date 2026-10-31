"""Server-side entitlements (§6.1): can(workspace, feature) / limit(workspace, metric), usage counters,
and fixed-window rate limits stored in Postgres (ASP-02)."""

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..errors import ApiError
from ..models import Tier, Workspace

# Seed values from spec §6.2 — admin can change them in Admin → Packages.
DEFAULT_TIERS = [
    dict(code="trial", name="Free Trial", price_monthly=0, price_annual=0, sort=0,
         limits=dict(searches_total=3, result_cap=10, reveals_month=0, emails_day=0, sample_drafts=3,
                     workspaces=1, seats=1, trial_days=14),
         features=dict(contacts_visible=False, send=False, ai_engine="template", agent="read-only")),
    dict(code="starter", name="Starter", price_monthly=3900, price_annual=39000, sort=1,
         limits=dict(searches_month=300, reveals_month=150, emails_day=20, workspaces=1, seats=1,
                     ai_tokens_month=400_000),
         features=dict(contacts_visible=True, send=True, ai_engine="template+small", agent="basic")),
    dict(code="pro", name="Pro", price_monthly=9900, price_annual=99000, sort=2,
         limits=dict(searches_month=5000, reveals_month=600, emails_day=20, workspaces=3, seats=3,
                     ai_tokens_month=4_000_000),
         features=dict(contacts_visible=True, send=True, ai_engine="frontier", agent="full", automations=True)),
    dict(code="top", name="Investor Relations", price_monthly=24900, price_annual=249000, sort=3,
         limits=dict(searches_month=5000, reveals_month=1500, emails_day=20, workspaces=10, seats=10,
                     ai_tokens_month=12_000_000),
         features=dict(contacts_visible=True, send=True, ai_engine="frontier+research", agent="full+ir",
                       automations=True, newsletter=True)),
]


def tier(db: Session, ws: Workspace) -> Tier:
    t = db.get(Tier, ws.tier_code)
    if t is None:
        raise ApiError(500, "EF-TIER-001", "Workspace tier is misconfigured")
    return t


def trial_expired(ws: Workspace) -> bool:
    return ws.tier_code == "trial" and ws.trial_ends_at is not None and ws.trial_ends_at < datetime.now(UTC)


def can(db: Session, ws: Workspace, feature: str) -> bool:
    return bool(tier(db, ws).features.get(feature))


def limit(db: Session, ws: Workspace, metric: str) -> int | None:
    v = tier(db, ws).limits.get(metric)
    return None if v is None else int(v)


def _period(metric_period: str, now: datetime) -> str:
    """Named periods ("all" | "month" | "day", UTC) or an explicit key such as a user-timezone date."""
    named = {"all": "all", "month": now.strftime("%Y-%m"), "day": now.strftime("%Y-%m-%d")}
    return named.get(metric_period, metric_period)


def usage(db: Session, ws: Workspace, metric: str, period: str) -> int:
    p = _period(period, datetime.now(UTC))
    return db.execute(
        text("select count from usage_counters where workspace_id=:w and metric=:m and period=:p"),
        {"w": ws.id, "m": metric, "p": p},
    ).scalar() or 0


def consume(db: Session, ws: Workspace, metric: str, period: str, cap: int | None, amount: int = 1) -> int:
    """Atomically increments a usage counter, refusing if it would exceed cap. Returns the new count."""
    p = _period(period, datetime.now(UTC))
    row = db.execute(
        text("""
            insert into usage_counters (workspace_id, metric, period, count) values (:w, :m, :p, :n)
            on conflict (workspace_id, metric, period) do update set count = usage_counters.count + :n
              where cast(:cap as integer) is null or usage_counters.count < :cap
            returning count
        """),
        {"w": ws.id, "m": metric, "p": p, "cap": cap, "n": amount},
    ).first()
    if row is None or (cap is not None and row[0] > cap):
        db.rollback()
        raise ApiError(402, "EF-LIMIT-001", "Plan limit reached",
                       f"Your plan allows {cap} {metric.replace('_', ' ')} per {period}.",
                       {"metric": metric, "limit": cap, "upgrade": True})
    return row[0]


def rate_limit(db: Session, key: str, per: int, window_s: int) -> None:
    now = datetime.now(UTC)
    start = datetime.fromtimestamp(int(now.timestamp()) // window_s * window_s, UTC)
    n = db.execute(
        text("""
            insert into rate_limits (key, window_start, count) values (:k, :s, 1)
            on conflict (key, window_start) do update set count = rate_limits.count + 1
            returning count
        """),
        {"k": key, "s": start},
    ).scalar()
    db.commit()
    if n > per:
        raise ApiError(429, "EF-RATE-001", "Too many requests", "Slow down and try again shortly.",
                       {"retry_after": window_s})
