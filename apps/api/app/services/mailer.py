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
import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    AuditLog,
    Broadcast,
    CardEvent,
    ConfigKV,
    Email,
    EmailEvent,
    Exclusion,
    FunnelCard,
    GmailAccount,
    Investor,
    Notification,
    Reminder,
    Sequence,
    User,
    Workspace,
    WorkspaceMember,
)
from . import ai, follow_up, tracker_link
from .entitlements import consume, limit, usage
from .gmail import GmailRevoked, build_mime, client_for, strip_quoted
from .outreach import fill_first_name, follow_up_slot, for_send, next_send_slot, usd

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


MAX_PER_DAY = 20  # founders' rule: never more than 20 outreach emails a day from one mailbox


def daily_cap(db: Session, ws: Workspace, acc: GmailAccount, now: datetime) -> int:
    """MAIL-05 cap from the tier (admin-configurable), reduced by the SEQ-08 warm-up ramp for new accounts."""
    cap = limit(db, ws, "emails_day")
    cap = int(cfg(db, "sending", {}).get("daily_cap", 20)) if cap is None else cap
    cap = min(cap, MAX_PER_DAY)
    age = (now - acc.connected_at).days if acc.connected_at else WARMUP_DAYS
    if age < WARMUP_DAYS:
        cap = min(cap, WARMUP_START + (cap - WARMUP_START) * age // WARMUP_DAYS)
    return max(cap, 0)


def sent_metric(user_id) -> str:
    """Per-sender daily counter key (usage_counters.metric is 32 chars)."""
    return f"sent:{user_id.hex[:24]}"


FREE_MAIL = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com", "yahoo.com",
             "yahoo.co.uk", "icloud.com", "me.com", "mac.com", "aol.com", "proton.me", "protonmail.com", "gmx.com",
             "gmx.de", "zoho.com", "yandex.com", "mail.com", "hotmail.co.uk", "outlook.co.uk"}


def who_of(db: Session, em: Email) -> str:
    seq = db.get(Sequence, em.sequence_id) if em.sequence_id else None
    inv = db.get(Investor, seq.investor_id) if seq is not None and seq.investor_id else None
    return inv.name if inv else ""


def domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].lower() if "@" in addr else ""


def primary(to: str) -> str:
    """First address of a To header (a card reply-all can carry several, the investor first)."""
    return to.split(",")[0].strip()


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


SAFETY = {"paused": False, "burst_max": 25, "burst_window_minutes": 10, "burst_pause_minutes": 60, "max_recipients": 10}
FOREVER = datetime(2100, 1, 1, tzinfo=UTC)


def safety(db: Session) -> dict:
    """Admin-configurable send guard rails (config key 'sending'), with safe defaults for anything missing."""
    c = cfg(db, "sending", {})
    return {k: c.get(k, v) for k, v in SAFETY.items()}


def sent_recently(db: Session, user_id, now: datetime, minutes: int) -> int:
    return db.scalar(select(func.count()).select_from(Email).where(
        Email.user_id == user_id, Email.status == "sent", Email.sent_at > now - timedelta(minutes=minutes))) or 0


def send_block(db: Session, ws_id, user_id, acc: GmailAccount | None, now: datetime) -> str:
    """Why nothing may leave this user's Gmail right now ('' = clear). Checked again for every single email at
    the moment it goes out, so a stale schedule, a removed teammate or a runaway loop can't send."""
    s = safety(db)
    if s["paused"]:
        return "Sending is paused for everyone by the EasyFundraise team"
    if acc is None or acc.status != "connected":
        return "Gmail not connected"
    if acc.paused_until and acc.paused_until > now:
        return acc.paused_reason or "Sending is paused"
    m = db.get(WorkspaceMember, (ws_id, user_id))
    if m is None or m.role not in ("owner", "editor"):
        return "Sender is no longer an editor of this workspace"
    return ""


def trip_burst(db: Session, ws_id, user_id, acc: GmailAccount, now: datetime) -> str:
    """More than burst_max emails from one mailbox inside the window looks like a runaway or misuse: stop this
    mailbox for a while and tell its owner. Returns the reason, or '' when within the limit."""
    s = safety(db)
    if sent_recently(db, user_id, now, int(s["burst_window_minutes"])) < int(s["burst_max"]):
        return ""
    acc.paused_until = now + timedelta(minutes=int(s["burst_pause_minutes"]))
    acc.paused_reason = (f"Paused: {s['burst_max']}+ emails in {s['burst_window_minutes']} minutes. "
                         "Resume in Settings if this was you.")
    log.warning("send burst: paused user %s until %s", user_id, acc.paused_until)
    notify(db, ws_id, user_id, "send_paused", "Sending paused for your safety",
           f"{s['burst_max']} or more emails went out from your Gmail in {s['burst_window_minutes']} minutes. "
           "If this wasn't you, disconnect Gmail and change your password. Otherwise resume in Settings.",
           "/app/settings#gmail")
    return acc.paused_reason


def _reschedule(em: Email, now: datetime, tz: str, reason: str) -> None:
    em.scheduled_for = next_send_slot(now + timedelta(hours=12), tz)
    em.error = reason


def send_due(db: Session, now: datetime | None = None, limit_n: int = 50, budget_s: float | None = None) -> int:
    """Sends due emails, oldest first: up to limit_n of them, or until budget_s seconds have passed.

    Each email is claimed on its own (FOR UPDATE SKIP LOCKED, one row) and committed before the next, so the lock
    is held for exactly the email being sent. Several workers can then drain one queue side by side without ever
    picking up the same email."""
    now = now or datetime.now(UTC)
    started = time.monotonic()
    sent, seen = 0, []
    while len(seen) < limit_n and (budget_s is None or time.monotonic() - started < budget_s):
        q = select(Email).where(Email.status == "scheduled", Email.scheduled_for <= now)
        if seen:
            q = q.where(Email.id.notin_(seen))  # one look per email per run, even if it stays due
        em = db.scalar(q.order_by(Email.scheduled_for).limit(1).with_for_update(skip_locked=True))
        if em is None:
            break
        seen.append(em.id)
        try:
            sent += _send_one(db, em, now)
        except Exception as e:  # one bad email never blocks the queue
            log.exception("send failed for %s", em.id)
            em.status, em.error = "failed", str(e)[:500]
        db.commit()
    return sent



def send_now_one(email_id) -> int:
    """Send one email the founder pressed Send now on, straight away instead of at the next worker tick. The row
    lock means the worker and this never both send it."""
    from ..db import SessionLocal

    with SessionLocal() as db:
        now = datetime.now(UTC)
        em = db.scalar(select(Email).where(Email.id == email_id, Email.status == "scheduled", Email.scheduled_for <= now)
                       .with_for_update(skip_locked=True))
        if em is None:
            return 0
        if em.user_id:  # one send at a time per mailbox, so the pacing gap holds when several finish together
            db.get(GmailAccount, em.user_id, with_for_update=True, populate_existing=True)
        try:
            n = _send_one(db, em, now)
        except Exception as e:
            log.exception("send now failed for %s", em.id)
            em.status, em.error, n = "failed", str(e)[:500], 0
        db.commit()
        return n


def _send_one(db: Session, em: Email, now: datetime) -> int:
    ws = db.get(Workspace, em.workspace_id)
    user = db.get(User, em.user_id) if em.user_id else None
    card = db.get(FunnelCard, em.card_id) if em.card_id else None
    seq = db.get(Sequence, em.sequence_id) if em.sequence_id else None
    tz = (card.investor_timezone if card else "") or "UTC"

    if seq is not None and seq.status != "approved":
        em.status = "cancelled"
        return 0
    if seq is not None and seq.engine == "drafting" and seq.created_at and seq.created_at > now - timedelta(minutes=10):
        em.scheduled_for = now + timedelta(seconds=30)  # the AI-personalised version is still being written: wait for it
        return 0
    if em.broadcast_id and db.get(Broadcast, em.broadcast_id).status == "cancelled":
        em.status = "cancelled"
        return 0
    if not em.to_email or user is None:
        em.status, em.error = "failed", "No recipient email or sender"
        return 0
    if excluded(db, ws.id, primary(em.to_email)) or (card and card.status == "Rejection"):  # SEQ-06
        em.status, em.error = "cancelled", "Recipient excluded"
        return 0
    if em.to_email.lower().startswith(ROLE_PREFIXES) and not (seq and seq.persona == "allow-role"):
        em.status, em.error = "cancelled", "Role address (info@, press@...) skipped"
        return 0
    if seq is not None:  # stop on any reply (SEQ-01), unless the founder resumed the follow-ups after it
        if db.scalar(select(func.count()).select_from(Email).where(Email.sequence_id == seq.id,
                                                                    Email.replied_at.is_not(None),
                                                                    Email.replied_at > seq.updated_at)):
            em.status = "cancelled"
            return 0
    if em.broadcast_id and em.step > 1 and db.scalar(select(func.count()).select_from(Email).where(
            Email.broadcast_id == em.broadcast_id, Email.card_id == em.card_id, Email.replied_at.is_not(None))):
        em.status = "cancelled"
        return 0

    acc = db.get(GmailAccount, user.id)
    if block := send_block(db, ws.id, user.id, acc, now):  # send safety: re-checked for every email
        if block.startswith("Sender is no longer"):
            em.status, em.error = "cancelled", block
        elif acc is not None and acc.paused_until and acc.paused_until > now and acc.paused_until < FOREVER:
            em.scheduled_for, em.error = acc.paused_until + timedelta(minutes=1), block
        else:
            _reschedule(em, now, tz, block)
        return 0
    if len([a for a in f"{em.to_email},{em.cc}".split(",") if a.strip()]) > int(safety(db)["max_recipients"]):
        em.status, em.error = "failed", "Too many recipients for one email"
        return 0
    if block := trip_burst(db, ws.id, user.id, acc, now):
        em.scheduled_for, em.error = acc.paused_until + timedelta(minutes=1), block
        return 0
    # A one-off email the founder wrote and sent from a tracker card (often a reply in an ongoing conversation):
    # the daily cap still counts it, but cold-outreach pacing and the per-firm cap don't hold it back.
    direct = seq is None and not em.broadcast_id
    if acc.next_send_at and acc.next_send_at > now and not direct:  # MAIL-06 pacing: never bursts
        em.scheduled_for = acc.next_send_at
        return 0

    day = user_day(user, now)
    cap = daily_cap(db, ws, acc, now)
    # The daily allowance counts investors, not emails: only a first email counts, never a follow-up or a reply
    # in a conversation that is already going (services/send_plan.py places first emails within it).
    counted = em.step == 1 and not em.broadcast_id and not (direct and em.gmail_thread_id)
    used = usage(db, ws, sent_metric(user.id), day)
    if counted and used >= cap:
        _reschedule(em, now, tz, f"Daily allowance reached ({cap} new investors a day): moved to the next send day")
        if not db.scalar(select(func.count()).select_from(Notification).where(
                Notification.user_id == user.id, Notification.kind == "cap_reached",
                Notification.created_at > now - timedelta(hours=20))):
            notify(db, ws.id, user.id, "cap_reached", f"Today's allowance used: {cap} new investors",
                   "First emails to the rest go in the next send window. Follow-ups still go as planned.",
                   "/app/outreach")
        return 0
    per_domain = int(cfg(db, "sending", {}).get("per_domain_daily_cap", 3))
    start = now - timedelta(hours=24)
    dom = domain(em.to_email)
    # The per-firm cap is about one firm's inbox: gmail.com, outlook.com etc. are different people, never one firm
    if get_settings().per_firm_limit_on and not direct and em.step == 1 and dom and dom not in FREE_MAIL and db.scalar(
            select(func.count()).select_from(Email).where(
                Email.workspace_id == ws.id, Email.sent_at > start, func.lower(Email.to_email).like(f"%@{dom}"))) >= per_domain:
        _reschedule(em, now, tz, f"Moved to the next send day: already {per_domain} emails to {dom} today (per-firm limit)")
        notify(db, ws.id, user.id, "cap_reached", f"{who_of(db, em) or em.to_email} moved to the next send day",
               f"{per_domain} emails already went to {dom} in the last 24 hours. We keep it to {per_domain} a day "
               "per firm so you don't land in spam.", "/app/outreach")
        return 0

    # Threading (MAIL-02): steps 2 and 3 reply in the thread of step 1.
    first = None
    if em.step > 1 and (seq is not None or em.broadcast_id):
        own = Email.sequence_id == seq.id if seq is not None else (Email.broadcast_id == em.broadcast_id) & (
            Email.card_id == em.card_id)
        first = db.scalar(select(Email).where(own, Email.step == 1, Email.status == "sent"))
        waiting = None if first else db.scalar(select(Email).where(own, Email.step == 1,
                                                                   Email.status.in_(("scheduled", "sending"))))
        if waiting is not None:  # email 1 was held back (e.g. daily allowance): keep the follow-up after it
            em.scheduled_for = follow_up_slot(max(waiting.scheduled_for or now, now), tz)
            return 0
        if first is None:
            em.status, em.error = "cancelled", "First email was not sent"
            return 0

    # A one-off reply written on a tracker card carries the Gmail thread and the Message-ID it answers.
    # A progress update to investors already emailed replies in their outreach thread the same way.
    reply_thread, reply_to = (em.gmail_thread_id, em.rfc_message_id) if direct or (em.broadcast_id and em.step == 1) else ("", "")

    # Merge field: {first name} becomes the recipient's first name in what is actually sent.
    who = (db.get(Investor, seq.investor_id).name if seq is not None and seq.investor_id else
           db.get(FunnelCard, em.card_id).name if em.card_id and db.get(FunnelCard, em.card_id) else "")
    if "first" in (em.body + em.subject).lower():
        em.body, em.subject = fill_first_name(em.body, who), fill_first_name(em.subject, who)

    em.body, em.subject = for_send(em.body, em.step if seq is not None else 1), usd(em.subject)
    em.open_token = em.open_token or secrets.token_urlsafe(18)
    html_part = pixel_html(em.body, em.open_token) if ws.tracking_enabled else None
    unsub = ""
    if em.broadcast_id and db.get(Broadcast, em.broadcast_id).kind == "investor_update":  # MAIL-07
        unsub = f"<mailto:{acc.email}?subject=unsubscribe>"
    if first is not None and seq is not None:  # same thread: "Re: <email 1 subject>" (build_mime adds the Re:)
        em.subject = f"Re: {re.sub(r'^\s*re:\s*', '', first.subject, flags=re.I)}"
    mime = build_mime(sender=acc.email, sender_name=user.name, to=em.to_email, subject=em.subject, text=em.body,
                      html=html_part, in_reply_to=first.rfc_message_id if first else reply_to, list_unsubscribe=unsub,
                      cc=em.cc if direct else "")
    em.status = "sending"
    db.flush()
    try:
        res = client_for(db, acc).send(mime, first.gmail_thread_id if first else reply_thread)
    except GmailRevoked:
        acc.status = "revoked"  # AUTH-03: pause all sends, tell the user
        em.status = "scheduled"
        _reschedule(em, now, tz, "Gmail disconnected")
        notify(db, ws.id, user.id, "gmail_disconnected", "Gmail disconnected",
               "Reconnect Gmail in Settings to resume sending.", "/app/settings")
        return 0

    em.status, em.sent_at, em.error = "sent", now, ""
    if seq is not None:  # keep each later follow-up at least 2 working days after this one (never earlier)
        prev = now
        for later in sorted((e for e in seq.emails if e.step > em.step and e.status == "scheduled"), key=lambda e: e.step):
            due = follow_up_slot(prev, tz)
            if later.scheduled_for is None or later.scheduled_for < due:
                later.scheduled_for = due
            prev = later.scheduled_for
    em.gmail_message_id, em.gmail_thread_id, em.rfc_message_id = res.message_id, res.thread_id, res.rfc_message_id
    n = consume(db, ws, sent_metric(user.id), day, None) if counted else used
    lo, hi = cfg(db, "sending", {}).get("pace_seconds", [45, 180])
    if not get_settings().is_prod:  # dev/UAT: a short gap so testing a queue of sends doesn't take minutes
        lo, hi = min(int(lo), 15), min(int(hi), 30)
    acc.next_send_at = now + timedelta(seconds=random.randint(int(lo), int(hi)))
    warn = int(cfg(db, "sending", {}).get("warn_at_pct", 80))
    if counted and cap and n == max(1, cap * warn // 100) and n < cap:
        notify(db, ws.id, user.id, "cap_warning", f"{n} of {cap} new investors emailed today",
               "Follow-ups don't count towards this.", "/app/outreach")
    if card:
        card.last_contacted_at = now
        db.add(CardEvent(workspace_id=ws.id, card_id=card.id, user_id=user.id, kind="email",
                         body=f"Email {em.step} sent: {em.subject}" if seq else
                         f"Email sent: {em.subject}\n\n{em.body}" if direct else f"Update sent: {em.subject}"))
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
BOUNCE = re.compile(r"\b(address not found|delivery status notification \(failure\)|message (was )?not delivered|"
                    r"undeliverable|recipient address rejected|user unknown|no such user|mailbox unavailable)\b", re.I)
DECK = re.compile(r"\b(deck|data ?room|materials|one[- ]pager)\b", re.I)


def classify(db: Session, ws: Workspace, text: str, headers: dict, sender: str) -> dict:
    """MAIL-03: positive / neutral / negative / auto / bounce / opt_out, plus extracted signals (TRK-03)."""
    low_sender = sender.lower()
    if ("mailer-daemon" in low_sender or "postmaster" in low_sender or "mail delivery subsystem" in low_sender
            or "delivery-status" in headers.get("content-type", "") or BOUNCE.search(text)):
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
        addr = primary(em.to_email).lower()
        if not excluded(db, ws.id, addr):
            db.add(Exclusion(workspace_id=ws.id, kind="email", value=addr, reason="bounced"))
        _stop(db, em)
        # Nothing else goes to this address: every scheduled or paused email to it (other follow-ups, updates)
        why = "Cancelled: address not found (the email bounced)"
        gone = db.scalars(select(Email).where(Email.workspace_id == ws.id, Email.status.in_(("scheduled", "paused")),
                                              func.lower(Email.to_email).like(f"%{addr}%"))).all()
        for other in gone:
            other.status, other.error = "cancelled", why
        em.error = "Bounced: address not found"
        db.add(AuditLog(actor_id=em.user_id, action="email.bounce", target=str(em.id),
                        after={"to": addr, "reason": "address not found", "snippet": msg.snippet[:200],
                               "cancelled": [str(o.id) for o in gone]}))
        notify(db, ws.id, em.user_id, "bounce", f"Email to {name} bounced: address not found",
               f"We cancelled {len(gone)} scheduled email{'s' if len(gone) != 1 else ''} to this address and won't email it again.",
               link)
        return
    if kind == "auto":
        return  # out-of-office: keep the sequence going
    em.replied_at, em.reply_kind = now, kind
    if kind == "opt_out":
        _stop(db, em, "replied")
    else:  # any real reply (yes, no or unclear) pauses the follow-ups; the founder resumes, sends or cancels them
        _pause(db, em)
    if kind == "positive" and card is None:  # an interested reply puts them in the tracker
        card = tracker_link.for_positive_reply(db, em)
        if card is not None:
            name, link = card.name, f"/app/funnel/{card.id}"
    if card:
        card.last_contacted_at = now
        text = strip_quoted(msg.snippet)
        meta = {"kind": kind, "signals": res.get("signals", []), "gmail_id": msg.id}
        if kind != "opt_out" and (d := follow_up.from_reply(db, card, em.user_id, text, now)):
            meta["follow_up"] = d.isoformat()
        db.add(CardEvent(workspace_id=ws.id, card_id=card.id, kind="reply", body=text[:500], meta=meta))
    if kind == "opt_out":  # MAIL-07
        if not excluded(db, ws.id, primary(em.to_email)):
            db.add(Exclusion(workspace_id=ws.id, kind="email", value=primary(em.to_email).lower(), reason="opt_out"))
        notify(db, ws.id, em.user_id, "reply", f"{name} asked not to be contacted", "Added to your exclusion list.", link)
        return
    if kind == "positive" and card and _auto(ws, "positive_reply"):
        target = 5 if "deck" in res.get("signals", []) else 3
        if card.stage < target:
            db.add(CardEvent(workspace_id=ws.id, card_id=card.id, kind="stage", body=f"Moved to stage {target} after a positive reply",
                             meta={"from": card.stage, "to": target, "auto": True}))
            card.stage = target
        if tracker_link.AUTO_TAG not in (card.tags or []):  # flagged until the founder acts on it
            card.tags = [*(card.tags or []), tracker_link.AUTO_TAG]
    title = {"positive": f"{name} replied: interested", "negative": f"{name} replied: passing",
             "neutral": f"{name} replied: needs your review"}[kind]
    body = msg.snippet[:200] + "\n\nFollow-ups are paused. Resume, send or cancel them in Outreach (filter: Paused)."
    if kind == "neutral" and em.card_id is None:
        body += " Add them to your tracker from the Outreach list if it's promising."
    if kind == "negative" and _auto(ws, "rejection_suggestion"):
        body += "\n\nMark as Rejection? Open the card to confirm."
    notify(db, ws.id, em.user_id, "reply", title, body, link)


def _pause(db: Session, em: Email) -> None:
    """A reply holds the rest of the sequence: unsent follow-ups wait as 'paused' until the founder decides."""
    if em.sequence_id:
        seq = db.get(Sequence, em.sequence_id)
        seq.status = "replied"
        for other in seq.emails:
            if other.status == "scheduled":
                other.status, other.error = "paused", "Paused: they replied"


def _stop(db: Session, em: Email, status: str = "stopped") -> None:
    if em.sequence_id:
        seq = db.get(Sequence, em.sequence_id)
        seq.status = status
        for other in seq.emails:
            if other.status == "scheduled":
                other.status = "cancelled"


def poll_replies(db: Session, now: datetime | None = None) -> int:
    """MAIL-03 polling fallback: checks threads we started that have no reply yet (last 60 days).
    One mailbox at a time here; the worker runs poll_mailbox for many mailboxes in parallel."""
    found = 0
    for uid in mailboxes_to_poll(db):
        found += poll_mailbox(db, uid, now)
    return found


def mailboxes_to_poll(db: Session) -> list:
    return list(db.scalars(select(GmailAccount.user_id).where(GmailAccount.status == "connected")))


def poll_mailbox(db: Session, user_id, now: datetime | None = None) -> int:
    """Reply check for one connected mailbox. A failure here (Gmail outage, bad token) is logged and never stops
    the other mailboxes from being checked."""
    now = now or datetime.now(UTC)
    acc = db.get(GmailAccount, user_id)
    if acc is None or acc.status != "connected":
        return 0
    tracked = db.scalars(select(Email).where(Email.user_id == acc.user_id, Email.status == "sent",
                                             Email.replied_at.is_(None), Email.bounced_at.is_(None),
                                             Email.sent_at > now - timedelta(days=60))).all()
    if not tracked:
        return 0
    found = 0
    try:
        gm = client_for(db, acc)
        changed = gm.changed_threads()
        by_thread: dict[str, list[Email]] = {}
        for e in tracked:
            by_thread.setdefault(e.gmail_thread_id, []).append(e)
        for tid, ems in by_thread.items():
            if changed is not None and tid not in changed:
                continue
            ours = {e.gmail_message_id for e in ems}
            latest = max(ems, key=lambda e: e.step)
            msgs = gm.thread(tid)  # oldest first
            # Only what came after our first email in this thread: Gmail can put a new sequence into an
            # older thread (same subject), and an earlier reply there (e.g. last week's "no") isn't an answer
            start = next((i for i, m in enumerate(msgs) if m.id in ours), 0)
            fresh = [m for m in msgs[start:] if m.id not in ours and acc.email.lower() not in m.sender.lower()
                     and not db.scalar(select(func.count()).select_from(EmailEvent).where(
                         EmailEvent.email_id == latest.id, EmailEvent.meta["message_id"].astext == m.id))]
            if fresh:
                handle_reply(db, latest, fresh[-1], now)  # the newest reply is their answer
                for m in fresh:
                    db.add(EmailEvent(workspace_id=latest.workspace_id, email_id=latest.id, kind="seen",
                                      meta={"message_id": m.id}))
                found += 1
    except GmailRevoked:
        acc.status = "revoked"
        notify(db, tracked[0].workspace_id, acc.user_id, "gmail_disconnected", "Gmail disconnected",
               "Reconnect Gmail in Settings to resume sending and reply tracking.", "/app/settings")
    except Exception:
        log.exception("reply poll failed for mailbox of user %s", user_id)
        db.rollback()
        return 0
    db.commit()
    return found
