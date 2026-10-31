"""§9.1 Personal Super Agent: AI drafting with a fact pack (SEQ-03, AGT-08), deck → profile (DECK-01),
meeting briefs (AGT-04), chat with previewed tools (AGT-05), memory (AGT-07), daily brief + insights
(AGT-02, §11.1). Every function has a deterministic path when AI is unavailable.
"""

import json
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    STAGES,
    AgentInstruction,
    AgentMemory,
    CardEvent,
    ChatMessage,
    CompanyProfile,
    Email,
    FunnelCard,
    Investor,
    MeetingBrief,
    Notification,
    Reminder,
    User,
    Workspace,
)
from . import ai, outreach
from .fit import fit, sector_overlap
from .notes import find_date

# ---------------- shared context ----------------


def instructions(db: Session, ws_id) -> str:
    return db.scalar(select(AgentInstruction.text).where(AgentInstruction.workspace_id == ws_id)
                     .order_by(AgentInstruction.version.desc())) or ""


def memory_text(db: Session, ws_id, n: int = 30) -> str:
    rows = db.scalars(select(AgentMemory).where(AgentMemory.workspace_id == ws_id)
                      .order_by(AgentMemory.created_at.desc()).limit(n)).all()
    return "\n".join(f"- ({m.kind}) {m.text}" for m in rows)


def shareable_profile(p: CompanyProfile | None) -> dict:
    """DECK-04: only fields the founder marked shareable may appear in emails."""
    if not p:
        return {}
    out = {}
    for f in ("company_name", "one_liner", "sectors", "stage", "geography", "round_size", "instrument", "traction",
              "business_model"):
        if (p.shareable or {}).get(f) is False:
            continue
        v = getattr(p, f)
        if v:
            out[f] = v
    return out


def fact_pack(inv: Investor, p: CompanyProfile | None) -> list[dict]:
    """Numbered facts the model may cite. Anything not here must not appear in an email."""
    e = inv.enrichment or {}
    src = (e.get("sources") or ["investor profile"])[0]
    facts: list[dict] = []

    def add(text: str, source: str) -> None:
        if text and text.strip():
            facts.append({"id": f"f{len(facts) + 1}", "text": text.strip()[:300], "source": source or "investor profile"})

    add(f"{inv.name} is {inv.role_at_firm or inv.title} at {inv.current_firm or inv.company}".strip(), "directory")
    if inv.investment_thesis:
        add(f"Thesis: {inv.investment_thesis[:280]}", src)
    for r in (e.get("recent_investments_12mo") or [])[:3]:
        if isinstance(r, dict) and r.get("company"):
            add(f"Recently invested in {r['company']}" + (f" ({r['round']})" if r.get("round") else "")
                + (f", {r['date']}" if r.get("date") else ""), r.get("source_url") or src)
    port = e.get("notable_portfolio") or inv.portfolio_sample
    if isinstance(port, str):
        port = [x.strip() for x in port.split(";") if x.strip()]
    if port:
        add(f"Portfolio includes {', '.join(port[:4])}", src)
    for n in (e.get("recent_news") or [])[:2]:
        if isinstance(n, dict) and n.get("headline"):
            add(f"News: {n['headline']}" + (f" ({n['date']})" if n.get("date") else ""), n.get("url") or src)
    for h in (e.get("personalization_hooks") or [])[:3]:
        if isinstance(h, str):
            add(f"Their own words / hook: {h}", src)
    if p and p.sectors:
        hits = sector_overlap(p.sectors, inv)
        if hits:
            add(f"Sector overlap with the founder's company: {', '.join(hits)}", "fit score")
    if inv.focus_stages:
        add(f"Invests at: {inv.focus_stages}", src)
    if inv.typical_check_size:
        add(f"Typical check: {inv.typical_check_size}", src)
    return facts


# ---------------- sequences (SEQ-01..05) ----------------

SEQ_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["emails"],
    "properties": {"emails": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["step", "hook", "subject", "body", "fact_ids"],
        "properties": {
            "step": {"type": "integer", "enum": [1, 2, 3]},
            "hook": {"type": "string", "enum": ["traction-first", "insight-first", "portfolio-adjacent", "thesis-echo",
                                                "social-proof", "deadline-allocation", "ask-for-advice", "breakup"]},
            "subject": {"type": "string"}, "body": {"type": "string"},
            "fact_ids": {"type": "array", "items": {"type": "string"}}}}}},
}

PERSONA_GUIDE = {
    "momentum": "Parallel process, real deadlines, lead with traction and specifics, short and confident, truthful "
                "scarcity only if given as a fact, one clear next step.",
    "warm-intro": "Warm and referral-led; reference the mutual connection only if it is a provided fact.",
    "technical-founder": "Concrete product and technical depth; plain words; offer a product walkthrough.",
    "humble-expert": "Curious and respectful; ask for perspective; still specific about what the company does.",
}


def ai_sequence(db: Session, ws: Workspace, inv: Investor, p: CompanyProfile | None, persona: str,
                signature: str) -> tuple[list[dict], str] | None:
    facts = fact_pack(inv, p)
    company = shareable_profile(p)
    system = (
        "Write a 3-email cold outreach sequence from a founder to one investor. E1 is the hook, E2 a genuinely new "
        "angle (never 'just checking in'), E3 a last touch (ask-for-advice or breakup). Each email uses a different "
        "hook family. Hard limits: E1 <= 110 words, E2 <= 70, E3 <= 50 (body only, before the signature). Subject <= 6 "
        "words, no ALL CAPS, no clickbait. E1 must use at least 2 investor facts, E2 and E3 at least 1. Use only the "
        "investor facts and company fields provided; cite fact ids you used. No links, no attachments, no greeting "
        "other than 'Hi <first name>,'. Do not add a signature or an opt-out line; they are appended later.\n"
        f"Persona: {persona}. {PERSONA_GUIDE.get(persona, '')}"
    )
    user = json.dumps({"investor_first_name": outreach.first_name(inv.name), "investor_facts": facts,
                       "company": company, "founder_instructions": instructions(db, ws.id)[:2000],
                       "what_worked_before": memory_text(db, ws.id, 10)}, default=str)
    out, engine = ai.json_call(db, ws, "draft", system, user, SEQ_SCHEMA, max_tokens=6000)
    if not out or len(out.get("emails", [])) != 3:
        return None
    by_id = {f["id"]: f for f in facts}
    emails = []
    for e in sorted(out["emails"], key=lambda x: x["step"]):
        body = "\n\n".join([e["body"].strip(), outreach.OPT_OUT])
        body = outreach.trim_to(body, outreach.LIMITS[e["step"]])
        if signature:
            body = f"{body}\n\n{signature}"
        subj = " ".join(e["subject"].split()[:outreach.SUBJECT_MAX_WORDS])
        if outreach.lint(subj, body, e["step"], signature):
            return None  # the deterministic engine is always lint-clean; use it instead
        emails.append(dict(step=e["step"], hook=e["hook"], subject=subj, body=body,
                           facts=[{"text": by_id[i]["text"], "source": by_id[i]["source"]}
                                  for i in e["fact_ids"] if i in by_id]))
    if [e["step"] for e in emails] != [1, 2, 3] or len({e["hook"] for e in emails}) < 3:
        return None
    return emails, engine


def draft_sequence(db: Session, ws: Workspace, inv: Investor, p: CompanyProfile | None, persona: str,
                   signature: str) -> tuple[list[dict], str]:
    got = ai_sequence(db, ws, inv, p, persona, signature)
    if got:
        return got
    return outreach.draft_sequence(inv, p, persona, instructions(db, ws.id), signature), "template"


# ---------------- deck → company profile (DECK-01) ----------------

PROFILE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["company_name", "one_liner", "sectors", "stage", "geography", "round_size", "instrument", "traction",
                 "business_model", "investor_types", "looking_for", "confidence", "gaps"],
    "properties": {
        "company_name": {"type": "string"}, "one_liner": {"type": "string"},
        "investor_types": {"type": "array", "items": {"type": "string", "enum": [
            "angel", "syndicate", "vc", "cvc", "family_office", "accelerator"]}},
        "looking_for": {"type": "string"},
        "sectors": {"type": "array", "items": {"type": "string"}},
        "stage": {"type": "string", "enum": ["", "pre-seed", "seed", "series-a", "series-b"]},
        "geography": {"type": "string"}, "round_size": {"type": "string"},
        "instrument": {"type": "string", "enum": ["", "SAFE", "Equity", "Convertible", "ASA", "Other"]},
        "traction": {"type": "string"}, "business_model": {"type": "string"},
        "confidence": {"type": "object", "additionalProperties": {"type": "string", "enum": ["high", "medium", "low"]}},
        "gaps": {"type": "array", "items": {"type": "string"}},
    },
}


def ai_profile(db: Session, ws: Workspace, deck_text: str, sector_vocab: list[str]) -> dict | None:
    system = ("Extract a structured company profile from a startup pitch deck's text. Use only what the deck says; "
              "leave a field empty when the deck doesn't state it. 'sectors' should use the closest labels from the "
              "provided vocabulary. 'investor_types' are the kinds of investors the round suits (angels for small "
              "pre-seed rounds, VCs for larger ones). 'looking_for' says in one line what the founder wants from "
              "investors (lead, sector expertise, intros), if the deck says. 'gaps' lists what seed investors usually "
              "ask for that the deck is missing.")
    user = json.dumps({"sector_vocabulary": sector_vocab[:80], "deck_text": deck_text[:60000]})
    out, _ = ai.json_call(db, ws, "profile", system, user, PROFILE_SCHEMA, max_tokens=3000)
    # Onboarding matters on every plan: plans without drafting AI still get the deck read by the small model.
    return out or ai.small_json(db, ws, f"{ai.SAFETY}\n\n{system}", user, PROFILE_SCHEMA, max_tokens=3000)


# ---------------- meeting brief (AGT-04) ----------------

BRIEF_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["who", "thesis", "recent", "overlaps", "likely_questions", "suggested_asks", "red_flags",
                 "talking_points"],
    "properties": {k: {"type": "array", "items": {"type": "string"}} for k in
                   ["recent", "overlaps", "likely_questions", "suggested_asks", "red_flags", "talking_points"]}
    | {"who": {"type": "string"}, "thesis": {"type": "string"}},
}

STAGE_QUESTIONS = {
    "pre-seed": ["Why is this team the one to build it?", "What have you learned from the first users?",
                 "How will you use this round to reach the next milestone?"],
    "seed": ["What drives growth today and is it repeatable?", "What does retention look like by cohort?",
             "Who else is in the round, and who leads?"],
    "series-a": ["What are unit economics and payback?", "How big is the pipeline and what converts?",
                 "What does the next 18 months of hiring look like?"],
}


def template_brief(inv: Investor | None, card: FunnelCard, p: CompanyProfile | None) -> dict:
    facts = fact_pack(inv, p) if inv else []
    e = (inv.enrichment or {}) if inv else {}
    flags = []
    if inv:
        if inv.active_last_12mo == "no":
            flags.append("No verified deals in the last 12 months.")
        if inv.leads_rounds == "no":
            flags.append("Usually follows rather than leads.")
        if inv.is_decision_maker is False:
            flags.append("Role may not make investment decisions; ask who does.")
        if inv.seed_fit is False:
            flags.append("Profile looks later-stage than your round.")
    f = fit(inv, p) if inv else {"reasons": []}
    stage = (p.stage if p else "") or "seed"
    prof = shareable_profile(p)
    return {
        "who": f"{card.name}, {(inv.role_at_firm or inv.title) if inv else card.investor_type} at "
               f"{(inv.current_firm or inv.company) if inv else card.firm}".strip(", "),
        "thesis": (inv.investment_thesis if inv else "") or "No thesis on record. Ask what they look for at your stage.",
        "recent": [x["text"] for x in facts if x["text"].startswith(("Recently", "News"))][:4],
        "overlaps": f["reasons"],
        "likely_questions": STAGE_QUESTIONS.get(stage, STAGE_QUESTIONS["seed"]),
        "suggested_asks": ["Do you have capacity to lead or join this round?", "What would you need to see to commit?",
                           "Who else should we talk to?"],
        "red_flags": flags,
        "talking_points": [v for v in [prof.get("one_liner"), prof.get("traction"),
                                       f"Raising {prof['round_size']}" if prof.get("round_size") else ""] if v]
        + ([f"Ask about {e['notable_portfolio'][0]}"] if isinstance(e.get("notable_portfolio"), list)
           and e.get("notable_portfolio") else []),
    }


def meeting_brief(db: Session, ws: Workspace, card: FunnelCard) -> MeetingBrief:
    inv = db.get(Investor, card.investor_id) if card.investor_id else None
    p = db.get(CompanyProfile, ws.id)
    notes = [ev.body for ev in db.scalars(select(CardEvent).where(CardEvent.card_id == card.id, CardEvent.kind.in_(
        ["note", "reply"])).order_by(CardEvent.created_at.desc()).limit(8))]
    content, engine = None, "template"
    if inv or notes:
        system = ("Prepare a one-page meeting brief for a founder about to meet an investor. Use only the facts, "
                  "notes and company fields given. Keep each list to 3-5 short items. Map talking points to the "
                  "company's shareable facts.")
        content, engine = ai.json_call(db, ws, "brief", system, json.dumps({
            "investor_facts": fact_pack(inv, p) if inv else [], "card": {"name": card.name, "firm": card.firm,
                                                                          "stage": STAGES[card.stage - 1]},
            "founder_notes": notes, "company": shareable_profile(p)}, default=str), BRIEF_SCHEMA, max_tokens=3000)
    if not content:
        content, engine = template_brief(inv, card, p), "template"
    b = MeetingBrief(workspace_id=ws.id, card_id=card.id, content=content, engine=engine)
    db.add(b)
    db.flush()
    return b


# ---------------- daily brief + insights (AGT-02, §11.1) ----------------


def insights(db: Session, ws_id) -> list[str]:
    rows = db.execute(select(Email.hook, func.count(), func.count(Email.replied_at)).where(
        Email.workspace_id == ws_id, Email.status == "sent", Email.sequence_id.is_not(None), Email.step == 1)
        .group_by(Email.hook)).all()
    out = []
    total_sent = sum(r[1] for r in rows)
    total_rep = sum(r[2] for r in rows)
    for hook, sent, rep in rows:
        if sent >= 10 and total_sent > sent:
            other = (total_rep - rep) / max(1, total_sent - sent)
            rate = rep / sent
            if other > 0 and rate / other >= 1.5:
                out.append(f"First emails using the {hook} hook get {rate / other:.1f}x more replies.")
    opened = db.scalar(select(func.count()).select_from(Email).where(Email.workspace_id == ws_id, Email.open_count >= 3,
                                                                    Email.replied_at.is_(None)))
    if opened:
        out.append(f"{opened} investor{'s' if opened > 1 else ''} opened your email 3+ times without replying. "
                   "A short WhatsApp or LinkedIn nudge often works here.")
    return out[:3]


def brief_data(db: Session, ws_id, user: User, today: date) -> dict:
    cards = db.scalars(select(FunnelCard).where(FunnelCard.workspace_id == ws_id, FunnelCard.deleted_at.is_(None))).all()
    due = [c for c in cards if c.next_contact_date == today and c.status == "Active"]
    overdue = [c for c in cards if c.next_contact_date and c.next_contact_date < today and c.status == "Active"]
    cold = [c for c in cards if c.status == "Active" and 2 <= c.stage <= 6 and c.last_contacted_at
            and c.last_contacted_at < datetime.now(UTC) - timedelta(days=14)]
    replies = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.workspace_id == ws_id, Notification.user_id == user.id, Notification.kind == "reply",
        Notification.read_at.is_(None))) or 0
    calls = [c for c in cards if c.call_at and today <= c.call_at.date() <= today + timedelta(days=1)]
    return {"replies": replies, "due": due, "overdue": overdue, "cold": cold, "calls": calls,
            "insights": insights(db, ws_id)}


def send_daily_briefs(db: Session, now: datetime | None = None) -> int:
    """Creates the in-app daily brief at the user's brief time (default 08:00, user TZ)."""
    from zoneinfo import ZoneInfo

    from ..models import WorkspaceMember

    now = now or datetime.now(UTC)
    n = 0
    for user in db.scalars(select(User).where(User.suspended_at.is_(None))).all():
        try:
            local = now.astimezone(ZoneInfo(user.timezone or "UTC"))
        except Exception:
            local = now
        at = (user.notify_prefs or {}).get("brief_time", "08:00")
        if user.last_brief_on == local.date() or local.strftime("%H:%M") < at:
            continue
        if (user.notify_prefs or {}).get("daily_brief", {}).get("in_app") is False:
            user.last_brief_on = local.date()
            continue
        for (ws_id,) in db.execute(select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)):
            d = brief_data(db, ws_id, user, local.date())
            parts = []
            if d["replies"]:
                parts.append(f"{d['replies']} repl{'ies' if d['replies'] > 1 else 'y'} to handle")
            if d["due"]:
                parts.append(f"{len(d['due'])} follow-up{'s' if len(d['due']) > 1 else ''} due today")
            if d["overdue"]:
                parts.append(f"{len(d['overdue'])} overdue")
            if d["calls"]:
                parts.append(f"{len(d['calls'])} call{'s' if len(d['calls']) > 1 else ''} today or tomorrow")
            if d["cold"]:
                parts.append(f"{len(d['cold'])} going cold")
            if not parts and not d["insights"]:
                continue
            db.add(Notification(workspace_id=ws_id, user_id=user.id, kind="daily_brief",
                                title="Your daily brief: " + (", ".join(parts) if parts else "one insight"),
                                body="\n".join(d["insights"]), link="/app"))
            n += 1
        user.last_brief_on = local.date()
    db.commit()
    return n


def prepare_call_briefs(db: Session, now: datetime | None = None) -> int:
    """§10.4: call date set → meeting brief ready 24h before."""
    now = now or datetime.now(UTC)
    cards = db.scalars(select(FunnelCard).where(FunnelCard.call_at > now, FunnelCard.call_at <= now + timedelta(hours=24),
                                                FunnelCard.deleted_at.is_(None))).all()
    n = 0
    for card in cards:
        if db.scalar(select(func.count()).select_from(MeetingBrief).where(
                MeetingBrief.card_id == card.id, MeetingBrief.created_at > now - timedelta(days=3))):
            continue
        ws = db.get(Workspace, card.workspace_id)
        meeting_brief(db, ws, card)
        owner = db.scalar(select(Reminder.user_id).where(Reminder.card_id == card.id).limit(1))
        if owner:
            db.add(Notification(workspace_id=ws.id, user_id=owner, kind="brief", title=f"Call with {card.name}: brief ready",
                                link=f"/app/funnel/{card.id}"))
        n += 1
    db.commit()
    return n


# ---------------- chat (AGT-05) ----------------

SYSTEM = """You are {name}, the founder's Raise Agent inside EasyFundraise: their assistant for the whole fundraise
and the whole site. You can search and research investors, manage the shortlist and investor tracker, set reminders,
update their company profile, settings, instructions and data room, read their calendar, and draft investor emails.
Today is {today}; the founder's timezone is {tz}.

How to work:
- Act, don't explain how to use the site. Use tools to look things up before answering and to make changes the
  founder asks for. Profile, settings, shortlist, tracker, reminders and data room text change at once.
- Emails are never sent from chat. propose_email drafts them for review; propose_send opens the confirm screen.
  When the founder says "email X", use find_contact first. One match: propose. Several: list them (name, firm,
  stage) and ask which. None: say so and offer to search the database.
- Moving or noting tracker cards and publishing the data room are proposals the founder taps; say so in one line.
- Answer in a few short sentences or a short list. Name investors with their firm. Offer one clear next step,
  using open_page for a button when it helps.

Founder instructions (highest priority after safety):
{instructions}
Company profile: {profile}
Memory:
{memory}"""


def chat(c, text: str) -> ChatMessage:
    from . import agent_tools, calendar

    db, ws, user = c.db, c.workspace, c.user
    db.add(ChatMessage(workspace_id=ws.id, user_id=user.id, role="user", text=text[:4000],
                       created_at=datetime.now(UTC)))  # explicit: now() is transaction time, both rows would tie
    db.flush()
    history = db.scalars(select(ChatMessage).where(ChatMessage.workspace_id == ws.id, ChatMessage.user_id == user.id)
                         .order_by(ChatMessage.created_at.desc()).limit(16)).all()[::-1]
    messages = [{"role": m.role, "content": m.text or "(done)"} for m in history]
    actions: list = []
    p = db.get(CompanyProfile, ws.id)
    system = SYSTEM.format(name=ws.agent_name, today=f"{date.today():%A %d %B %Y}", tz=user.timezone,
                           instructions=instructions(db, ws.id)[:2000] or "(none)",
                           profile=json.dumps(shareable_profile(p), default=str), memory=memory_text(db, ws.id) or "(none)")
    tools = agent_tools.TOOLS + calendar.TOOLS
    reply = ""
    for _ in range(8):
        resp = ai.tool_turn(db, ws, system, messages, tools)
        if resp is None:
            reply = fallback_chat(c, text, actions)
            break
        if resp.stop_reason == "refusal":
            reply = "I can't help with that one."
            break
        messages.append({"role": "assistant", "content": resp.content})
        uses = [b for b in resp.content if b.type == "tool_use"]
        reply = "".join(b.text for b in resp.content if b.type == "text").strip()
        if resp.stop_reason != "tool_use" or not uses:
            break
        results = []
        for b in uses:
            args = b.input if isinstance(b.input, dict) else {}
            try:
                if b.name in calendar.TOOL_NAMES:
                    out = calendar.run(c, b.name, args)
                else:
                    out = agent_tools.run(c, b.name, args, actions)
                db.flush()
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
            except Exception as e:  # report tool errors to the model instead of failing the chat
                db.rollback()
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": f"Error: {e}", "is_error": True})
        messages.append({"role": "user", "content": results})
    msg = ChatMessage(workspace_id=ws.id, user_id=user.id, role="assistant", text=reply or "Done.", actions=actions,
                      created_at=datetime.now(UTC))
    db.add(msg)
    db.commit()
    return msg


def fallback_chat(c, text: str, actions: list) -> str:
    """Without an AI key: understand the common asks directly instead of a canned summary."""
    import re

    from . import agent_tools

    low = text.lower().strip()
    if low.startswith("remember"):
        agent_tools.run(c, "remember", {"text": text.split(" ", 1)[-1]}, actions)
        return "Saved to memory."
    d = find_date(text, date.today())
    if "remind" in low and d:
        agent_tools.run(c, "create_reminder", {"title": text[:200], "due": d.isoformat()}, actions)
        return f"Done. I'll remind you on {d:%a %d %b}."
    if "data room" in low or "dataroom" in low:
        r = json.loads(agent_tools.run(c, "get_data_room", {}, actions))
        comp = r["completeness"]
        agent_tools.run(c, "open_page", {"page": "data_room", "label": "Open data room"}, actions)
        miss = ", ".join(m["label"] for m in comp["missing"][:5])
        state = "published" if r["published"] else "not published yet"
        return f"Your data room is {comp['pct']}% complete and {state}." + (f" Still to add: {miss}." if miss else "")
    m = re.match(r"(?:send |draft )?(?:an )?e-?mail(?: to)? (.+)", low)
    if m:
        who = m.group(1).strip(" .?!'\"")
        found = json.loads(agent_tools.run(c, "find_contact", {"name": who}, actions))
        hits = found["in_tracker"] or found["in_database"]
        if not hits:
            return f"I couldn't find {who} in your tracker or the investor database."
        if len(hits) > 1:
            return "Which one?\n" + "\n".join(f"- {h['name']} ({h.get('firm') or ''})" for h in hits[:8])
        iid = hits[0].get("investor_id")
        if iid:
            agent_tools.run(c, "propose_email", {"investor_id": iid}, actions)
            return f"Tap below to draft emails to {hits[0]['name']}. You'll review and confirm before anything sends."
        return f"{hits[0]['name']} is in your tracker but not in the investor database, so I can't draft for them yet."
    if any(w in low for w in ("find", "search", "investor", "angel", "vc", "fund")) and len(low) > 8:
        r = json.loads(agent_tools.run(c, "search_investors", {"query": text}, actions)) if not low.startswith(
            "who should") else None
        if r and r["top"]:
            agent_tools.run(c, "open_page", {"page": "investors", "label": "See all in Investors"}, actions)
            return f"{r['total']} investors match. Top picks:\n" + "\n".join(
                f"- {x['name']}, {x['firm']} ({x['match']} match)" for x in r["top"][:5])
    o = agent_tools.overview(c)
    lines = [f"{len(o['follow_ups_due'])} follow-ups due today, {len(o['overdue'])} overdue, "
             f"{o['unread_replies']} replies to handle. Data room {o['data_room']['complete_pct']}% complete."]
    lines += [f"Next: {n}" for n in (o["overdue"] + o["follow_ups_due"])[:3]]
    lines.append("For full answers and changes from chat, add an Anthropic API key (ANTHROPIC_API_KEY).")
    return "\n".join(lines)


def apply_action(c, msg: ChatMessage, action_id: str) -> dict:
    db, ws, user = c.db, c.workspace, c.user
    acts = [dict(a) for a in msg.actions]
    a = next((x for x in acts if x["id"] == action_id), None)
    if a is None or a["state"] != "pending":
        return {"ok": False}
    result: dict = {"ok": True}
    if a["type"] in ("move", "note"):
        from .agent_tools import find_card

        card = find_card(c, a["args"]["card_id"])
        if card is None:
            return {"ok": False}
        if a["type"] == "move":
            st = int(a["args"]["stage"])
            db.add(CardEvent(workspace_id=ws.id, card_id=card.id, user_id=user.id, kind="stage",
                             body=f"{STAGES[card.stage - 1]} → {STAGES[st - 1]}", meta={"old": card.stage, "new": st, "agent": True}))
            card.stage = st
        else:
            db.add(CardEvent(workspace_id=ws.id, card_id=card.id, user_id=user.id, kind="note", body=a["args"]["text"][:4000],
                             meta={"agent": True}))
        result["card_id"] = str(card.id)
    elif a["type"] == "sequence":
        from ..routers.sequences import DraftIn, draft

        result["sequence_id"] = draft(DraftIn(investor_id=a["args"]["investor_id"]), c)["id"]
    elif a["type"] == "publish_room":
        from ..routers.dataroom import ensure_room, room_out

        room = ensure_room(db, ws.id, ws.name)
        room.published, room.access = True, a["args"].get("access", "public")
        result["url"] = room_out(room)["url"]
    a["state"] = "applied"
    msg.actions = acts
    db.commit()
    return result
