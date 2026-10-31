"""Gmail connection (AUTH-02/03, progressive consent), open-pixel tracking (TRK-01) and the outreach
dashboard (TRK-04)."""

import base64
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import Ctx, ctx
from ..errors import ApiError
from ..models import Email, EmailEvent, FunnelCard, GmailAccount, Sequence
from ..services.calendar import SCOPE as CAL_SCOPE
from ..services.calendar import connected as calendar_connected
from ..services.entitlements import usage
from ..services.gmail import SCOPES, client_for, store_tokens
from ..services.mailer import FOREVER, daily_cap, safety, sent_metric, user_day
from .auth import GOOGLE_AUTH, GOOGLE_TOKEN, google_reason, safe_next

router = APIRouter(tags=["outreach"])
public = APIRouter(tags=["tracking"])
GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


def gmail_out(acc: GmailAccount | None, db: Session, c: Ctx) -> dict:
    if acc is None:
        return {"connected": False, "fake_available": get_settings().gmail_fake, "calendar": False}
    now = datetime.now(UTC)
    cap = daily_cap(db, c.workspace, acc, now)
    return {"connected": acc.status == "connected", "status": acc.status, "email": acc.email, "mode": acc.mode,
            "connected_at": acc.connected_at, "sent_today": usage(db, c.workspace, sent_metric(c.user.id), user_day(c.user, now)),
            "daily_cap": cap, "fake_available": get_settings().gmail_fake, "calendar": calendar_connected(acc),
            "paused_until": acc.paused_until if acc.paused_until and acc.paused_until > now else None,
            "paused_reason": acc.paused_reason if acc.paused_until and acc.paused_until > now else "",
            "burst_max": safety(db)["burst_max"], "burst_window_minutes": safety(db)["burst_window_minutes"]}


@router.post("/gmail/pause")
def gmail_pause(c: Ctx = Depends(ctx)):
    """Stops every email from leaving this user's Gmail (scheduled ones wait) until they resume."""
    acc = c.db.get(GmailAccount, c.user.id)
    if acc is None:
        raise ApiError(404, "EF-MAIL-004", "Gmail is not connected")
    acc.paused_until, acc.paused_reason = FOREVER, "Paused by you. Nothing sends until you resume."
    c.audit("gmail.pause", c.user.email)
    c.db.commit()
    return gmail_out(acc, c.db, c)


@router.post("/gmail/resume")
def gmail_resume(c: Ctx = Depends(ctx)):
    acc = c.db.get(GmailAccount, c.user.id)
    if acc is None:
        raise ApiError(404, "EF-MAIL-004", "Gmail is not connected")
    before = acc.paused_reason
    acc.paused_until, acc.paused_reason = None, ""
    c.audit("gmail.resume", c.user.email, before={"reason": before})
    c.db.commit()
    return gmail_out(acc, c.db, c)


@router.get("/gmail")
def gmail_status(c: Ctx = Depends(ctx)):
    return gmail_out(c.db.get(GmailAccount, c.user.id), c.db, c)


@router.get("/gmail/connect")
def gmail_connect(request: Request, next: str = "/app/settings?gmail=connected", calendar: bool = False,
                  c: Ctx = Depends(ctx)):
    """AUTH-02: Gmail scopes are requested at sign-up or later, when the user first wants to send.
    calendar=1 adds read-only Google Calendar so the Raise Agent can see investor meetings."""
    s = get_settings()
    next = safe_next(next, "/app/settings?gmail=connected")
    if s.gmail_fake:
        acc = c.db.get(GmailAccount, c.user.id) or GmailAccount(user_id=c.user.id, email=c.user.email)
        acc.mode, acc.status, acc.email = "fake", "connected", c.user.email
        if calendar and "calendar" not in (acc.scopes or ""):
            acc.scopes = f"{acc.scopes or ''} {CAL_SCOPE}".strip()
        c.db.merge(acc)
        c.db.commit()
        return RedirectResponse(f"{s.web_origin}{next}")
    if not s.google_client_id:
        raise ApiError(503, "EF-MAIL-001", "Gmail connection is not configured")
    state = secrets.token_urlsafe(24)
    params = dict(client_id=s.google_client_id, response_type="code",
                  scope=f"{SCOPES} {CAL_SCOPE}" if calendar else SCOPES, access_type="offline",
                  include_granted_scopes="true", prompt="consent", login_hint=c.user.email, state=state,
                  redirect_uri=f"{s.web_origin}/api/gmail/callback")
    resp = RedirectResponse(f"{GOOGLE_AUTH}?{urlencode(params)}")
    resp.set_cookie("ef_gmail_state", state, max_age=600, httponly=True, samesite="lax", secure=s.env != "dev")
    resp.set_cookie("ef_gmail_next", next, max_age=600, httponly=True, samesite="lax", secure=s.env != "dev")
    return resp


@router.get("/gmail/callback")
def gmail_callback(request: Request, code: str = "", state: str = "", error: str = "", c: Ctx = Depends(ctx)):
    s = get_settings()
    if error:
        return RedirectResponse(f"{s.web_origin}/app/settings?gmail=denied")
    if not code or state != request.cookies.get("ef_gmail_state"):
        raise ApiError(400, "EF-MAIL-002", "Gmail connection failed", "Invalid OAuth state. Please try again.")
    r = httpx.post(GOOGLE_TOKEN, data=dict(code=code, client_id=s.google_client_id, client_secret=s.google_client_secret,
                                           grant_type="authorization_code", redirect_uri=f"{s.web_origin}/api/gmail/callback"),
                   timeout=15)
    if r.status_code != 200:
        raise ApiError(400, "EF-MAIL-003", "Gmail connection failed", f"Google rejected the code: {google_reason(r)}")
    j = r.json()
    granted = j.get("scope", "")
    if "gmail.send" not in granted:
        return RedirectResponse(f"{s.web_origin}/app/settings?gmail=missing_scope")
    store_tokens(c.db, c.user.id, c.user.email, j)
    c.audit("gmail.connect", c.user.email)
    c.db.commit()
    resp = RedirectResponse(f"{s.web_origin}{safe_next(request.cookies.get('ef_gmail_next', ''), '/app/settings?gmail=connected')}")
    resp.delete_cookie("ef_gmail_state")
    resp.delete_cookie("ef_gmail_next")
    return resp


@router.delete("/gmail")
def gmail_disconnect(c: Ctx = Depends(ctx)):
    acc = c.db.get(GmailAccount, c.user.id)
    if acc:
        client_for(c.db, acc).revoke()
        c.db.delete(acc)
        c.audit("gmail.disconnect", c.user.email)
        c.db.commit()
    return {"ok": True}


# ---------------- tracking (TRK-01) ----------------

PREFETCH = ("googleimageproxy", "yahoomailproxy")


@public.get("/t/o/{token}.gif")
def open_pixel(token: str, request: Request, db: Session = Depends(get_db)):
    em = db.scalar(select(Email).where(Email.open_token == token[:40]))
    if em and em.sent_at:
        now = datetime.now(UTC)
        ua = request.headers.get("user-agent", "").lower()
        proxy = any(p in ua for p in PREFETCH)
        # Ignore immediate fetches right after sending (sender's own Sent view / security scanners) and count
        # image-proxy fetches only once (Apple MPP / Gmail proxy prefetch).
        if now - em.sent_at > timedelta(seconds=30) and not (proxy and em.open_count > 0):
            em.open_count += 1
            em.opened_at = em.opened_at or now
            db.add(EmailEvent(workspace_id=em.workspace_id, email_id=em.id, kind="open", meta={"proxy": proxy}))
            if em.open_count == 3 and em.card_id and not em.replied_at:
                from ..services.mailer import notify

                card = db.get(FunnelCard, em.card_id)
                notify(db, em.workspace_id, em.user_id, "hot", f"{card.name} opened your email 3 times",
                       "Good moment for a short nudge.", f"/app/funnel/{card.id}")
            db.commit()
    return Response(GIF, media_type="image/gif", headers={"Cache-Control": "no-store, private", "Pragma": "no-cache"})


# ---------------- dashboard (TRK-04) ----------------


@router.get("/outreach/stats")
def stats(days: int = 90, c: Ctx = Depends(ctx)):
    since = datetime.now(UTC) - timedelta(days=min(days, 365))
    base = [Email.workspace_id == c.ws_id, Email.status == "sent", Email.sent_at > since]

    def agg(group):
        cols = [func.count(), func.count(Email.opened_at), func.count(Email.replied_at),
                func.sum(case((Email.reply_kind == "positive", 1), else_=0)), func.count(Email.bounced_at)]
        q = select(group, *cols).where(*base)
        if group is Sequence.persona:
            q = q.join(Sequence, Sequence.id == Email.sequence_id)
        return [{"key": str(r[0] or "update"), "sent": r[1], "opened": r[2], "replied": r[3], "positive": int(r[4] or 0),
                 "bounced": r[5], "open_rate": round(r[2] / r[1], 3) if r[1] else 0,
                 "reply_rate": round(r[3] / r[1], 3) if r[1] else 0}
                for r in c.db.execute(q.group_by(group).order_by(func.count().desc())).all()]

    total = agg(Email.workspace_id)
    queued = c.db.scalar(select(func.count()).select_from(Email).where(Email.workspace_id == c.ws_id,
                                                                      Email.status == "scheduled"))
    recent = c.db.execute(select(Email, FunnelCard.name).outerjoin(FunnelCard, FunnelCard.id == Email.card_id)
                          .where(Email.workspace_id == c.ws_id, Email.status.in_(["sent", "scheduled", "failed"]))
                          .order_by(func.coalesce(Email.sent_at, Email.scheduled_for).desc()).limit(50)).all()
    return {
        "total": total[0] if total else {"sent": 0, "opened": 0, "replied": 0, "positive": 0, "bounced": 0,
                                         "open_rate": 0, "reply_rate": 0},
        "queued": queued, "by_step": agg(Email.step), "by_hook": agg(Email.hook), "by_persona": agg(Sequence.persona),
        "by_hour": agg(func.extract("hour", Email.sent_at)),
        "recent": [{"id": str(e.id), "to": name or e.to_email, "card_id": str(e.card_id) if e.card_id else None,
                    "subject": e.subject, "step": e.step, "status": e.status, "sent_at": e.sent_at,
                    "scheduled_for": e.scheduled_for, "opened": e.open_count, "reply": e.reply_kind, "error": e.error}
                   for e, name in recent],
    }
