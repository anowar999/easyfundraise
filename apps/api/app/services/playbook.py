"""The founder's email playbook: what emails 1, 2 and 3 are about, one special line, and a quick update.

- angles: three focus areas, each with the founder's key message ("Problem: 230m people ask ChatGPT health
  questions every week ..."). Every investor gets them in a random order (1-2-3, 3-1-2, 2-3-1 ...), and the AI
  rephrases them for that investor. The angle used is stored on each email's hook ("playbook-2") so the Activity
  tab shows which angle gets replies.
- special_line: one standout line ("Selected by EWOR ...") placed in one of the three emails, picked at random.
- quick_update: a short recent update. New drafts carry it in their first email; "apply to unsent emails" puts it
  in the next email still to go out on every live sequence, replacing an older update.
"""

import json
import random
import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Email, Sequence, Workspace

DEFAULT_LABELS = ("Problem", "Solution or traction", "Market size or momentum")
UPDATE_PREFIX = "Quick update:"
MAX_MESSAGE, MAX_SPECIAL, MAX_UPDATE = 600, 300, 300


def get(ws: Workspace) -> dict:
    raw = ws.email_playbook or {}
    got = list(raw.get("angles") or [])
    angles = []
    for i in range(3):
        a = got[i] if i < len(got) and isinstance(got[i], dict) else {}
        angles.append({"label": (a.get("label") or DEFAULT_LABELS[i]).strip()[:60],
                       "message": (a.get("message") or "").strip()[:MAX_MESSAGE]})
    return {"angles": angles, "special_line": (raw.get("special_line") or "").strip()[:MAX_SPECIAL],
            "shuffle": raw.get("shuffle", True) is not False,
            "quick_update": (raw.get("quick_update") or "").strip()[:MAX_UPDATE],
            "quick_update_at": raw.get("quick_update_at")}


def save(ws: Workspace, pb: dict) -> dict:
    keep = {k: v for k, v in (ws.email_playbook or {}).items() if k == "suggest"}
    ws.email_playbook = {**keep, **pb, "angles": [dict(a) for a in pb["angles"]]}
    return get(ws)


def active(pb: dict) -> bool:
    return any(a["message"] for a in pb["angles"]) or bool(pb["special_line"])


def plan(pb: dict, rng: random.Random | None = None) -> dict[int, dict]:
    """Per step 1-3: {angle_no, label, message, special}. The angles with a message are dealt out in a random
    order (when shuffle is on); the special line lands on one random step."""
    rng = rng or random.Random()
    filled = [i for i, a in enumerate(pb["angles"]) if a["message"]]
    order = rng.sample(filled, len(filled)) if pb["shuffle"] else filled
    special_step = rng.choice([1, 2, 3]) if pb["special_line"] else 0
    out = {}
    for step in (1, 2, 3):
        i = order[step - 1] if step - 1 < len(order) else None
        a = pb["angles"][i] if i is not None else None
        out[step] = {"angle_no": i + 1 if a else 0, "label": a["label"] if a else "", "message": a["message"] if a else "",
                     "special": pb["special_line"] if step == special_step else ""}
    return out


def hook_for(step_plan: dict) -> str | None:
    return f"playbook-{step_plan['angle_no']}" if step_plan.get("angle_no") else None


# ---------------- quick update ----------------

def _split_tail(body: str, signature: str) -> tuple[list[str], list[str]]:
    """Paragraphs of the email body and the tail that stays at the end (opt-out line, signature)."""
    from .outreach import OPT_OUT

    sig = signature.strip()
    text = body
    tail: list[str] = []
    if sig and text.rstrip().endswith(sig):
        text, tail = text.rstrip()[:-len(sig)].rstrip(), [sig]
    paras = [p for p in text.split("\n\n")]
    if paras and paras[-1].strip() == OPT_OUT:
        tail.insert(0, paras.pop())
    return paras, tail


def strip_update(body: str) -> str:
    return "\n\n".join(p for p in body.split("\n\n") if not p.strip().startswith(UPDATE_PREFIX))


def with_update(body: str, update: str, signature: str = "") -> str:
    """Puts "Quick update: ..." just above the opt-out line (and signature), replacing an older one."""
    paras, tail = _split_tail(strip_update(body), signature)
    if update.strip():
        line = update.strip()
        line = line[0].upper() + line[1:]
        line = line if re.search(r"[.!?]$", line) else f"{line}."
        # just before the ask (the last paragraph), after the greeting and the main message
        paras.insert(len(paras) - 1 if len(paras) >= 3 else len(paras), f"{UPDATE_PREFIX} {line}")
    return "\n\n".join(paras + tail)


def unsent(db: Session, ws_id) -> list[Email]:
    """The next email still to go out on every draft or live sequence."""
    rows = db.scalars(select(Sequence).where(Sequence.workspace_id == ws_id,
                                             Sequence.status.in_(["draft", "approved"]))).all()
    out = []
    for s in rows:
        todo = sorted((e for e in s.emails if e.status in ("draft", "scheduled")), key=lambda e: e.step)
        if todo:
            out.append(todo[0])
    return out


def apply_update(db: Session, ws: Workspace, signature: str) -> int:
    """Writes the current quick update into the next unsent email of every sequence (and takes older updates out
    of the later ones). Returns how many emails changed."""
    pb = get(ws)
    n = 0
    rows = db.scalars(select(Sequence).where(Sequence.workspace_id == ws.id,
                                             Sequence.status.in_(["draft", "approved"]))).all()
    for s in rows:
        todo = sorted((e for e in s.emails if e.status in ("draft", "scheduled")), key=lambda e: e.step)
        for k, em in enumerate(todo):
            new = with_update(em.body, pb["quick_update"], signature) if k == 0 else strip_update(em.body)
            if new != em.body:
                em.body, n = new, n + 1
    return n


def set_update(ws: Workspace, text: str) -> dict:
    pb = get(ws)
    pb["quick_update"] = text.strip()[:MAX_UPDATE]
    pb["quick_update_at"] = datetime.now(UTC).isoformat() if pb["quick_update"] else None
    return save(ws, pb)


# ---------------- suggestions from the founder's own deck ----------------

SUGGEST_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["angles", "special_line", "quick_update"],
    "properties": {
        "angles": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                              "required": ["label", "message"],
                                              "properties": {"label": {"type": "string"}, "message": {"type": "string"}}}},
        "special_line": {"type": "string"}, "quick_update": {"type": "string"}},
}

GENERIC = {
    "angles": [{"label": "Problem", "message": "The problem your customers face, with one number that shows how big it is."},
               {"label": "Solution or traction", "message": "How you solve it, and your best proof: users, customers, "
                                                            "growth or a pilot."},
               {"label": "Market size or momentum", "message": "How big the market is, or why now is the moment."}],
    "special_line": "",  # the screens show a neutral hint; only a deck gives a real one
    "quick_update": "",
}


def _from_profile(p) -> dict:
    """No AI: build examples from the company profile fields that came from the deck."""
    if not p or not (p.one_liner or p.traction):
        return {**GENERIC, "source": "generic"}
    name = p.company_name or "We"
    one = (p.one_liner or "").strip().rstrip(".")
    angles = [dict(a) for a in GENERIC["angles"]]
    if one:
        angles[0]["message"] = f"{name}: {one}."
    if p.traction:
        angles[1]["message"] = p.traction.strip().rstrip(".") + "."
    if p.business_model:
        angles[2] = {"label": "Business model", "message": p.business_model.strip().rstrip(".") + "."}
    return {"angles": angles, "special_line": "", "quick_update": "", "source": "profile"}


def suggest(db: Session, ws: Workspace, p) -> dict:
    """Email 1-3 key messages, a special line and a quick-update example, picked by AI from this founder's own deck
    (cached until the profile changes). Falls back to the profile fields, then to neutral wording."""
    from . import ai
    from .agent import email_company, money_talk

    key = f"{p.updated_at.isoformat() if p and p.updated_at else ''}:{len(p.deck_text) if p else 0}"
    cached = (ws.email_playbook or {}).get("suggest") or {}
    if cached.get("key") == key and cached.get("data"):
        return cached["data"]
    data = None
    if p and (p.deck_text or p.one_liner):
        system = (
            f"{ai.SAFETY}\n\nFrom a startup's pitch deck, pick what its cold emails to investors should lead with. "
            "Return exactly 3 angles, each a short focus label (1-3 words, e.g. Problem, Traction, Market size) and a "
            "key message of 1-2 sentences in the founder's voice, using the deck's own strongest specific numbers and "
            "names (never invent any). Angle 1 is the problem, angle 2 the solution or traction, angle 3 the market "
            "size or why now. special_line is the single most impressive credential in the deck (an accelerator, "
            "award, notable customer, partner or team pedigree), one sentence; empty if there is none. quick_update "
            "is an example of a short recent-news line this founder might add, phrased as an example. Never mention "
            "money: no investing, round, raise, ticket, valuation, revenue amounts or currencies.")
        user = json.dumps({"company": email_company(p), "deck_text": (p.deck_text or "")[:20000]}, default=str)
        out = ai.small_json(db, ws, system, user, SUGGEST_SCHEMA, max_tokens=1200)
        if out and len(out.get("angles", [])) >= 3 and not money_talk(
                *[a["message"] for a in out["angles"]], out.get("special_line", "")):
            data = {"angles": [{"label": a["label"].strip()[:60], "message": a["message"].strip()[:MAX_MESSAGE]}
                               for a in out["angles"][:3]],
                    "special_line": out.get("special_line", "").strip()[:MAX_SPECIAL],
                    "quick_update": out.get("quick_update", "").strip()[:MAX_UPDATE], "source": "deck"}
    if data is None:
        data = _from_profile(p)
    if data["source"] != "generic" or not p:
        ws.email_playbook = {**(ws.email_playbook or {}), "suggest": {"key": key, "data": data}}
    return data


def prompts(s: dict) -> list[dict]:
    """Example asks for the outreach agent bar, built from this founder's suggestions. label is the chip text;
    text goes into the box (full, for the founder to edit). send is true for a plain question."""
    def short(t: str, n: int = 60) -> str:
        t = t.strip()
        return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"

    real = s.get("source") != "generic"
    a = s["angles"][0]
    lead = f"Email 1 should be {a['label'].lower()} focused: "
    out = [{"label": lead + (short(a["message"]) if real else "…"), "text": lead + (a["message"] if real else "")}]
    sp = s.get("special_line") or ""
    lead = "Use this line in one email: "
    out.append({"label": lead + (short(sp, 50) if sp else "…"), "text": lead + sp})
    q = (s.get("quick_update") or "").removeprefix("Quick update:").strip()
    q = re.sub(r"^e\.g\.\s*", "", q, flags=re.I)
    lead = "Quick update: "
    deck = s.get("source") == "deck" and q
    out.append({"label": lead + (short(q, 50) if deck else "…"), "text": lead + (q if deck else "")})
    ask = "Who in my outreach list hasn't been sent anything yet?"
    out.append({"label": ask, "text": ask, "send": True})
    return out
