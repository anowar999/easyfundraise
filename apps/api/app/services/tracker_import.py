"""Founder tracker import (§10.6): CSV/XLSX with any layout similar to common founder trackers
(e.g. "Wave | Prio | Investment firm | Investor type | Contact person | Linked In | Can lead | ...").

Flow: parse() -> detect header row + suggest column mapping per sheet -> user confirms mapping ->
rows_to_cards() -> funnel cards (deduped by email / LinkedIn / name+firm, linked to database investors).
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

FIELDS = {
    # card field: header synonyms (lowercased, punctuation stripped)
    "name": ["contact person", "contact", "name", "investor name", "full name", "person", "investor"],
    "firm": ["investment firm", "firm", "fund", "company", "vc name", "organisation", "organization", "vc"],
    "investor_type": ["investor type", "type", "category"],
    "priority": ["prio", "priority", "tier"],
    "status": ["status", "status 10 days rule"],
    "stage": ["stage", "pipeline stage", "funnel stage"],
    "can_lead": ["can lead", "lead", "leads"],
    "ticket_size": ["check size", "check size range", "ticket", "ticket size", "cheque size", "amount"],
    "agreed_size": ["agreed size", "committed", "commitment"],
    "instrument": ["instrument"],
    "contact_method": ["contact method", "channel", "method"],
    "email": ["email", "e mail", "email address"],
    "linkedin": ["linked in", "linkedin", "linkedin url", "linkedin profile"],
    "referrer": ["who can intro", "referrer", "intro by", "introducer", "intro via", "warm intro"],
    "last_contacted": ["last meeting date", "last contacted", "last contact", "message sent", "last touch",
                       "date requested"],
    "next_contact": ["next touch date", "next touch", "next contact", "next contact date", "follow up date"],
    "notes": ["notes", "notes desirability value add focus", "comments", "comment", "description"],
    "next_steps": ["next steps todos", "next steps", "todo", "todos", "action"],
    "tags": ["wave", "tags", "tag", "round"],
}


def _key(h) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(h or "").lower())).strip()


METHODS = {"email", "linkedin", "whatsapp", "sms", "intro", "in person", "phone"}
SYN = {_key(s): f for f, syns in FIELDS.items() for s in syns}


@dataclass
class Sheet:
    name: str
    rows: list[list]  # raw cell values
    header_row: int = 0
    headers: list[str] = field(default_factory=list)
    mapping: dict[int, str] = field(default_factory=dict)  # column index -> card field

    def data_rows(self) -> list[list]:
        return [r for r in self.rows[self.header_row + 1:] if any(_s(c) for c in r)]


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def parse(filename: str, content: bytes) -> list[Sheet]:
    if filename.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheets = [Sheet(ws.title, [list(r) for r in ws.iter_rows(values_only=True)]) for ws in wb.worksheets]
    elif filename.lower().endswith((".csv", ".txt")):
        text = content.decode("utf-8-sig", errors="replace")
        sheets = [Sheet("CSV", [list(r) for r in csv.reader(io.StringIO(text))])]
    else:
        raise ValueError("Upload a .csv or .xlsx file")
    for sh in sheets:
        detect(sh)
    return sheets


def detect(sh: Sheet) -> None:
    """Header row = the row (within the first 20) whose cells match the most known headers."""
    best, best_score = 0, -1
    for i, row in enumerate(sh.rows[:20]):
        score = sum(1 for c in row if _key(c) in SYN)
        if score > best_score:
            best, best_score = i, score
    sh.header_row = best
    hdr = sh.rows[best] if sh.rows else []
    sh.headers = [_s(c) for c in hdr]
    used: set[str] = set()
    for idx, h in enumerate(sh.headers):
        f = SYN.get(_key(h))
        if f and f not in used:
            sh.mapping[idx], used = f, used | {f}
    # Unlabelled columns: infer email / LinkedIn from values
    sample = sh.data_rows()[:30]
    width = max((len(r) for r in sh.rows[best:best + 40]), default=0)
    for idx in range(width):
        if idx in sh.mapping:
            continue
        vals = [_s(r[idx]) for r in sample if idx < len(r) and _s(r[idx])]
        if not vals:
            continue
        if "email" not in used and sum("@" in v and "." in v for v in vals) / len(vals) > 0.6:
            sh.mapping[idx], used = "email", used | {"email"}
        elif "linkedin" not in used and sum("linkedin.com" in v.lower() for v in vals) / len(vals) > 0.6:
            sh.mapping[idx], used = "linkedin", used | {"linkedin"}
        elif "contact_method" not in used and all(_key(v) in METHODS for v in vals):
            sh.mapping[idx], used = "contact_method", used | {"contact_method"}


def score(sh: Sheet) -> int:
    """How usable a sheet is: needs a name column and data rows."""
    if "name" not in sh.mapping.values() and "firm" not in sh.mapping.values():
        return 0
    return len(sh.mapping) * 10 + min(len(sh.data_rows()), 500)


# ---------- value normalisation ----------

def map_stage(v: str) -> int | None:
    s = _key(v)
    if not s:
        return None
    for kw, n in (("payment", 9), ("received", 9), ("signed", 8), ("term sheet", 7), ("ts", 7), ("offer", 7),
                  ("deep dive", 6), ("dd", 6), ("due diligence", 6), ("deck", 5), ("first call", 4),
                  ("call", 4), ("meeting", 4), ("in contact", 3), ("contact", 3), ("intro", 2),
                  ("not started", 1)):
        if re.search(rf"\b{kw}\b", s):
            return n
    m = re.match(r"^(\d)", s)
    return min(int(m.group(1)) + 1, 9) if m else None


def map_status(v: str) -> str:
    s = _key(v)
    if not s:
        return ""
    for st in ("rejection", "ghosting", "inactive", "active"):
        if st in s:
            return st.capitalize()
    if "reject" in s or "pass" in s:
        return "Rejection"
    if "ghost" in s:
        return "Ghosting"
    return "Active"


def map_priority(v: str) -> str:
    s = _s(v).upper()
    if not s:
        return ""
    if s in {"A", "B", "C", "D"}:
        return f"P{'ABCD'.index(s) + 1}"
    m = re.search(r"([1-4])", s)
    return f"P{m.group(1)}" if m else ""


def map_type(v: str) -> str:
    s = _key(v)
    table = [("family", "Family Office"), ("private equity", "PE/Growth"), ("pe", "PE/Growth"),
             ("growth", "PE/Growth"), ("corporate", "Corporate VC"), ("cvc", "Corporate VC"),
             ("angel", "Angel"), ("general partner", "General Partner"), ("gp", "General Partner"),
             ("principal", "Principal/Associate"), ("associate", "Principal/Associate"),
             ("junior", "Junior/Analyst"), ("analyst", "Junior/Analyst"), ("partner", "VC Partner"),
             ("vc", "VC Partner")]
    for kw, out in table:
        if re.search(rf"\b{kw}\b", s):
            return out
    return "Other" if s else ""


def map_bool(v) -> str:
    if isinstance(v, bool):
        return "Yes" if v else "No"
    s = _key(v)
    return {"yes": "Yes", "y": "Yes", "true": "Yes", "no": "No", "n": "No", "false": "No",
            "maybe": "Maybe"}.get(s, "")


def to_date(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) and 20000 < v < 80000:  # Excel serial
        return date(1899, 12, 30) + timedelta(days=int(v))
    s = _s(v)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%d-%m-%Y", "%d %b %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def money(v) -> str:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        n = float(v)
        return f"${n / 1e6:g}M" if n >= 1e6 else f"${n / 1e3:g}K" if n >= 1e3 else f"${n:g}"
    return _s(v)


def contact_method_from(row: dict) -> str:
    v = _key(row.get("contact_method"))
    for m in ("email", "linkedin", "whatsapp", "sms", "intro", "in person"):
        if m in v:
            return {"email": "Email", "linkedin": "LinkedIn", "whatsapp": "WhatsApp", "sms": "SMS",
                    "intro": "Intro", "in person": "In person"}[m]
    return ""


def row_to_card(raw: list, mapping: dict[int, str]) -> dict | None:
    row: dict = {}
    for idx, f in mapping.items():
        if idx < len(raw) and raw[idx] not in (None, ""):
            row[f] = raw[idx]
    name = _s(row.get("name"))
    firm = _s(row.get("firm"))
    if not name and not firm:
        return None
    # "Errol Damelin - Angel" style names
    if not row.get("investor_type") and " - " in name:
        name, _, t = name.partition(" - ")
        row["investor_type"] = t
    notes = [x for x in (_s(row.get("notes")), _s(row.get("next_steps")) and f"Next steps: {_s(row.get('next_steps'))}")
             if x]
    tags = []
    if _s(row.get("tags")):
        t = _s(row["tags"])
        tags.append(f"Wave {t}" if t.isdigit() else t)
    lc = to_date(row.get("last_contacted"))
    email = _s(row.get("email")).lower()
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        email = ""
    return dict(
        name=(name or firm)[:200], firm=firm, investor_type=map_type(row.get("investor_type")),
        priority=map_priority(row.get("priority")),
        status=map_status(row.get("status")), stage=map_stage(_s(row.get("stage"))) or 1,
        can_lead=map_bool(row.get("can_lead")), ticket_size=money(row.get("ticket_size")),
        agreed_size=money(row.get("agreed_size")), instrument=_s(row.get("instrument"))[:16],
        contact_method=contact_method_from(row), email=email, linkedin=_s(row.get("linkedin")),
        referrer=_s(row.get("referrer")),
        last_contacted=lc, next_contact=to_date(row.get("next_contact")), notes=notes, tags=tags,
    )
