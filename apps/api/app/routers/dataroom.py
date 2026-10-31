"""§14 Data room: one-page company site at /r/<slug> built from the Company Profile, with access modes
(DR-02), per-viewer analytics (DR-03), gated documents, version history (DR-04) and noindex by default (DR-05)."""

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response, UploadFile
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import Ctx, client_ip, ctx
from ..errors import ApiError, not_found
from ..models import (
    CompanyProfile,
    DataRoom,
    DataRoomDoc,
    DataRoomLink,
    DataRoomView,
    FunnelCard,
    Notification,
    WorkspaceMember,
)
from ..services import ai, room_fill
from ..services.crypto import password_hash, password_ok
from ..services.entitlements import rate_limit

router = APIRouter(prefix="/data-room", tags=["data-room"])
public = APIRouter(prefix="/public/rooms", tags=["data-room-public"])
SECTION_TYPES = ("problem", "solution", "product", "traction", "market", "why_now", "business_model", "team", "ask",
                 "use_of_funds", "faq", "text")
MAX_DOC = 20 * 1024 * 1024


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "room"


def default_sections(p: CompanyProfile | None) -> list[dict]:
    """The investor-ready order: story first, then market and model, team, then the ask."""
    return [
        {"id": "problem", "type": "problem", "title": "The problem", "body": ""},
        {"id": "solution", "type": "solution", "title": "Our solution", "body": ""},
        {"id": "product", "type": "product", "title": "Product", "body": (p.one_liner if p else ""), "links": []},
        {"id": "traction", "type": "traction", "title": "Traction", "body": (p.traction if p else ""), "metrics": []},
        {"id": "market", "type": "market", "title": "Market opportunity", "body": "", "metrics": []},
        {"id": "why_now", "type": "why_now", "title": "Why now", "body": ""},
        {"id": "business_model", "type": "business_model", "title": "Business model",
         "body": (p.business_model if p else "")},
        {"id": "team", "type": "team", "title": "Team", "body": "", "people": []},
        {"id": "ask", "type": "ask", "title": "The ask", "body": "",
         "metrics": [{"label": "Raising", "value": (p.round_size if p else "") or ""},
                     {"label": "Instrument", "value": (p.instrument if p else "") or ""}]},
        {"id": "use_of_funds", "type": "use_of_funds", "title": "Use of funds", "body": "", "items": []},
        {"id": "faq", "type": "faq", "title": "FAQ", "items": []},
    ]


def upgrade_content(content: dict, p: CompanyProfile | None) -> bool:
    """Rooms made before the full section set get the new sections slotted into place, once."""
    if content.get("layout", 1) >= 2:
        return False
    secs = list(content.get("sections", []))
    have = {s.get("id") for s in secs}
    for i, d in enumerate(default_sections(p)):
        if d["id"] in have:
            continue
        before = [x["id"] for x in default_sections(p)[:i]]
        at = max((j + 1 for j, s in enumerate(secs) if s.get("id") in before), default=0)
        secs.insert(at, d)
    content["sections"] = secs
    content["layout"] = 2
    return True


def default_content(p: CompanyProfile | None) -> dict:
    name = (p.company_name if p else "") or "Our company"
    return {
        "layout": 2,
        "hero": {"title": name, "one_liner": (p.one_liner if p else ""), "round": (p.round_size if p else ""),
                 "instrument": (p.instrument if p else ""), "cta_label": "Book a call", "cta_url": ""},
        "sections": default_sections(p),
    }


def ensure_room(db, ws_id, ws_name: str) -> DataRoom:
    """Every workspace gets a draft room the first time it is needed (opening the page or uploading a deck)."""
    room = db.get(DataRoom, ws_id)
    p = db.get(CompanyProfile, ws_id)
    if room is None:
        base = slugify((p.company_name if p else "") or ws_name)
        slug = base
        while db.scalar(select(func.count()).select_from(DataRoom).where(DataRoom.slug == slug)):
            slug = f"{base}-{secrets.token_hex(2)}"
        room = DataRoom(workspace_id=ws_id, slug=slug, content=default_content(p), versions=[])
        db.add(room)
        db.commit()
    elif (room.content or {}).get("layout", 1) < 2:
        content = dict(room.content or {})
        upgrade_content(content, p)
        room.content = content
        db.commit()
    return room


def _room(c: Ctx) -> DataRoom:
    return ensure_room(c.db, c.ws_id, c.workspace.name)


def room_out(room: DataRoom) -> dict:
    return {"slug": room.slug, "published": room.published, "access": room.access, "has_password": bool(room.password_hash),
            "indexable": room.indexable, "content": room.content, "updated_at": room.updated_at,
            "versions": [{"at": v["at"]} for v in (room.versions or [])],
            "url": f"{get_settings().web_origin}/r/{room.slug}"}


@router.get("")
def get_room(c: Ctx = Depends(ctx)):
    room = _room(c)
    docs = c.db.scalars(select(DataRoomDoc).where(DataRoomDoc.workspace_id == c.ws_id).order_by(DataRoomDoc.created_at))
    links = c.db.execute(select(DataRoomLink, FunnelCard.name).outerjoin(FunnelCard, FunnelCard.id == DataRoomLink.card_id)
                         .where(DataRoomLink.workspace_id == c.ws_id).order_by(DataRoomLink.created_at.desc()).limit(200)).all()
    base = f"{get_settings().web_origin}/r/{room.slug}"
    docs = list(docs)
    return {**room_out(room), "completeness": room_fill.completeness(room.content or {}, len(docs)),
            "docs": [{"id": str(d.id), "label": d.label, "filename": d.filename, "size": d.size, "gated": d.gated} for d in docs],
            "links": [{"id": str(lk.id), "label": lk.label or name or "Link", "card_id": str(lk.card_id) if lk.card_id else None,
                       "url": f"{base}?k={lk.token}", "expires_at": lk.expires_at, "revoked": lk.revoked_at is not None}
                      for lk, name in links]}


class RoomIn(BaseModel):
    slug: str | None = Field(None, min_length=3, max_length=60, pattern="^[a-z0-9-]+$")
    published: bool | None = None
    access: str | None = Field(None, pattern="^(public|password|email|magic)$")
    password: str | None = Field(None, min_length=6, max_length=200)
    indexable: bool | None = None
    content: dict | None = None


@router.put("")
def put_room(body: RoomIn, c: Ctx = Depends(ctx)):
    c.require_editor()
    room = _room(c)
    if body.slug and body.slug != room.slug:
        if c.db.scalar(select(func.count()).select_from(DataRoom).where(DataRoom.slug == body.slug)):
            raise ApiError(409, "EF-DR-001", "That address is taken")
        room.slug = body.slug
    if body.content is not None:
        secs = body.content.get("sections", [])
        if not isinstance(secs, list) or len(secs) > 30 or any(s.get("type") not in SECTION_TYPES for s in secs):
            raise ApiError(422, "EF-DR-002", "Invalid sections")
        room.versions = ([{"at": datetime.now(UTC).isoformat(), "content": room.content}] + (room.versions or []))[:10]
        room.content = {**body.content, "layout": 2}
    if body.password:
        room.password_hash = password_hash(body.password)
    for k in ("published", "access", "indexable"):
        v = getattr(body, k)
        if v is not None:
            setattr(room, k, v)
    if room.access == "password" and not room.password_hash:
        raise ApiError(422, "EF-DR-003", "Set a password for password access")
    c.audit("dataroom.update", room.slug)
    c.db.commit()
    return room_out(room)


@router.post("/restore/{idx}")
def restore(idx: int, c: Ctx = Depends(ctx)):
    c.require_editor()
    room = _room(c)
    vs = room.versions or []
    if not 0 <= idx < len(vs):
        raise not_found("Version")
    cur = {"at": datetime.now(UTC).isoformat(), "content": room.content}
    room.content = vs[idx]["content"]
    room.versions = ([cur] + vs[:idx] + vs[idx + 1:])[:10]
    c.db.commit()
    return room_out(room)


@router.post("/docs")
async def upload_doc(file: UploadFile, label: str = "", gated: bool = True, c: Ctx = Depends(ctx)):
    c.require_editor()
    data = await file.read(MAX_DOC + 1)
    if len(data) > MAX_DOC:
        raise ApiError(413, "EF-DR-010", "Documents must be 20MB or smaller")
    ctype = file.content_type or "application/octet-stream"
    allowed = ("application/pdf", "image/", "text/csv", "application/vnd.openxmlformats", "application/vnd.ms-excel")
    if not ctype.startswith(allowed):
        raise ApiError(415, "EF-DR-011", "Upload a PDF, spreadsheet or image")
    if ctype == "application/pdf" and not data.startswith(b"%PDF"):
        raise ApiError(415, "EF-DR-011", "That file is not a valid PDF")
    d = DataRoomDoc(workspace_id=c.ws_id, label=(label or file.filename or "Document")[:200],
                    filename=(file.filename or "document")[:200], content_type=ctype, size=len(data), data=data, gated=gated)
    c.db.add(d)
    c.db.commit()
    return {"id": str(d.id)}


@router.delete("/docs/{did}")
def delete_doc(did: str, c: Ctx = Depends(ctx)):
    c.require_editor()
    d = c.db.get(DataRoomDoc, uuid.UUID(did))
    if d is None or d.workspace_id != c.ws_id:
        raise not_found("Document")
    c.db.delete(d)
    c.db.commit()
    return {"ok": True}


class LinkIn(BaseModel):
    card_id: str | None = None
    label: str = Field("", max_length=200)
    expires_days: int | None = Field(None, ge=1, le=365)


def make_link(db: Session, ws_id, card_id=None, label: str = "", days: int | None = None) -> DataRoomLink:
    lk = DataRoomLink(workspace_id=ws_id, token=secrets.token_urlsafe(16), card_id=card_id, label=label,
                      expires_at=datetime.now(UTC) + timedelta(days=days) if days else None)
    db.add(lk)
    db.flush()
    return lk


@router.post("/links")
def create_link(body: LinkIn, c: Ctx = Depends(ctx)):
    c.require_editor()
    room = _room(c)
    card_id = None
    if body.card_id:
        card = c.db.get(FunnelCard, uuid.UUID(body.card_id))
        if card is None or card.workspace_id != c.ws_id:
            raise not_found("Card")
        existing = c.db.scalar(select(DataRoomLink).where(DataRoomLink.card_id == card.id, DataRoomLink.revoked_at.is_(None)))
        if existing:
            return {"id": str(existing.id), "url": f"{get_settings().web_origin}/r/{room.slug}?k={existing.token}"}
        card_id = card.id
    lk = make_link(c.db, c.ws_id, card_id, body.label, body.expires_days)
    c.db.commit()
    return {"id": str(lk.id), "url": f"{get_settings().web_origin}/r/{room.slug}?k={lk.token}"}


@router.delete("/links/{lid}")
def revoke_link(lid: str, c: Ctx = Depends(ctx)):
    c.require_editor()
    lk = c.db.get(DataRoomLink, uuid.UUID(lid))
    if lk is None or lk.workspace_id != c.ws_id:
        raise not_found("Link")
    lk.revoked_at = datetime.now(UTC)
    c.db.commit()
    return {"ok": True}


@router.get("/views")
def views(card_id: str | None = None, c: Ctx = Depends(ctx)):
    q = select(DataRoomView, FunnelCard.name).outerjoin(FunnelCard, FunnelCard.id == DataRoomView.card_id).where(
        DataRoomView.workspace_id == c.ws_id)
    if card_id:
        q = q.where(DataRoomView.card_id == uuid.UUID(card_id))
    rows = c.db.execute(q.order_by(DataRoomView.started_at.desc()).limit(200)).all()
    return {"items": [{"id": str(v.id), "viewer": name or v.viewer_email or "Anonymous", "card_id": str(v.card_id) if v.card_id else None,
                       "seconds": v.seconds, "sections": v.sections, "downloads": v.downloads, "started_at": v.started_at}
                      for v, name in rows]}


class PolishIn(BaseModel):
    text: str = Field(min_length=10, max_length=4000)
    section: str = Field("text", max_length=40)


@router.post("/polish")
def polish(body: PolishIn, c: Ctx = Depends(ctx)):
    """DR-04 "polish this section": tighten the founder's text without adding claims."""
    rate_limit(c.db, f"polish:{c.user.id}", 10, 60)
    out, engine = ai.json_call(c.db, c.workspace, "polish",
                               "Rewrite one section of a startup's investor page: clearer, shorter, concrete. Keep every "
                               "fact and number exactly; add nothing new.",
                               f"Section: {body.section}\n\n{body.text}",
                               {"type": "object", "additionalProperties": False, "required": ["text"],
                                "properties": {"text": {"type": "string"}}}, max_tokens=1500, effort="low")
    c.db.commit()
    if not out:
        raise ApiError(409, "EF-AI-001", "AI polish isn't available on your plan")
    return {"text": out["text"], "engine": engine}


# ---------------- public ----------------


def _sign(slug: str, val: str) -> str:
    return hmac.new(get_settings().secret_key.encode(), f"{slug}|{val}".encode(), hashlib.sha256).hexdigest()[:32]


def _cookie_name(slug: str) -> str:
    return f"ef_room_{hashlib.sha1(slug.encode()).hexdigest()[:10]}"


def _viewer(request: Request, room: DataRoom, db: Session, k: str = "") -> tuple[bool, str, DataRoomLink | None]:
    """Returns (allowed, viewer identity, link)."""
    if k:
        lk = db.scalar(select(DataRoomLink).where(DataRoomLink.token == k[:40], DataRoomLink.workspace_id == room.workspace_id))
        if lk and not lk.revoked_at and (not lk.expires_at or lk.expires_at > datetime.now(UTC)):
            return True, f"link:{lk.id}", lk
    raw = request.cookies.get(_cookie_name(room.slug), "")
    if "." in raw:
        val, sig = raw.rsplit(".", 1)
        if hmac.compare_digest(sig, _sign(room.slug, val)):
            lk = None
            if val.startswith("link:"):
                lk = db.get(DataRoomLink, uuid.UUID(val[5:]))
                if lk is None or lk.revoked_at:
                    return False, "", None
            return True, val, lk
    if room.access == "public":
        return True, "", None
    return False, "", None


def _public_room(db: Session, slug: str) -> DataRoom:
    room = db.scalar(select(DataRoom).where(DataRoom.slug == slug[:80]))
    if room is None or not room.published:
        raise not_found("Data room")
    return room


@public.get("/{slug}/meta")
def room_meta(slug: str, db: Session = Depends(get_db)):
    """For the page <head>: title and whether search engines may index (DR-05). Does not log a view."""
    room = _public_room(db, slug)
    hero = room.content.get("hero", {})
    locked = room.access != "public"
    return {"title": hero.get("title", ""), "one_liner": "" if locked else hero.get("one_liner", ""),
            "indexable": room.indexable and not locked}


@public.get("/{slug}")
def view_room(slug: str, request: Request, response: Response, k: str = "", db: Session = Depends(get_db)):
    rate_limit(db, f"room:{client_ip(request)}", 120, 60)
    room = _public_room(db, slug)
    ok, who, lk = _viewer(request, room, db, k)
    hero = room.content.get("hero", {})
    if not ok:
        return {"locked": True, "access": room.access, "title": hero.get("title", ""), "indexable": False}
    if k and lk:
        response.set_cookie(_cookie_name(room.slug), f"{who}.{_sign(room.slug, who)}", max_age=30 * 86400,
                            httponly=True, samesite="lax", secure=not get_settings().env == "dev")
    email = who[6:] if who.startswith("email:") else ""
    card_id = lk.card_id if lk else None
    if email and not card_id:  # DR-02: email-gated viewers are matched to funnel investors
        card_id = db.scalar(select(FunnelCard.id).where(FunnelCard.workspace_id == room.workspace_id,
                                                        func.lower(FunnelCard.email) == email.lower(),
                                                        FunnelCard.deleted_at.is_(None)).limit(1))
    view = DataRoomView(workspace_id=room.workspace_id, card_id=card_id, link_id=lk.id if lk else None, viewer_email=email)
    db.add(view)
    if card_id:
        card = db.get(FunnelCard, card_id)
        owner = db.scalar(select(WorkspaceMember.user_id).where(WorkspaceMember.workspace_id == room.workspace_id,
                                                                WorkspaceMember.role == "owner").limit(1))
        recent = db.scalar(select(func.count()).select_from(Notification).where(
            Notification.workspace_id == room.workspace_id, Notification.kind == "data_room",
            Notification.link == f"/app/funnel/{card_id}", Notification.created_at > datetime.now(UTC) - timedelta(hours=12)))
        if owner and not recent:
            db.add(Notification(workspace_id=room.workspace_id, user_id=owner, kind="data_room",
                                title=f"{card.name} is viewing your data room", link=f"/app/funnel/{card_id}"))
    db.commit()
    docs = db.scalars(select(DataRoomDoc).where(DataRoomDoc.workspace_id == room.workspace_id).order_by(DataRoomDoc.created_at))
    return {"locked": False, "content": room.content, "indexable": room.indexable and room.access == "public",
            "view_id": str(view.id),
            "docs": [{"id": str(d.id), "label": d.label, "filename": d.filename, "size": d.size} for d in docs]}


class UnlockIn(BaseModel):
    password: str | None = Field(None, max_length=200)
    email: EmailStr | None = None


@public.post("/{slug}/unlock")
def unlock(slug: str, body: UnlockIn, request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit(db, f"room-unlock:{client_ip(request)}", 10, 300)
    room = _public_room(db, slug)
    if room.access == "password":
        if not body.password or not password_ok(body.password, room.password_hash):
            raise ApiError(403, "EF-DR-020", "Wrong password")
        val = f"pw:{secrets.token_hex(4)}"
        if body.email:
            val = f"email:{body.email.lower()}"
    elif room.access == "email":
        if not body.email:
            raise ApiError(422, "EF-DR-021", "Enter your email to view")
        val = f"email:{body.email.lower()}"
    elif room.access == "public":
        return {"ok": True}
    else:
        raise ApiError(403, "EF-DR-022", "This data room needs a personal link")
    response.set_cookie(_cookie_name(room.slug), f"{val}.{_sign(room.slug, val)}", max_age=30 * 86400, httponly=True,
                        samesite="lax", secure=get_settings().env != "dev")
    return {"ok": True}


class PingIn(BaseModel):
    view_id: str
    seconds: int = Field(ge=0, le=600)
    sections: dict[str, int] = {}


@public.post("/{slug}/ping")
def ping(slug: str, body: PingIn, request: Request, db: Session = Depends(get_db)):
    """DR-03: viewer heartbeat with seconds spent per section since the last ping."""
    rate_limit(db, f"room-ping:{client_ip(request)}", 120, 60)
    room = _public_room(db, slug)
    try:
        v = db.get(DataRoomView, uuid.UUID(body.view_id))
    except ValueError:
        v = None
    if v is None or v.workspace_id != room.workspace_id or v.started_at < datetime.now(UTC) - timedelta(hours=6):
        return {"ok": False}
    v.seconds += min(body.seconds, 600)
    secs = dict(v.sections or {})
    for k, n in list(body.sections.items())[:40]:
        secs[k[:40]] = secs.get(k[:40], 0) + max(0, min(int(n), 600))
    v.sections, v.last_ping_at = secs, datetime.now(UTC)
    db.commit()
    return {"ok": True}


@public.get("/{slug}/docs/{did}")
def download(slug: str, did: str, request: Request, view: str = "", db: Session = Depends(get_db)):
    rate_limit(db, f"room-doc:{client_ip(request)}", 30, 60)
    room = _public_room(db, slug)
    ok, who, _ = _viewer(request, room, db)
    d = db.get(DataRoomDoc, uuid.UUID(did))
    if d is None or d.workspace_id != room.workspace_id:
        raise not_found("Document")
    if not ok or (d.gated and not who):
        raise ApiError(403, "EF-DR-030", "Open the data room from your personal link or enter your email first")
    if view:
        try:
            v = db.get(DataRoomView, uuid.UUID(view))
        except ValueError:
            v = None
        if v and v.workspace_id == room.workspace_id:
            v.downloads = [*(v.downloads or []), {"doc": d.label, "at": datetime.now(UTC).isoformat()}][:50]
            db.commit()
    return RawResponse(d.data, media_type=d.content_type, headers={
        "Content-Disposition": f'attachment; filename="{re.sub(r"[^A-Za-z0-9._-]", "_", d.filename)}"',
        "Cache-Control": "private, no-store"})
