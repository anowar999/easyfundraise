"""Send pipeline (MAIL-01/02/05/06, TZ-03) and reply/bounce detection (MAIL-03/04, §10.4 automations).

`send_due` runs every minute in the worker. Each scheduled email is re-checked at send time: sequence still
approved, no reply in the thread, recipient not excluded or opted out, Gmail connected, daily cap in the
sender's timezone, warm-up ramp, per-firm cap and pacing. Anything that can't go now is pushed to the next
send slot instead of being dropped.
"""

import html
import logging
import random
import re
import secrets
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    Broadcast,
    CardEvent,
    ConfigKV,
    Email,
    EmailEvent,
    Exclusion,
    FunnelCard,
    GmailAccount,
    Notification,
    Reminder,
    Sequence,
    User,
    Workspace,
)
from . import ai
from .entitlements import consume, limit, usage
from .gmail import GmailRevoked, build_mime, client_for
from .outreach import next_send_slot

log = logging.getLogger("easyfundraise.mailer")
ROLE_PREFIXES = ("info@", "press@", "hello@", "contact@", "admin@", "support@", "team@", "office@")
WARMUP_DAYS, WARMUP_START = 10, 5


def cfg(db: Session, key: str, default):
    row = db.get(ConfigKV, key)
    return row.value if row else default


def user_day(user: User, now: datetime) -> str:
    try:
        tz = ZoneInfo(user.timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    return now.astimezone(tz).strftime("%Y-%m-%d")


def daily_cap(db: Session, ws: Workspace, acc: GmailAccount, now: datetime) -> int:
    """MAIL-05 cap from the tier (admin-configurable), reduced by the SEQ-08 warm-up ramp for new accounts."""
    cap = limit(db, ws, "emails_day")
    cap = int(cfg(db, "sending", {}).get("daily_cap", 20)) if cap is None else cap
    age = (now - acc.connected_at).days if acc.connected_at else WARMUP_DAYS
    if age < WARMUP_DAYS:
        cap = min(cap, WARMUP_START + (cap - WARMUP_START) * age // WARMUP_DAYS)
    return max(cap, 0)


def sent_metric(user_id) -> str:
    """Per-sender daily counter key (usage_counters.metric is 32 chars)."""
    return f"sent:{user_id.hex[:24]}"


def domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].lower() if "@" in addr else ""


def excluded(db: Session, ws_id, addr: str) -> bool:
    addr = addr.lower()
    return bool(db.scalar(select(func.count()).select_from(Exclusion).where(
        Exclusion.workspace_id == ws_id,
        ((Exclusion.kind == "email") & (func.lower(Exclusion.value) == addr))
        | ((Exclusion.kind == "domain") & (func.lower(Exclusion.value) == domain(addr))))))


def notify(db: Session, ws_id, user_id, kind: str, title: str, body: str = "", link: str = "") -> None:
    """§10.5: respects the user's per-type in-app preference."""
    user = db.get(User, user_id) if user_id else None
    if user is None or ((user.notify_prefs or {}).get(kind) or {}).get("in_app") is False:
        return
    db.add(Notification(workspace_id=ws_id, user_id=user_id, kind=kind, title=title, body=body, link=link))


def pixel_html(text: str, token: str) -> str:
    """Light HTML twin of the plain text with the TRK-01 open pixel."""
    base = get_settings().tracking_base_url.rstrip("/")
    paras = "".join(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in text.split("\n\n"))
    return (f'<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.5">{paras}</div>'
            f'<img src="{base}/t/o/{token}.gif" width="1" height="1" alt="" style="display:none">')


def _reschedule(em: Email, now: datetime, tz: str, reason: str) -> None:
    em.scheduled_for = next_send_slot(now + timedelta(hours=12), tz)
    em.error = reason


def send_due(db: Session, now: datetime | None = None, limit_n: int = 50) -> int:
    now = now or datetime.now(UTC)
    rows = db.scalars(select(Email).where(Email.status == "scheduled", Email.scheduled_for <= now)
                      .order_by(Email.scheduled_for).limit(limit_n).with_for_update(skip_locked=True)).all()
    sent = 0
    for em in rows:
        try:
            sent += _send_one(db, em, now)
        except Exception as e:  # one bad email never blocks the queue
            log.exception("send failed for %s", em.id)
            em.status, em.error = "failed", str(e)[:500]
        db.commit()
    return sent


def _send_one(db: Session, em: Email, now: datetime) -> int:
    ws = db.get(Workspace, em.workspace_id)
    user = db.get(User, em.user_id) if em.user_id else None
    card = db.get(FunnelCard, em.card_id) if em.card_id else None
    seq = db.get(Sequence, em.sequence_id) if em.sequence_id else None
    tz = (card.investor_timezone if card else "") or "UTC"

    if seq is not None and seq.status != "approved":
        em.status = "cancelled"
        return 0
    if em.broadcast_id and db.get(Broadcast, em.broadcast_id).status == "cancelled":
        em.status = "cancelled"
        return 0
    if not em.to_email or user is None:
        em.status, em.error = "failed", "No recipient email or sender"
        return 0
    if excluded(db, ws.id, em.to_email) or (card and card.status == "Rejection"):  # SEQ-06
        em.status, em.error = "cancelled", "Recipient excluded"
        return 0
    if em.to_email.lower().startswith(ROLE_PREFIXES) and not (seq and seq.persona == "allow-role"):
        em.status, em.error = "cancelled", "Role address (info@, press@...) skipped"
        return 0
    if seq is not None:  # stop on any reply (SEQ-01)
        if db.scalar(select(func.count()).select_from(Email).where(Email.sequence_id == seq.id,
                                                                    Email.replied_at.is_not(None))):
            em.status = "cancelled"
            return 0
    if em.broadcast_id and em.step > 1 and db.scalar(select(func.count()).select_from(Email).where(
            Email.broadcast_id == em.broadcast_id, Email.card_id == em.card_id, Email.replied_at.is_not(None))):
        em.status = "cancelled"
        return 0

    acc = db.get(GmailAccount, user.id)
    if acc is None or acc.status != "connected":
        _reschedule(em, now, tz, "Gmail not connected")
        return 0
    if acc.next_send_at and acc.next_send_at > now:  # MAIL-06 pacing: never bursts
        em.scheduled_for = acc.next_send_at
        return 0

    day = user_day(user, now)
    cap = daily_cap(db, ws, acc, now)
    used = usage(db, ws, sent_metric(user.id), day)
    if used >= cap:
        _reschedule(em, now, tz, "Daily send cap reached")
        if not db.scalar(select(func.count()).select_from(Notification).where(
                Notification.user_id == user.id, Notification.kind == "cap_reached",
                Notification.created_at > now - timedelta(hours=20))):
            notify(db, ws.id, user.id, "cap_reached", f"Daily send cap reached ({cap})",
                   "Remaining emails move to your next send window.", "/app/outreach")
        return 0
    per_domain = int(cfg(db, "sending", {}).get("per_domain_daily_cap", 3))
    start = now - timedelta(hours=24)
    if db.scalar(select(func.count()).select_from(Email).where(
            Email.workspace_id == ws.id, Email.sent_at > start,
            func.lower(Email.to_email).like(f"%@{domain(em.to_email)}"))) >= per_domain:
        _reschedule(em, now, tz, "Per-firm daily cap reached")
        return 0

    # Threading (MAIL-02): steps 2 and 3 reply in the thread of step 1.
    first = None
    if em.step > 1 and (seq is not None or em.broadcast_id):
        own = Email.sequence_id == seq.id if seq is not None else (Email.broadcast_id == em.broadcast_id) & (
            Email.card_id == em.card_id)
        first = db.scalar(select(Email).where(own, Email.step == 1, Email.status == "sent"))
        if first is None:
            em.status, em.error = "cancelled", "First email was not sent"
            return 0

    em.open_token = em.open_token or secrets.token_urlsafe(18)
    html_part = pixel_html(em.body, em.open_token) if ws.tracking_enabled else None
    unsub = ""
    if em.broadcast_id and db.get(Broadcast, em.broadcast_id).kind == "investor_update":  # MAIL-07
        unsub = f"<mailto:{acc.email}?subject=unsubscribe>"
    mime = build_mime(sender=acc.email, sender_name=user.name, to=em.to_email, subject=em.subject, text=em.body,
                      html=html_part, in_reply_to=first.rfc_message_id if first else "", list_unsubscribe=unsub)
    em.status = "sending"
    db.flush()
    try:
        res = client_for(db, acc).send(mime, first.gmail_thread_id if first else "")
    except GmailRevoked:
        acc.status = "revoked"  # AUTH-03: pause all sends, tell the user
        em.status = "scheduled"
        _reschedule(em, now, tz, "Gmail disconnected")
        notify(db, ws.id, user.id, "gmail_disconnected", "Gmail disconnected",
               "Reconnect Gmail in Settings to resume sending.", "/app/settings")
        return 0

    em.status, em.sent_at, em.error = "sent", now, ""
    em.gmail_message_id, em.gmail_thread_id, em.rfc_message_id = res.message_id, res.thread_id, res.rfc_message_id
    n = consume(db, ws, sent_metric(user.id), day, None)
    lo, hi = cfg(db, "sending", {}).get("pace_seconds", [45, 180])
    acc.next_send_at = now + timedelta(seconds=random.randint(int(lo), int(hi)))
    warn = int(cfg(db, "sending", {}).get("warn_at_pct", 80))
    if cap and n == max(1, cap * warn // 100) and n < cap:
        notify(db, ws.id, user.id, "cap_warning", f"{n} of {cap} emails sent today", "", "/app/outreach")
    if card:
        card.last_contacted_at = now
        db.add(CardEvent(workspace_id=ws.id, card_id=card.id, user_id=user.id, kind="email",
                         body=f"Email {em.step} sent: {em.subject}" if seq else f"Update sent: {em.subject}"))
    if seq is not None and em.step == 3:
        # §10.4: no reply 7 days after E3 → ghosting suggestion
        db.add(Reminder(workspace_id=ws.id, user_id=user.id, card_id=em.card_id,
                        title="No reply after 3 emails: mark as Ghosting or try a different angle?",
                        due_at=now + timedelta(days=7)))
    return 1


# ---------------- replies ----------------

POSITIVE = re.compile(r"\b(interested|let'?s (talk|chat|meet)|happy to (chat|talk|meet)|send (over )?(the )?deck|"
                      r"book a (call|time)|calendly|sounds (good|great)|keen to|would love to|set up a call|"
                      r"available (on|next)|free (on|next))\b", re.I)
NEGATIVE = re.compile(r"\b(not (a )?fit|pass(ing)?\b|not interested|no thanks|not for us|outside (our|my) (focus|thesis)|"
                      r"we don'?t invest|not investing|decline)\b", re.I)
OPT_OUT = re.compile(r"^\s*(no|no thanks|stop|unsubscribe|remove me)[.!]?\s*$|\bunsubscribe\b|\bremove me\b", re.I)
AUTO = re.compile(r"\b(out of (the )?office|ooo|on vacation|on leave|auto(matic)? reply|away until)\b", re.I)
DECK = re.compile(r"\b(deck|data ?room|materials|one[- ]pager)\b", re.I)


def classify(db: Session, ws: Workspace, text: str, headers: dict, sender: str) -> dict:
    """MAIL-03: positive / neutral / negative / auto / bounce / opt_out, plus extracted signals (TRK-03)."""
    low_sender = sender.lower()
    if "mailer-daemon" in low_sender or "postmaster" in low_sender or "delivery-status" in headers.get("content-type", ""):
        return {"kind": "bounce", "signals": []}
    if headers.get("auto-submitted", "no").lower() not in ("", "no") or AUTO.search(text):
        return {"kind": "auto", "signals": []}
    if OPT_OUT.search(text):
        return {"kind": "opt_out", "signals": []}
    signals = ["deck"] if DECK.search(text) else []
    kind = "negative" if NEGATIVE.search(text) else "positive" if POSITIVE.search(text) else ""
    if not kind:
        out, _ = ai.json_call(db, ws, "classify", "Classify an investor's reply to a founder's outreach email.",
                              f"Reply:\n{text[:2000]}", {
                                  "type": "object", "additionalProperties": False, "required": ["kind", "signals"],
                                  "properties": {"kind": {"type": "string", "enum": ["positive", "neutral", "negative"]},
                                                 "signals": {"type": "array", "items": {"type": "string", "enum": [
                                                     "deck", "call", "passed", "referral", "timing"]}}}},
                              max_tokens=300, effort="low")
        if out:
            return out
        kind = "neutral"
    return {"kind": kind, "signals": signals}


def _auto(ws: Workspace, key: str) -> bool:
    return (ws.automations or {}).get(key, True)


def handle_reply(db: Session, em: Email, msg, now: datetime) -> None:
    ws = db.get(Workspace, em.workspace_id)
    res = classify(db, ws, msg.snippet, msg.headers, msg.sender)
    kind = res["kind"]
    db.add(EmailEvent(workspace_id=ws.id, email_id=em.id, kind="bounce" if kind == "bounce" else "reply",
                      meta={"kind": kind, "signals": res.get("signals", []), "snippet": msg.snippet[:300]}))
    card = db.get(FunnelCard, em.card_id) if em.card_id else None
    name = card.name if card else em.to_email
    link = f"/app/funnel/{card.id}" if card else "/app/outreach"
    if kind == "bounce":  # MAIL-04
        em.bounced_at = now
        if not excluded(db, ws.id, em.to_email):
            db.add(Exclusion(workspace_id=ws.id, kind="email", value=em.to_email.lower(), reason="bounced"))
        _stop(db, em)
        notify(db, ws.id, em.user_id, "bounce", f"Email to {name} bounced", "The address is marked invalid.", link)
        return
    if kind == "auto":
        return  # out-of-office: keep the sequence going
    em.replied_at, em.reply_kind = now, kind
    _stop(db, em, "replied")
    if card:
        card.last_contacted_at = now
        db.add(CardEvent(workspace_id=ws.id, card_id=card.id, kind="reply", body=msg.snippet[:500],
                         meta={"kind": kind, "signals": res.get("signals", [])}))
    if kind == "opt_out":  # MAIL-07
        if not excluded(db, ws.id, em.to_email):
            db.add(Exclusion(workspace_id=ws.id, kind="email", value=em.to_email.lower(), reason="opt_out"))
        notify(db, ws.id, em.user_id, "reply", f"{name} asked not to be contacted", "Added to your exclusion list.", link)
        return
    if kind == "positive" and card and _auto(ws, "positive_reply"):
        target = 5 if "deck" in res.get("signals", []) else 3
        if card.stage < target:
            db.add(CardEvent(workspace_id=ws.id, card_id=card.id, kind="stage", body=f"Moved to stage {target} after a positive reply",
                             meta={"from": card.stage, "to": target, "auto": True}))
            card.stage = target
    title = {"positive": f"{name} replied: interested", "negative": f"{name} replied: passing",
             "neutral": f"{name} replied"}[kind]
    body = msg.snippet[:200]
    if kind == "negative" and _auto(ws, "rejection_suggestion"):
        body += "\n\nMark as Rejection? Open the card to confirm."
    notify(db, ws.id, em.user_id, "reply", title, body, link)


def _stop(db: Session, em: Email, status: str = "stopped") -> None:
    if em.sequence_id:
        seq = db.get(Sequence, em.sequence_id)
        seq.status = status
        for other in seq.emails:
            if other.status == "scheduled":
                other.status = "cancelled"


def poll_replies(db: Session, now: datetime | None = None) -> int:
    """MAIL-03 polling fallback: checks threads we started that have no reply yet (last 60 days)."""
    now = now or datetime.now(UTC)
    found = 0
    for acc in db.scalars(select(GmailAccount).where(GmailAccount.status == "connected")).all():
        tracked = db.scalars(select(Email).where(Email.user_id == acc.user_id, Email.status == "sent",
                                                 Email.replied_at.is_(None), Email.bounced_at.is_(None),
                                                 Email.sent_at > now - timedelta(days=60))).all()
        if not tracked:
            continue
        gm = client_for(db, acc)
        try:
            changed = gm.changed_threads()
            by_thread: dict[str, list[Email]] = {}
            for e in tracked:
                by_thread.setdefault(e.gmail_thread_id, []).append(e)
            for tid, ems in by_thread.items():
                if changed is not None and tid not in changed:
                    continue
                ours = {e.gmail_message_id for e in ems}
                latest = max(ems, key=lambda e: e.step)
                for m in gm.thread(tid):
                    if m.id in ours or acc.email.lower() in m.sender.lower():
                        continue
                    if db.scalar(select(func.count()).select_from(EmailEvent).where(
                            EmailEvent.email_id == latest.id, EmailEvent.meta["message_id"].astext == m.id)):
                        continue
                    handle_reply(db, latest, m, now)
                    db.add(EmailEvent(workspace_id=latest.workspace_id, email_id=latest.id, kind="seen",
                                      meta={"message_id": m.id}))
                    found += 1
                    break
        except GmailRevoked:
            acc.status = "revoked"
            notify(db, tracked[0].workspace_id, acc.user_id, "gmail_disconnected", "Gmail disconnected",
                   "Reconnect Gmail in Settings to resume sending and reply tracking.", "/app/settings")
        db.commit()
    return found
