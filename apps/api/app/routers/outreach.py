"""Gmail connection (AUTH-02/03, progressive consent), open-pixel tracking (TRK-01) and the outreach
dashboard (TRK-04)."""

import base64
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import Ctx, ctx
from ..errors import ApiError
from ..models import Email, EmailEvent, FunnelCard, GmailAccount, Sequence
from ..services import playbook, test_investors
from ..services.agent import money_talk
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


# ---------------- email playbook + round/progress update ----------------


def playbook_out(c: Ctx) -> dict:
    pb = playbook.get(c.workspace)
    texts = [e["message"] for e in pb["emails"]] + pb["strengths"] + [pb["update"]]
    return {**pb, "unsent": len(playbook.unsent(c.db, c.ws_id)), "money_warning": money_talk(*texts, pb["ask"])}


class EmailPlanIn(BaseModel):
    focus: str | None = Field(None, max_length=80)
    message: str | None = Field(None, max_length=playbook.MAX_MESSAGE)


class PlaybookIn(BaseModel):
    emails: list[EmailPlanIn] | None = Field(None, max_length=3)
    ask: str | None = Field(None, max_length=playbook.MAX_ASK)
    strengths: list[str] | None = Field(None, max_length=playbook.MAX_STRENGTHS)


def _merged(c: Ctx, body: PlaybookIn | None) -> dict:
    pb = playbook.get(c.workspace)
    if body is None:
        return pb
    return playbook.merge(pb, [e.model_dump() for e in body.emails] if body.emails is not None else None, body.ask,
                          [x[:playbook.MAX_STRENGTH] for x in body.strengths] if body.strengths is not None else None)


@router.get("/outreach/playbook")
def get_playbook(c: Ctx = Depends(ctx)):
    return playbook_out(c)


class FillIn(BaseModel):
    focuses: list[str] | None = Field(None, max_length=3)
    refresh: bool = False  # re-read the data room and deck now instead of using the last fill


@router.post("/outreach/playbook/fill")
def fill_playbook(body: FillIn, c: Ctx = Depends(ctx)):
    """What each email should say for the chosen focuses, what we're looking for, strengths and an example
    update, picked by AI from this founder's own deck. Nothing is saved; the founder reviews it first."""
    from ..models import CompanyProfile
    from ..services.entitlements import rate_limit

    if body.refresh:
        rate_limit(c.db, f"pbfill:{c.user.id}", 20, 3600)
    s = playbook.fill(c.db, c.workspace, c.db.get(CompanyProfile, c.ws_id), body.focuses, refresh=body.refresh)
    c.db.commit()
    return {**s, "prompts": playbook.prompts(s)}


@router.get("/outreach/playbook/suggest")
def suggest_playbook(c: Ctx = Depends(ctx)):
    """The fill for the founder's current focuses (cached), with example asks for the outreach agent bar."""
    from ..models import CompanyProfile

    s = playbook.fill(c.db, c.workspace, c.db.get(CompanyProfile, c.ws_id),
                      [e["focus"] for e in playbook.get(c.workspace)["emails"]])
    c.db.commit()
    return {**s, "prompts": playbook.prompts(s)}


@router.put("/outreach/playbook")
def put_playbook(body: PlaybookIn, c: Ctx = Depends(ctx)):
    """Each email's main focus and what it says, what we're looking for, and strengths. Used by every new draft
    and redraft."""
    c.require_editor()
    before = playbook.get(c.workspace)
    pb = {**_merged(c, body), "saved_at": datetime.now(UTC).isoformat()}
    playbook.save(c.workspace, pb)
    c.audit("playbook.update", str(c.ws_id), before={"emails": before["emails"], "ask": before["ask"]},
            after={"emails": pb["emails"], "ask": pb["ask"]})
    c.db.commit()
    return playbook_out(c)


class PreviewIn(PlaybookIn):
    investor_id: str | None = None
    skip: list[str] = Field(default_factory=list, max_length=20)  # "try another investor"


def _sample_investor(c: Ctx, iid: str | None, skip: list[str]):
    """Who to preview for: the one asked for, else the shortlist, the tracker, then the best match."""
    import uuid as _uuid

    from ..models import CompanyProfile, Investor, ShortlistItem
    from ..services.fit import fit

    if iid:
        try:
            inv = c.db.get(Investor, _uuid.UUID(iid))
        except ValueError:
            inv = None
        if test_investors.visible(inv, c.user.email):
            return inv
    seen = set(skip)
    for q in (select(ShortlistItem.investor_id).where(ShortlistItem.workspace_id == c.ws_id)
              .order_by(ShortlistItem.created_at.desc()).limit(30),
              select(FunnelCard.investor_id).where(FunnelCard.workspace_id == c.ws_id, FunnelCard.investor_id.is_not(None),
                                                   FunnelCard.deleted_at.is_(None)).limit(30)):
        for i in c.db.scalars(q).all():
            if str(i) not in seen:
                inv = c.db.get(Investor, i)
                if test_investors.visible(inv, c.user.email) and not inv.is_honeypot:
                    return inv
    p = c.db.get(CompanyProfile, c.ws_id)
    rows = c.db.scalars(select(Investor).where(Investor.suppressed.is_(False), Investor.is_honeypot.is_(False),
                                               *test_investors.conds(c.user.email))
                        .order_by(Investor.enriched.desc(), Investor.seed_fit.desc().nulls_last()).limit(60)).all()
    rows = [r for r in rows if str(r.id) not in seen]
    return max(rows, key=lambda i: fit(i, p)["score"]) if rows else None


@router.post("/outreach/playbook/preview")
def preview_playbook(body: PreviewIn, c: Ctx = Depends(ctx)):
    """The three emails one real investor would get with this playbook (saved or not). Nothing is stored."""
    from ..models import CompanyProfile
    from ..services import agent
    from ..services.entitlements import rate_limit

    rate_limit(c.db, f"preview:{c.ws_id}", 30, 3600)
    inv = _sample_investor(c, body.investor_id, body.skip)
    if inv is None:
        raise ApiError(404, "EF-PB-001", "No investor to preview with yet", "Add an investor to your shortlist first.")
    emails, engine = agent.draft_sequence(c.db, c.workspace, inv, c.db.get(CompanyProfile, c.ws_id), "momentum",
                                          c.user.signature, _merged(c, body))
    c.db.commit()
    return {"investor": {"id": str(inv.id), "name": inv.name, "firm": inv.current_firm or inv.company},
            "engine": engine, "emails": [{"step": e["step"], "subject": e["subject"], "body": e["body"],
                                          "update": bool(e.get("pre_update_body"))} for e in emails]}


class UpdateIn(BaseModel):
    text: str = Field("", max_length=playbook.MAX_UPDATE)
    apply: bool = True  # also turn the next unsent follow-up of every sequence into the update email


@router.put("/outreach/quick-update")
def put_quick_update(body: UpdateIn, c: Ctx = Depends(ctx)):
    """A round / progress update. The next follow-up still to go out on every sequence becomes a short update
    email (the update, what we're looking for, the call). Clearing it restores those follow-ups."""
    c.require_editor()
    playbook.set_update(c.workspace, body.text)
    changed = playbook.apply_update(c.db, c.workspace, c.user.signature) if body.apply else 0
    c.audit("playbook.update_note", str(c.ws_id), after={"text": body.text.strip(), "emails": changed})
    c.db.commit()
    return {**playbook_out(c), "changed": changed}


def redraft_all(c: Ctx, cap: int = 25) -> dict:
    """Redraft every sequence that is still a draft (nothing scheduled or sent) with the current playbook."""
    from .sequences import RegenIn, regenerate

    rows = c.db.scalars(select(Sequence).where(Sequence.workspace_id == c.ws_id, Sequence.status == "draft")
                        .order_by(Sequence.created_at.desc()).limit(cap)).all()
    for s in rows:
        regenerate(str(s.id), RegenIn(persona=s.persona if s.persona in ("momentum", "warm-intro", "technical-founder",
                                                                          "humble-expert") else "momentum"), c)
    return {"redrafted": len(rows)}


@router.post("/outreach/playbook/redraft")
def redraft(c: Ctx = Depends(ctx)):
    c.require_editor()
    out = redraft_all(c)
    c.audit("playbook.redraft", str(c.ws_id), after=out)
    c.db.commit()
    return {**out, **playbook_out(c)}
