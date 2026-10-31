"""§9.1 agent endpoints: chat with previewed actions (AGT-05), memory (AGT-07), meeting briefs (AGT-04),
positioning advice from matches (DECK-02 b-d), feedback (§9.8)."""

import re
import uuid
from collections import Counter

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from ..deps import Ctx, ctx
from ..errors import ApiError, not_found
from ..models import AgentMemory, ChatMessage, CompanyProfile, Feedback, FunnelCard, GmailAccount, Investor, MeetingBrief
from ..services import agent, ai
from ..services.entitlements import rate_limit
from ..services.fit import fit

router = APIRouter(prefix="/agent", tags=["agent"])


def m_out(m: ChatMessage) -> dict:
    return {"id": str(m.id), "role": m.role, "text": m.text, "actions": m.actions, "created_at": m.created_at}


@router.get("/chat")
def history(c: Ctx = Depends(ctx)):
    rows = c.db.scalars(select(ChatMessage).where(ChatMessage.workspace_id == c.ws_id, ChatMessage.user_id == c.user.id)
                        .order_by(ChatMessage.created_at.desc()).limit(60)).all()[::-1]
    from ..services.calendar import connected

    return {"items": [m_out(m) for m in rows], "ai": ai.model_for(c.db, c.workspace, "chat") is not None,
            "calendar": connected(c.db.get(GmailAccount, c.user.id)),
            "agent_name": c.workspace.agent_name}


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/chat")
def send(body: ChatIn, c: Ctx = Depends(ctx)):
    rate_limit(c.db, f"chat:{c.user.id}", 20, 60)
    return m_out(agent.chat(c, body.text))


@router.post("/chat/{mid}/actions/{aid}")
def apply(mid: str, aid: str, c: Ctx = Depends(ctx)):
    c.require_editor()
    m = c.db.get(ChatMessage, uuid.UUID(mid))
    if m is None or m.workspace_id != c.ws_id or m.user_id != c.user.id:
        raise not_found("Message")
    r = agent.apply_action(c, m, aid)
    if not r["ok"]:
        raise ApiError(409, "EF-AGT-001", "That action was already handled")
    return {**r, "message": m_out(m)}


@router.delete("/chat")
def clear(c: Ctx = Depends(ctx)):
    for m in c.db.scalars(select(ChatMessage).where(ChatMessage.workspace_id == c.ws_id, ChatMessage.user_id == c.user.id)):
        c.db.delete(m)
    c.db.commit()
    return {"ok": True}


# ---- memory ----


@router.get("/memory")
def list_memory(c: Ctx = Depends(ctx)):
    rows = c.db.scalars(select(AgentMemory).where(AgentMemory.workspace_id == c.ws_id).order_by(AgentMemory.created_at.desc()))
    return {"items": [{"id": str(m.id), "kind": m.kind, "text": m.text, "source": m.source, "created_at": m.created_at}
                      for m in rows]}


class MemoryIn(BaseModel):
    text: str = Field(min_length=2, max_length=500)
    kind: str = Field("fact", pattern="^(fact|preference|worked|raise)$")


@router.post("/memory")
def add_memory(body: MemoryIn, c: Ctx = Depends(ctx)):
    c.require_editor()
    m = AgentMemory(workspace_id=c.ws_id, kind=body.kind, text=body.text.strip(), source="manual")
    c.db.add(m)
    c.db.commit()
    return {"id": str(m.id)}


@router.delete("/memory/{mid}")
def delete_memory(mid: str, c: Ctx = Depends(ctx)):
    m = c.db.get(AgentMemory, uuid.UUID(mid))
    if m is None or m.workspace_id != c.ws_id:
        raise not_found("Memory")
    c.db.delete(m)
    c.db.commit()
    return {"ok": True}


# ---- meeting briefs ----


def _card(c: Ctx, cid: str) -> FunnelCard:
    card = c.db.get(FunnelCard, uuid.UUID(cid))
    if card is None or card.workspace_id != c.ws_id or card.deleted_at:
        raise not_found("Card")
    return card


@router.get("/briefs/{cid}")
def get_brief(cid: str, c: Ctx = Depends(ctx)):
    card = _card(c, cid)
    b = c.db.scalar(select(MeetingBrief).where(MeetingBrief.card_id == card.id).order_by(MeetingBrief.created_at.desc()))
    return {"brief": {"id": str(b.id), "content": b.content, "engine": b.engine, "created_at": b.created_at} if b else None}


@router.post("/briefs/{cid}")
def make_brief(cid: str, c: Ctx = Depends(ctx)):
    rate_limit(c.db, f"brief:{c.user.id}", 10, 60)
    card = _card(c, cid)
    b = agent.meeting_brief(c.db, c.workspace, card)
    c.db.commit()
    return {"brief": {"id": str(b.id), "content": b.content, "engine": b.engine, "created_at": b.created_at}}


# ---- positioning (DECK-02 b-d) ----

MONEY = re.compile(r"\$?\s?(\d+(?:\.\d+)?)\s?(k|m|mm|million)?", re.I)


def _amount(s: str) -> float | None:
    m = MONEY.search(s or "")
    if not m:
        return None
    v = float(m.group(1))
    unit = (m.group(2) or "").lower()
    return v * (1_000_000 if unit in ("m", "mm", "million") else 1000 if unit == "k" else 1)


@router.get("/positioning")
def positioning(c: Ctx = Depends(ctx)):
    prof = c.db.get(CompanyProfile, c.ws_id)
    if not prof or not prof.sectors:
        return {"needs_profile": True}
    cand = c.db.scalars(select(Investor).where(
        ~Investor.suppressed, ~Investor.is_honeypot, Investor.enriched,
        or_(Investor.industries.overlap(prof.sectors), *[Investor.focus_sectors.ilike(f"%{s}%") for s in prof.sectors]),
    ).limit(800)).all()
    matched = [i for i in cand if fit(i, prof)["score"] >= 40]
    if not matched:
        return {"needs_profile": False, "matches": 0, "advice": ["Not enough enriched matches yet to give advice."]}
    checks = sorted(a for a in (_amount(i.typical_check_size) for i in matched) if a and 1000 <= a <= 50_000_000)
    leads = sum(1 for i in matched if i.leads_rounds == "yes")
    stages = Counter(w for i in matched for w in ("pre-seed", "seed", "series a")
                     if w in (i.focus_stages or "").lower())
    asks = Counter(w for i in matched for w in ("traction", "revenue", "mrr", "team", "market", "pilot", "retention")
                   if w in (i.investment_thesis or "").lower())
    advice = []
    n = len(matched)
    if stages:
        top, cnt = stages.most_common(1)[0]
        advice.append(f"{round(100 * cnt / n)}% of your {n} matched investors say they back {top} rounds.")
    if checks:
        mid = checks[len(checks) // 2]
        advice.append(f"Typical check among matches is about ${mid / 1000:,.0f}K "
                      f"(middle half ${checks[len(checks) // 4] / 1000:,.0f}K to ${checks[3 * len(checks) // 4] / 1000:,.0f}K).")
    advice.append(f"{leads} of {n} matches are known to lead rounds. "
                  + ("Line up a lead first, then fill with followers." if leads < n / 4 else "You have real lead options."))
    gaps = [f"Matched investors often mention {w}; make sure your deck shows it."
            for w, _ in asks.most_common(3) if w not in (prof.traction or "").lower() + (prof.deck_text or "").lower()[:20000]]
    return {"needs_profile": False, "matches": n, "advice": advice, "gaps": gaps[:3],
            "check_sizes": {"p25": checks[len(checks) // 4] if checks else None, "median": checks[len(checks) // 2] if checks else None,
                            "p75": checks[3 * len(checks) // 4] if checks else None},
            "lead_share": round(leads / n, 2)}


class FeedbackIn(BaseModel):
    target: str = Field(pattern="^(email|brief|suggestion|chat)$")
    target_id: str = Field(max_length=64)
    rating: int = Field(ge=-1, le=1)
    reason: str = Field("", max_length=500)


@router.post("/feedback")
def feedback(body: FeedbackIn, c: Ctx = Depends(ctx)):
    c.db.add(Feedback(workspace_id=c.ws_id, user_id=c.user.id, **body.model_dump()))
    c.db.commit()
    return {"ok": True}
