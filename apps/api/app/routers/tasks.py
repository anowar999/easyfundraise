"""Founder Tasks: a simple priority board (To do / In progress / Done, Archive hidden) for the founder's own work."""

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..deps import Ctx, ctx
from ..errors import ApiError, not_found
from ..models import FounderTask

router = APIRouter(prefix="/tasks", tags=["tasks"])
STATUSES = ("todo", "doing", "done", "archived")


def next_follow_up(t: FounderTask, today: date) -> str | None:
    """The earliest follow-up date from today on (else the latest past one, so an overdue check-back shows)."""
    ds = sorted(d for d in (t.follow_ups or []) if d)
    upcoming = [d for d in ds if d >= today.isoformat()]
    return upcoming[0] if upcoming else (ds[-1] if ds else None)


def out(t: FounderTask, today: date | None = None) -> dict:
    today = today or date.today()
    due = t.deadline
    return {"id": str(t.id), "title": t.title, "description": t.description, "status": t.status,
            "priority": t.priority, "urgent": t.urgent, "progress": t.progress,
            "deadline": due, "follow_ups": t.follow_ups or [], "next_follow_up": next_follow_up(t, today),
            "owner": t.owner, "depends_on": t.depends_on, "position": t.position, "done_at": t.done_at,
            "created_at": t.created_at, "updated_at": t.updated_at,
            "overdue": bool(due and due < today and t.status not in ("done", "archived")),
            "due_today": bool(t.status not in ("done", "archived") and (
                due == today or next_follow_up(t, today) == today.isoformat()))}


def _rank(t: FounderTask) -> tuple:
    """Most important first: urgent, then priority, then nearest deadline, then the board's own order."""
    return (not t.urgent, t.priority, t.deadline or date.max, t.position)


@router.get("")
def list_tasks(archived: bool = False, c: Ctx = Depends(ctx)):
    q = select(FounderTask).where(FounderTask.workspace_id == c.ws_id)
    q = q.where(FounderTask.status == "archived") if archived else q.where(FounderTask.status != "archived")
    rows = sorted(c.db.scalars(q), key=lambda t: (STATUSES.index(t.status), t.position))
    today = date.today()
    open_ = sorted((t for t in rows if t.status in ("todo", "doing")), key=_rank)
    return {"items": [out(t, today) for t in rows],
            "top": [out(t, today) for t in open_[:3]],
            "urgent": [out(t, today) for t in open_ if t.urgent],
            "due_today": sum(1 for t in rows if out(t, today)["due_today"])}


class TaskIn(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = Field(None, max_length=4000)
    status: str | None = None
    priority: int | None = Field(None, ge=1, le=3)
    urgent: bool | None = None
    progress: int | None = Field(None, ge=0, le=100)
    deadline: date | None = None
    follow_ups: list[date] | None = Field(None, max_length=20)
    owner: str | None = Field(None, max_length=200)
    depends_on: str | None = Field(None, max_length=1000)
    position: float | None = None


def _apply(t: FounderTask, body: TaskIn) -> None:
    data = body.model_dump(exclude_unset=True)
    if "status" in data:
        if data["status"] not in STATUSES:
            raise ApiError(422, "EF-VAL-010", "Unknown task status")
        if data["status"] == "done" and t.status != "done":
            t.done_at = datetime.now(UTC)
            data.setdefault("progress", 100)
            t.urgent = False  # done clears the pin
        elif data["status"] in ("todo", "doing"):
            t.done_at = None
    if "follow_ups" in data:
        data["follow_ups"] = sorted({d.isoformat() for d in data["follow_ups"] or []})
    if "title" in data and not (data["title"] or "").strip():
        raise ApiError(422, "EF-VAL-011", "Give the task a title")
    for k, v in data.items():
        setattr(t, k, v.strip() if isinstance(v, str) else v)
    if t.progress >= 100 and t.status in ("todo", "doing") and "progress" in data:
        t.status, t.done_at, t.urgent = "done", datetime.now(UTC), False


def _get(c: Ctx, tid: str) -> FounderTask:
    try:
        t = c.db.get(FounderTask, uuid.UUID(tid))
    except ValueError:
        t = None
    if t is None or t.workspace_id != c.ws_id:
        raise not_found("Task")
    return t


@router.post("")
def create_task(body: TaskIn, c: Ctx = Depends(ctx)):
    c.require_editor()
    if not body.title:
        raise ApiError(422, "EF-VAL-011", "Give the task a title")
    status = body.status or "todo"
    top = c.db.scalar(select(func.min(FounderTask.position)).where(
        FounderTask.workspace_id == c.ws_id, FounderTask.status == status)) or 0
    t = FounderTask(workspace_id=c.ws_id, user_id=c.user.id, title="", description="", status="todo", priority=2,
                    urgent=False, progress=0, follow_ups=[], owner="", depends_on="", position=top - 1)  # on top
    _apply(t, body)
    c.db.add(t)
    c.db.commit()
    return out(t)


@router.patch("/{tid}")
def update_task(tid: str, body: TaskIn, c: Ctx = Depends(ctx)):
    c.require_editor()
    t = _get(c, tid)
    _apply(t, body)
    c.db.commit()
    return out(t)


@router.delete("/{tid}")
def delete_task(tid: str, c: Ctx = Depends(ctx)):
    c.require_editor()
    c.db.delete(_get(c, tid))
    c.db.commit()
    return {"ok": True}
