"""Ticket (cheque) size per deal, parsed from free text into numbers the UI can format ("$50k-$2m").

The research text (`typical_check_size`) is preferred (DATA-01); the directory figure (`check_size_src`) is only a
fallback for investors not yet researched, and is flagged as such. Text that does not start with an amount
("unknown (...)", "Large-cap PE equity checks ...") yields nothing rather than a guess."""

import re

_CUR = r"(?:us\$|\$|€|£|usd|eur|gbp)"
_NUM = r"\d+(?:[.,]\d+)*"
_UNIT = r"(?:thousand|million|billion|bn|mm|k|m|b)"
_RE = re.compile(
    rf"^\s*(?P<pre>~|≈|approx(?:imately)?\.?|about|around|up\s+to|under|below|<|over|above|from|>|min(?:imum)?\.?)?\s*"
    rf"(?P<c1>{_CUR})?\s*(?P<n1>{_NUM})\s*(?P<u1>{_UNIT})?(?![a-z])"
    rf"(?:\s*(?:-|–|—|to)\s*(?P<c2>{_CUR})?\s*(?P<n2>{_NUM})\s*(?P<u2>{_UNIT})?(?![a-z]))?"
    rf"\s*(?P<plus>\+)?\s*(?P<c3>usd|eur|gbp|€|£)?",
    re.IGNORECASE,
)
_MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9}
_CODE = {"$": "USD", "us$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP"}


def _num(s: str) -> float:
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):
        return float(s.replace(",", ""))
    return float(s.replace(",", "."))


def parse(raw: str) -> dict | None:
    """'$50K-$2M' -> {min: 50000, max: 2000000, currency: 'USD'}; 'up to $1m' -> {min: None, max: 1e6};
    '$250K+' -> {min: 250000, max: None}. None when the text doesn't lead with an amount."""
    m = _RE.match(raw or "")
    if not m:
        return None
    cur = next((c for c in (m["c1"], m["c2"], m["c3"]) if c), None)
    u1, u2 = (m["u1"] or "").lower(), (m["u2"] or "").lower()
    if not (cur or u1 or u2):
        return None  # a bare number ("2 deals a year") is not a ticket
    try:
        lo = _num(m["n1"]) * _MULT.get(u1 or u2, 1)  # "$1-2M": the unit of the upper bound applies to both
        hi = _num(m["n2"]) * _MULT.get(u2, 1) if m["n2"] else lo
    except ValueError:
        return None
    if lo <= 0 or hi < lo:
        return None
    pre = (m["pre"] or "").lower().replace(" ", "")
    if pre in ("upto", "under", "below", "<"):
        lo = None
    if m["plus"] or pre in ("over", "above", ">", "from", "min", "min.", "minimum", "minimum."):
        hi = None if lo == hi else hi
    return {"min": int(lo) if lo is not None else None, "max": int(hi) if hi is not None else None,
            "currency": _CODE.get((cur or "$").lower(), "USD")}


def fields(*, research: str = "", directory: str = "", tracker: str = "") -> dict:
    """API fields: ticket_min / ticket_max / ticket_currency / ticket_source (tracker | research | directory)."""
    for source, raw in (("tracker", tracker), ("research", research), ("directory", directory)):
        p = parse(raw)
        if p:
            return {"ticket_min": p["min"], "ticket_max": p["max"], "ticket_currency": p["currency"],
                    "ticket_source": source}
        if source == "research" and (raw or "").strip():
            break  # researched but not a clear figure ("unknown ..."): don't fall back to the unreliable tag
    return {"ticket_min": None, "ticket_max": None, "ticket_currency": None, "ticket_source": None}


def for_investor(enriched: bool | None, typical_check_size: str | None, check_size_src: str | None,
                 tracker: str = "") -> dict:
    return fields(tracker=tracker, research=(typical_check_size or "") if enriched else "",
                  directory=check_size_src or "")
