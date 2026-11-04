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

LIMITS = {1: 140, 2: 120, 3: 100}  # word limits including the opt-out line (a "Quick update:" line is extra)
SUBJECT_MAX_WORDS = 7
DEFAULT_DAYS = {1: 0, 2: 4, 3: 10}  # legacy calendar-day spacing (kept for reference)
FOLLOW_UP_WORKDAYS = 2  # a follow-up goes 2 working days after the email before it, if no reply
WEEKDAYS = (0, 1, 2, 3, 4)
OPT_OUT = ""  # founders asked for no "reply 'no'" line; replies like "no" / "unsubscribe" still stop a sequence
SPAM_PHRASES = ("guaranteed", "act now", "100% free", "risk-free", "click here", "limited time", "urgent",
                "once in a lifetime", "no obligation", "!!!", "$$$")
SHORTENERS = ("bit.ly", "tinyurl", "t.co/", "goo.gl", "ow.ly", "buff.ly")
PERSONAS = ("momentum", "warm-intro", "technical-founder", "humble-expert")


def words(s: str) -> int:
    return len(re.findall(r"\b[\w'’-]+\b", s))


def first_name(name: str) -> str:
    return (name.split() or ["there"])[0]


FIRST_NAME_FIELD = "{first name}"
_FIELD = re.compile(r"\{\{?\s*first[ _]?name\s*\}\}?", re.I)


def fill_first_name(text: str, name: str) -> str:
    """Swap {first name} (also {first_name}, {{first name}}) for the recipient's first name at send time."""
    return _FIELD.sub(first_name(name or ""), text or "")


def with_first_name_field(text: str, name: str) -> str:
    """The other way round, for previews: the investor's first name shown as {first name}."""
    fn = first_name(name or "")
    return re.sub(rf"\b{re.escape(fn)}\b", FIRST_NAME_FIELD, text or "") if fn != "there" else text


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
                   instructions: str = "", signature: str = "", plan: dict | None = None) -> list[dict]:
    """Returns three emails [{step, hook, subject, body, facts}]. plan (services/playbook.plan) builds them the
    founder's way: about them + what we're building, then the problem, then market and traction, each with the ask."""
    f = _facts(inv, p)
    company, one, traction = _pitch(p)
    fn = first_name(inv.name)
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
        opener = f"Your focus on {f['thesis'][:90].lower()} is why I'm writing."
        facts1.append({"text": "Thesis", "source": f["source"]})
    fit_line = ""
    if f["sectors"]:
        fit_line = f"We're building in {f['sectors'][0]}, which sits squarely in {f['firm'] or 'your'} focus."
        facts1.append({"text": f"Sector match: {f['sectors'][0]}", "source": "investor profile"})
    pitch = f"{company}: {one}."
    if traction:
        pitch += f" {traction}."
        facts1.append({"text": "Traction (shareable)", "source": "Company Profile"})
    ask = {
        "momentum": "Open to a 20-minute call this week or next?",
        "warm-intro": "Would you be open to a short call? Happy to send the deck first.",
        "technical-founder": "Happy to walk you through the product and architecture on a 20-minute call.",
        "humble-expert": "I'd value 20 minutes of your perspective, even if the timing isn't right.",
    }.get(persona, "Open to a 20-minute call?")
    e1 = "\n\n".join(x for x in [f"Hi {fn},", " ".join(x for x in [opener, fit_line] if x), pitch, ask, OPT_OUT] if x)
    subj1 = f"{company} x {f['firm']}" if f["firm"] else f"{company} for {fn}"

    # E2 — new angle: insight / thesis echo (not "just checking in")
    facts2: list[dict] = []
    if f["hooks"]:
        hook_line = f"One more reason I thought of you: {f['hooks'][0].rstrip('.')}."
        facts2.append({"text": f["hooks"][0], "source": f["source"]})
    elif f["news"]:
        hook_line = f"Read about {f['news'][0]['headline'].rstrip('.')}, which connects to what we do."
        facts2.append({"text": f["news"][0]["headline"], "source": f["news"][0].get("url", f["source"])})
    else:
        hook_line = f"One more thought on why {company} matters: {one[0].lower() + one[1:] if one else 'the problem we solve is growing'}."
    e2 = "\n\n".join([f"Hi {fn},", hook_line,
                      f"{traction + '. ' if traction else ''}Happy to send a short overview, or find 20 minutes?"])
    subj2 = f"Quick update from {company}"

    # E3 — last touch / ask-for-advice
    e3 = "\n\n".join([f"Hi {fn},",
                      "Last note from me. If this isn't a fit, who else should I talk to? "
                      "A name or a 'no' both help."])
    subj3 = "Closing the loop"

    hooks = ["thesis-echo" if f["thesis"] else "portfolio-adjacent", "insight-first", "ask-for-advice"]
    subjects = [subj1, subj2, subj3]
    if plan:  # the founder's playbook: fixed shape per email, their words for each part
        about = " ".join(x for x in [opener, fit_line] if x)
        cta = "Would you be open to a 20-minute call?"
        parts = {1: [about, plan[1]["message"] or pitch],
                 2: [plan[2]["message"] or hook_line, f"A reminder of what we do: {one}." if one else ""],
                 3: [plan[3]["message"] or (f"{traction}." if traction else pitch)]}
        bodies = []
        for step in (1, 2, 3):
            bodies.append("\n\n".join(x for x in [f"Hi {fn},", *parts[step], *plan[step]["strengths"], plan["ask"],
                                                   ask if step == 1 else cta, OPT_OUT] if x))
        e1, e2, e3 = bodies
        hooks = ["playbook-1", "playbook-2", "playbook-3"]
        subjects = [subject_options(step, inv, p)[0] for step in (1, 2, 3)]

    out = []
    for step, hook, subj, body, facts in [(1, hooks[0], subjects[0], e1, facts1), (2, hooks[1], subjects[1], e2, facts2),
                                          (3, hooks[2], subjects[2], e3, [])]:
        keep = tuple(plan[step]["strengths"]) + ((plan["ask"],) if plan["ask"] else ()) if plan else ()
        body = trim_to(body, LIMITS[step], keep)
        if signature:
            body = f"{body}\n\n{signature}"
        out.append(dict(step=step, hook=hook, subject=" ".join(subj.split()[:SUBJECT_MAX_WORDS]), body=body,
                        facts=facts))
    return out


def trim_to(body: str, max_words: int, keep: tuple[str, ...] = ()) -> str:
    """Drop the least important middle paragraph until within limit (greeting, ask, opt-out and `keep` stay)."""
    paras = body.split("\n\n")
    while words("\n\n".join(paras)) > max_words and len(paras) > 3:
        middle = [i for i in range(1, len(paras) - 2) if paras[i] not in keep]
        if not middle:
            break
        paras.pop(min(middle, key=lambda i: abs(i - len(paras) // 2)))
    return "\n\n".join(paras)


MONEY = re.compile(r"(?<![A-Za-z])(?:US)?\$\s?(\d[\d,.]*\s?(?:[kKmMbB](?:n|illion)?\b)?)")
LINK_LINE = re.compile(r"^\s*(?:[\w .]{0,20}:\s*)?(?:https?://|www\.)\S+\s*$|^\s*[\w-]+(?:\.[\w-]+)*\.(?:com|ai|io|co|uk|org|net|app|dev)(?:/\S*)?\s*$"
                       r"|linkedin\.com/", re.I)
URL = re.compile(r"(?:https?://|www\.)\S+", re.I)


def usd(text: str) -> str:
    """$2M -> USD 2M: written-out currency reads better and money symbols are a spam-filter signal."""
    return MONEY.sub(lambda m: f"USD {m.group(1).strip()}", text or "")


def for_send(body: str, step: int) -> str:
    """What an outreach email says when it goes: USD instead of $, and no website / LinkedIn links in follow-ups
    (email 1 already carried them; extra links in a thread raise the spam score). Links inside a sentence the
    founder wrote, like a data room link, are kept; lines that are only a link are dropped."""
    out = usd(body)
    if step > 1:
        lines = [ln for ln in out.split("\n") if not (LINK_LINE.search(ln) and len(URL.sub("", ln).split()) <= 2)]
        out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).rstrip()
    return out


def lint(subject: str, body: str, step: int, signature: str = "") -> list[str]:
    """SEQ-02 / SEQ-08 pre-send linter. Returns problems (empty = OK)."""
    issues = []
    b = body.replace(signature, "") if signature else body
    b = "\n\n".join(x for x in b.split("\n\n") if not x.strip().startswith("Quick update:"))
    if words(b) > LIMITS[step]:
        issues.append(f"Email {step} is {words(b)} words; limit is {LIMITS[step]}.")
    if words(re.sub(r"^\s*re:\s*", "", subject, flags=re.I)) > SUBJECT_MAX_WORDS:
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
    return issues


def next_send_slot(after: datetime, tz_name: str, weekdays: tuple[int, ...] = (1, 2, 3)) -> datetime:
    """Next 08:30-11:30 / 13:30-16:30 slot in the investor's local time on one of these weekdays (TZ-02).
    First emails go Tue-Thu; follow-ups any weekday."""
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    local = after.astimezone(tz)
    windows = [(time(8, 30), time(11, 30)), (time(13, 30), time(16, 30))]
    for day in range(0, 14):
        d = (local + timedelta(days=day)).date()
        if d.weekday() not in weekdays:
            continue
        for start, end in windows:
            s = datetime.combine(d, start, tz)
            e = datetime.combine(d, end, tz)
            if local < e:
                return max(s, local).astimezone(UTC)
    return after


def add_workdays(after: datetime, n: int, tz_name: str) -> datetime:
    """The morning (08:30 their time) n working days after this moment, skipping Saturday and Sunday."""
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    d = after.astimezone(tz).date()
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return datetime.combine(d, time(8, 30), tz).astimezone(UTC)


def follow_up_slot(prev: datetime, tz_name: str) -> datetime:
    return next_send_slot(add_workdays(prev, FOLLOW_UP_WORKDAYS, tz_name), tz_name, WEEKDAYS)


def schedule(emails: list, start: datetime, tz_name: str) -> None:
    """Email 1 in the next Tue-Thu send window; each follow-up 2 working days after the one before."""
    prev = None
    for em in sorted(emails, key=lambda e: e.step):
        if em.status == "sent":
            prev = em.sent_at
            continue
        em.scheduled_for = next_send_slot(start, tz_name) if prev is None else follow_up_slot(prev, tz_name)
        em.status = "scheduled"
        prev = em.scheduled_for


def subject_options(step: int, inv: Investor, p: CompanyProfile | None, current: str = "") -> list[str]:
    """Different subject lines for the same email, so a founder's outreach doesn't go out as one bulk subject."""
    import random

    company, one, _ = _pitch(p)
    fn, firm = first_name(inv.name), (inv.current_firm or inv.company or "").strip()
    short = " ".join(one.split()[:4]).rstrip(",;:") if one and one != "what we're building" else ""
    if step == 1:
        opts = [f"{company} x {firm}" if firm else "", f"{company} for {firm}" if firm else "", f"{fn}, meet {company}",
                f"Intro: {company}", f"{company} intro for {fn}", f"{short} ({company})" if short else "",
                f"A note from {company}"]
    elif step == 2:
        opts = [f"{fn}, one more on {company}", f"Following up: {company}", f"{company}, a quick follow-up",
                f"More on {company} for {firm}" if firm else "", f"{company}: the problem we solve"]
    else:
        opts = [f"{company}: where we are now", f"{fn}, last note on {company}", f"{company} progress for {firm}" if firm else "",
                f"Closing the loop on {company}", f"{company}: market and traction"]
    opts = [" ".join(o.split()[:SUBJECT_MAX_WORDS]) for o in opts if o]
    random.Random(f"{inv.id}:{step}").shuffle(opts)  # each investor starts from a different pattern
    return ([current] if current else []) + [o for o in opts if o != current]


def vary_subjects(db, ws_id, emails: list[dict], inv: Investor, p: CompanyProfile | None) -> None:
    """Make each step's subject unique across this workspace's other outreach (other investors), in place."""
    from sqlalchemy import func, select

    from ..models import Email, Sequence

    rows = db.execute(select(Email.step, func.lower(Email.subject)).join(Sequence, Sequence.id == Email.sequence_id)
                      .where(Email.workspace_id == ws_id, Sequence.investor_id != inv.id)).all()
    used: dict[int, set[str]] = {}
    for step, subj in rows:
        used.setdefault(step, set()).add((subj or "").strip())
    for e in emails:
        if e["step"] != 1:
            continue  # follow-ups reply in email 1's thread as "Re: <its subject>"
        taken = used.get(e["step"], set())
        if e["subject"].strip().lower() not in taken:
            continue
        for cand in subject_options(e["step"], inv, p)[0:]:
            if cand.lower() not in taken:
                e["subject"] = cand
                break
        else:
            e["subject"] = " ".join(f"{e['subject']} for {first_name(inv.name)}".split()[-SUBJECT_MAX_WORDS:])


def thread_subjects(emails: list) -> None:
    """Follow-ups go in the same Gmail thread as email 1, so their subject is "Re: <email 1 subject>". Works on
    dicts and Email rows."""
    get = (lambda e, k: e[k]) if emails and isinstance(emails[0], dict) else getattr
    first = next((get(e, "subject") for e in emails if get(e, "step") == 1), "")
    base = re.sub(r"^\s*re:\s*", "", first or "", flags=re.I).strip()
    if not base:
        return
    for e in emails:
        if get(e, "step") > 1:
            if isinstance(e, dict):
                e["subject"] = f"Re: {base}"
            else:
                e.subject = f"Re: {base}"
