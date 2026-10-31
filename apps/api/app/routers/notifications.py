"""§10.5 notifications + reminders, and the Home "daily brief" (AGT-02, deterministic version)."""

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..deps import Ctx, ctx
from ..errors import not_found
from ..models import STAGES, FunnelCard, Notification, Reminder

router = APIRouter(tags=["notifications"])


def fire_due_reminders(db: Session, now: datetime | None = None) -> int:
    """Turns due reminders into notifications. Idempotent: run by the worker every minute and lazily on read."""
    now = now or datetime.now(UTC)
    due = db.scalars(select(Reminder).where(Reminder.due_at <= now, Reminder.notified_at.is_(None),
                                            Reminder.done_at.is_(None)).limit(500).with_for_update(skip_locked=True)).all()
    for r in due:
        db.add(Notification(workspace_id=r.workspace_id, user_id=r.user_id, kind="reminder", title=r.title,
                            link=f"/app/funnel/{r.card_id}" if r.card_id else "/app"))
        r.notified_at = now
    db.commit()
    return len(due)


def n_out(n: Notification) -> dict:
    return {"id": str(n.id), "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
            "read": n.read_at is not None, "created_at": n.created_at}


@router.get("/notifications")
def list_notifications(unread: bool = False, c: Ctx = Depends(ctx)):
    fire_due_reminders(c.db)
    conds = [Notification.user_id == c.user.id, Notification.workspace_id == c.ws_id]
    if unread:
        conds.append(Notification.read_at.is_(None))
    rows = c.db.scalars(select(Notification).where(*conds).order_by(Notification.created_at.desc()).limit(100)).all()
    count = c.db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == c.user.id, Notification.workspace_id == c.ws_id, Notification.read_at.is_(None)))
    return {"items": [n_out(n) for n in rows], "unread": count}


@router.post("/notifications/read")
def mark_read(ids: list[str] | None = None, c: Ctx = Depends(ctx)):
    q = update(Notification).where(Notification.user_id == c.user.id, Notification.read_at.is_(None))
    if ids:
        q = q.where(Notification.id.in_([uuid.UUID(i) for i in ids]))
    c.db.execute(q.values(read_at=datetime.now(UTC)))
    c.db.commit()
    return {"ok": True}


@router.get("/reminders")
def list_reminders(c: Ctx = Depends(ctx)):
    rows = c.db.execute(select(Reminder, FunnelCard.name).outerjoin(FunnelCard, FunnelCard.id == Reminder.card_id)
                        .where(Reminder.workspace_id == c.ws_id, Reminder.done_at.is_(None))
                        .order_by(Reminder.due_at).limit(200)).all()
    return {"items": [{"id": str(r.id), "title": r.title, "due_at": r.due_at, "card_id": str(r.card_id) if r.card_id else None,
                       "card_name": name, "overdue": r.due_at < datetime.now(UTC)} for r, name in rows]}


class ReminderIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    due_at: datetime
    card_id: str | None = None


@router.post("/reminders")
def create_reminder(body: ReminderIn, c: Ctx = Depends(ctx)):
    card_id = None
    if body.card_id:
        card = c.db.get(FunnelCard, uuid.UUID(body.card_id))
        if card is None or card.workspace_id != c.ws_id:
            raise not_found("Card")
        card_id = card.id
    r = Reminder(workspace_id=c.ws_id, user_id=c.user.id, card_id=card_id, title=body.title.strip(),
                 due_at=body.due_at)
    c.db.add(r)
    c.db.commit()
    return {"id": str(r.id)}


class ReminderAction(BaseModel):
    action: str = Field(pattern="^(done|snooze)$")
    days: int = Field(1, ge=1, le=90)


@router.post("/reminders/{rid}")
def act_reminder(rid: str, body: ReminderAction, c: Ctx = Depends(ctx)):
    r = c.db.get(Reminder, uuid.UUID(rid))
    if r is None or r.workspace_id != c.ws_id:
        raise not_found("Reminder")
    if body.action == "done":
        r.done_at = datetime.now(UTC)
    else:
        r.due_at, r.notified_at = max(r.due_at, datetime.now(UTC)) + timedelta(days=body.days), None
    c.db.commit()
    return {"ok": True}


@router.get("/home")
def home(c: Ctx = Depends(ctx)):
    """Daily brief: follow-ups due, overdue, going cold, stage counts and next-best actions."""
    fire_due_reminders(c.db)
    today = date.today()
    base = [FunnelCard.workspace_id == c.ws_id, FunnelCard.deleted_at.is_(None)]
    counts = dict(c.db.execute(select(FunnelCard.stage, func.count()).where(*base).group_by(FunnelCard.stage)).all())
    due = c.db.scalars(select(FunnelCard).where(*base, FunnelCard.next_contact_date <= today,
                                                FunnelCard.status.in_(["Active", "Ghosting"]))
                       .order_by(FunnelCard.next_contact_date).limit(10)).all()
    cold_cut = datetime.now(UTC) - timedelta(days=14)
    cold = c.db.scalars(select(FunnelCard).where(*base, FunnelCard.status == "Active", FunnelCard.stage.between(3, 7),
                                                 FunnelCard.last_contacted_at < cold_cut)
                        .order_by(FunnelCard.last_contacted_at).limit(5)).all()
    calls = c.db.scalars(select(FunnelCard).where(*base, FunnelCard.call_at >= datetime.now(UTC),
                                                  FunnelCard.call_at < datetime.now(UTC) + timedelta(days=7))
                         .order_by(FunnelCard.call_at).limit(5)).all()
    committed = c.db.scalar(select(func.count()).select_from(FunnelCard).where(*base, FunnelCard.stage >= 8)) or 0
    brief = lambda x: {"id": str(x.id), "name": x.name, "firm": x.firm, "stage": x.stage,  # noqa: E731
                       "stage_label": STAGES[x.stage - 1], "next_contact_date": x.next_contact_date,
                       "call_at": x.call_at, "last_contacted_at": x.last_contacted_at, "status": x.status}
    actions = []
    if due:
        actions.append({"title": f"Follow up with {len(due)} investor{'s' if len(due) > 1 else ''} due today",
                        "link": "/app/funnel?needs_action=1"})
    if cold:
        actions.append({"title": f"{cold[0].name} is going cold. Send a short nudge?",
                        "link": f"/app/funnel/{cold[0].id}"})
    if not counts:
        actions.append({"title": "Import your existing investor tracker", "link": "/app/funnel/import"})
        actions.append({"title": "Find investors that fit your company", "link": "/app/investors"})
    return {
        "agent_name": c.workspace.agent_name,
        "stage_counts": [{"stage": i + 1, "label": s, "count": counts.get(i + 1, 0)} for i, s in enumerate(STAGES)],
        "total": sum(counts.values()), "committed": committed,
        "due": [brief(x) for x in due], "going_cold": [brief(x) for x in cold], "calls": [brief(x) for x in calls],
        "actions": actions[:3],
    }
