"""Shortlist: investors saved while browsing, then moved to the investor tracker (funnel) in one go."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from ..deps import Ctx, ctx
from ..errors import not_found
from ..models import CompanyProfile, Investor, ShortlistItem
from ..services.fit import fit
from .funnel import CardIn, create_card
from .investors import _funnel_ids, _outreach_ids, card

router = APIRouter(prefix="/shortlist", tags=["shortlist"])


def _investor(c: Ctx, iid: str) -> Investor:
    try:
        inv = c.db.get(Investor, uuid.UUID(iid))
    except ValueError:
        inv = None
    if inv is None or inv.suppressed:
        raise not_found("Investor")
    return inv


@router.get("")
def list_shortlist(c: Ctx = Depends(ctx)):
    rows = c.db.execute(select(Investor, ShortlistItem.created_at).join(
        ShortlistItem, ShortlistItem.investor_id == Investor.id).where(
        ShortlistItem.workspace_id == c.ws_id, ~Investor.suppressed).order_by(ShortlistItem.created_at.desc())).all()
    prof, fids, oids = c.db.get(CompanyProfile, c.ws_id), _funnel_ids(c), _outreach_ids(c)
    return {"items": [{**card(i, fit(i, prof), i.id in fids, True, i.id in oids), "added_at": at} for i, at in rows]}


@router.put("/{iid}")
def add(iid: str, c: Ctx = Depends(ctx)):
    inv = _investor(c, iid)
    if c.db.get(ShortlistItem, (c.ws_id, inv.id)) is None:
        c.db.add(ShortlistItem(workspace_id=c.ws_id, investor_id=inv.id))
        c.db.commit()
    return {"ok": True, "count": _count(c)}


@router.delete("/{iid}")
def remove(iid: str, c: Ctx = Depends(ctx)):
    inv = _investor(c, iid)
    c.db.execute(delete(ShortlistItem).where(ShortlistItem.workspace_id == c.ws_id, ShortlistItem.investor_id == inv.id))
    c.db.commit()
    return {"ok": True, "count": _count(c)}


def _count(c: Ctx) -> int:
    return len(c.db.scalars(select(ShortlistItem.investor_id).where(ShortlistItem.workspace_id == c.ws_id)).all())


class ToTrackerIn(BaseModel):
    investor_ids: list[str] = Field(min_length=1, max_length=200)


@router.post("/to-tracker")
def to_tracker(body: ToTrackerIn, c: Ctx = Depends(ctx)):
    """Adds each investor to the tracker (existing cards are kept) and removes them from the shortlist."""
    c.require_editor()
    added = 0
    fids = _funnel_ids(c)
    for iid in body.investor_ids:
        inv = _investor(c, iid)
        if inv.id not in fids:
            create_card(CardIn(investor_id=str(inv.id)), c)
            added += 1
        c.db.execute(delete(ShortlistItem).where(ShortlistItem.workspace_id == c.ws_id, ShortlistItem.investor_id == inv.id))
    c.db.commit()
    return {"added": added, "count": _count(c)}
