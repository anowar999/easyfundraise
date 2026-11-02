"""The founder's email playbook: what emails 1, 2 and 3 are about, one special line, and a quick update.

- angles: three focus areas, each with the founder's key message ("Problem: 230m people ask ChatGPT health
  questions every week ..."). Every investor gets them in a random order (1-2-3, 3-1-2, 2-3-1 ...), and the AI
  rephrases them for that investor. The angle used is stored on each email's hook ("playbook-2") so the Activity
  tab shows which angle gets replies.
- special_line: one standout line ("Selected by EWOR ...") placed in one of the three emails, picked at random.
- quick_update: a short recent update. New drafts carry it in their first email; "apply to unsent emails" puts it
  in the next email still to go out on every live sequence, replacing an older update.
"""

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
    ws.email_playbook = {**pb, "angles": [dict(a) for a in pb["angles"]]}
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
