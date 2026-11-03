"""Google Calendar (read-only) for the Raise Agent: which meetings are about the raise, and with whom.

It rides on the same Google grant as Gmail (incremental consent adds calendar.readonly). An event counts as raise
related when an attendee is in the investor tracker or the investor database, or its title reads like a pitch.
In dev with EF_GMAIL_MODE=fake the calendar is built from tracker call dates so the agent can be tried end to end.
"""

import json
import re
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select

from ..deps import Ctx
from ..models import FunnelCard, GmailAccount, Investor
from .gmail import GmailRevoked, GoogleGmail

SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
RAISE_WORDS = re.compile(r"\b(investor|investment|invest|pitch|vc|venture|ventures|capital|fund|fundraise|fundraising|"
                         r"angel|seed|series [ab]|term sheet|due diligence|dd|partners? meeting|ic meeting|intro)\b", re.I)

TOOLS = [{
    "name": "calendar_events",
    "description": "The founder's Google Calendar (read-only). Returns meetings in a window with raise_related "
                   "flags and the matching tracker card. Use for 'what meetings do I have', 'am I meeting any "
                   "investors this week', or to prepare for a call.",
    "input_schema": {"type": "object", "properties": {
        "days_ahead": {"type": "integer", "description": "default 7"},
        "days_back": {"type": "integer", "description": "default 0"},
        "raise_only": {"type": "boolean", "description": "only meetings about the raise"}}},
}]
TOOL_NAMES = {t["name"] for t in TOOLS}


class CalendarBlocked(Exception):
    """Google refused the calendar read for a reason reconnecting won't fix (e.g. the Calendar API is off in the
    Google Cloud project). Carries a plain message and, when Google gives one, the page that fixes it."""

    def __init__(self, message: str, link: str = ""):
        super().__init__(message)
        self.message, self.link = message, link


def blocked(r: httpx.Response) -> Exception:
    try:
        err = r.json().get("error") or {}
    except ValueError:
        err = {}
    reasons = {str(x.get("reason", "")) for x in err.get("errors") or []}
    for d in err.get("details") or []:
        reasons.add(str(d.get("reason", "")))
    text = str(err.get("message", ""))
    if reasons & {"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}:
        return GmailRevoked()  # calendar permission missing: reconnecting with calendar fixes it
    if reasons & {"accessNotConfigured", "SERVICE_DISABLED"} or "has not been used" in text or "disabled" in text:
        m = re.search(r"https://console\.(?:developers|cloud)\.google\.com/\S+?(?=[\s\"]|then|$)", text)
        link = m.group(0).rstrip(".") if m else "https://console.cloud.google.com/apis/library/calendar-json.googleapis.com"
        return CalendarBlocked("The Google Calendar API is switched off in your Google Cloud project. Turn it on, "
                               "wait a few minutes, then reload.", link)
    return CalendarBlocked(f"Google refused the calendar read: {text[:200] or 'permission denied'}.")


def connected(acc: GmailAccount | None) -> bool:
    return bool(acc and acc.status == "connected" and (acc.mode == "fake" or "calendar" in (acc.scopes or "")))


def _google_events(db, acc: GmailAccount, start: datetime, end: datetime) -> list[dict]:
    tok = GoogleGmail(db, acc)._token()
    r = httpx.get(API, headers={"Authorization": f"Bearer {tok}"}, timeout=20, params={
        "timeMin": start.isoformat(), "timeMax": end.isoformat(), "singleEvents": "true", "orderBy": "startTime",
        "maxResults": 100})
    if r.status_code == 401:
        raise GmailRevoked()
    if r.status_code == 403:
        raise blocked(r)
    r.raise_for_status()
    out = []
    for e in r.json().get("items", []):
        if e.get("status") == "cancelled":
            continue
        st = e.get("start", {})
        out.append({"title": e.get("summary", "(no title)"), "start": st.get("dateTime") or st.get("date"),
                    "end": (e.get("end") or {}).get("dateTime"), "location": e.get("location", "")[:200],
                    "link": e.get("hangoutLink", ""),
                    "attendees": [{"email": (a.get("email") or "").lower(), "name": a.get("displayName", "")}
                                  for a in e.get("attendees", []) if not a.get("self")][:20]})
    return out


def _fake_events(c: Ctx, start: datetime, end: datetime) -> list[dict]:
    cards = c.db.scalars(select(FunnelCard).where(FunnelCard.workspace_id == c.ws_id, FunnelCard.deleted_at.is_(None),
                                                  FunnelCard.call_at.between(start, end))).all()
    return [{"title": f"Call with {x.name}" + (f" ({x.firm})" if x.firm else ""), "start": x.call_at.isoformat(),
             "end": (x.call_at + timedelta(minutes=30)).isoformat(), "location": "", "link": "",
             "attendees": [{"email": "", "name": x.name}]} for x in cards]


def events(c: Ctx, days_ahead: int = 7, days_back: int = 0) -> list[dict] | None:
    """None when the calendar isn't connected."""
    acc = c.db.get(GmailAccount, c.user.id)
    if not connected(acc):
        return None
    now = datetime.now(UTC)
    start, end = now - timedelta(days=max(0, min(days_back, 60))), now + timedelta(days=max(1, min(days_ahead, 60)))
    evs = _fake_events(c, start, end) if acc.mode == "fake" else _google_events(c.db, acc, start, end)
    return [tag(c, e) for e in evs]


def tag(c: Ctx, e: dict) -> dict:
    """Mark raise-related meetings and link them to a tracker card."""
    emails = [a["email"] for a in e["attendees"] if a["email"]]
    names = [a["name"] for a in e["attendees"] if a["name"]]
    cards = c.db.scalars(select(FunnelCard).where(FunnelCard.workspace_id == c.ws_id, FunnelCard.deleted_at.is_(None))).all()
    card = None
    title = e["title"].lower()
    for x in cards:
        inv = c.db.get(Investor, x.investor_id) if x.investor_id and emails else None
        mails = {(x.email or "").lower(), (inv.email or "").lower() if inv else ""} - {""}
        if mails & set(emails) or (x.name and (
                x.name.lower() in title or any(x.name.lower() == n.lower() for n in names))):
            card = x
            break
    known = bool(emails) and bool(c.db.scalar(select(func.count()).select_from(Investor).where(
        ~Investor.suppressed, func.lower(Investor.email).in_(emails))))
    related = bool(card or known or RAISE_WORDS.search(e["title"]))
    return {**e, "raise_related": related,
            "tracker_card": {"card_id": str(card.id), "name": card.name, "firm": card.firm} if card else None}


def run(c: Ctx, name: str, args: dict) -> str:
    try:
        evs = events(c, int(args.get("days_ahead") or 7), int(args.get("days_back") or 0))
    except CalendarBlocked as e:
        return f"Couldn't read the calendar: {e.message} Fix link: {e.link or 'none'}. Do not suggest reconnecting."
    except (GmailRevoked, httpx.HTTPError):
        return "Couldn't read the calendar; Google access may have expired. Suggest reconnecting in settings."
    if evs is None:
        return ("Calendar isn't connected. Tell the founder they can connect Google Calendar (read-only) in "
                "Settings, and offer open_page settings.")
    if args.get("raise_only"):
        evs = [e for e in evs if e["raise_related"]]
    return json.dumps(evs[:40])
