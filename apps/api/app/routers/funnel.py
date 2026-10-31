"""§10 Investor Tracker (fundraising CRM): cards, stage moves, notes -> reminders (AGT-06), CSV export of
own data (ASP-03) and founder spreadsheet import (§10.6)."""

import csv
import io
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from ..deps import Ctx, ctx
from ..errors import ApiError, not_found
from ..models import CARD_TYPES, STAGES, STATUSES, CardEvent, FunnelCard, Investor, Notification, Reminder
from ..services import tracker_import as ti
from ..services.dataset_import import norm_linkedin, norm_name
from ..services.notes import parse_note

router = APIRouter(prefix="/funnel", tags=["funnel"])

TYPE_FROM_INVESTOR = {"angel": "Angel", "vc": "VC Partner", "pe": "PE/Growth", "growth": "PE/Growth",
                      "cvc": "Corporate VC", "family_office": "Family Office", "syndicate": "Angel"}


def heat(card: FunnelCard, last_event: datetime | None) -> str:
    """§10.3 heat overlay. Hot needs open/reply signals (from tracking); here: activity recency."""
    last = max([d for d in (card.last_contacted_at, last_event) if d], default=None)
    if last is None:
        return "cold"
    age = datetime.now(UTC) - last
    return "warm" if age <= timedelta(days=14) else "cold"


def out(card: FunnelCard, last_event: datetime | None = None, today: date | None = None) -> dict:
    today = today or date.today()
    return {
        "id": str(card.id), "investor_id": str(card.investor_id) if card.investor_id else None,
        "name": card.name, "firm": card.firm, "investor_type": card.investor_type, "priority": card.priority,
        "status": card.status, "stage": card.stage, "stage_label": STAGES[card.stage - 1], "position": card.position,
        "can_lead": card.can_lead, "ticket_size": card.ticket_size, "agreed_size": card.agreed_size,
        "instrument": card.instrument, "contact_method": card.contact_method, "email": card.email,
        "referrer": card.referrer, "last_contacted_at": card.last_contacted_at,
        "next_contact_date": card.next_contact_date, "call_at": card.call_at,
        "investor_timezone": card.investor_timezone, "source": card.source, "tags": card.tags,
        "shareable": card.shareable, "starred": card.starred, "star_reason": card.star_reason,
        "created_at": card.created_at, "updated_at": card.updated_at,
        "overdue": bool(card.next_contact_date and card.next_contact_date < today),
        "due_today": card.next_contact_date == today, "heat": heat(card, last_event),
        **_activity(card, last_event),
    }


STALE_DAYS = 7


def _activity(card: FunnelCard, last_event: datetime | None) -> dict:
    """When anything last happened on the card (note, email, stage/status change, edit) and whether an open
    investor has gone 7+ days without an update."""
    seen = [x for x in (last_event, card.updated_at, card.last_contacted_at, card.created_at) if x]
    last = max(seen) if seen else None
    days = (datetime.now(UTC) - last).days if last else 0
    return {"last_activity_at": last, "days_since_update": days,
            "stale": card.status in ("Active", "Ghosting") and days >= STALE_DAYS}


@router.get("/meta")
def meta():
    return {"stages": [{"value": i + 1, "label": s} for i, s in enumerate(STAGES)], "statuses": STATUSES,
            "types": CARD_TYPES, "priorities": ["P1", "P2", "P3", "P4"], "can_lead": ["Yes", "No", "Maybe"],
            "instruments": ["SAFE", "Note", "Equity"],
            "contact_methods": ["Email", "LinkedIn", "WhatsApp", "SMS", "Intro", "In person"]}


@router.get("")
def list_cards(q: str = "", status: str = "", stage: int | None = None, priority: str = "", type: str = "",
               needs_action: bool = False, tag: str = "", c: Ctx = Depends(ctx)):
    conds = [FunnelCard.workspace_id == c.ws_id, FunnelCard.deleted_at.is_(None)]
    if q:
        conds.append(or_(FunnelCard.name.ilike(f"%{q}%"), FunnelCard.firm.ilike(f"%{q}%")))
    if status:
        conds.append(FunnelCard.status == status)
    if stage:
        conds.append(FunnelCard.stage == stage)
    if priority:
        conds.append(FunnelCard.priority == priority)
    if type:
        conds.append(FunnelCard.investor_type == type)
    if tag:
        conds.append(FunnelCard.tags.any(tag))
    if needs_action:
        conds.append(FunnelCard.next_contact_date <= date.today())
    last = (select(CardEvent.card_id, func.max(CardEvent.created_at).label("last"))
            .where(CardEvent.workspace_id == c.ws_id).group_by(CardEvent.card_id).subquery())
    rows = c.db.execute(select(FunnelCard, last.c.last).outerjoin(last, last.c.card_id == FunnelCard.id)
                        .where(*conds).order_by(FunnelCard.stage, FunnelCard.position, FunnelCard.created_at)).all()
    return {"items": [out(r[0], r[1]) for r in rows]}


class CardIn(BaseModel):
    name: str | None = Field(None, max_length=200)
    firm: str | None = Field(None, max_length=300)
    investor_type: str | None = None
    priority: str | None = Field(None, pattern="^P[1-4]$")
    status: str | None = None
    stage: int | None = Field(None, ge=1, le=9)
    can_lead: str | None = Field(None, pattern="^(Yes|No|Maybe|)$")
    ticket_size: str | None = Field(None, max_length=100)
    agreed_size: str | None = Field(None, max_length=100)
    instrument: str | None = Field(None, max_length=16)
    contact_method: str | None = Field(None, max_length=16)
    email: str | None = Field(None, max_length=320)
    referrer: str | None = Field(None, max_length=300)
    next_contact_date: date | None = None
    call_at: datetime | None = None
    investor_timezone: str | None = Field(None, max_length=64)
    tags: list[str] | None = Field(None, max_length=20)
    shareable: bool | None = None
    starred: bool | None = None
    star_reason: str | None = Field(None, max_length=200)
    investor_id: str | None = None


def _validate(body: CardIn) -> None:
    if body.status is not None and body.status not in STATUSES:
        raise ApiError(422, "EF-VAL-002", "Unknown status")
    if body.investor_type and body.investor_type not in CARD_TYPES:
        raise ApiError(422, "EF-VAL-003", "Unknown investor type")


def _get(c: Ctx, cid: str) -> FunnelCard:
    try:
        card = c.db.get(FunnelCard, uuid.UUID(cid))
    except ValueError:
        card = None
    if card is None or card.workspace_id != c.ws_id or card.deleted_at:
        raise not_found("Card")
    return card


def _event(c: Ctx, card: FunnelCard, kind: str, body: str = "", **meta) -> None:
    c.db.add(CardEvent(workspace_id=c.ws_id, card_id=card.id, user_id=c.user.id, kind=kind, body=body, meta=meta))


def _reminder_at(d: date, tz: str) -> datetime:
    """TZ-04: reminders fire at 09:00 in the user's timezone on the day."""
    try:
        z = ZoneInfo(tz or "UTC")
    except Exception:
        z = ZoneInfo("UTC")
    return datetime.combine(d, time(9, 0), z).astimezone(UTC)


def set_next_contact(c: Ctx, card: FunnelCard, d: date | None, title: str | None = None) -> None:
    card.next_contact_date = d
    # Replace the open next-contact reminder for this card
    for r in c.db.scalars(select(Reminder).where(Reminder.card_id == card.id, Reminder.done_at.is_(None),
                                                 Reminder.notified_at.is_(None))):
        c.db.delete(r)
    if d:
        c.db.add(Reminder(workspace_id=c.ws_id, user_id=c.user.id, card_id=card.id,
                          title=title or f"Follow up with {card.name}", due_at=_reminder_at(d, c.user.timezone)))


def apply(c: Ctx, card: FunnelCard, body: CardIn) -> None:
    data = body.model_dump(exclude_unset=True)
    data.pop("investor_id", None)
    if "stage" in data and data["stage"] != card.stage:
        _event(c, card, "stage", f"{STAGES[card.stage - 1]} → {STAGES[data['stage'] - 1]}",
               old=card.stage, new=data["stage"])
    if "status" in data and data["status"] != card.status:
        _event(c, card, "status", f"{card.status} → {data['status']}", old=card.status, new=data["status"])
    if "call_at" in data and data["call_at"] and data["call_at"] != card.call_at:
        _event(c, card, "call", f"Call set for {data['call_at']:%d %b %Y %H:%M}")
        c.db.add(Reminder(workspace_id=c.ws_id, user_id=c.user.id, card_id=card.id,
                          title=f"Call with {card.name} tomorrow: prep your brief",
                          due_at=data["call_at"] - timedelta(hours=24)))
    if "next_contact_date" in data:
        set_next_contact(c, card, data.pop("next_contact_date"))
    if "starred" in data and data["starred"] != card.starred:
        reason = data.get("star_reason", card.star_reason) or ""
        _event(c, card, "star", ("Starred" + (f": {reason}" if reason else "")) if data["starred"] else "Unstarred")
    for k, v in data.items():
        setattr(card, k, v.strip() if isinstance(v, str) else v)


@router.post("")
def create_card(body: CardIn, c: Ctx = Depends(ctx)):
    c.require_editor()
    _validate(body)
    inv = None
    if body.investor_id:
        inv = c.db.get(Investor, uuid.UUID(body.investor_id))
        if inv is None or inv.suppressed:
            raise not_found("Investor")
        dup = c.db.scalar(select(FunnelCard).where(FunnelCard.workspace_id == c.ws_id, FunnelCard.investor_id == inv.id,
                                                   FunnelCard.deleted_at.is_(None)))
        if dup:
            return out(dup)
    if not (body.name or inv):
        raise ApiError(422, "EF-VAL-004", "Name is required")
    stage = body.stage or 1
    pos = (c.db.scalar(select(func.max(FunnelCard.position)).where(FunnelCard.workspace_id == c.ws_id,
                                                                   FunnelCard.stage == stage)) or 0) + 1
    card = FunnelCard(workspace_id=c.ws_id, name=body.name or inv.name, stage=stage, position=pos,
                      source="Database" if inv else "Manual", tags=[])
    if inv:
        card.investor_id, card.firm = inv.id, inv.current_firm or inv.company
        card.investor_type = TYPE_FROM_INVESTOR.get(inv.investor_type, "Other")
        card.investor_timezone = inv.timezone
    c.db.add(card)
    c.db.flush()
    apply(c, card, body)
    _event(c, card, "created", "Added to investor tracker", source=card.source)
    c.db.commit()
    return out(card)


@router.get("/{cid}")
def get_card(cid: str, c: Ctx = Depends(ctx)):
    card = _get(c, cid)
    events = c.db.scalars(select(CardEvent).where(CardEvent.card_id == card.id).order_by(CardEvent.created_at.desc())
                          .limit(200)).all()
    reminders = c.db.scalars(select(Reminder).where(Reminder.card_id == card.id, Reminder.done_at.is_(None))
                             .order_by(Reminder.due_at)).all()
    return {**out(card, events[0].created_at if events else None),
            "events": [{"id": str(e.id), "kind": e.kind, "body": e.body, "meta": e.meta, "created_at": e.created_at}
                       for e in events],
            "reminders": [{"id": str(r.id), "title": r.title, "due_at": r.due_at} for r in reminders]}


@router.patch("/{cid}")
def patch_card(cid: str, body: CardIn, c: Ctx = Depends(ctx)):
    c.require_editor()
    _validate(body)
    card = _get(c, cid)
    apply(c, card, body)
    c.db.commit()
    return out(card)


class MoveIn(BaseModel):
    stage: int = Field(ge=1, le=9)
    before_id: str | None = None  # place above this card; None = end of column


@router.post("/{cid}/move")
def move_card(cid: str, body: MoveIn, c: Ctx = Depends(ctx)):
    """Drag-and-drop between columns; fractional positions avoid renumbering the column."""
    c.require_editor()
    card = _get(c, cid)
    col = c.db.scalars(select(FunnelCard).where(FunnelCard.workspace_id == c.ws_id, FunnelCard.stage == body.stage,
                                                FunnelCard.deleted_at.is_(None), FunnelCard.id != card.id)
                       .order_by(FunnelCard.position)).all()
    idx = next((i for i, x in enumerate(col) if str(x.id) == body.before_id), len(col))
    prev = col[idx - 1].position if idx > 0 else (col[0].position - 2 if col else 0)
    nxt = col[idx].position if idx < len(col) else prev + 2
    apply(c, card, CardIn(stage=body.stage))
    card.position = (prev + nxt) / 2
    c.db.commit()
    return out(card)


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


@router.post("/{cid}/notes")
def add_note(cid: str, body: NoteIn, c: Ctx = Depends(ctx)):
    """AGT-06: notes are parsed; dates become reminders, other signals become one-click suggestions."""
    c.require_editor()
    card = _get(c, cid)
    _event(c, card, "note", body.body.strip())
    try:
        today = datetime.now(ZoneInfo(c.user.timezone or "UTC")).date()
    except Exception:
        today = date.today()
    parsed = parse_note(body.body, today)
    created = None
    if parsed["reminder_date"]:
        created = parsed["reminder_date"]
        if not card.next_contact_date or created < card.next_contact_date or card.next_contact_date < today:
            set_next_contact(c, card, created, f"{card.name}: {body.body.strip()[:80]}")
    c.db.commit()
    return {"reminder_date": created, "suggestions": parsed["suggestions"]}


class ContactIn(BaseModel):
    method: str = Field("Email", max_length=16)
    note: str = Field("", max_length=500)


@router.post("/{cid}/contacted")
def mark_contacted(cid: str, body: ContactIn, c: Ctx = Depends(ctx)):
    """Quick action from mobile: logs a touch (e.g. WhatsApp nudge sent, SEQ-07) and updates Last contacted."""
    c.require_editor()
    card = _get(c, cid)
    card.last_contacted_at = datetime.now(UTC)
    card.contact_method = card.contact_method or body.method
    if card.stage < 3:
        apply(c, card, CardIn(stage=3))
    _event(c, card, "contact", f"Contacted via {body.method}" + (f": {body.note}" if body.note else ""))
    c.db.commit()
    return out(card)


@router.delete("/{cid}")
def delete_card(cid: str, c: Ctx = Depends(ctx)):
    c.require_editor()
    card = _get(c, cid)
    card.deleted_at = datetime.now(UTC)  # soft delete (§18.1)
    c.db.commit()
    return {"ok": True}


# ---------- Export (own data only, watermarked; ASP-03) ----------

EXPORT_COLS = ["name", "firm", "investor_type", "priority", "status", "stage_label", "can_lead", "ticket_size",
               "agreed_size", "instrument", "contact_method", "email", "referrer", "last_contacted_at",
               "next_contact_date", "tags"]


@router.get("/export/csv")
def export_csv(c: Ctx = Depends(ctx)):
    cards = c.db.scalars(select(FunnelCard).where(FunnelCard.workspace_id == c.ws_id, FunnelCard.deleted_at.is_(None))
                         .order_by(FunnelCard.stage, FunnelCard.position)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(EXPORT_COLS)
    for card in cards:
        o = out(card)
        w.writerow([";".join(o[k]) if k == "tags" else (o[k] or "") for k in EXPORT_COLS])
    w.writerow([f"# exported by EasyFundraise workspace {c.ws_id} on {datetime.now(UTC):%Y-%m-%d}"])
    c.access("export", None, rows=len(cards))
    c.db.commit()
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=investor-funnel.csv"})


# ---------- Founder tracker import (CSV / XLSX) ----------

MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_IMPORT_ROWS = 5000


async def _read_upload(file: UploadFile) -> tuple[str, bytes]:
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise ApiError(413, "EF-IMP-001", "File is larger than 10MB")
    return file.filename or "upload.csv", data


def _columns(sh: ti.Sheet) -> list[dict]:
    """Every column that has a header, a suggested field, or any data (so unlabelled columns can be mapped)."""
    rows = sh.data_rows()[:200]
    width = max([len(sh.headers), *(len(r) for r in rows)], default=0)
    cols = []
    for i in range(width):
        h = sh.headers[i] if i < len(sh.headers) else ""
        if h or i in sh.mapping or any(i < len(r) and ti._s(r[i]) for r in rows):
            cols.append({"index": i, "header": h or f"Column {i + 1}", "field": sh.mapping.get(i)})
    return cols


@router.post("/import/preview")
async def import_preview(file: UploadFile, c: Ctx = Depends(ctx)):
    """Detects header rows and suggests a column mapping for every sheet; nothing is written."""
    c.require_editor()
    name, data = await _read_upload(file)
    try:
        sheets = ti.parse(name, data)
    except ValueError as e:
        raise ApiError(415, "EF-IMP-002", str(e)) from e
    except Exception as e:
        raise ApiError(422, "EF-IMP-003", "Could not read that file", "Is it a valid .xlsx or .csv?") from e
    ranked = sorted(sheets, key=ti.score, reverse=True)
    return {
        "filename": name,
        "fields": list(ti.FIELDS.keys()),
        "suggested_sheet": ranked[0].name if ranked and ti.score(ranked[0]) else None,
        "sheets": [{
            "name": sh.name, "header_row": sh.header_row, "rows": sum(1 for r in sh.data_rows() if ti.row_to_card(r, sh.mapping)) if sh.mapping else len(sh.data_rows()),
            "score": ti.score(sh),
            "columns": _columns(sh),
            "preview": [[ti._s(v) for v in r[:30]] for r in sh.data_rows()[:5]],
        } for sh in sheets],
    }


@router.post("/import/commit")
async def import_commit(file: UploadFile, sheet: str, mapping: str, update_existing: bool = True,
                        header_row: int | None = None, c: Ctx = Depends(ctx)):
    """Creates funnel cards from the confirmed mapping. Dedup: email -> LinkedIn -> name+firm. Rows that
    match a database investor (by LinkedIn or email) are linked so the card gets the full profile."""
    import json

    c.require_editor()
    try:
        m = {int(k): v for k, v in json.loads(mapping).items() if v in ti.FIELDS}
    except Exception as e:
        raise ApiError(422, "EF-IMP-004", "Invalid column mapping") from e
    if not ({"name", "firm"} & set(m.values())):
        raise ApiError(422, "EF-IMP-005", "Map at least a name or firm column")
    name, data = await _read_upload(file)
    sh = next((s for s in ti.parse(name, data) if s.name == sheet), None)
    if sh is None:
        raise ApiError(422, "EF-IMP-006", "Sheet not found in file")
    if header_row is not None:
        sh.header_row = header_row
    rows = [r for r in (ti.row_to_card(raw, m) for raw in sh.data_rows()[:MAX_IMPORT_ROWS]) if r]

    existing = c.db.scalars(select(FunnelCard).where(FunnelCard.workspace_id == c.ws_id,
                                                     FunnelCard.deleted_at.is_(None))).all()
    by_email = {x.email: x for x in existing if x.email}
    by_inv = {x.investor_id: x for x in existing if x.investor_id}
    by_name = {(norm_name(x.name), norm_name(x.firm)): x for x in existing}
    lis = {norm_linkedin(r["linkedin"]) for r in rows if r["linkedin"]}
    emails = {r["email"] for r in rows if r["email"]}
    inv_by_li = {i.linkedin: i for i in c.db.scalars(select(Investor).where(Investor.linkedin.in_(lis), ~Investor.suppressed))} if lis else {}
    inv_by_email = {i.email: i for i in c.db.scalars(select(Investor).where(Investor.email.in_(emails), ~Investor.suppressed))} if emails else {}

    created = updated = linked = 0
    pos: dict[int, float] = {}
    for r in rows:
        inv = inv_by_li.get(norm_linkedin(r["linkedin"])) if r["linkedin"] else None
        inv = inv or (inv_by_email.get(r["email"]) if r["email"] else None)
        card = (by_email.get(r["email"]) if r["email"] else None) or (by_inv.get(inv.id) if inv else None) \
            or by_name.get((norm_name(r["name"]), norm_name(r["firm"])))
        is_new = card is None
        if is_new:
            if r["stage"] not in pos:
                pos[r["stage"]] = (c.db.scalar(select(func.max(FunnelCard.position)).where(
                    FunnelCard.workspace_id == c.ws_id, FunnelCard.stage == r["stage"])) or 0)
            pos[r["stage"]] += 1
            card = FunnelCard(workspace_id=c.ws_id, name=r["name"], source="Import", tags=[], position=pos[r["stage"]],
                              stage=r["stage"])
            c.db.add(card)
            c.db.flush()
            created += 1
        elif not update_existing:
            continue
        else:
            updated += 1
        if inv and not card.investor_id:
            card.investor_id, card.investor_timezone = inv.id, card.investor_timezone or inv.timezone
            linked += 1
        for k in ("firm", "investor_type", "priority", "status", "stage", "can_lead", "ticket_size", "agreed_size",
                  "instrument", "contact_method", "email", "referrer"):
            if r[k]:
                setattr(card, k, r[k])
        card.tags = sorted(set(card.tags or []) | set(r["tags"]))
        if r["last_contacted"]:
            card.last_contacted_at = datetime.combine(r["last_contacted"], time(12), UTC)
        if r["next_contact"]:
            # Past dates show as "overdue" on the card; don't flood the inbox with a reminder for each one.
            if r["next_contact"] >= date.today():
                set_next_contact(c, card, r["next_contact"])
            else:
                card.next_contact_date = r["next_contact"]
        for note in r["notes"]:
            _event(c, card, "note", note, imported=True)
        if is_new:
            _event(c, card, "created", f"Imported from {name}", source="Import")
        if r["email"]:
            by_email[r["email"]] = card
        by_name[(norm_name(card.name), norm_name(card.firm))] = card
        if card.investor_id:
            by_inv[card.investor_id] = card
    c.db.add(Notification(workspace_id=c.ws_id, user_id=c.user.id, kind="import_done",
                          title=f"Imported {created + updated} investors into your investor tracker",
                          body=f"{created} new, {updated} updated, {linked} matched to the database.", link="/app/funnel"))
    c.audit("funnel.import", name, after={"created": created, "updated": updated, "linked": linked})
    c.db.commit()
    return {"created": created, "updated": updated, "linked": linked, "skipped": len(sh.data_rows()) - len(rows)}



# ---------- Mail on the card: latest Gmail thread, AI update, reply in thread ----------

@router.get("/{cid}/mail")
def card_mail(cid: str, c: Ctx = Depends(ctx)):
    from ..models import GmailAccount
    from ..services import card_mail

    card = _get(c, cid)
    to = card_mail.address(c.db, c.ws_id, card)
    acc = c.db.get(GmailAccount, c.user.id)
    base = {"to": to, "connected": bool(acc and acc.status == "connected"), "from": acc.email if acc else "",
            "signature": c.user.signature, "thread": [], "thread_id": "", "reply_to": "",
            "reply_all": {"to": [to] if to else [], "cc": []}, "subject": ""}
    if not to or not base["connected"]:
        return base
    msgs = card_mail.latest_thread(c.db, acc, to)
    c.db.commit()  # a refreshed access token
    if not msgs:
        return base
    ra = card_mail.reply_all(msgs, acc.email, to)
    return {**base, "thread": [card_mail.msg_out(m, acc.email) for m in msgs[-10:]], "thread_id": msgs[-1].thread_id,
            "reply_to": msgs[-1].rfc_message_id, "reply_all": {"to": ra["to"], "cc": ra["cc"]},
            "subject": ra["subject"]}


class MailDraftIn(BaseModel):
    ask: str = Field("", max_length=500)


@router.post("/{cid}/mail/draft")
def card_mail_draft(cid: str, body: MailDraftIn | None = None, c: Ctx = Depends(ctx)):
    from ..models import GmailAccount
    from ..services import card_mail
    from ..services.entitlements import rate_limit

    rate_limit(c.db, f"card-mail:{c.user.id}", 20, 60)
    card = _get(c, cid)
    to = card_mail.address(c.db, c.ws_id, card)
    acc = c.db.get(GmailAccount, c.user.id)
    thread = card_mail.latest_thread(c.db, acc, to) if to and acc and acc.status == "connected" else []
    out = card_mail.draft_reply(c.db, c.workspace, card, thread, body.ask if body else "", c.user.name)
    c.db.commit()
    return out


class MailSendIn(BaseModel):
    subject: str = Field("", max_length=300)  # ignored on a thread reply: it keeps "Re: <thread subject>"
    body: str = Field(min_length=1, max_length=10000)
    add_signature: bool = True
    thread_id: str = Field("", max_length=200)
    reply_to: str = Field("", max_length=500)  # Message-ID of the message being answered
    send_at: datetime | None = None  # later = held and sent from the founder's Gmail at that time


@router.post("/{cid}/mail/send")
def card_mail_send(cid: str, body: MailSendIn, c: Ctx = Depends(ctx)):
    from ..models import Email, GmailAccount
    from ..services import card_mail, mailer
    from ..services.entitlements import can

    c.require_editor()
    card = _get(c, cid)
    if not can(c.db, c.workspace, "send"):
        raise ApiError(402, "EF-TIER-030", "Upgrade to send emails", "Trial accounts can draft but not send.",
                       {"upgrade": True})
    to = card_mail.address(c.db, c.ws_id, card)
    if not to:
        raise ApiError(409, "EF-MAIL-020", "Add this investor's email first", "", {"needs_email": True})
    acc = c.db.get(GmailAccount, c.user.id)
    if acc is None or acc.status != "connected":
        raise ApiError(409, "EF-SEQ-007", "Connect Gmail to send", "Emails go out from your own Gmail.",
                       {"needs_gmail": True})
    now = datetime.now(UTC)
    text = body.body.strip()
    if body.add_signature and c.user.signature.strip() and not text.endswith(c.user.signature.strip()):
        text = f"{text}\n\n{c.user.signature.strip()}"
    at = card_mail.when(body.send_at, now)
    recipients, cc, subject, thread_id, reply_to = [to], [], body.subject.strip(), "", ""
    if body.thread_id:  # reply all, worked out from the thread itself rather than trusted from the browser
        msgs = card_mail.latest_thread(c.db, acc, to)
        if msgs and msgs[-1].thread_id == body.thread_id:
            ra = card_mail.reply_all(msgs, acc.email, to)
            recipients, cc, subject = ra["to"] or [to], ra["cc"], ra["subject"] or subject
            thread_id, reply_to = msgs[-1].thread_id, msgs[-1].rfc_message_id
    if not subject:
        raise ApiError(422, "EF-MAIL-021", "Add a subject", "")
    em = Email(workspace_id=c.ws_id, card_id=card.id, user_id=c.user.id, to_email=", ".join(recipients),
               cc=", ".join(cc), step=1, hook="reply", subject=subject, body=text, status="scheduled",
               scheduled_for=at, gmail_thread_id=thread_id, rfc_message_id=reply_to)
    c.db.add(em)
    c.db.flush()
    if at > now:
        _event(c, card, "email", f"Email scheduled for {at:%d %b %Y %H:%M} UTC: {em.subject}")
    else:
        mailer._send_one(c.db, em, now)
    c.audit("card.mail", str(card.id), after={"status": em.status})
    c.db.commit()
    return {"id": str(em.id), "status": em.status, "scheduled_for": em.scheduled_for, "sent_at": em.sent_at,
            "error": em.error}


@router.get("/{cid}/summary")
def card_summary(cid: str, c: Ctx = Depends(ctx)):
    """Where this investor stands and the founder's next step, for the top of the card."""
    from ..services import card_summary as cs

    card = _get(c, cid)
    res = cs.summary(c.db, c.workspace, card)
    c.db.commit()  # AI usage
    return res
