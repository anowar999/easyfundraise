"""Account email (sign-in links) over plain SMTP, plus signed, short-lived sign-in tokens."""

import base64
import hashlib
import hmac
import smtplib
import time
from email.message import EmailMessage

from ..config import get_settings

LINK_TTL = 15 * 60


def smtp_ready() -> bool:
    return bool(get_settings().smtp_host)


def _sig(payload: str) -> str:
    key = hashlib.sha256(("signin:" + get_settings().secret_key).encode()).digest()
    return base64.urlsafe_b64encode(hmac.new(key, payload.encode(), hashlib.sha256).digest()[:24]).decode().rstrip("=")


def sign_in_token(email: str, now: float | None = None) -> str:
    payload = base64.urlsafe_b64encode(f"{email.lower()}|{int((now or time.time()) + LINK_TTL)}".encode()).decode().rstrip("=")
    return f"{payload}.{_sig(payload)}"


def read_sign_in_token(token: str) -> str | None:
    """The email inside a valid, unexpired token, else None."""
    payload, _, sig = token.partition(".")
    if not payload or not hmac.compare_digest(sig, _sig(payload)):
        return None
    try:
        email, _, exp = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode().rpartition("|")
        return email if int(exp) >= time.time() else None
    except (ValueError, UnicodeDecodeError):
        return None


def send_sign_in_link(to: str, link: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, "Your EasyFundraise sign-in link"
    msg.set_content(f"Click to sign in to EasyFundraise:\n\n{link}\n\nThe link works for 15 minutes. "
                    "If you didn't ask for it, you can ignore this email.")
    msg.add_alternative(
        f"""<div style="font-family:Inter,Arial,sans-serif;max-width:460px;margin:0 auto;padding:24px;color:#0b1220">
<p style="font-size:20px;font-weight:700;margin:0 0 16px">Easy<span style="color:#0f62fe">Fundraise</span></p>
<p style="font-size:16px;line-height:1.5">Click the button to sign in. The link works for 15 minutes.</p>
<p style="margin:24px 0"><a href="{link}" style="background:#0f62fe;color:#fff;text-decoration:none;padding:12px 22px;border-radius:999px;font-weight:600;display:inline-block">Sign in to EasyFundraise</a></p>
<p style="font-size:13px;color:#5b6478">If you didn't ask for this, you can ignore this email.</p></div>""",
        subtype="html")
    _send(msg)


def send_login_code(to: str, code: str, minutes: int) -> None:
    """Second step of password sign-in: a one-time code to the account's own email."""
    s = get_settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, f"{code} is your EasyFundraise sign-in code"
    msg.set_content(f"Your EasyFundraise sign-in code is {code}\n\nIt works once, for {minutes} minutes. "
                    "If you didn't just try to sign in, change your password in Settings.")
    msg.add_alternative(
        f"""<div style="font-family:Inter,Arial,sans-serif;max-width:460px;margin:0 auto;padding:24px;color:#0b1220">
<p style="font-size:20px;font-weight:700;margin:0 0 16px">Easy<span style="color:#0f62fe">Fundraise</span></p>
<p style="font-size:16px;line-height:1.5">Enter this code to finish signing in. It works once, for {minutes} minutes.</p>
<p style="font-size:34px;font-weight:700;letter-spacing:8px;margin:24px 0;font-family:Menlo,Consolas,monospace">{code}</p>
<p style="font-size:13px;color:#5b6478">If you didn't just try to sign in, someone may know your password. Change it in Settings.</p></div>""",
        subtype="html")
    _send(msg)


def _send(msg: EmailMessage) -> None:
    s = get_settings()
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)
