"""§9.1 Personal Super Agent: AI drafting with a fact pack (SEQ-03, AGT-08), deck → profile (DECK-01),
meeting briefs (AGT-04), chat with previewed tools (AGT-05), memory (AGT-07), daily brief + insights
(AGT-02, §11.1). Every function has a deterministic path when AI is unavailable.
"""

import json
import uuid
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
    Sequence,
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
                 "business_model", "confidence", "gaps"],
    "properties": {
        "company_name": {"type": "string"}, "one_liner": {"type": "string"},
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
              "provided vocabulary. 'gaps' lists what seed investors usually ask for that the deck is missing.")
    out, _ = ai.json_call(db, ws, "profile", system,
                          json.dumps({"sector_vocabulary": sector_vocab[:80], "deck_text": deck_text[:60000]}),
                          PROFILE_SCHEMA, max_tokens=3000)
    return out


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

TOOLS = [
    {"name": "search_investors", "description": "Search the investor database by free text (sector, thesis, location, name).",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "list_funnel", "description": "List the founder's funnel cards, optionally filtered by stage (1-9) or status.",
     "input_schema": {"type": "object", "properties": {"stage": {"type": "integer"}, "status": {"type": "string"}}}},
    {"name": "get_card", "description": "Get one funnel card with its latest notes and events. Accepts a card id or a name.",
     "input_schema": {"type": "object", "properties": {"card": {"type": "string"}}, "required": ["card"]}},
    {"name": "explain_fit", "description": "Explain the fit score for an investor id against the company profile.",
     "input_schema": {"type": "object", "properties": {"investor_id": {"type": "string"}}, "required": ["investor_id"]}},
    {"name": "create_reminder", "description": "Create a reminder now (applied immediately). due is YYYY-MM-DD.",
     "input_schema": {"type": "object", "properties": {"title": {"type": "string"}, "due": {"type": "string"},
                                                       "card_id": {"type": "string"}}, "required": ["title", "due"]}},
    {"name": "remember", "description": "Save a durable fact about the company, the raise or what works (agent memory).",
     "input_schema": {"type": "object", "properties": {"text": {"type": "string"},
                                                       "kind": {"type": "string", "enum": ["fact", "preference", "worked", "raise"]}},
                      "required": ["text"]}},
    {"name": "propose_move", "description": "Propose moving a funnel card to a stage (1-9). The founder must click to apply.",
     "input_schema": {"type": "object", "properties": {"card_id": {"type": "string"}, "stage": {"type": "integer"}},
                      "required": ["card_id", "stage"]}},
    {"name": "propose_note", "description": "Propose adding a note to a funnel card. The founder must click to apply.",
     "input_schema": {"type": "object", "properties": {"card_id": {"type": "string"}, "text": {"type": "string"}},
                      "required": ["card_id", "text"]}},
    {"name": "propose_sequence", "description": "Propose drafting a 3-email outreach sequence for an investor id.",
     "input_schema": {"type": "object", "properties": {"investor_id": {"type": "string"}}, "required": ["investor_id"]}},
]


def _uuid(s: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(s))
    except ValueError:
        return None


def _find_card(db: Session, ws_id, ref: str) -> FunnelCard | None:
    cid = _uuid(ref)
    q = select(FunnelCard).where(FunnelCard.workspace_id == ws_id, FunnelCard.deleted_at.is_(None))
    if cid:
        return db.scalar(q.where(FunnelCard.id == cid))
    return db.scalar(q.where(func.lower(FunnelCard.name).contains(ref.lower().strip())).limit(1))


def run_tool(db: Session, ws: Workspace, user: User, name: str, args: dict, actions: list) -> str:
    if name == "search_investors":
        rows = db.scalars(select(Investor).where(~Investor.suppressed, ~Investor.is_honeypot, Investor.search_tsv.op("@@")(
            func.websearch_to_tsquery("english", args.get("query", "")[:200]))).order_by(Investor.enriched.desc()).limit(8)).all()
        p = db.get(CompanyProfile, ws.id)
        return json.dumps([{"investor_id": str(i.id), "name": i.name, "firm": i.current_firm or i.company,
                            "type": i.investor_type, "fit": fit(i, p)["score"]} for i in rows])
    if name == "list_funnel":
        q = select(FunnelCard).where(FunnelCard.workspace_id == ws.id, FunnelCard.deleted_at.is_(None))
        if args.get("stage"):
            q = q.where(FunnelCard.stage == int(args["stage"]))
        if args.get("status"):
            q = q.where(FunnelCard.status == args["status"])
        return json.dumps([{"card_id": str(c.id), "name": c.name, "firm": c.firm, "stage": STAGES[c.stage - 1],
                            "status": c.status, "next_contact": str(c.next_contact_date or "")}
                           for c in db.scalars(q.order_by(FunnelCard.stage.desc()).limit(40))])
    if name == "get_card":
        c = _find_card(db, ws.id, args.get("card", ""))
        if not c:
            return "No matching card."
        evs = db.scalars(select(CardEvent).where(CardEvent.card_id == c.id).order_by(CardEvent.created_at.desc()).limit(8))
        return json.dumps({"card_id": str(c.id), "name": c.name, "firm": c.firm, "stage": STAGES[c.stage - 1],
                           "status": c.status, "ticket": c.ticket_size, "referrer": c.referrer,
                           "next_contact": str(c.next_contact_date or ""), "call_at": str(c.call_at or ""),
                           "events": [{"kind": e.kind, "body": e.body[:300], "at": str(e.created_at.date())} for e in evs]})
    if name == "explain_fit":
        inv = db.get(Investor, _uuid(args.get("investor_id", "")) or uuid.uuid4())
        return json.dumps(fit(inv, db.get(CompanyProfile, ws.id))) if inv and not inv.suppressed else "Investor not found."
    if name == "create_reminder":
        try:
            due = date.fromisoformat(args["due"])
        except (KeyError, ValueError):
            return "Invalid date; use YYYY-MM-DD."
        card = _find_card(db, ws.id, args["card_id"]) if args.get("card_id") else None
        db.add(Reminder(workspace_id=ws.id, user_id=user.id, card_id=card.id if card else None, title=args["title"][:300],
                        due_at=datetime.combine(due, datetime.min.time(), UTC) + timedelta(hours=9)))
        actions.append({"id": uuid.uuid4().hex[:8], "type": "reminder", "label": f"Reminder set: {args['title'][:80]} ({due})",
                        "args": args, "state": "applied"})
        return "Reminder created."
    if name == "remember":
        db.add(AgentMemory(workspace_id=ws.id, kind=args.get("kind", "fact"), text=args["text"][:500], source="chat"))
        actions.append({"id": uuid.uuid4().hex[:8], "type": "memory", "label": f"Remembered: {args['text'][:80]}",
                        "args": args, "state": "applied"})
        return "Saved to memory."
    if name in ("propose_move", "propose_note"):
        c = _find_card(db, ws.id, args.get("card_id", ""))
        if not c:
            return "No matching card."
        if name == "propose_move":
            st = int(args.get("stage", 0))
            if not 1 <= st <= 9:
                return "Stage must be 1-9."
            label = f"Move {c.name} to {STAGES[st - 1]}"
        else:
            label = f"Add note to {c.name}: {args.get('text', '')[:80]}"
        actions.append({"id": uuid.uuid4().hex[:8], "type": name.removeprefix("propose_"), "label": label,
                        "args": {**args, "card_id": str(c.id)}, "state": "pending"})
        return "Proposed; the founder will confirm."
    if name == "propose_sequence":
        inv = db.get(Investor, _uuid(args.get("investor_id", "")) or uuid.uuid4())
        if not inv or inv.suppressed:
            return "Investor not found."
        actions.append({"id": uuid.uuid4().hex[:8], "type": "sequence", "label": f"Draft emails to {inv.name}",
                        "args": {"investor_id": str(inv.id)}, "state": "pending"})
        return "Proposed; the founder will confirm."
    return "Unknown tool."


def chat(db: Session, ws: Workspace, user: User, text: str) -> ChatMessage:
    db.add(ChatMessage(workspace_id=ws.id, user_id=user.id, role="user", text=text[:4000]))
    db.flush()
    history = db.scalars(select(ChatMessage).where(ChatMessage.workspace_id == ws.id, ChatMessage.user_id == user.id)
                         .order_by(ChatMessage.created_at.desc()).limit(16)).all()[::-1]
    messages = [{"role": m.role, "content": m.text or "(done)"} for m in history]
    actions: list = []
    p = db.get(CompanyProfile, ws.id)
    system = (f"You are {ws.agent_name}, the founder's fundraising agent. Today is {date.today()} and the founder's "
              f"timezone is {user.timezone}. Be brief: a few sentences or a short list. Use tools to look things up "
              "before answering. Changes to cards and new drafts are proposals the founder confirms; say so.\n"
              f"Founder instructions (highest priority after safety):\n{instructions(db, ws.id)[:2000]}\n"
              f"Company: {json.dumps(shareable_profile(p), default=str)}\nMemory:\n{memory_text(db, ws.id)}")
    reply = ""
    for _ in range(6):
        resp = ai.tool_turn(db, ws, system, messages, TOOLS)
        if resp is None:
            reply = fallback_chat(db, ws, user, text, actions)
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
            try:
                out = run_tool(db, ws, user, b.name, b.input if isinstance(b.input, dict) else {}, actions)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
            except Exception as e:  # report tool errors to the model instead of failing the chat
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": f"Error: {e}", "is_error": True})
        messages.append({"role": "user", "content": results})
    msg = ChatMessage(workspace_id=ws.id, user_id=user.id, role="assistant", text=reply or "Done.", actions=actions)
    db.add(msg)
    db.commit()
    return msg


def fallback_chat(db: Session, ws: Workspace, user: User, text: str, actions: list) -> str:
    """Without AI: handle 'remind me…' and 'remember…', otherwise summarise today's priorities."""
    low = text.lower().strip()
    if low.startswith("remember"):
        run_tool(db, ws, user, "remember", {"text": text.split(" ", 1)[-1]}, actions)
        return "Saved to memory."
    d = find_date(text, date.today())
    if "remind" in low and d:
        run_tool(db, ws, user, "create_reminder", {"title": text[:200], "due": d.isoformat()}, actions)
        return f"Done. I'll remind you on {d:%a %d %b}."
    b = brief_data(db, ws.id, user, date.today())
    lines = [f"{len(b['due'])} follow-ups due today, {len(b['overdue'])} overdue, {b['replies']} replies to handle."]
    lines += [f"Next: {c.name} ({c.firm})" for c in (b["overdue"] + b["due"])[:3]]
    lines.append("Full chat needs AI drafting on your plan. You can still ask me to 'remind me …' or 'remember …'.")
    return "\n".join(lines)


def apply_action(db: Session, ws: Workspace, user: User, msg: ChatMessage, action_id: str) -> dict:
    acts = [dict(a) for a in msg.actions]
    a = next((x for x in acts if x["id"] == action_id), None)
    if a is None or a["state"] != "pending":
        return {"ok": False}
    result: dict = {"ok": True}
    if a["type"] in ("move", "note"):
        card = _find_card(db, ws.id, a["args"]["card_id"])
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
        inv = db.get(Investor, uuid.UUID(a["args"]["investor_id"]))
        p = db.get(CompanyProfile, ws.id)
        emails, engine = draft_sequence(db, ws, inv, p, "momentum", user.signature)
        seq = Sequence(workspace_id=ws.id, investor_id=inv.id, user_id=user.id, engine=engine)
        db.add(seq)
        db.flush()
        for e in emails:
            db.add(Email(workspace_id=ws.id, sequence_id=seq.id, user_id=user.id, **e))
        result["sequence_id"] = str(seq.id)
    a["state"] = "applied"
    msg.actions = acts
    db.commit()
    return result
