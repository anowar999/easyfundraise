"""Idempotent investor dataset importer (§22). Re-runnable as the directory and enrichment files grow.

Directory CSV rows upsert on `linkedin`. Enrichment JSONL rows join to the directory by normalised name
(the enrichment `wid` does not index the directory), disambiguated by firm / email domain, and every
changed enrichment is kept as a new `investor_enrichment_versions` row (never overwritten).
"""

import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models import Investor, InvestorEnrichmentVersion, SuppressedInvestor
from .derive import infer_timezone, investor_type, is_decision_maker, location_parts, seed_fit

csv.field_size_limit(10_000_000)


def norm_name(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


def norm_linkedin(url: str) -> str:
    u = (url or "").strip().lower().split("?")[0].rstrip("/")
    u = re.sub(r"^https?://(www\.)?", "", u)
    return f"https://{u}" if u else ""


def _split(s: str, sep: str) -> list[str]:
    return [p.strip() for p in (s or "").split(sep) if p.strip()]


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return "; ".join(_text(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)
    return str(v).strip()


def import_directory(db: Session, path: Path, batch: int = 1000) -> dict:
    suppressed = set(db.scalars(select(SuppressedInvestor.linkedin)))
    by_li: dict[str, dict] = {}
    skipped = 0
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            li = norm_linkedin(r.get("linkedin", ""))
            if not li or li in suppressed or not r.get("name"):
                skipped += 1
                continue
            country, _ = location_parts(r.get("location", ""))
            more = re.sub(r"\D", "", r.get("more_portfolio", "") or "")
            row = dict(
                linkedin=li, name=r["name"].strip(), title=r.get("title", "").strip(),
                company=r.get("company", "").strip(), industries=_split(r.get("industries", ""), ","),
                stages_src=r.get("stages", ""), check_size_src=r.get("check_size", ""),
                location=r.get("location", ""), country=country, timezone=infer_timezone(r.get("location", "")),
                email=r.get("email", "").strip().lower(), x_url=r.get("x", ""), photo_url=r.get("photo_url", ""),
                portfolio_sample=_split(r.get("portfolio_sample", ""), ";"), more_portfolio=int(more or 0),
                investor_type=investor_type("", r.get("title", "")),
            )
            if li in by_li:  # same person under URL variants: merge industry tags
                row["industries"] = sorted(set(by_li[li]["industries"]) | set(row["industries"]))
            by_li[li] = row
    rows = list(by_li.values())
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        stmt = insert(Investor).values(chunk)
        # Directory refresh must not clobber enrichment-derived columns.
        cols = ["name", "title", "company", "industries", "stages_src", "check_size_src", "location", "country",
                "timezone", "email", "x_url", "photo_url", "portfolio_sample", "more_portfolio"]
        stmt = stmt.on_conflict_do_update(index_elements=["linkedin"],
                                          set_={c: stmt.excluded[c] for c in cols} | {"updated_at": datetime.now(UTC)})
        db.execute(stmt)
    db.commit()
    return {"directory_rows": len(rows), "skipped": skipped}


def _pick(cands: list[Investor], rec: dict) -> Investor | None:
    if len(cands) == 1:
        return cands[0]
    firm = norm_name(rec.get("current_firm", ""))
    site = re.sub(r"^https?://(www\.)?", "", (rec.get("firm_website") or "").lower()).split("/")[0]
    for c in cands:
        if firm and (firm in norm_name(c.company) or norm_name(c.company) in firm):
            return c
        if site and c.email.endswith("@" + site):
            return c
    return None


def apply_enrichment(inv: Investor, rec: dict) -> None:
    g = lambda k: _text(rec.get(k))  # noqa: E731
    inv.enriched = True
    inv.enrichment = rec
    inv.current_firm, inv.firm_website, inv.firm_type = g("current_firm"), g("firm_website"), g("firm_type")
    inv.role_at_firm, inv.identity_confidence = g("role_at_firm"), g("identity_confidence").lower()
    inv.active_last_12mo = (g("active_last_12mo") or "unknown").lower()
    inv.leads_rounds = (g("leads_rounds") or "unknown").split()[0].lower()
    inv.instrument_preference = g("instrument_preference") or "unknown"
    inv.focus_sectors, inv.focus_stages = g("focus_sectors"), g("focus_stages")
    inv.geography_focus, inv.typical_check_size = g("geography_focus"), g("typical_check_size")
    inv.investment_thesis, inv.about = g("investment_thesis"), g("about")
    inv.investor_type = investor_type(inv.firm_type, inv.role_at_firm)
    inv.seed_fit = seed_fit(inv.firm_type, inv.focus_stages, inv.role_at_firm)
    inv.is_decision_maker = is_decision_maker(inv.role_at_firm)
    inv.enriched_at = datetime.now(UTC)


def import_enrichment(db: Session, path: Path) -> dict:
    by_name: dict[str, list[Investor]] = defaultdict(list)
    for inv in db.scalars(select(Investor)):
        by_name[norm_name(inv.name)].append(inv)
    latest = {iid: h for iid, h in db.execute(
        select(InvestorEnrichmentVersion.investor_id, InvestorEnrichmentVersion.data_hash)
        .order_by(InvestorEnrichmentVersion.created_at))}
    matched = unmatched = new_versions = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            inv = _pick(by_name.get(norm_name(rec.get("name", "")), []), rec)
            if inv is None:
                unmatched += 1
                continue
            matched += 1
            h = hashlib.sha256(json.dumps(rec, sort_keys=True).encode()).hexdigest()
            if latest.get(inv.id) != h:
                db.add(InvestorEnrichmentVersion(investor_id=inv.id, data=rec, data_hash=h))
                new_versions += 1
            apply_enrichment(inv, rec)
    db.commit()
    return {"enrichment_matched": matched, "enrichment_unmatched": unmatched, "new_versions": new_versions}
