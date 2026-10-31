"""§8 Investor discovery. Contact fields never appear in list payloads (ASP-01); they are returned only
by POST /investors/{id}/reveal, which checks entitlement, spends a credit once and logs the access."""

import time
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import and_, func, literal_column, or_, select, text
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Ctx, client_ip, ctx
from ..errors import ApiError, not_found
from ..models import (
    AuditLog,
    CompanyProfile,
    Exclusion,
    FunnelCard,
    Investor,
    InvestorResearch,
    RemovalRequest,
    Reveal,
    ShortlistItem,
)
from ..services import ai, search_parse
from ..services.entitlements import can, consume, limit, rate_limit, trial_expired, usage
from ..services.fit import SIMILAR_SQL, fit

router = APIRouter(prefix="/investors", tags=["investors"])
public = APIRouter(prefix="/public", tags=["public"])

TYPE_LABEL = {"angel": "Angel", "vc": "VC", "pe": "PE / Buyout", "growth": "Growth equity", "cvc": "Corporate VC",
              "family_office": "Family office", "wealth_manager": "Wealth manager", "accelerator": "Accelerator",
              "syndicate": "Angel syndicate", "other": "Other"}


def domain(url: str) -> str:
    d = (url or "").strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.")
    return d.split("/")[0] if "." in d else ""


def card(inv: Investor, f: dict | None = None, in_funnel: bool = False, in_shortlist: bool = False) -> dict:
    """List-safe representation: no email / LinkedIn / X (ASP-01)."""
    return {
        "id": str(inv.id), "name": inv.name, "title": inv.role_at_firm or inv.title,
        "firm": inv.current_firm or inv.company, "listed_company": inv.company,
        "location": inv.location, "country": inv.country, "photo_url": inv.photo_url,
        "firm_domain": domain(inv.firm_website), "industries": inv.industries[:6],
        "investor_type": inv.investor_type, "investor_type_label": TYPE_LABEL.get(inv.investor_type, "Other"),
        "seed_fit": inv.seed_fit, "is_decision_maker": inv.is_decision_maker, "enriched": inv.enriched,
        "identity_confidence": inv.identity_confidence or None,
        # DATA-02: only "yes" is surfaced; unknown is never rendered as inactive.
        "verified_recent_deal": inv.active_last_12mo == "yes",
        "thesis_summary": (inv.investment_thesis or "")[:240],
        "check_size": inv.typical_check_size if inv.enriched else "",
        "has_email": bool(inv.email), "in_funnel": in_funnel, "in_shortlist": in_shortlist,
        **({"fit": f} if f else {}),
    }


class SearchParams(BaseModel):
    q: str = ""
    sector: list[str] = []
    stage: str = ""
    geo: str = ""
    investor_type: list[str] = []
    decision_maker: bool = False
    active: bool = False
    seed_fit: bool = False
    leads: bool = False
    has_email: bool = False
    enriched: bool = False
    not_in_funnel: bool = False
    country: str = ""
    check_min: int | None = None
    check_max: int | None = None
    page: int = 1

    def has_criteria(self) -> bool:
        return bool(self.q or self.sector or self.stage or self.geo or self.investor_type or self.decision_maker
                    or self.active or self.seed_fit or self.leads or self.has_email or self.enriched or self.country
                    or self.check_min or self.check_max)


# Directory cheque size ("$150K", "$1.6M") as dollars, null when it isn't a single clean figure.
CHECK_USD = literal_column("""(case when check_size_src ~* '^\\$?[0-9]+(\\.[0-9]+)?\\s*[km]$'
    then regexp_replace(check_size_src, '[^0-9.]', '', 'g')::numeric
         * (case when check_size_src ~* 'm\\s*$' then 1000000 else 1000 end) end)""")


def _base_filters(c: Ctx, p: SearchParams):
    conds = [~Investor.suppressed]
    if p.q.strip():
        q = p.q.strip()[:200]
        conds.append(or_(Investor.search_tsv.op("@@")(func.websearch_to_tsquery("english", q)),
                         Investor.name.ilike(f"%{q}%"), Investor.company.ilike(f"%{q}%"),
                         Investor.current_firm.ilike(f"%{q}%")))
    if p.sector:
        conds.append(Investor.industries.overlap(p.sector[:10]))
    if p.stage:
        conds.append(or_(Investor.focus_stages.ilike(f"%{p.stage}%"),
                         and_(Investor.focus_stages == "", Investor.stages_src.ilike(f"%{p.stage}%"))))
    if p.geo:
        conds.append(or_(Investor.location.ilike(f"%{p.geo}%"), Investor.geography_focus.ilike(f"%{p.geo}%")))
    if p.investor_type:
        conds.append(Investor.investor_type.in_(p.investor_type))
    if p.decision_maker:
        conds.append(Investor.is_decision_maker.is_(True))
    if p.active:
        conds.append(Investor.active_last_12mo == "yes")
    if p.seed_fit:
        conds.append(Investor.seed_fit.is_(True))
    if p.leads:
        conds.append(Investor.leads_rounds.in_(["yes", "sometimes"]))
    if p.has_email:
        conds.append(Investor.email != "")
    if p.enriched:
        conds.append(Investor.enriched.is_(True))
    if p.country:
        conds.append(func.lower(Investor.country) == p.country.lower()[:80])
    if p.check_min:
        conds.append(CHECK_USD >= p.check_min)
    if p.check_max:
        conds.append(CHECK_USD <= p.check_max)
    if p.not_in_funnel:
        conds.append(~Investor.id.in_(select(FunnelCard.investor_id).where(
            FunnelCard.workspace_id == c.ws_id, FunnelCard.investor_id.is_not(None), FunnelCard.deleted_at.is_(None))))
    return conds


def _shortlist_ids(c: Ctx) -> set:
    return set(c.db.scalars(select(ShortlistItem.investor_id).where(ShortlistItem.workspace_id == c.ws_id)))


def _funnel_ids(c: Ctx) -> set:
    return set(c.db.scalars(select(FunnelCard.investor_id).where(
        FunnelCard.workspace_id == c.ws_id, FunnelCard.investor_id.is_not(None), FunnelCard.deleted_at.is_(None))))


@router.get("")
def search(
    q: str = "", sector: list[str] = Query(default=[]), stage: str = "", geo: str = "",
    investor_type: list[str] = Query(default=[]), decision_maker: bool = False, active: bool = False,
    seed_fit: bool = False, leads: bool = False, has_email: bool = False, enriched: bool = False,
    not_in_funnel: bool = False, country: str = "", check_min: int | None = None, check_max: int | None = None,
    page: int = Query(1, ge=1, le=400), c: Ctx = Depends(ctx),
):
    p = SearchParams(q=q, sector=sector, stage=stage, geo=geo, investor_type=investor_type,
                     decision_maker=decision_maker, active=active, seed_fit=seed_fit, leads=leads,
                     has_email=has_email, enriched=enriched, not_in_funnel=not_in_funnel, country=country,
                     check_min=check_min, check_max=check_max, page=page)
    rate_limit(c.db, f"search:m:{c.user.id}", 60, 60)  # ASP-02
    rate_limit(c.db, f"search:h:{c.user.id}", 600, 3600)
    if trial_expired(c.workspace):
        raise ApiError(402, "EF-TIER-010", "Your trial has ended", "Upgrade to keep searching.", {"upgrade": True})
    page_size = 10  # ASP-03: ten per page, numbered pages
    cap = limit(c.db, c.workspace, "result_cap")
    if cap is not None and (page - 1) * page_size >= cap:
        raise ApiError(402, "EF-LIMIT-002", "Upgrade to see more results", "", {"upgrade": True})
    counted = page == 1 and p.has_criteria()
    if counted:
        total_cap = limit(c.db, c.workspace, "searches_total")
        if total_cap is not None:
            consume(c.db, c.workspace, "searches", "all", total_cap)
        else:
            consume(c.db, c.workspace, "searches", "month", limit(c.db, c.workspace, "searches_month"))
    conds = _base_filters(c, p)
    total = c.db.scalar(select(func.count()).select_from(Investor).where(*conds))
    order = [Investor.enriched.desc(), Investor.seed_fit.desc().nulls_last(), Investor.name]
    if p.q.strip():
        order.insert(0, func.ts_rank(Investor.search_tsv, func.websearch_to_tsquery("english", p.q[:200])).desc())
    n = min(page_size, cap - (page - 1) * page_size) if cap else page_size  # the last capped page may be short
    rows = c.db.scalars(select(Investor).where(*conds).order_by(*order).offset((page - 1) * page_size).limit(n)).all()
    prof = c.db.get(CompanyProfile, c.ws_id)
    fids, sids = _funnel_ids(c), _shortlist_ids(c)
    c.access("search", None, params=p.model_dump(exclude_defaults=True), results=len(rows))
    c.db.commit()
    return {
        "total": total if cap is None else min(total, cap), "all_total": total, "page": page, "page_size": page_size,
        "items": [card(i, fit(i, prof), i.id in fids, i.id in sids) for i in rows],
        "searches_used": usage(c.db, c.workspace, "searches", "all" if cap else "month"),
        "searches_limit": limit(c.db, c.workspace, "searches_total") or limit(c.db, c.workspace, "searches_month"),
        "contacts_locked": not can(c.db, c.workspace, "contacts_visible"),
    }


STAGE_FACETS = [("pre-seed", "Pre-seed"), ("seed", "Seed"), ("series a", "Series A"), ("series b", "Series B")]


def _facets(db: Session) -> dict:
    sectors = db.execute(text("""select ind, count(*) from investors, unnest(industries) ind
                                 where not suppressed group by ind order by count(*) desc limit 80""")).all()
    types = dict(db.execute(select(Investor.investor_type, func.count()).where(~Investor.suppressed)
                            .group_by(Investor.investor_type)).all())
    stages = []
    for v, label in STAGE_FACETS:
        n = db.scalar(select(func.count()).select_from(Investor).where(~Investor.suppressed, or_(
            Investor.focus_stages.ilike(f"%{v}%"), and_(Investor.focus_stages == "", Investor.stages_src.ilike(f"%{v}%")))))
        if n:
            stages.append({"value": v, "label": label, "count": n})
    countries = db.execute(select(Investor.country, func.count()).where(~Investor.suppressed, Investor.country != "")
                           .group_by(Investor.country).order_by(func.count().desc()).limit(60)).all()
    return {"sectors": [{"value": r[0], "count": r[1]} for r in sectors],
            "investor_types": [{"value": k, "label": v, "count": types[k]} for k, v in TYPE_LABEL.items() if types.get(k)],
            "stages": stages, "countries": [{"value": r[0], "count": r[1]} for r in countries]}


_facet_cache: dict = {}


@router.get("/facets")
def facets(c: Ctx = Depends(ctx)):
    """Only options that have investors behind them (no empty "Series B"). Cached for 10 minutes."""
    hit = _facet_cache.get("v")
    if hit and hit[0] > time.time():
        return hit[1]
    out = _facets(c.db)
    _facet_cache["v"] = (time.time() + 600, out)
    return out


class AiSearchIn(BaseModel):
    q: str = Field(min_length=2, max_length=300)


@router.post("/ai-search")
def ai_search(body: AiSearchIn, c: Ctx = Depends(ctx)):
    """Plain-language search -> filters. The client then runs the normal search with them, so limits still apply."""
    rate_limit(c.db, f"aisearch:{c.user.id}", 30, 60)
    f = facets(c)
    out = search_parse.parse(c.db, c.workspace, body.q, [s["value"] for s in f["sectors"]],
                             [x["value"] for x in f["countries"]])
    c.db.commit()
    return out


@router.get("/recommended")
def recommended(c: Ctx = Depends(ctx)):
    """DECK-02(a): investors ranked by fit for this workspace's Company Profile, with reasons."""
    prof = c.db.get(CompanyProfile, c.ws_id)
    if not prof or not prof.sectors:
        return {"items": [], "needs_profile": True}
    sectors = prof.sectors
    cand = c.db.scalars(select(Investor).where(
        ~Investor.suppressed, ~Investor.is_honeypot, Investor.identity_confidence != "low",  # DATA-03
        or_(Investor.industries.overlap(sectors), *[Investor.focus_sectors.ilike(f"%{s}%") for s in sectors]),
    ).order_by(Investor.enriched.desc(), Investor.seed_fit.desc().nulls_last()).limit(600)).all()
    excl = _exclusions(c)
    scored = [(fit(i, prof), i) for i in cand if not is_excluded(i, excl)]
    scored.sort(key=lambda x: -x[0]["score"])
    fids, sids = _funnel_ids(c), _shortlist_ids(c)
    cap = limit(c.db, c.workspace, "result_cap") or 100  # paged ten at a time in the app
    return {"items": [card(i, f, i.id in fids, i.id in sids) for f, i in scored[:cap]], "needs_profile": False}


def _exclusions(c: Ctx) -> list[tuple[str, str]]:
    return [(e.kind, e.value) for e in c.db.scalars(select(Exclusion).where(Exclusion.workspace_id == c.ws_id))]


def is_excluded(inv: Investor, excl: list[tuple[str, str]]) -> bool:
    email = inv.email.lower()
    firm = f"{inv.company} {inv.current_firm}".lower()
    for kind, v in excl:
        if (kind == "email" and email == v) or (kind == "domain" and email.endswith("@" + v.lstrip("@"))) \
                or (kind == "firm" and v in firm) or (kind == "linkedin" and v.rstrip("/") in inv.linkedin):
            return True
    return False


def _get(c: Ctx, iid: str) -> Investor:
    try:
        inv = c.db.get(Investor, uuid.UUID(iid))
    except ValueError:
        inv = None
    if inv is None or inv.suppressed:
        raise not_found("Investor")
    return inv


def _revealed(c: Ctx, inv: Investor) -> bool:
    return c.db.get(Reveal, (c.ws_id, inv.id)) is not None


def contacts(inv: Investor) -> dict:
    return {"email": inv.email, "linkedin": inv.linkedin, "x": inv.x_url}


@router.get("/{iid}")
def profile(iid: str, c: Ctx = Depends(ctx)):
    rate_limit(c.db, f"profile:{c.user.id}", 120, 60)
    inv = _get(c, iid)
    prof = c.db.get(CompanyProfile, c.ws_id)
    e = inv.enrichment or {}
    revealed = _revealed(c, inv)
    funnel = c.db.scalar(select(FunnelCard).where(FunnelCard.workspace_id == c.ws_id, FunnelCard.investor_id == inv.id,
                                                  FunnelCard.deleted_at.is_(None)))
    c.access("profile", inv.id)
    c.db.commit()
    return {
        **card(inv, fit(inv, prof), funnel is not None, c.db.get(ShortlistItem, (c.ws_id, inv.id)) is not None),
        "funnel_card_id": str(funnel.id) if funnel else None,
        "excluded": is_excluded(inv, _exclusions(c)),
        "about": inv.about, "investment_thesis": inv.investment_thesis, "focus_sectors": inv.focus_sectors,
        "focus_stages": inv.focus_stages, "geography_focus": inv.geography_focus,
        "typical_check_size": inv.typical_check_size, "fund_size_or_aum": e.get("fund_size_or_aum", ""),
        "leads_rounds": inv.leads_rounds, "instrument_preference": inv.instrument_preference,
        "investments_per_year_estimate": e.get("investments_per_year_estimate", ""),
        "decision_speed": e.get("decision_speed", ""), "value_add": e.get("value_add", ""),
        "notable_portfolio": e.get("notable_portfolio") or inv.portfolio_sample,
        "more_portfolio": inv.more_portfolio,
        "recent_investments_12mo": e.get("recent_investments_12mo", []),
        "last_known_investment_date": e.get("last_known_investment_date", ""),
        "recent_news": e.get("recent_news", []), "public_content": e.get("public_content", []),
        "personalization_hooks": e.get("personalization_hooks", []), "best_email_angle": e.get("best_email_angle", ""),
        "sources": e.get("sources", []), "notes": e.get("notes", ""), "firm_website": inv.firm_website,
        "firm_type": inv.firm_type, "timezone": inv.timezone,
        "directory_tags": {"stages": inv.stages_src, "check_size": inv.check_size_src},
        "revealed": revealed, "contacts": contacts(inv) if revealed else None,
        "contacts_locked": not can(c.db, c.workspace, "contacts_visible"),
    }


@router.post("/{iid}/reveal")
def reveal(iid: str, c: Ctx = Depends(ctx)):
    rate_limit(c.db, f"reveal:{c.user.id}", 30, 60)
    inv = _get(c, iid)
    if _revealed(c, inv):  # re-reveal is free
        return {"contacts": contacts(inv), "charged": False}
    if not can(c.db, c.workspace, "contacts_visible") or trial_expired(c.workspace):
        raise ApiError(402, "EF-TIER-020", "Upgrade to reveal contacts",
                       "Contact details unlock on Starter and above.", {"upgrade": True})
    if inv.is_honeypot:  # ASP-05: reveal of a honeypot record proves scraping
        c.user.suspended_at = datetime.now(UTC)
        c.db.add(AuditLog(actor_id=c.user.id, action="honeypot.reveal", target=str(inv.id), ip=c.ip))
        c.db.commit()
        raise ApiError(403, "EF-AUTH-003", "Account suspended")
    consume(c.db, c.workspace, "reveals", "month", limit(c.db, c.workspace, "reveals_month"))
    c.db.add(Reveal(workspace_id=c.ws_id, investor_id=inv.id))
    c.access("reveal", inv.id)
    c.db.commit()
    return {"contacts": contacts(inv), "charged": True}


@router.get("/{iid}/similar")
def similar(iid: str, c: Ctx = Depends(ctx)):
    inv = _get(c, iid)
    if not inv.industries:
        return {"items": []}
    rows = c.db.execute(text(SIMILAR_SQL), {"id": inv.id, "inds": inv.industries, "itype": inv.investor_type,
                                            "n": 12}).all()
    ids = [r.id for r in rows]
    invs = {i.id: i for i in c.db.scalars(select(Investor).where(Investor.id.in_(ids)))}
    prof = c.db.get(CompanyProfile, c.ws_id)
    return {"items": [card(invs[i], fit(invs[i], prof)) for i in ids if i in invs]}


RESEARCH_TTL = timedelta(days=30)


def research_out(r: InvestorResearch | None) -> dict | None:
    return {**r.data, "researched_at": r.created_at.isoformat()} if r else None


@router.get("/{iid}/research")
def get_research(iid: str, c: Ctx = Depends(ctx)):
    inv = _get(c, iid)
    return {"research": research_out(c.db.get(InvestorResearch, inv.id)), "available": ai.available()}


@router.post("/{iid}/research")
def run_research(iid: str, c: Ctx = Depends(ctx)):
    """Live web research on this investor's firm, thesis, portfolio, partners and news. Cached for 30 days and
    shared across workspaces (public information only); each fresh run uses one research credit."""
    rate_limit(c.db, f"research:{c.user.id}", 5, 60)
    inv = _get(c, iid)
    cached = c.db.get(InvestorResearch, inv.id)
    if cached and cached.created_at > datetime.now(UTC) - RESEARCH_TTL:
        return {"research": research_out(cached), "charged": False}
    if not ai.available():
        raise ApiError(503, "EF-AI-010", "Research needs an Anthropic API key",
                       "Add ANTHROPIC_API_KEY to apps/api/.env to turn on live research.")
    consume(c.db, c.workspace, "research", datetime.now(UTC).strftime("%Y-%m"), limit(c.db, c.workspace, "research_month"))
    firm = inv.current_firm or inv.company
    who = (f"Investor: {inv.name}, {inv.role_at_firm or inv.title} at {firm}." + (f" Firm website: {inv.firm_website}."
           if inv.firm_website else "") + (f" Based in {inv.location}." if inv.location else "")
           + " Research the firm's thesis, portfolio, partners and the last 12 months of news.")
    data, model = ai.research(c.db, c.workspace, who)
    if not data:
        c.db.commit()
        raise ApiError(502, "EF-AI-011", "Research didn't come back", "Please try again in a minute.")
    if cached:
        cached.data, cached.model, cached.created_at = data, model, datetime.now(UTC)
    else:
        cached = InvestorResearch(investor_id=inv.id, data=data, model=model, created_at=datetime.now(UTC))
        c.db.add(cached)
    c.access("research", inv.id)
    c.db.commit()
    return {"research": research_out(cached), "charged": True}


@router.get("/lookup/company")
def company_lookup(name: str = Query(min_length=2, max_length=200), c: Ctx = Depends(ctx)):
    """SRCH-03: investors who invested in <company> (from stored portfolio / recent deals), then similar ones."""
    rate_limit(c.db, f"search:m:{c.user.id}", 60, 60)
    n = name.strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/")[0]
    n = n.split(".")[0] if "." in n and " " not in n else n
    rows = c.db.scalars(select(Investor).where(~Investor.suppressed, or_(
        func.array_to_string(Investor.portfolio_sample, "|").ilike(f"%{n}%"),
        Investor.enrichment["notable_portfolio"].astext.ilike(f"%{n}%"),
        Investor.enrichment["recent_investments_12mo"].astext.ilike(f"%{n}%"),
    )).limit(25)).all()
    prof = c.db.get(CompanyProfile, c.ws_id)
    items = []
    for i in rows:
        e = i.enrichment or {}
        deal = next((d for d in (e.get("recent_investments_12mo") or [])
                     if isinstance(d, dict) and n in str(d.get("company", "")).lower()), None)
        items.append({**card(i, fit(i, prof)), "evidence": deal or {"company": name, "source": "portfolio listing"}})
    similar_items: list[dict] = []
    if rows:
        inds = sorted({x for i in rows for x in i.industries})[:12]
        seen = {i.id for i in rows}
        cand = c.db.scalars(select(Investor).where(~Investor.suppressed, ~Investor.is_honeypot,
                                                   Investor.industries.overlap(inds), ~Investor.id.in_(seen))
                            .order_by(Investor.enriched.desc(), Investor.seed_fit.desc().nulls_last()).limit(200)).all()
        scored = sorted(((fit(i, prof), i) for i in cand), key=lambda x: -x[0]["score"])[:10]
        similar_items = [card(i, f) for f, i in scored]
    c.access("search", None, company_lookup=name, results=len(items))
    c.db.commit()
    return {"company": name, "investors": items, "similar": similar_items}


# ---------- DATA-04 public removal / update request ----------

class RemovalIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    linkedin: str = Field("", max_length=300)
    kind: str = Field("remove", pattern="^(remove|update)$")
    message: str = Field("", max_length=2000)


@public.post("/investor-requests")
def investor_request(body: RemovalIn, request: Request, db: Session = Depends(get_db)):
    rate_limit(db, f"public:removal:{client_ip(request)}", 5, 3600)
    db.add(RemovalRequest(**body.model_dump()))
    db.commit()
    return {"ok": True, "message": "Thanks. We'll process your request within 72 hours."}
