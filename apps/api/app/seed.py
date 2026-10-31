"""Seed reference data (tiers, default config). Idempotent: never overwrites admin edits."""

from sqlalchemy.orm import Session

from .models import ConfigKV, Tier
from .services.entitlements import DEFAULT_TIERS, PREVIOUS_LIMITS

DEFAULT_CONFIG = {
    "sending": {"daily_cap": 20, "warn_at_pct": 80, "pace_seconds": [45, 180], "per_domain_daily_cap": 3,
                # send safety (see mailer.SAFETY): a global stop, a burst limit per mailbox, recipients per email
                "paused": False, "burst_max": 25, "burst_window_minutes": 10, "burst_pause_minutes": 60,
                "max_recipients": 10},
    "send_window": {"days": ["Tue", "Wed", "Thu"], "slots": [["08:30", "11:30"], ["13:30", "16:30"]]},
    "sequence": {"days": {"1": 0, "2": 4, "3": 10}, "max_words": {"1": 120, "2": 80, "3": 60}, "subject_max_words": 7},
    "fit_weights": {"sector": 30, "stage": 20, "geo": 10, "check": 5, "decision_maker": 10, "active": 10, "seed_fit": 15},
    "feature_flags": {"sending": False, "tracking": False, "agent_chat": False},
}


def seed(db: Session) -> None:
    for t in DEFAULT_TIERS:
        row = db.get(Tier, t["code"])
        if row is None:
            db.add(Tier(**t))
        elif row.limits == PREVIOUS_LIMITS.get(t["code"]):  # never edited by an admin: move to the new defaults
            row.limits = dict(t["limits"])
    for k, v in DEFAULT_CONFIG.items():
        if db.get(ConfigKV, k) is None:
            db.add(ConfigKV(key=k, value=v))
    db.commit()
