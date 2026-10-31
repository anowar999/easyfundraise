"""Workspace settings: usage/plan, Company Profile + deck upload (DECK-01), agent instructions (AGT-01),
exclusion list (SEQ-06), user settings (timezone, signature)."""

import io
import json
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy import text as sql_text

from ..deps import Ctx, ctx
from ..errors import ApiError
from ..models import AgentInstruction, CompanyProfile, Exclusion, Tier
from ..services import ai
from ..services.entitlements import admin_unlocked, tier, trial_expired, usage
from ..services.mailer import sent_metric, user_day

router = APIRouter(prefix="/workspace", tags=["workspace"])

SECTOR_KEYWORDS = {
    "Artificial Intelligence": ("ai ", "artificial intelligence", "machine learning", "llm", "genai"),
    "Digital Health & HealthTech": ("digital health", "healthtech", "telehealth", "patient", "clinic", "doctor"),
    "Healthcare & Biotech": ("biotech", "therapeutic", "drug", "pharma", "medtech"),
    "FinTech": ("fintech", "payments", "banking", "lending", "insurance"),
    "SaaS & Enterprise": ("saas", "b2b", "enterprise", "subscription software"),
    "Climate & Energy": ("climate", "carbon", "energy", "solar", "battery"),
    "EdTech": ("edtech", "education", "learning platform", "students"),
    "E-commerce & Retail": ("e-commerce", "ecommerce", "retail", "d2c", "marketplace"),
    "Consumer Goods (CPG)": ("cpg", "consumer goods", "beverage", "food brand"),
    "Cybersecurity": ("security", "cyber"),
    "Supply Chain & Logistics": ("logistics", "supply chain", "freight", "delivery"),
    "Wellness & Fitness": ("wellness", "fitness", "mental health", "longevity"),
}
STAGE_KEYWORDS = [("series-a", ("series a",)), ("pre-seed", ("pre-seed", "preseed", "pre seed")),
                  ("seed", ("seed",))]


@router.get("")
def get_workspace(c: Ctx = Depends(ctx)):
    t = tier(c.db, c.workspace)
    return {
        "id": str(c.ws_id), "name": c.workspace.name, "agent_name": c.workspace.agent_name, "role": c.role,
        "tier": {"code": t.code, "name": t.name, "limits": t.limits, "features": t.features},
        "trial_ends_at": c.workspace.trial_ends_at, "trial_expired": trial_expired(c.workspace),
        "admin_unlocked": admin_unlocked(c.db, c.workspace),
        "tracking_enabled": c.workspace.tracking_enabled, "consent_level": c.workspace.consent_level,
        "automations": {k: (c.workspace.automations or {}).get(k, True) for k in AUTOMATIONS},
        "ai": ai.model_for(c.db, c.workspace, "draft") is not None,
        "ai_tokens_month": usage(c.db, c.workspace, "ai_tokens", "month"),
        "usage": {
            "searches_total": usage(c.db, c.workspace, "searches", "all"),
            "searches_month": usage(c.db, c.workspace, "searches", "month"),
            "reveals_month": usage(c.db, c.workspace, "reveals", "month"),
            "emails_today": usage(c.db, c.workspace, sent_metric(c.user.id), user_day(c.user, datetime.now(UTC))),
        },
    }


AUTOMATIONS = ("positive_reply", "rejection_suggestion", "ghosting_suggestion", "call_brief")


class WorkspacePatch(BaseModel):
    name: str | None = Field(None, max_length=200)
    agent_name: str | None = Field(None, max_length=60)
    tracking_enabled: bool | None = None
    consent_level: str | None = Field(None, pattern="^(approved_sequences|ask_every_send)$")
    automations: dict[str, bool] | None = None


@router.patch("")
def patch_workspace(body: WorkspacePatch, c: Ctx = Depends(ctx)):
    c.require_editor()
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "automations":
            v = {**(c.workspace.automations or {}), **{a: bool(x) for a, x in v.items() if a in AUTOMATIONS}}
        setattr(c.workspace, k, v.strip() if isinstance(v, str) else v)
    c.audit("workspace.update", str(c.ws_id), after=body.model_dump(exclude_none=True))
    c.db.commit()
    return {"ok": True}


@router.get("/tiers")
def list_tiers(c: Ctx = Depends(ctx)):
    rows = c.db.scalars(select(Tier).where(Tier.visible).order_by(Tier.sort))
    return [{"code": t.code, "name": t.name, "price_monthly": t.price_monthly, "price_annual": t.price_annual,
             "limits": t.limits, "features": t.features} for t in rows]


# ---------- Company profile ----------

class ProfileIn(BaseModel):
    company_name: str = Field("", max_length=200)
    one_liner: str = Field("", max_length=500)
    sectors: list[str] = Field(default_factory=list, max_length=10)
    stage: str = Field("", max_length=32)
    geography: str = Field("", max_length=200)
    round_size: str = Field("", max_length=100)
    instrument: str = Field("", max_length=32)
    traction: str = Field("", max_length=500)
    business_model: str = Field("", max_length=500)
    investor_types: list[str] = Field(default_factory=list, max_length=8)
    looking_for: str = Field("", max_length=1000)
    shareable: dict[str, bool] = Field(default_factory=dict)


def _profile(c: Ctx) -> CompanyProfile:
    p = c.db.get(CompanyProfile, c.ws_id)
    if p is None:
        p = CompanyProfile(workspace_id=c.ws_id, sectors=[], shareable={})
        c.db.add(p)
        c.db.flush()
    return p


def _profile_out(p: CompanyProfile) -> dict:
    return {k: getattr(p, k) for k in ("company_name", "one_liner", "sectors", "stage", "geography", "round_size",
                                       "instrument", "traction", "business_model", "investor_types", "looking_for",
                                       "shareable", "deck_filename")} | {"complete": profile_complete(p)}


def profile_complete(p: CompanyProfile | None) -> bool:
    """Enough to match investors and personalise emails: what they do, their sector and the round."""
    return bool(p and p.sectors and (p.one_liner or p.deck_text) and (p.stage or p.round_size))


@router.get("/profile")
def get_profile(c: Ctx = Depends(ctx)):
    p = _profile(c)
    c.db.commit()
    return _profile_out(p)


@router.put("/profile")
def put_profile(body: ProfileIn, c: Ctx = Depends(ctx)):
    c.require_editor()
    p = _profile(c)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    c.db.commit()
    return _profile_out(p)


def extract_profile(text: str) -> dict:
    low = f" {text.lower()} "
    sectors = [s for s, kws in SECTOR_KEYWORDS.items() if any(k in low for k in kws)]
    stage = next((s for s, kws in STAGE_KEYWORDS if any(k in low for k in kws)), "")
    m = re.search(r"rais(?:e|ing)\s+(?:a\s+)?(?:\w+\s+){0,3}?(\$\s?\d+(?:\.\d+)?\s?(?:k|m|mm|million)?)", low)
    traction = re.search(r"([^.\n]*(?:mrr|arr|revenue|users|customers|patients|consultations)[^.\n]*)", text, re.I)
    first = next((ln.strip() for ln in text.splitlines() if len(ln.strip()) > 25), "")
    return {"sectors": sectors[:5], "stage": stage, "round_size": m.group(1).upper().replace(" ", "") if m else "",
            "traction": traction.group(1).strip()[:300] if traction else "", "one_liner": first[:200]}


MAX_SLIDES = 20


@router.post("/deck")
async def upload_deck(file: UploadFile, c: Ctx = Depends(ctx)):
    """DECK-01 (deterministic tier): PDF text extraction -> suggested Company Profile fields for review."""
    c.require_editor()
    data = await file.read(50 * 1024 * 1024 + 1)
    if len(data) > 50 * 1024 * 1024:
        raise ApiError(413, "EF-DECK-001", "Deck is larger than 50MB")
    if not data.startswith(b"%PDF"):
        raise ApiError(415, "EF-DECK-002", "Upload your deck as a PDF")
    from pypdf import PdfReader

    try:
        pages = PdfReader(io.BytesIO(data)).pages
        n_pages = len(pages)
        slides = [(pg.extract_text() or "") for pg in pages[:MAX_SLIDES]]
        text = "\n".join(slides)
    except Exception as e:
        raise ApiError(422, "EF-DECK-003", "Could not read that PDF") from e
    if n_pages > MAX_SLIDES:
        raise ApiError(422, "EF-DECK-004", f"Keep your deck to {MAX_SLIDES} slides or fewer",
                       f"This PDF has {n_pages} pages. Investors read short decks; trim it and upload again.")
    p = _profile(c)
    p.deck_filename, p.deck_text = (file.filename or "deck.pdf")[:200], text[:200_000]
    c.db.commit()
    from ..services import agent

    vocab = [r[0] for r in c.db.execute(sql_text(
        "select ind from investors, unnest(industries) ind group by ind order by count(*) desc limit 80")).all()]
    suggested = agent.ai_profile(c.db, c.workspace, text, vocab)
    c.db.commit()
    room = _room_from_deck(c, slides)
    if suggested:
        return {"suggested": suggested, "engine": "ai", "pages_text_chars": len(text), "slides": n_pages, "data_room": room}
    return {"suggested": extract_profile(text), "engine": "template", "pages_text_chars": len(text), "slides": n_pages,
            "data_room": room}


def _room_from_deck(c: Ctx, slides: list[str]) -> dict:
    """The deck drafts the data room: empty sections are written from it, the founder's own text is kept."""
    from ..services import room_fill
    from .dataroom import ensure_room

    room = ensure_room(c.db, c.ws_id, c.workspace.name)
    drafted, engine = room_fill.draft(c.db, c.workspace, slides)
    content = json.loads(json.dumps(room.content or {}))
    filled = room_fill.apply(content, drafted)
    if filled:
        room.versions = ([{"at": datetime.now(UTC).isoformat(), "content": room.content}] + (room.versions or []))[:10]
        room.content = content
    c.db.commit()
    return {"filled": filled, "engine": engine, "completeness": room_fill.completeness(content)["pct"]}


# ---------- Agent instructions ----------

class InstructionsIn(BaseModel):
    text: str = Field(max_length=4000)


@router.get("/agent-instructions")
def get_instructions(c: Ctx = Depends(ctx)):
    row = c.db.scalar(select(AgentInstruction).where(AgentInstruction.workspace_id == c.ws_id)
                      .order_by(AgentInstruction.version.desc()))
    return {"text": row.text if row else "", "version": row.version if row else 0}


@router.put("/agent-instructions")
def put_instructions(body: InstructionsIn, c: Ctx = Depends(ctx)):
    c.require_editor()
    v = c.db.scalar(select(func.max(AgentInstruction.version)).where(AgentInstruction.workspace_id == c.ws_id)) or 0
    c.db.add(AgentInstruction(workspace_id=c.ws_id, version=v + 1, text=body.text.strip()))
    c.db.commit()
    return {"version": v + 1, "summary": summarise_instructions(body.text)}


def summarise_instructions(text: str) -> list[str]:
    """Agent confirms understanding (AGT-01) — deterministic echo of each instruction line."""
    parts = [p.strip(" .-•") for p in re.split(r"[\n;]|(?<=\.)\s", text) if p.strip(" .-•")]
    return [f"Understood: {p}" for p in parts[:10]]


# ---------- Exclusions ----------

class ExclusionIn(BaseModel):
    kind: str = Field(pattern="^(email|domain|firm|linkedin)$")
    value: str = Field(min_length=2, max_length=300)


@router.get("/exclusions")
def list_exclusions(c: Ctx = Depends(ctx)):
    rows = c.db.scalars(select(Exclusion).where(Exclusion.workspace_id == c.ws_id).order_by(Exclusion.created_at))
    return [{"id": str(e.id), "kind": e.kind, "value": e.value} for e in rows]


@router.post("/exclusions")
def add_exclusion(body: ExclusionIn, c: Ctx = Depends(ctx)):
    c.require_editor()
    v = body.value.strip().lower()
    if not c.db.scalar(select(Exclusion).where(Exclusion.workspace_id == c.ws_id, Exclusion.kind == body.kind,
                                               Exclusion.value == v)):
        c.db.add(Exclusion(workspace_id=c.ws_id, kind=body.kind, value=v))
        c.db.commit()
    return {"ok": True}


@router.delete("/exclusions/{eid}")
def delete_exclusion(eid: str, c: Ctx = Depends(ctx)):
    c.require_editor()
    c.db.execute(delete(Exclusion).where(Exclusion.workspace_id == c.ws_id, Exclusion.id == eid))
    c.db.commit()
    return {"ok": True}


# ---------- User settings ----------

class UserPatch(BaseModel):
    timezone: str | None = Field(None, max_length=64)
    signature: str | None = Field(None, max_length=2000)
    name: str | None = Field(None, max_length=200)
    notify_prefs: dict | None = None  # §10.5


@router.patch("/me")
def patch_me(body: UserPatch, c: Ctx = Depends(ctx)):
    from zoneinfo import ZoneInfo

    if body.timezone:
        try:
            ZoneInfo(body.timezone)
        except Exception as e:
            raise ApiError(422, "EF-VAL-001", "Unknown timezone") from e
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "notify_prefs":
            v = {**(c.user.notify_prefs or {}), **v}
        setattr(c.user, k, v)
    c.db.commit()
    return {"ok": True}

