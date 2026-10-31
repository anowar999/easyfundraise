"""§11.2 Investor fit score (0-100 + top reasons) and §11.3 static similarity."""

import re

from ..models import CompanyProfile, Investor

WEIGHTS = dict(sector=30, stage=20, geo=10, check=5, decision_maker=10, active=10, seed_fit=15)

STAGE_WORDS = {
    "pre-seed": ("pre-seed", "preseed", "pre seed", "angel", "idea"),
    "seed": ("seed",),
    "series-a": ("series a", "series-a", "early stage", "early-stage"),
    "series-b": ("series b", "growth"),
}
REGIONS = {
    "europe": ("europe", "united kingdom", "uk", "germany", "france", "netherlands", "spain", "nordic", "eu"),
    "us": ("united states", "us", "usa", "north america", "america"),
    "uk": ("united kingdom", "uk", "london", "europe"),
    "india": ("india", "south asia", "asia"),
    "sea": ("southeast asia", "singapore", "indonesia", "asia", "sea"),
    "global": ("global", "worldwide"),
}


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", s.lower()) if w not in {"and", "the", "tech", "for"}}


def sector_overlap(profile_sectors: list[str], inv: Investor) -> list[str]:
    hits = []
    hay = " ".join([*inv.industries, inv.focus_sectors, inv.investment_thesis]).lower()
    for s in profile_sectors:
        ws = _words(s)
        if s.lower() in hay or (ws and len(ws & _words(hay)) >= max(1, len(ws) // 2)):
            hits.append(s)
    return hits


def fit(inv: Investor, p: CompanyProfile | None) -> dict:
    """Returns {score, reasons[], warnings[]}. Works without a profile (generic early-stage quality)."""
    score, reasons, warnings = 0.0, [], []
    if p and p.sectors:
        hits = sector_overlap(p.sectors, inv)
        if hits:
            score += WEIGHTS["sector"] * min(1, len(hits) / max(1, min(len(p.sectors), 2)))
            reasons.append(f"Invests in {', '.join(hits[:3])}")
    if p and p.stage:
        stages = (inv.focus_stages or inv.stages_src).lower()
        if any(w in stages for w in STAGE_WORDS.get(p.stage, (p.stage,))):
            # Directory stage tags are unreliable (DATA-01): half credit unless enriched.
            score += WEIGHTS["stage"] * (1 if inv.focus_stages else 0.5)
            reasons.append(f"Backs {p.stage} rounds" + ("" if inv.focus_stages else " (unverified tag)"))
    if p and p.geography:
        hay = f"{inv.geography_focus} {inv.location}".lower()
        g = p.geography.lower()
        if any(k in hay for k in REGIONS.get(g, (g,))) or "global" in hay:
            score += WEIGHTS["geo"]
            reasons.append(f"Covers {p.geography}")
    if inv.typical_check_size and "unknown" not in inv.typical_check_size.lower():
        score += WEIGHTS["check"]
    if inv.is_decision_maker:
        score += WEIGHTS["decision_maker"]
        reasons.append("Decision-maker at the firm")
    elif inv.is_decision_maker is False:
        warnings.append("Role looks non-investing (ops / finance / IR)")
    if inv.active_last_12mo == "yes":
        score += WEIGHTS["active"]
        reasons.append("Verified deal in the last 12 months")
    if inv.seed_fit:
        score += WEIGHTS["seed_fit"]
        reasons.append("Genuine early-stage check-writer")
    elif inv.seed_fit is False:
        score -= 25
        warnings.append("Not an early-stage investor (PE / growth / non-investing role)")
    if inv.identity_confidence == "low":
        score -= 15
        warnings.append("Identity needs verification")
    return {"score": max(0, min(100, round(score))), "reasons": reasons[:3], "warnings": warnings}


SIMILAR_SQL = """
select i.id, i.name, i.company, i.current_firm, i.title, i.photo_url, i.investor_type, i.seed_fit,
       i.identity_confidence, i.active_last_12mo, i.location, i.industries,
       cardinality(array(select unnest(i.industries) intersect select unnest(CAST(:inds AS text[])))) as overlap
from investors i
where i.id <> :id and not i.suppressed and not i.is_honeypot and i.industries && CAST(:inds AS text[])
  and coalesce(i.identity_confidence, '') <> 'low'
order by (cardinality(array(select unnest(i.industries) intersect select unnest(CAST(:inds AS text[]))))::float
          / greatest(cardinality(i.industries), 1))
         + case when i.investor_type = :itype then 0.5 else 0 end
         + case when i.seed_fit then 0.3 else 0 end
         + case when i.enriched then 0.2 else 0 end desc
limit :n
"""
