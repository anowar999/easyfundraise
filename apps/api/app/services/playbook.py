"""The founder's email playbook: how emails 1, 2 and 3 are built, filled by AI from their own deck.

Every email has a fixed shape and one main focus the founder chooses (the AI fills in what it says):
- Email 1: about the investor and the synergy with us, then what we're building (focus 1), then what we're
  looking for (the ask), then a call to action.
- Email 2: focus 2 (by default the problem we solve) instead of the synergy, then what we're building said a
  different way, then what we're looking for and the call to action.
- Email 3: focus 3 (by default market opportunity and traction), then what we're looking for and the call.
- strengths: the founder's credentials ("we've worked together for 5 years", "selected by EWOR"). Each one goes
  into one of the three emails, picked at random per investor.
- update: a round / progress / FOMO update. The next follow-up still to go out on every sequence becomes a short
  update email: the update first, then what we're looking for and the call. Clearing it restores that follow-up.

The AI rewords every email for each investor, keeping the founder's numbers and names exactly.
"""

import json
import random
import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DataRoom, Email, Sequence, Workspace

DEFAULT_FOCUS = ("What we're building", "The problem we solve", "Market opportunity and traction")
STRUCTURE = (
    "About them and the synergy with us, then {focus}, then what we're looking for, then a call to action.",
    "{focus} (instead of the synergy), then what we're building said a different way, then what we're looking for "
    "and the call to action.",
    "{focus}, then what we're looking for and the call to action.",
)
CTA = "Would you be open to a 20-minute call?"
MAX_MESSAGE, MAX_ASK, MAX_STRENGTH, MAX_UPDATE, MAX_STRENGTHS = 600, 400, 300, 400, 4


def _clean(s, n: int) -> str:
    return (s or "").strip()[:n] if isinstance(s, str) else ""


def get(ws: Workspace) -> dict:
    raw = ws.email_playbook or {}
    got = list(raw.get("emails") or raw.get("angles") or [])  # "angles" is the first version's name
    emails = []
    for i in range(3):
        e = got[i] if i < len(got) and isinstance(got[i], dict) else {}
        emails.append({"focus": _clean(e.get("focus") or e.get("label"), 80) or DEFAULT_FOCUS[i],
                       "message": _clean(e.get("message"), MAX_MESSAGE)})
    strengths = [_clean(s, MAX_STRENGTH) for s in (raw.get("strengths") or []) if _clean(s, MAX_STRENGTH)]
    if not strengths and _clean(raw.get("special_line"), MAX_STRENGTH):
        strengths = [_clean(raw.get("special_line"), MAX_STRENGTH)]
    return {"emails": emails, "ask": _clean(raw.get("ask"), MAX_ASK), "strengths": strengths[:MAX_STRENGTHS],
            "update": _clean(raw.get("update") or raw.get("quick_update"), MAX_UPDATE),
            "update_at": raw.get("update_at") or raw.get("quick_update_at"), "saved_at": raw.get("saved_at")}


def save(ws: Workspace, pb: dict) -> dict:
    keep = {k: v for k, v in (ws.email_playbook or {}).items() if k == "suggest"}
    ws.email_playbook = {**keep, "emails": [dict(e) for e in pb["emails"]], "ask": pb["ask"],
                         "strengths": list(pb["strengths"]), "update": pb["update"], "update_at": pb["update_at"],
                         "saved_at": pb.get("saved_at")}
    return get(ws)


def merge(pb: dict, emails: list | None = None, ask: str | None = None, strengths: list | None = None) -> dict:
    """pb with the given parts replaced (validated); used by the API, the agent and the preview."""
    pb = {**pb, "emails": [dict(e) for e in pb["emails"]]}
    for i, e in enumerate((emails or [])[:3]):
        if not isinstance(e, dict):
            continue
        if e.get("focus") is not None:
            pb["emails"][i]["focus"] = _clean(e["focus"], 80) or DEFAULT_FOCUS[i]
        if e.get("message") is not None:
            pb["emails"][i]["message"] = _clean(e["message"], MAX_MESSAGE)
    if ask is not None:
        pb["ask"] = _clean(ask, MAX_ASK)
    if strengths is not None:
        pb["strengths"] = [_clean(s, MAX_STRENGTH) for s in strengths if _clean(s, MAX_STRENGTH)][:MAX_STRENGTHS]
    return pb


def plan(pb: dict, rng: random.Random | None = None) -> dict:
    """Per step 1-3: {focus, message, structure, strengths}, plus the ask. Each strength lands in one random email."""
    rng = rng or random.Random()
    out: dict = {"ask": pb["ask"]}
    for step in (1, 2, 3):
        e = pb["emails"][step - 1]
        out[step] = {"focus": e["focus"], "message": e["message"],
                     "structure": STRUCTURE[step - 1].format(focus=e["focus"].lower()), "strengths": []}
    steps = rng.sample([1, 2, 3], 3)
    for k, s in enumerate(pb["strengths"]):
        out[steps[k % 3]]["strengths"].append(s)
    return out


def hook_for(step: int) -> str:
    return f"playbook-{step}"


# ---------------- round / progress update ----------------

def _first_name(body: str) -> str:
    m = re.match(r"\s*Hi ([^,\n]+),", body or "")
    return m.group(1).strip() if m else "there"


def update_email(fn: str, update: str, ask: str, signature: str = "") -> str:
    from .outreach import OPT_OUT

    line = update.strip()
    line = line[0].upper() + line[1:]
    line = line if re.search(r"[.!?]$", line) else f"{line}."
    body = "\n\n".join(x for x in [f"Hi {fn},", line, ask.strip(), CTA, OPT_OUT] if x)
    return f"{body}\n\n{signature.strip()}" if signature.strip() else body


def _live(db: Session, ws_id) -> list[Sequence]:
    return db.scalars(select(Sequence).where(Sequence.workspace_id == ws_id,
                                             Sequence.status.in_(["draft", "approved"]))).all()


def unsent(db: Session, ws_id) -> list[Email]:
    """The next follow-up still to go out on every draft or live sequence (where an update would go)."""
    out = []
    for s in _live(db, ws_id):
        todo = sorted((e for e in s.emails if e.status in ("draft", "scheduled") and e.step >= 2), key=lambda e: e.step)
        if todo:
            out.append(todo[0])
    return out


def apply_to(emails: list, pb: dict, signature: str) -> int:
    """Turns the first of these unsent follow-ups into the update email (keeping its original to restore) and
    restores the rest. Works on Email rows or draft dicts. Returns how many changed."""
    n = 0
    todo = sorted((e for e in emails if _get(e, "status", "draft") in ("draft", "scheduled") and _get(e, "step") >= 2),
                  key=lambda e: _get(e, "step"))
    for k, em in enumerate(todo):
        original = _get(em, "pre_update_body") or ""
        if k == 0 and pb["update"]:
            new = update_email(_first_name(_get(em, "body")), pb["update"], pb["ask"], signature)
            if new != _get(em, "body"):
                if not original:
                    _set(em, "pre_update_body", _get(em, "body"))
                _set(em, "body", new)
                n += 1
        elif original:
            _set(em, "body", original)
            _set(em, "pre_update_body", None)
            n += 1
    return n


def _get(e, k, default=None):
    return e.get(k, default) if isinstance(e, dict) else getattr(e, k, default)


def _set(e, k, v):
    if isinstance(e, dict):
        e[k] = v
    else:
        setattr(e, k, v)


def apply_update(db: Session, ws: Workspace, signature: str) -> int:
    pb = get(ws)
    return sum(apply_to(list(s.emails), pb, signature) for s in _live(db, ws.id))


def set_update(ws: Workspace, text: str) -> dict:
    pb = get(ws)
    pb["update"] = _clean(text, MAX_UPDATE)
    pb["update_at"] = datetime.now(UTC).isoformat() if pb["update"] else None
    return save(ws, pb)


# ---------------- AI fill from the founder's own deck ----------------

FILL_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["messages", "ask", "strengths", "update_example"],
    "properties": {"messages": {"type": "array", "items": {"type": "string"}}, "ask": {"type": "string"},
                   "strengths": {"type": "array", "items": {"type": "string"}}, "update_example": {"type": "string"}},
}


def profile_ask(p) -> str:
    """'What we're looking for' from the profile's own round fields (no AI)."""
    if not p or not (p.round_size or "").strip() or (p.shareable or {}).get("round_size") is False:
        return ""
    stage = (p.stage or "").strip()
    ask = f"We're raising {p.round_size.strip()}{' ' + stage if stage else ''}."
    lf = (p.looking_for or "").strip().rstrip(".")
    if lf:
        ask += f" We're looking for {lf[0].lower()}{lf[1:]}."
    return ask


ROOM_TYPES = ("problem", "solution", "product", "traction", "market", "why_now", "team", "business_model")
# What each focus draws on in the data room, by the words in it; first match wins.
FOCUS_SECTIONS = [
    (("problem", "pain", "challenge"), ("problem",)),
    (("market", "opportunity"), ("market", "traction")),
    (("traction", "progress", "growth", "customer", "result"), ("traction",)),
    (("build", "solution", "product", "what we do", "how it works"), ("solution", "product")),
    (("why now", "timing"), ("why_now",)),
    (("team", "founder"), ("team",)),
    (("business model", "revenue", "pricing"), ("business_model",)),
]
STEP_SECTIONS = {0: ("solution", "product"), 1: ("problem",), 2: ("market", "traction")}


def room_facts(db: Session, ws_id) -> tuple[dict[str, str], str]:
    """The founder's data room sections as plain text (body plus 'label: value' metrics), and when it changed."""
    room = db.get(DataRoom, ws_id)
    if not room:
        return {}, ""
    out: dict[str, str] = {}
    for sec in (room.content or {}).get("sections") or []:
        t = sec.get("type")
        if t not in ROOM_TYPES:
            continue
        body = re.sub(r"\s+", " ", str(sec.get("body") or "")).strip()
        metrics = "; ".join(f"{m.get('label', '').strip()}: {str(m.get('value', '')).strip()}"
                            for m in sec.get("metrics") or [] if isinstance(m, dict) and str(m.get("value") or "").strip())
        text = " ".join(x for x in (body, f"({metrics})" if metrics and body else metrics) if x)
        if text:
            out[t] = (out.get(t, "") + " " + text).strip()[:1500]
    one = str(((room.content or {}).get("hero") or {}).get("one_liner") or "").strip()
    if one:
        out["one_liner"] = one
    return out, room.updated_at.isoformat() if room.updated_at else ""


def sections_for(focus: str, step: int) -> tuple[str, ...]:
    f = (focus or "").lower()
    for words, secs in FOCUS_SECTIONS:
        if any(w in f for w in words):
            return secs
    return STEP_SECTIONS[step]


def _sentences(text: str, n: int = 2, cap: int = 320) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    out = " ".join(parts[:n]).strip()
    if len(out) > cap:
        out = out[:cap].rsplit(" ", 1)[0].rstrip(",;:") + "."
    return out if not out or out[-1] in ".!?)" else out + "."


def _from_room(room: dict, focuses: list[str], p) -> list[str]:
    msgs = []
    for i, f in enumerate(focuses):
        secs = [room[k] for k in sections_for(f, i) if room.get(k)]
        msgs.append(" ".join(_sentences(x, 2 if len(secs) == 1 else 1) for x in secs))
    return msgs


def _from_profile(p, focuses: list[str], room: dict | None = None) -> dict:
    """No AI: fill from the data room sections for each focus, then the profile fields that came from the deck."""
    room = room or {}
    if not room and (not p or not (p.one_liner or p.traction or p.round_size)):
        return {"emails": [{"focus": f, "message": ""} for f in focuses], "ask": "", "strengths": [],
                "update_example": "", "source": "generic"}
    name = (p.company_name if p else "") or "We"
    one = ((p.one_liner if p else "") or room.get("one_liner", "")).strip().rstrip(".")
    traction = ((p.traction if p else "") or "").strip().rstrip(".")
    by_room = _from_room(room, focuses, p)
    msgs = []
    for i, f in enumerate(focuses):
        secs = sections_for(f, i)
        fallback = (f"{name}: {one}." if one and ("solution" in secs or "product" in secs) else
                    f"{traction}." if traction and "traction" in secs else "")
        msgs.append(by_room[i] or fallback)
    ask = profile_ask(p)
    return {"emails": [{"focus": f, "message": m} for f, m in zip(focuses, msgs, strict=True)], "ask": ask,
            "strengths": [], "update_example": "", "source": "data room" if any(by_room) else "profile"}


def fill(db: Session, ws: Workspace, p, focuses: list[str] | None = None, refresh: bool = False) -> dict:
    """What each email says for the chosen focuses, what we're looking for, the founder's strengths and an
    example update: picked by AI from the founder's own deck (cached per deck and focuses). Falls back to the
    profile fields, then to blanks with neutral hints in the screens."""
    from . import ai
    from .agent import email_company, money_talk

    focuses = [(_clean(f, 80) or DEFAULT_FOCUS[i]) for i, f in enumerate((focuses or list(DEFAULT_FOCUS))[:3])]
    while len(focuses) < 3:
        focuses.append(DEFAULT_FOCUS[len(focuses)])
    room, room_at = room_facts(db, ws.id)
    key = (f"{p.updated_at.isoformat() if p and p.updated_at else ''}:{len(p.deck_text) if p else 0}:{room_at}:"
           f"{'|'.join(focuses)}")
    cached = (ws.email_playbook or {}).get("suggest") or {}
    if not refresh and cached.get("key") == key and cached.get("data"):
        return cached["data"]
    data = None
    if (p and (p.deck_text or p.one_liner)) or room:
        system = (
            f"{ai.SAFETY}\n\nYou set up a founder's cold emails to investors from their own pitch deck. For each of "
            "the 3 email focuses given, write what that part of the email should say: 1-2 sentences in the founder's "
            "voice ('we'), using the strongest specific numbers and names, never invented ones, and nothing "
            "about money except in ask. ask is 'what we're looking for': the raise amount and stage exactly as the "
            "deck states them, plus what kind of partner they want if stated (e.g. 'We're raising $750k pre-seed and "
            "looking for an angel with healthcare distribution.'); empty if the deck gives no amount. Never mention "
            "valuation or an investor's ticket or cheque size. strengths: up to 3 standout credentials from the deck "
            "(team history, accelerator, awards, notable customers, partners, advisors), one sentence each; none if "
            "there are none. update_example: one example round or progress update this founder might send later.\n\n"
            "data_room holds the founder's own, up-to-date sections and wins over the deck when they differ. For "
            "each focus use the section named in focus_sources: a problem focus says the problem (who has it, how "
            "big or costly it is), never the one-liner or the product; a 'what we're building' focus says the "
            "solution and product; a market or traction focus gives the market size and the traction numbers. "
            "Use the deck only for what the data room leaves out.")
        user = json.dumps({"focuses": focuses, "company": email_company(p) if p else {},
                           "focus_sources": {f: list(sections_for(f, i)) for i, f in enumerate(focuses)},
                           "data_room": room, "deck_text": ((p.deck_text if p else "") or "")[:20000]}, default=str)
        out = ai.small_json(db, ws, system, user, FILL_SCHEMA, max_tokens=1500)
        if out and len(out.get("messages", [])) >= 3 and not money_talk(*out["messages"][:3], *out.get("strengths", [])):
            data = {"emails": [{"focus": f, "message": _clean(m, MAX_MESSAGE)}
                               for f, m in zip(focuses, out["messages"][:3], strict=True)],
                    "ask": "" if money_talk(out.get("ask", "")) else _clean(out.get("ask"), MAX_ASK),
                    "strengths": [_clean(s, MAX_STRENGTH) for s in out.get("strengths", []) if s.strip()][:3],
                    "update_example": _clean(out.get("update_example"), MAX_UPDATE),
                    "source": "data room" if room else "deck"}
    if data is None:
        data = _from_profile(p, focuses, room)
    if data["source"] != "generic":
        ws.email_playbook = {**(ws.email_playbook or {}), "suggest": {"key": key, "data": data}}
    return data


def prompts(s: dict) -> list[dict]:
    """Example asks for the outreach agent bar, from this founder's own fill. label is the chip text; text goes in
    the box for the founder to edit. send is true for a plain question."""
    def short(t: str, n: int = 55) -> str:
        t = t.strip()
        return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"

    e2 = s["emails"][1]
    lead = f"Email 2 should focus on {e2['focus'].lower()}: "
    out = [{"label": lead + (short(e2["message"]) or "…"), "text": lead + e2["message"]}]
    st = (s.get("strengths") or [""])[0]
    out.append({"label": "Add a strength: " + (short(st, 50) or "…"), "text": "Add a strength: " + st})
    up = s.get("update_example") or ""
    out.append({"label": "Round update: " + (short(up, 50) or "…"), "text": "Round update: " + up})
    q = "Who in my outreach list hasn't been sent anything yet?"
    out.append({"label": q, "text": q, "send": True})
    return out
