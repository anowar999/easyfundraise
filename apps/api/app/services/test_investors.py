"""Test investors: real inboxes the founder owns, added so they can try search, reveal and sending end to end.

Everyone sees them in dev/UAT. On live (or a local copy run with EF_LIVE_RULES=true) only the accounts in
EF_TEST_INVESTOR_USERS see them. They never appear on public pages. The records (with their email addresses) live
in a private JSON file, not in this public repo, and are loaded with `python -m app.cli test-investors`.
"""

import json
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Investor
from .dataset_import import apply_enrichment
from .derive import infer_timezone, investor_type, location_parts


def sees(email: str) -> bool:
    return get_settings().sees_test_investors(email)


def conds(email: str) -> list:
    """Extra WHERE conditions for an investor query made by this user."""
    return [] if sees(email) else [~Investor.is_test]


def visible(inv: Investor | None, email: str) -> bool:
    return bool(inv) and not inv.suppressed and (not inv.is_test or sees(email))


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def upsert(db: Session, records: list[dict]) -> list[str]:
    """Create or refresh each test investor (keyed by its LinkedIn, or `test:<name>` when it has none)."""
    done = []
    for r in records:
        name, email = (r.get("name") or "").strip(), (r.get("email") or "").strip().lower()
        if not name or "@" not in email:
            raise ValueError(f"each test investor needs a name and an email: {r!r}")
        li = (r.get("linkedin") or "").strip() or f"test:{_slug(name)}"
        inv = db.scalar(select(Investor).where(Investor.linkedin == li)) or Investor(linkedin=li)
        if inv.id is None:
            db.add(inv)
        loc, title, firm = r.get("location", ""), r.get("title", "Partner"), r.get("firm", "")
        inds = list(r.get("industries") or [])
        inv.name, inv.title, inv.company, inv.email, inv.industries = name, title, firm, email, inds
        inv.location, inv.country, inv.timezone = loc, location_parts(loc)[0], infer_timezone(loc)
        inv.stages_src, inv.check_size_src = r.get("stages", "Pre-Seed; Seed; Series A"), r.get("check_size", "")
        inv.is_test, inv.is_honeypot, inv.suppressed, inv.source = True, False, False, "test"
        types = r.get("types") or ["Angel", "VC"]
        apply_enrichment(inv, {
            "current_firm": firm, "firm_website": r.get("website", ""), "role_at_firm": title,
            "firm_type": r.get("firm_type", "VC fund"), "identity_confidence": "high", "active_last_12mo": "yes",
            "leads_rounds": r.get("leads_rounds", "sometimes"), "instrument_preference": r.get("instruments", "SAFE; equity"),
            "focus_sectors": "; ".join(inds), "focus_stages": r.get("focus_stages", "pre-seed; seed; series A"),
            "geography_focus": r.get("geography", ""), "typical_check_size": r.get("check_size", ""),
            "investment_thesis": r.get("thesis", ""), "about": r.get("about", ""),
            "investor_types": types, "personalization_hooks": r.get("hooks", []),
            "notable_portfolio": r.get("portfolio", []), "sources": ["test investor"],
        })
        inv.investor_type = r.get("investor_type") or investor_type(inv.firm_type, title)
        done.append(f"{name} <{email}>")
    db.commit()
    return done


def load(db: Session, path: Path) -> list[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return upsert(db, data if isinstance(data, list) else data.get("investors", []))
