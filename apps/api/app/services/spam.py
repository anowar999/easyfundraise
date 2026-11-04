"""Spam score for one outreach email (0 = clean, 100 = will likely land in spam) and the sending domain's
SPF / DKIM / DMARC check. Scores are rule-based so they are instant, explainable and the same every time."""

import re

from .outreach import LIMITS, SHORTENERS, SUBJECT_MAX_WORDS, words

WARN, BLOCK = 30, 60  # 30+ shows a warning; 60+ can't be scheduled until it's fixed

TRIGGERS = (
    "guaranteed", "guarantee", "act now", "100% free", "free money", "risk-free", "risk free", "click here",
    "click below", "limited time", "urgent", "once in a lifetime", "no obligation", "winner", "congratulations",
    "double your", "earn extra", "make money", "cash bonus", "best price", "lowest price", "buy now", "order now",
    "special promotion", "exclusive deal", "this isn't spam", "not spam", "dear friend", "100%", "miracle",
    "incredible deal", "apply now", "call now", "don't delete", "don’t delete", "unsecured", "billion dollars",
)
FAKE_THREAD = re.compile(r"^\s*(re|fwd?)\s*:", re.I)
LINK = re.compile(r"https?://[^\s)>\]]+", re.I)
IP_LINK = re.compile(r"https?://\d{1,3}(\.\d{1,3}){3}", re.I)


def score(subject: str, body: str, step: int = 1, first_name: str = "") -> dict:
    """{'score': 0-100, 'level': 'good'|'warn'|'high', 'reasons': [...]} for the email as it will be sent."""
    pts: list[tuple[int, str]] = []
    subj, low = (subject or "").strip(), f"{subject}\n{body}".lower()
    bare = FAKE_THREAD.sub("", subj).strip()

    hits = sorted({t for t in TRIGGERS if t in low})
    if hits:
        pts.append((min(45, 15 * len(hits)), f"Spam-trigger words: {', '.join(hits[:4])}"))
    if not bare:
        pts.append((25, "Empty subject"))
    elif bare.isupper() and len(bare) > 3:
        pts.append((25, "Subject is ALL CAPS"))
    if words(bare) > SUBJECT_MAX_WORDS + 2:
        pts.append((10, "Long subject"))
    if step == 1 and FAKE_THREAD.match(subj):
        pts.append((25, "First email pretends to be a reply (Re:/Fwd:)"))
    shouty = [w for w in re.findall(r"\b[A-Z]{4,}\b", f"{subject} {body}") if w not in ("SaaS", "B2B", "B2C", "NHS", "HIPAA", "GDPR")]
    if len(shouty) > 2:
        pts.append((10, f"{len(shouty)} words in capitals"))
    bangs = (subject + body).count("!")
    if bangs > 2 or "!!" in subject + body:
        pts.append((min(15, 5 * bangs), "Too many exclamation marks"))
    if "?" in subj and "!" in subj:
        pts.append((5, "Subject mixes ?! punctuation"))
    links = LINK.findall(body or "")
    if len(links) > 1:
        pts.append((10 * (len(links) - 1), f"{len(links)} links (keep to one)"))
    if any(s in low for s in SHORTENERS):
        pts.append((30, "Link shortener"))
    if IP_LINK.search(body or ""):
        pts.append((30, "Link to a bare IP address"))
    if len(re.findall(r"[$£€]\s?\d", f"{subject} {body}")) > 2:
        pts.append((10, "Lots of money amounts"))
    n = words(body or "")
    if n > LIMITS.get(step, 140) + 40:
        pts.append((10, f"Long email ({n} words)"))
    elif n < 25:
        pts.append((10, "Very short email"))
    named = bool(re.search(r"\{\{?\s*first[ _]?name", body or "", re.I)) or (
        first_name and first_name.lower() in (body or "").lower()[:120])
    if not named:
        pts.append((10, "Not addressed to the investor by name"))
    if "<img" in low or "<html" in low:
        pts.append((15, "HTML or images in a cold email"))
    total = min(100, sum(p for p, _ in pts))
    return {"score": total, "level": "high" if total >= BLOCK else "warn" if total >= WARN else "good",
            "reasons": [r for _, r in sorted(pts, key=lambda x: -x[0])]}


# ---------------- sending domain: SPF / DKIM / DMARC ----------------

FREE_MAIL = ("gmail.com", "googlemail.com")


def _txt(name: str) -> list[str]:
    try:
        import dns.resolver

        ans = dns.resolver.resolve(name, "TXT", lifetime=4)
        return [b"".join(r.strings).decode(errors="ignore") for r in ans]
    except Exception:
        return []


def domain_auth(email: str) -> dict:
    """Is the sending domain set up so Gmail/Outlook trust it? Google signs @gmail.com mail itself."""
    domain = (email or "").rsplit("@", 1)[-1].lower().strip()
    if not domain:
        return {"domain": "", "checks": [], "ok": False}
    if domain in FREE_MAIL:
        return {"domain": domain, "ok": True, "managed": True,
                "checks": [{"name": n, "ok": True, "detail": "Handled by Google for gmail.com"} for n in ("SPF", "DKIM", "DMARC")]}
    spf = next((t for t in _txt(domain) if t.lower().startswith("v=spf1")), "")
    dmarc = next((t for t in _txt(f"_dmarc.{domain}") if t.lower().startswith("v=dmarc1")), "")
    dkim = next((t for t in _txt(f"google._domainkey.{domain}") if "p=" in t), "")
    checks = [
        {"name": "SPF", "ok": "_spf.google.com" in spf,
         "detail": "Includes Google" if "_spf.google.com" in spf else ("Found, but doesn't include _spf.google.com" if spf
                                                                         else "No SPF record")},
        {"name": "DKIM", "ok": bool(dkim), "detail": "Google DKIM key found" if dkim else
         "No google._domainkey record: turn on DKIM in Google Admin > Gmail > Authenticate email"},
        {"name": "DMARC", "ok": bool(dmarc), "detail": dmarc[:80] if dmarc else "No DMARC record (add v=DMARC1; p=none to start)"},
    ]
    return {"domain": domain, "ok": all(c["ok"] for c in checks), "managed": False, "checks": checks}
