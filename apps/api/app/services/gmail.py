"""MAIL-01..03: the user's own Gmail as the sending mailbox.

`client_for(db, account)` returns a GoogleGmail (real API over httpx) or, in dev/tests with EF_GMAIL_MODE=fake,
a FakeGmail that records messages in memory so the whole send/reply pipeline can run without Google.
"""

import base64
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import GmailAccount
from .crypto import decrypt, encrypt

API = "https://gmail.googleapis.com/gmail/v1/users/me"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SCOPES = "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly"


class GmailRevoked(Exception):
    """Google revoked the grant (AUTH-03): pause sends and ask the user to reconnect."""


@dataclass
class Sent:
    message_id: str
    thread_id: str
    rfc_message_id: str


@dataclass
class ThreadMessage:
    id: str
    sender: str
    snippet: str
    headers: dict = field(default_factory=dict)
    at: datetime | None = None


def build_mime(*, sender: str, sender_name: str, to: str, subject: str, text: str, html: str | None = None,
               in_reply_to: str = "", list_unsubscribe: str = "") -> EmailMessage:
    """Plain-text-first MIME (SEQ-08). Follow-ups carry In-Reply-To/References (MAIL-02)."""
    m = EmailMessage()
    m["From"] = formataddr((sender_name, sender)) if sender_name else sender
    m["To"] = to
    m["Subject"] = (f"Re: {subject}" if in_reply_to and not subject.lower().startswith("re:") else subject)
    m["Message-ID"] = make_msgid(domain=sender.split("@")[-1] or "easyfundraise.com")
    if in_reply_to:
        m["In-Reply-To"] = in_reply_to
        m["References"] = in_reply_to
    if list_unsubscribe:
        m["List-Unsubscribe"] = list_unsubscribe
    m.set_content(text)
    if html:
        m.add_alternative(html, subtype="html")
    return m


class GoogleGmail:
    def __init__(self, db: Session, account: GmailAccount):
        self.db, self.acc = db, account

    def _token(self) -> str:
        acc = self.acc
        if acc.access_token_enc and acc.access_expires_at and acc.access_expires_at > datetime.now(UTC) + timedelta(seconds=60):
            return decrypt(acc.access_token_enc)
        s = get_settings()
        r = httpx.post(TOKEN_URL, data=dict(client_id=s.google_client_id, client_secret=s.google_client_secret,
                                            refresh_token=decrypt(acc.refresh_token_enc), grant_type="refresh_token"),
                       timeout=15)
        if r.status_code == 400 and r.json().get("error") == "invalid_grant":
            raise GmailRevoked()
        r.raise_for_status()
        j = r.json()
        acc.access_token_enc = encrypt(j["access_token"])
        acc.access_expires_at = datetime.now(UTC) + timedelta(seconds=int(j.get("expires_in", 3600)))
        self.db.flush()
        return j["access_token"]

    def _req(self, method: str, path: str, **kw) -> dict:
        r = httpx.request(method, f"{API}{path}", headers={"Authorization": f"Bearer {self._token()}"}, timeout=20, **kw)
        if r.status_code == 401:
            raise GmailRevoked()
        r.raise_for_status()
        return r.json() if r.content else {}

    def send(self, mime: EmailMessage, thread_id: str = "") -> Sent:
        body = {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode()}
        if thread_id:
            body["threadId"] = thread_id
        j = self._req("POST", "/messages/send", json=body)
        # Read back the Message-ID Gmail stored so follow-ups can reference it exactly.
        meta = self._req("GET", f"/messages/{j['id']}", params={"format": "metadata", "metadataHeaders": "Message-ID"})
        hdr = {h["name"].lower(): h["value"] for h in meta.get("payload", {}).get("headers", [])}
        return Sent(j["id"], j["threadId"], hdr.get("message-id", mime["Message-ID"]))

    def thread(self, thread_id: str) -> list[ThreadMessage]:
        j = self._req("GET", f"/threads/{thread_id}", params={"format": "metadata",
                                                              "metadataHeaders": ["From", "Subject", "Auto-Submitted",
                                                                                  "Content-Type"]})
        out = []
        for m in j.get("messages", []):
            hdr = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
            out.append(ThreadMessage(m["id"], hdr.get("from", ""), m.get("snippet", ""), hdr,
                                     datetime.fromtimestamp(int(m.get("internalDate", "0")) / 1000, UTC)))
        return out

    def changed_threads(self) -> set[str] | None:
        """Thread ids touched since the stored historyId (MAIL-03 polling via history.list). None = full scan."""
        if not self.acc.history_id:
            self.acc.history_id = str(self._req("GET", "/profile").get("historyId", ""))
            return None
        try:
            j = self._req("GET", "/history", params={"startHistoryId": self.acc.history_id,
                                                     "historyTypes": "messageAdded", "maxResults": 500})
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:  # history expired
                self.acc.history_id = ""
                return None
            raise
        self.acc.history_id = str(j.get("historyId", self.acc.history_id))
        return {m["message"]["threadId"] for h in j.get("history", []) for m in h.get("messagesAdded", [])}

    def revoke(self) -> None:
        try:
            httpx.post(REVOKE_URL, params={"token": decrypt(self.acc.refresh_token_enc)}, timeout=10)
        except httpx.HTTPError:
            pass


class FakeGmail:
    """In-memory mailbox for dev and tests. `FakeGmail.inbound(thread_id, sender, text)` simulates a reply."""

    threads: dict[str, list[ThreadMessage]] = {}
    sent: list[EmailMessage] = []

    def __init__(self, db: Session, account: GmailAccount):
        self.acc = account

    def send(self, mime: EmailMessage, thread_id: str = "") -> Sent:
        tid = thread_id or "t_" + secrets.token_hex(6)
        mid = "m_" + secrets.token_hex(6)
        FakeGmail.sent.append(mime)
        text = mime.get_body(preferencelist=("plain",)).get_content()
        FakeGmail.threads.setdefault(tid, []).append(ThreadMessage(mid, self.acc.email, text[:200], {}, datetime.now(UTC)))
        return Sent(mid, tid, mime["Message-ID"])

    def thread(self, thread_id: str) -> list[ThreadMessage]:
        return list(FakeGmail.threads.get(thread_id, []))

    def changed_threads(self) -> set[str] | None:
        return None

    def revoke(self) -> None:
        pass

    @classmethod
    def inbound(cls, thread_id: str, sender: str, text: str, headers: dict | None = None) -> None:
        cls.threads.setdefault(thread_id, []).append(
            ThreadMessage("m_" + secrets.token_hex(6), sender, text, headers or {}, datetime.now(UTC)))

    @classmethod
    def reset(cls) -> None:
        cls.threads.clear()
        cls.sent.clear()


def client_for(db: Session, account: GmailAccount) -> GoogleGmail | FakeGmail:
    if account.mode == "fake":
        if get_settings().is_prod:
            raise GmailRevoked()
        return FakeGmail(db, account)
    return GoogleGmail(db, account)
