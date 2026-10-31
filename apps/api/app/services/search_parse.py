"""Plain-language investor search ("angels actively investing in healthcare, 500k cheques") -> structured filters.

Claude (small model) does the parsing when a key is configured; a keyword parser covers the same ground without it,
so the search box always understands stage, investor type, sector, country, cheque size and activity words.
"""

import logging
import re

from sqlalchemy.orm import Session

from ..models import Workspace
from . import ai

log = logging.getLogger("easyfundraise.search")

TYPES = {"angel": ("angel", "angels", "business angel"), "syndicate": ("syndicate",),
         "vc": ("vc", "vcs", "venture", "fund", "funds"), "family_office": ("family office",),
         "cvc": ("corporate", "cvc", "strategic"), "accelerator": ("accelerator", "incubator")}
STAGES = [("pre-seed", ("pre-seed", "preseed", "pre seed")), ("series a", ("series a", "series-a")),
          ("series b", ("series b", "series-b")), ("seed", ("seed",))]
SECTOR_SYNONYMS = {
    "health": "Health", "healthcare": "Health", "medtech": "Health", "biotech": "Biotech", "pharma": "Biotech",
    "ai": "Artificial Intelligence", "artificial intelligence": "Artificial Intelligence", "ml": "Artificial Intelligence",
    "fintech": "Fintech", "payments": "Fintech", "insurtech": "Fintech", "saas": "SaaS", "b2b": "SaaS",
    "enterprise": "SaaS", "climate": "Climate", "cleantech": "Climate", "energy": "Energy", "edtech": "EdTech",
    "education": "EdTech", "ecommerce": "E-commerce", "e-commerce": "E-commerce", "retail": "Retail",
    "consumer": "Consumer", "cpg": "Consumer Goods", "security": "Cyber", "cyber": "Cyber",
    "cybersecurity": "Cyber", "logistics": "Logistics", "supply chain": "Supply Chain", "proptech": "PropTech",
    "real estate": "Real Estate", "deep tech": "Deep Tech", "hardware": "Hardware", "robotics": "Robotics",
    "gaming": "Gaming", "media": "Media", "mobility": "Mobility", "food": "Food", "agtech": "Ag",
    "crypto": "Crypto", "web3": "Crypto", "blockchain": "Crypto", "marketplace": "Marketplace",
    "hr": "HR", "legal": "Legal", "wellness": "Wellness", "fitness": "Fitness", "travel": "Travel",
}
COUNTRY_ALIASES = {"uk": "United Kingdom", "britain": "United Kingdom", "england": "United Kingdom",
                   "london": "United Kingdom", "us": "United States", "usa": "United States", "america": "United States",
                   "uae": "United Arab Emirates", "dubai": "United Arab Emirates", "berlin": "Germany",
                   "paris": "France", "nyc": "United States", "new york": "United States",
                   "san francisco": "United States", "silicon valley": "United States", "bay area": "United States"}
REGIONS = ("europe", "asia", "africa", "latin america", "middle east", "nordics", "southeast asia")
AMOUNT = re.compile(r"(?:[$£€]\s?)?(\d+(?:\.\d+)?)\s?(k|m|mm|million|thousand)\b", re.I)


def amount_range(text: str) -> tuple[int | None, int | None]:
    """'500k cheques' -> a band around $500K; '100k-250k' -> that range."""
    nums = []
    for n, unit in AMOUNT.findall(text):
        mult = 1_000 if unit.lower() in ("k", "thousand") else 1_000_000
        nums.append(int(float(n) * mult))
    if not nums:
        return None, None
    if len(nums) >= 2:
        return min(nums), max(nums)
    return int(nums[0] * 0.4), int(nums[0] * 2.5)


def keyword_parse(q: str, sectors: list[str], countries: list[str]) -> dict:
    low = f" {q.lower()} "
    out: dict = {"investor_type": [], "stage": "", "sector": [], "country": "", "geo": "", "check_min": None,
                 "check_max": None, "active": False, "leads": False, "q": ""}
    for t, words in TYPES.items():
        if any(re.search(rf"\b{re.escape(w)}\b", low) for w in words):
            out["investor_type"].append(t)
    if "angel" in out["investor_type"] and "syndicate" not in out["investor_type"]:
        out["investor_type"].append("syndicate")
    for stage, words in STAGES:
        if any(w in low for w in words):
            out["stage"] = stage
            break
    for word, frag in SECTOR_SYNONYMS.items():
        if re.search(rf"\b{re.escape(word)}\b", low):
            out["sector"] += [s for s in sectors if frag.lower() in s.lower() and s not in out["sector"]]
    for s in sectors:  # exact sector names typed in full
        if s.lower() in low and s not in out["sector"]:
            out["sector"].append(s)
    for alias, country in COUNTRY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", low):
            out["country"] = country
    for c in sorted(countries, key=len, reverse=True):
        if re.search(rf"\b{re.escape(c.lower())}\b", low):
            out["country"] = c
            break
    if not out["country"]:
        out["geo"] = next((r for r in REGIONS if r in low), "")
    out["check_min"], out["check_max"] = amount_range(q)
    out["active"] = bool(re.search(r"\bactive(ly)?\b|\brecent(ly)?\b|\bthis year\b|\blast 12", low))
    out["leads"] = bool(re.search(r"\blead(s|ing)?\b", low))
    if not any((out["investor_type"], out["stage"], out["sector"], out["country"], out["geo"], out["check_min"],
                out["active"], out["leads"])):
        out["q"] = q.strip()  # nothing structured: plain keyword / name search
    out["sector"] = out["sector"][:6]
    return out


def schema(sectors: list[str]) -> dict:
    return {
        "type": "object", "additionalProperties": False,
        "required": ["investor_type", "stage", "sector", "country", "geo", "check_min", "check_max", "active", "leads",
                     "q", "summary"],
        "properties": {
            "investor_type": {"type": "array", "items": {"type": "string", "enum": [
                "angel", "syndicate", "vc", "cvc", "family_office", "accelerator", "growth", "pe"]}},
            "stage": {"type": "string", "enum": ["", "pre-seed", "seed", "series a", "series b"]},
            "sector": {"type": "array", "items": {"type": "string", "enum": sectors}},
            "country": {"type": "string"}, "geo": {"type": "string"},
            "check_min": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "check_max": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "active": {"type": "boolean"}, "leads": {"type": "boolean"},
            "q": {"type": "string"}, "summary": {"type": "string"},
        },
    }


SYSTEM = """Turn a founder's investor search into filters for an investor database.
- investor_type: who they asked for (angels also include syndicates). Empty when not said.
- stage: the round they mention, if any. sector: every listed sector that matches what they said (health -> all
  health sectors). country: a country name exactly as in the list, or "". geo: a region such as "Europe" only when
  no single country fits.
- check_min/check_max in USD: a single cheque size like "500k" means roughly 200000 to 1250000; a range keeps its ends.
- active: they want investors who invested recently. leads: they want lead investors.
- q: keywords that don't fit any filter (a firm or person name, a niche like "clinical trials"), else "".
- summary: one short line saying what you searched for, e.g. "Angels in health, active, $200K-$1.25M cheques"."""


def parse(db: Session, ws: Workspace, q: str, sectors: list[str], countries: list[str]) -> dict:
    base = keyword_parse(q, sectors, countries)
    if ai.available() and sectors:
        got = ai.small_json(db, ws, SYSTEM, f"Countries in the database: {', '.join(countries[:60])}\n\nSearch: {q}",
                            schema(sectors))
        if got:
            got["country"] = got["country"] if got.get("country") in countries else ""
            got["sector"] = [s for s in got.get("sector", []) if s in sectors][:6]
            return {**base, **got, "engine": "ai"}
    return {**base, "summary": "", "engine": "keywords"}
