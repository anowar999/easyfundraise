"""Aggregate investor statistics for the public investor-list pages (SEO). Counts, countries, sectors and firm
names only: no individual investor is ever named or exposed here."""

import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy import and_, func, literal_column, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import client_ip
from ..errors import ApiError
from ..models import Investor
from ..services.entitlements import rate_limit

router = APIRouter(prefix="/public/investor-stats", tags=["public"])
MIN_FIRM = 2  # a firm is only listed when several of its investors are in the segment
_cache: dict[str, tuple[float, dict]] = {}
TTL = 6 * 3600


def segment_filter(segment: str):
    stages = func.lower(func.coalesce(Investor.stages_src, "") + " " + func.coalesce(Investor.focus_stages, ""))
    title = func.lower(func.coalesce(Investor.title, "") + " " + func.coalesce(Investor.company, ""))
    match segment:
        case "angel":
            return or_(Investor.investor_type.in_(["angel", "syndicate"]), title.contains("angel"))
        case "vc":
            return or_(Investor.investor_type.in_(["vc", "cvc"]),
                       and_(title.op("~")("partner|principal|associate|venture"),
                            Investor.investor_type.notin_(["pe", "wealth_manager", "growth"])))
        case "seed":
            return stages.contains("seed")
        case "pre-seed":
            return or_(stages.contains("pre-seed"), stages.contains("pre seed"), stages.contains("preseed"))
        case "all":
            return literal_column("true")
    raise ApiError(404, "EF-NF-001", "Unknown segment")


def _base(segment: str, country: str = "", sector: str = ""):
    conds = [~Investor.suppressed, ~Investor.is_honeypot, segment_filter(segment)]
    if country:
        conds.append(func.lower(Investor.country) == country.lower())
    if sector:
        conds.append(Investor.industries.any(sector))
    return conds


def _cached(key: str, fn):
    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    val = fn()
    _cache[key] = (time.time() + TTL, val)
    return val


@router.get("")
def stats(request: Request, segment: str = "all", country: str = "", sector: str = "", db: Session = Depends(get_db)):
    rate_limit(db, f"seo:{client_ip(request)}", 120, 60)
    country, sector = country[:80], sector[:80]

    def build():
        conds = _base(segment, country, sector)
        n = db.scalar(select(func.count()).select_from(Investor).where(*conds)) or 0
        countries = db.execute(select(Investor.country, func.count()).where(*conds, Investor.country != "")
                               .group_by(Investor.country).order_by(func.count().desc()).limit(10)).all()
        sec = func.unnest(Investor.industries).label("s")
        sectors = db.execute(select(sec, func.count()).where(*conds).group_by("s").order_by(func.count().desc()).limit(10)).all()
        firm = func.coalesce(func.nullif(Investor.current_firm, ""), Investor.company)
        firms = db.execute(select(firm, func.count()).where(*conds, firm != "").group_by(firm)
                           .having(func.count() >= MIN_FIRM).order_by(func.count().desc()).limit(12)).all()
        leads = db.scalar(select(func.count()).select_from(Investor).where(*conds, Investor.leads_rounds == "yes")) or 0
        active = db.scalar(select(func.count()).select_from(Investor).where(*conds, Investor.active_last_12mo == "yes")) or 0
        return {"segment": segment, "country": country, "sector": sector, "count": n,
                "countries": [{"name": c, "count": k} for c, k in countries],
                "sectors": [{"name": s, "count": k} for s, k in sectors],
                "firms": [{"name": f, "count": k} for f, k in firms],
                "leads": leads, "active_last_12mo": active}

    return _cached(f"s|{segment}|{country.lower()}|{sector}", build)


@router.get("/index")
def index(request: Request, db: Session = Depends(get_db)):
    """Counts per country and per sector for each segment, so the site only publishes pages with real depth."""
    rate_limit(db, f"seo:{client_ip(request)}", 120, 60)

    def build():
        out: dict = {"countries": {}, "sectors": {}}
        for seg in ("all", "angel", "vc", "seed", "pre-seed"):
            conds = _base(seg)
            out["countries"][seg] = {c: k for c, k in db.execute(
                select(Investor.country, func.count()).where(*conds, Investor.country != "")
                .group_by(Investor.country).order_by(func.count().desc()).limit(40)).all()}
            sec = func.unnest(Investor.industries).label("s")
            out["sectors"][seg] = {s: k for s, k in db.execute(
                select(sec, func.count()).where(*conds).group_by("s").order_by(func.count().desc()).limit(40)).all()}
        out["total"] = db.scalar(select(func.count()).select_from(Investor).where(*_base("all")))
        return out

    return _cached("index", build)
