"""Counts for the sidebar badges: one cheap call instead of loading each list."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from ..deps import Ctx, ctx
from ..models import FounderTask, FunnelCard, Investor, Sequence, ShortlistItem
from ..services import test_investors

router = APIRouter(prefix="/nav", tags=["nav"])


@router.get("/counts")
def counts(c: Ctx = Depends(ctx)):
    one = c.db.scalar
    return {
        "outreach": one(select(func.count(func.distinct(Sequence.investor_id))).where(Sequence.workspace_id == c.ws_id)) or 0,
        "tracker": one(select(func.count()).select_from(FunnelCard).where(
            FunnelCard.workspace_id == c.ws_id, FunnelCard.deleted_at.is_(None))) or 0,
        "shortlist": one(select(func.count()).select_from(ShortlistItem).join(
            Investor, Investor.id == ShortlistItem.investor_id).where(  # same rows the shortlist page shows
            ShortlistItem.workspace_id == c.ws_id, ~Investor.suppressed, *test_investors.conds(c.user.email))) or 0,
        "tasks": one(select(func.count()).select_from(FounderTask).where(
            FounderTask.workspace_id == c.ws_id, FounderTask.status.in_(("todo", "doing")))) or 0,
    }
