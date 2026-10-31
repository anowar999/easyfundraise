"""§9.3 Outreach sequences: deterministic template engine ("own engine" tier, COST-01) + pre-send linter
(SEQ-02/SEQ-08) + scheduling into the investor's local send window (TZ-02).

The engine only uses stored facts (enrichment + Company Profile fields marked shareable), so it never
fabricates deals, dates or quotes (AGT-08). Every fact used is returned with its source for
"Why I wrote this" (§9.8).
"""

import re
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..models import CompanyProfile, Investor
from .fit import sector_overlap

LIMITS = {1: 120, 2: 80, 3: 60}
SUBJECT_MAX_WORDS = 7
DEFAULT_DAYS = {1: 0, 2: 4, 3: 10}
OPT_OUT = "If this isn't relevant, reply 'no' and I won't follow up."
SPAM_PHRASES = ("guaranteed", "act now", "100% free", "risk-free", "click here", "limited time", "urgent",
                "once in a lifetime", "no obligation", "!!!", "$$$")
SHORTENERS = ("bit.ly", "tinyurl", "t.co/", "goo.gl", "ow.ly", "buff.ly")
PERSONAS = ("momentum", "warm-intro", "technical-founder", "humble-expert")


def words(s: str) -> int:
    return len(re.findall(r"\b[\w'’-]+\b", s))


def first_name(name: str) -> str:
    return (name.split() or ["there"])[0]


def _shareable(p: CompanyProfile | None, field: str) -> str:
    if not p:
        return ""
    if p.shareable and p.shareable.get(field) is False:
        return ""
    return (getattr(p, field) or "").strip()


def _facts(inv: Investor, p: CompanyProfile | None) -> dict:
    e = inv.enrichment or {}
    src = (e.get("sources") or [""])[0]
    port = e.get("notable_portfolio") or inv.portfolio_sample
    if isinstance(port, str):
        port = [x.strip() for x in port.split(";") if x.strip()]
    recent = [r for r in (e.get("recent_investments_12mo") or []) if isinstance(r, dict) and r.get("company")]
    news = [n for n in (e.get("recent_news") or []) if isinstance(n, dict) and n.get("headline")]
    hooks = [h for h in (e.get("personalization_hooks") or []) if isinstance(h, str)]
    return dict(
        portfolio=port[:3], recent=recent[:1], news=news[:1], hooks=hooks, source=src,
        thesis=(inv.investment_thesis or "").split(". ")[0].strip(". "),
        sectors=sector_overlap(p.sectors, inv) if p and p.sectors else [],
        firm=inv.current_firm or inv.company,
    )


def _pitch(p: CompanyProfile | None) -> tuple[str, str, str]:
    company = _shareable(p, "company_name") or "my company"
    one = _shareable(p, "one_liner") or "what we're building"
    traction = _shareable(p, "traction")
    return company, one.rstrip("."), traction.rstrip(".")


def draft_sequence(inv: Investor, p: CompanyProfile | None, persona: str = "momentum",
                   instructions: str = "", signature: str = "") -> list[dict]:
    """Returns three emails [{step, hook, subject, body, facts}] that each use a different hook family."""
    f = _facts(inv, p)
    company, one, traction = _pitch(p)
    fn = first_name(inv.name)
    round_size = _shareable(p, "round_size")
    stage = (p.stage if p else "") or "seed"
    facts1: list[dict] = []

    # E1 — personalised hook (>=2 personalisation facts when available, SEQ-03)
    opener = ""
    if f["recent"]:
        r = f["recent"][0]
        opener = f"Saw you backed {r['company']}{' (' + r['round'] + ')' if r.get('round') else ''} recently."
        facts1.append({"text": f"Recent investment: {r['company']}", "source": r.get("source_url", f["source"])})
    elif f["portfolio"]:
        opener = f"Your work with {f['portfolio'][0]} is why I'm writing."
        facts1.append({"text": f"Portfolio: {f['portfolio'][0]}", "source": f["source"] or "directory"})
    elif f["thesis"]:
        opener = f"Your focus on {f['thesis'][:90].lower()} caught my eye."
        facts1.append({"text": "Investment thesis", "source": f["source"]})
    fit_line = ""
    if f["sectors"]:
        fit_line = f"We're building in {f['sectors'][0]}, which sits squarely in {f['firm'] or 'your'} focus."
        facts1.append({"text": f"Sector match: {f['sectors'][0]}", "source": "investor profile"})
    pitch = f"{company}: {one}."
    if traction:
        pitch += f" {traction}."
        facts1.append({"text": "Traction (shareable)", "source": "Company Profile"})
    ask = {
        "momentum": f"We're raising our {stage} round{' of ' + round_size if round_size else ''} and moving quickly. "
                    "Open to a 20-minute call this week or next?",
        "warm-intro": "Would you be open to a short call? Happy to send the deck first.",
        "technical-founder": "Happy to walk you through the product and architecture on a 20-minute call.",
        "humble-expert": "I'd value 20 minutes of your perspective, even if the timing isn't right.",
    }.get(persona, "Open to a 20-minute call?")
    e1 = "\n\n".join(x for x in [f"Hi {fn},", " ".join(x for x in [opener, fit_line] if x), pitch, ask, OPT_OUT] if x)
    subj1 = f"{company} x {f['firm']}" if f["firm"] else f"{company}: {stage} round"

    # E2 — new angle: insight / thesis echo (not "just checking in")
    facts2: list[dict] = []
    if f["hooks"]:
        hook_line = f"One more reason I thought of you: {f['hooks'][0].rstrip('.')}."
        facts2.append({"text": f["hooks"][0], "source": f["source"]})
    elif f["news"]:
        hook_line = f"Read about {f['news'][0]['headline'].rstrip('.')}, which connects to what we do."
        facts2.append({"text": f["news"][0]["headline"], "source": f["news"][0].get("url", f["source"])})
    else:
        hook_line = f"One thing we've learned building {company}: customers buy speed, not features."
    e2 = "\n\n".join([f"Hi {fn},", hook_line,
                      f"{traction + '. ' if traction else ''}Worth a quick look at the deck?", OPT_OUT])
    subj2 = f"Quick update from {company}"

    # E3 — last touch / ask-for-advice
    e3 = "\n\n".join([f"Hi {fn},",
                      "Last note from me. If this isn't a fit, who else should I talk to? "
                      "A name or a 'no' both help.", OPT_OUT])
    subj3 = "Closing the loop"

    out = []
    for step, hook, subj, body, facts in [(1, "thesis-echo" if f["thesis"] else "portfolio-adjacent", subj1, e1, facts1),
                                          (2, "insight-first", subj2, e2, facts2),
                                          (3, "ask-for-advice", subj3, e3, [])]:
        body = trim_to(body, LIMITS[step])
        if signature:
            body = f"{body}\n\n{signature}"
        out.append(dict(step=step, hook=hook, subject=" ".join(subj.split()[:SUBJECT_MAX_WORDS]), body=body,
                        facts=facts))
    return out


def trim_to(body: str, max_words: int) -> str:
    """Drop the least important middle paragraph until within limit (greeting, ask and opt-out are kept)."""
    paras = body.split("\n\n")
    while words("\n\n".join(paras)) > max_words and len(paras) > 3:
        paras.pop(len(paras) // 2)
    return "\n\n".join(paras)


def lint(subject: str, body: str, step: int, signature: str = "") -> list[str]:
    """SEQ-02 / SEQ-08 pre-send linter. Returns problems (empty = OK)."""
    issues = []
    b = body.replace(signature, "") if signature else body
    if words(b) > LIMITS[step]:
        issues.append(f"Email {step} is {words(b)} words; limit is {LIMITS[step]}.")
    if words(subject) > SUBJECT_MAX_WORDS:
        issues.append(f"Subject is over {SUBJECT_MAX_WORDS} words.")
    if subject.isupper() and len(subject) > 3:
        issues.append("Subject is ALL CAPS.")
    low = body.lower()
    for ph in SPAM_PHRASES:
        if ph in low:
            issues.append(f"Spam-trigger phrase: “{ph}”.")
    if any(s in low for s in SHORTENERS):
        issues.append("Link shorteners are not allowed.")
    if len(re.findall(r"https?://", body)) > 1:
        issues.append("Use at most one link (data room or calendar).")
    if "reply 'no'" not in low and "reply “no”" not in low:
        issues.append("Missing opt-out line.")
    return issues


def next_send_slot(after: datetime, tz_name: str) -> datetime:
    """Next Tue-Thu 08:30-11:30 / 13:30-16:30 slot in the investor's local time (TZ-02)."""
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    local = after.astimezone(tz)
    windows = [(time(8, 30), time(11, 30)), (time(13, 30), time(16, 30))]
    for day in range(0, 14):
        d = (local + timedelta(days=day)).date()
        if d.weekday() not in (1, 2, 3):  # Tue-Thu only; Mon/Fri/weekends need a user override
            continue
        for start, end in windows:
            s = datetime.combine(d, start, tz)
            e = datetime.combine(d, end, tz)
            if local < e:
                return max(s, local).astimezone(UTC)
    return after


def schedule(emails: list, start: datetime, tz_name: str, days: dict[int, int] = DEFAULT_DAYS) -> None:
    for em in emails:
        em.scheduled_for = next_send_slot(start + timedelta(days=days[em.step]), tz_name)
        em.status = "scheduled"
