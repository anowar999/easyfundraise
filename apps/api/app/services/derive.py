"""Derived investor fields (DATA-01) and timezone inference (TZ-02)."""

import re

EARLY = ("angel", "operator", "syndicate", "seed", "pre-seed", "early-stage", "early stage", "accelerator",
         "venture studio", "micro")
LATE = ("pe ", "pe/", "private equity", "buyout", "growth equity", "wealth", "family office", "hedge",
        "investment bank", "asset manag")
OPS_ROLES = ("cfo", "chief financial", "investor relations", " ir", "head of ir", "talent", "operations",
             "operating", "controller", "accountant", "marketing", "hr ", "human resources", "people",
             "communications", "compliance", "counsel", "legal", "recruit", "office manager", "assistant",
             "board member", "analyst", "platform")
DECISION_ROLES = ("partner", "general partner", "gp", "founder", "managing director", "principal",
                  "angel", "investor", "ceo", "president", "chair", "head of investments", "cio",
                  "chief investment", "venture")


def investor_type(firm_type: str, title: str = "") -> str:
    """Normalised category used for filters and badges (§8.2)."""
    f = f"{firm_type} {title}".lower()
    if not f.strip():
        return "other"
    if "family office" in f:
        return "family_office"
    if "cvc" in f or "corporate" in f:
        return "cvc"
    if "wealth" in f:
        return "wealth_manager"
    if "accelerator" in f or "incubator" in f:
        return "accelerator"
    if "syndicate" in f:
        return "syndicate"
    if re.search(r"\bpe\b|private equity|buyout", f):
        return "pe"
    if "growth" in f and "vc" not in f:
        return "growth"
    if "angel" in f:
        return "angel"
    if "vc" in f or "venture" in f or "fund" in f:
        return "vc"
    return "other"


def is_decision_maker(role: str) -> bool | None:
    r = f" {role.lower()} "
    if not role.strip():
        return None
    if any(k in r for k in ("general partner", "managing partner", "founding partner", "managing director")):
        return True
    if any(k in r for k in OPS_ROLES):
        return False
    return any(k in r for k in DECISION_ROLES)


def seed_fit(firm_type: str, focus_stages: str, role: str) -> bool | None:
    """True only for genuine pre-seed/seed check-writers; None when we have no enrichment."""
    if not (firm_type or focus_stages):
        return None
    ft, st = firm_type.lower(), focus_stages.lower()
    late = any(k in f"{ft} " for k in LATE) or ("not early" in st)
    early = any(k in ft for k in EARLY) or any(k in st for k in ("pre-seed", "seed", "angel", "early"))
    if late and not any(k in ft for k in ("angel", "seed")):
        return False
    if is_decision_maker(role) is False:
        return False
    return early


# --- timezone inference (TZ-02). Coarse but deterministic; admins can override per investor. ---

US_STATES = {
    "Pacific": ("California", "Washington", "Oregon", "Nevada"),
    "Mountain": ("Colorado", "Utah", "Arizona", "New Mexico", "Idaho", "Montana", "Wyoming"),
    "Central": ("Texas", "Illinois", "Minnesota", "Wisconsin", "Missouri", "Tennessee", "Louisiana", "Iowa",
                "Oklahoma", "Kansas", "Nebraska", "Alabama", "Arkansas", "Mississippi"),
}
US_TZ = {"Pacific": "America/Los_Angeles", "Mountain": "America/Denver", "Central": "America/Chicago"}
COUNTRY_TZ = {
    "United States": "America/New_York", "Canada": "America/Toronto", "United Kingdom": "Europe/London",
    "Ireland": "Europe/Dublin", "Germany": "Europe/Berlin", "France": "Europe/Paris", "Spain": "Europe/Madrid",
    "Italy": "Europe/Rome", "Netherlands": "Europe/Amsterdam", "Belgium": "Europe/Brussels",
    "Switzerland": "Europe/Zurich", "Sweden": "Europe/Stockholm", "Denmark": "Europe/Copenhagen",
    "Norway": "Europe/Oslo", "Finland": "Europe/Helsinki", "Portugal": "Europe/Lisbon",
    "Poland": "Europe/Warsaw", "Austria": "Europe/Vienna", "Israel": "Asia/Jerusalem",
    "United Arab Emirates": "Asia/Dubai", "Saudi Arabia": "Asia/Riyadh", "India": "Asia/Kolkata",
    "Singapore": "Asia/Singapore", "Hong Kong": "Asia/Hong_Kong", "China": "Asia/Shanghai",
    "Japan": "Asia/Tokyo", "South Korea": "Asia/Seoul", "Indonesia": "Asia/Jakarta",
    "Australia": "Australia/Sydney", "New Zealand": "Pacific/Auckland", "Brazil": "America/Sao_Paulo",
    "Mexico": "America/Mexico_City", "Nigeria": "Africa/Lagos", "Kenya": "Africa/Nairobi",
    "South Africa": "Africa/Johannesburg", "Egypt": "Africa/Cairo", "Turkey": "Europe/Istanbul",
    "Pakistan": "Asia/Karachi", "Bangladesh": "Asia/Dhaka", "Vietnam": "Asia/Ho_Chi_Minh",
    "Thailand": "Asia/Bangkok", "Malaysia": "Asia/Kuala_Lumpur", "Philippines": "Asia/Manila",
    "Estonia": "Europe/Tallinn", "Luxembourg": "Europe/Luxembourg", "Greece": "Europe/Athens",
    "Czech Republic": "Europe/Prague", "Argentina": "America/Argentina/Buenos_Aires",
    "Chile": "America/Santiago", "Colombia": "America/Bogota",
}


def location_parts(location: str) -> tuple[str, str]:
    parts = [p.strip() for p in location.split(",") if p.strip()]
    country = parts[-1] if parts else ""
    region = parts[-2] if len(parts) >= 2 else ""
    return country, region


def infer_timezone(location: str) -> str:
    country, region = location_parts(location)
    if country == "United States":
        for zone, states in US_STATES.items():
            if region in states:
                return US_TZ[zone]
    return COUNTRY_TZ.get(country, "")
