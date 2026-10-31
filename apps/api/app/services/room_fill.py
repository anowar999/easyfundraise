"""Deck -> data room. Uploading a deck drafts the investor page so founders edit instead of starting blank.

Claude (small model) writes each section from the deck text when a key is configured; otherwise slides are matched
to sections by their headings. Only empty sections are filled, so nothing the founder wrote is overwritten.
"""

import re

from sqlalchemy.orm import Session

from ..models import Workspace
from . import ai

# Section id -> words a slide heading uses for it
HEADINGS = {
    "problem": ("problem", "pain", "challenge"),
    "solution": ("solution", "how it works", "our approach"),
    "product": ("product", "demo", "platform", "features"),
    "traction": ("traction", "growth", "milestones", "results", "metrics", "kpis"),
    "market": ("market", "tam", "opportunity", "market size"),
    "why_now": ("why now", "timing"),
    "business_model": ("business model", "revenue model", "pricing", "how we make money", "monetisation",
                       "monetization", "unit economics"),
    "team": ("team", "founders", "leadership", "about us"),
    "ask": ("the ask", "ask", "investment", "fundraise", "the round", "raising", "terms"),
    "use_of_funds": ("use of funds", "use of proceeds", "allocation of funds"),
}
TEXT_SECTIONS = tuple(HEADINGS)
MAX_BODY = 1200


def _clean(s: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", s)).strip()


def keyword_fill(pages: list[str]) -> dict[str, str]:
    """Match each slide to a section by its first few lines; the rest of the slide becomes the section text."""
    out: dict[str, str] = {}
    for page in pages:
        lines = [ln.strip() for ln in page.splitlines() if ln.strip()]
        if not lines:
            continue
        head = " ".join(lines[:3]).lower()
        best = None
        for sid in ("use_of_funds", "why_now", "business_model", *TEXT_SECTIONS):  # specific phrases first
            if any(re.search(rf"\b{re.escape(w)}\b", head) for w in HEADINGS[sid]):
                best = sid
                break
        if not best or best in out:
            continue
        body = "\n".join(lines[1:]) if len(lines) > 1 else ""
        if len(body) >= 20:
            out[best] = _clean(body)[:MAX_BODY]
    return out


SYSTEM = """You turn a startup's pitch deck text into the sections of its investor data room page.
Write each section as a short, plain paragraph (or a few lines) using only facts in the deck. Keep numbers exact.
Leave a section "" when the deck says nothing about it. No hype words, no invented metrics."""


def schema() -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(TEXT_SECTIONS),
            "properties": {k: {"type": "string"} for k in TEXT_SECTIONS}}


def draft(db: Session, ws: Workspace, pages: list[str]) -> tuple[dict[str, str], str]:
    text = "\n\n".join(f"--- Slide {i + 1} ---\n{p}" for i, p in enumerate(pages))[:60_000]
    if ai.available() and text.strip():
        got = ai.small_json(db, ws, SYSTEM, text, schema(), max_tokens=3000)
        if got:
            return {k: _clean(v)[:MAX_BODY] for k, v in got.items() if k in HEADINGS and isinstance(v, str) and v.strip()}, "ai"
    return keyword_fill(pages), "keywords"


def has_content(s: dict) -> bool:
    return bool((s.get("body") or "").strip() or any((m.get("value") or "").strip() for m in s.get("metrics") or [])
                or s.get("people") or s.get("items") or s.get("links"))


def apply(content: dict, drafted: dict[str, str]) -> list[str]:
    """Fill empty sections in place; returns the ids that changed."""
    filled = []
    for s in content.get("sections", []):
        sid = s.get("id")
        if sid in drafted and not (s.get("body") or "").strip():
            s["body"] = drafted[sid]
            filled.append(sid)
    return filled


# What a complete investor page has; weights add to 100
CHECKLIST = [("hero", "Company and one-liner", 10), ("problem", "Problem", 9), ("solution", "Solution", 9),
             ("product", "Product and demo link", 9), ("traction", "Traction", 10), ("market", "Market opportunity", 8),
             ("why_now", "Why now", 6), ("business_model", "Business model", 8), ("team", "Team", 10),
             ("ask", "The ask", 9), ("use_of_funds", "Use of funds", 7), ("faq", "FAQ", 5)]


def completeness(content: dict, docs: int = 0) -> dict:
    by_id = {s.get("id"): s for s in content.get("sections", [])}
    hero = content.get("hero", {})
    done, missing = 0, []
    for sid, label, w in CHECKLIST:
        if sid == "hero":
            ok = bool((hero.get("title") or "").strip() and (hero.get("one_liner") or "").strip())
        elif sid == "product":
            s = by_id.get(sid) or {}
            ok = bool((s.get("body") or "").strip()) and bool(s.get("links"))
        elif sid == "team":
            ok = bool((by_id.get(sid) or {}).get("people"))
        elif sid == "faq":
            ok = bool((by_id.get(sid) or {}).get("items"))
        else:
            ok = has_content(by_id.get(sid) or {})
        if ok:
            done += w
        else:
            missing.append({"id": sid, "label": label})
    return {"pct": done, "missing": missing, "has_docs": docs > 0}
