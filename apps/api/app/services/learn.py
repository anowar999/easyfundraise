"""Learning from the founder's own results: which email 1 subject styles and which angles (per email) get replies
and opens. New drafts lean towards what works; the Outreach page suggests updating emails not sent yet."""

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Email, Sequence

MIN_SENT = 5  # per style or angle before it's compared
MIN_TOTAL = 10  # sent emails before anything is concluded
LIFT = 1.3  # the winner must beat the rest by this much

STYLES = [  # (key, label, test on the lower-cased subject)
    ("question", "a question", lambda s: s.rstrip().endswith("?")),
    ("x-firm", "“Company x Firm”", lambda s: " x " in s),
    ("for-firm", "“Company for Firm”", lambda s: " for " in s and " intro for " not in s),
    ("name-first", "their first name first", lambda s: bool(re.match(r"^[a-z][\w'-]*, ", s))),
    ("intro", "“Intro …”", lambda s: s.startswith("intro") or " intro" in s),
    ("number", "a number or metric", lambda s: bool(re.search(r"\d", s))),
]


def style(subject: str) -> str:
    s = re.sub(r"^\s*re:\s*", "", (subject or "").lower()).strip()
    return next((k for k, _, t in STYLES if t(s)), "plain")


LABEL = {k: lbl for k, lbl, _ in STYLES} | {"plain": "a plain statement"}


def _rows(db: Session, ws_id, days: int = 180) -> list[Email]:
    since = datetime.now(UTC) - timedelta(days=days)
    return list(db.scalars(select(Email).join(Sequence, Sequence.id == Email.sequence_id).where(
        Email.workspace_id == ws_id, Email.status == "sent", Email.sent_at >= since)).all())


def _rates(group: list[Email], opens: bool) -> dict:
    n = len(group)
    replied = sum(1 for e in group if e.replied_at and e.reply_kind not in ("bounce", "auto"))
    opened = sum(1 for e in group if e.open_count > 0)
    return {"sent": n, "replied": replied, "reply_rate": replied / n if n else 0,
            "open_rate": (opened / n if n else 0) if opens else None}


def _best(groups: dict[str, list[Email]], opens: bool) -> tuple[str, dict, float] | None:
    """The group that clearly does best: by replies, or by opens when nobody has replied yet."""
    stats = {k: _rates(v, opens) for k, v in groups.items() if len(v) >= MIN_SENT}
    if len(stats) < 2:
        return None
    metric = "reply_rate" if any(s["replied"] for s in stats.values()) else ("open_rate" if opens else None)
    if metric is None:
        return None
    k, top = max(stats.items(), key=lambda kv: kv[1][metric] or 0)
    rest = [s[metric] or 0 for kk, s in stats.items() if kk != k]
    avg = sum(rest) / len(rest)
    if not top[metric] or (avg and top[metric] < avg * LIFT):
        return None
    return k, top, (top[metric] / avg if avg else 0)


def opens_count() -> bool:
    """Opens only mean something when the tracking image is on an address Google's servers can reach."""
    from ..config import get_settings

    base = get_settings().tracking_base_url.lower()
    return not any(h in base for h in ("localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal", "://192.168."))


def insights(db: Session, ws_id, opens: bool | None = None) -> dict:
    opens = opens_count() if opens is None else opens
    rows = _rows(db, ws_id)
    out: dict = {"sent": len(rows), "need": MIN_TOTAL, "enough": len(rows) >= MIN_TOTAL, "findings": [],
                 "prefer": {"subject_style": None, "hooks": {}}}
    if not out["enough"]:
        return out
    firsts: dict[str, list[Email]] = {}
    for e in rows:
        if e.step == 1:
            firsts.setdefault(style(e.subject), []).append(e)
    if win := _best(firsts, opens):
        k, s, lift = win
        out["prefer"]["subject_style"] = k
        out["findings"].append({"kind": "subject", "step": 1, "key": k, **s, "lift": round(lift, 1),
                                "text": f"Email 1 subjects with {LABEL[k]} get {_pct(s)} ({s['sent']} sent)"
                                        + (f", {lift:.1f}x the others" if lift else "")})
    for step in (1, 2, 3):
        hooks: dict[str, list[Email]] = {}
        for e in rows:
            if e.step == step and e.hook:
                hooks.setdefault(e.hook, []).append(e)
        if win := _best(hooks, opens):
            k, s, lift = win
            out["prefer"]["hooks"][step] = k
            out["findings"].append({"kind": "angle", "step": step, "key": k, **s, "lift": round(lift, 1),
                                    "text": f"Email {step} leading with “{_hook(k)}” gets {_pct(s)} ({s['sent']} sent)"})
    return out


def _pct(s: dict) -> str:
    if s["replied"]:
        return f"{round(s['reply_rate'] * 100)}% replies"
    return f"{round((s['open_rate'] or 0) * 100)}% opens"


def _hook(k: str) -> str:
    return k.replace("playbook-", "your email ").replace("-", " ")


def prompt_note(db: Session, ws_id, opens: bool | None = None) -> str:
    """One line for the drafting prompt: what has worked in this founder's outreach so far."""
    i = insights(db, ws_id, opens)
    return " ".join(f["text"] + "." for f in i["findings"])


def prefer_subject(db: Session, ws_id, emails: list[dict], options: list[str], opens: bool | None = None) -> None:
    """Give email 1 a subject in the winning style when there is one (and it isn't already)."""
    k = insights(db, ws_id, opens)["prefer"]["subject_style"]
    if not k:
        return
    for e in emails:
        if e["step"] == 1 and style(e["subject"]) != k:
            pick = next((o for o in options if style(o) == k), None)
            if pick:
                e["subject"] = pick
