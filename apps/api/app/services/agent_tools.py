"""The founder assistant's tools (AGT-05): everything the founder can do on the site, reachable from chat.

Reversible changes (profile, settings, shortlist, tracker, data room text, reminders, memory) apply at once and show
up as "Done" chips. Anything that reaches outside the workspace waits for the founder's tap: drafting emails,
publishing the data room, and above all sending, which always goes through the sequence confirm screen.
"""

import json
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from urllib.parse import quote

from sqlalchemy import func, or_, select

from ..deps import Ctx
from ..errors import ApiError
from ..models import (
    STAGES,
    STATUSES,
    AgentInstruction,
    AgentMemory,
    CardEvent,
    CompanyProfile,
    FunnelCard,
    Investor,
    InvestorResearch,
    Reminder,
    Sequence,
    ShortlistItem,
)
from .fit import fit

PROFILE_FIELDS = ("company_name", "one_liner", "sectors", "stage", "geography", "round_size", "instrument", "traction",
                  "business_model", "investor_types", "looking_for")
ROOM_SECTIONS = ("problem", "solution", "product", "traction", "market", "why_now", "business_model", "team", "ask",
                 "use_of_funds", "faq")
PAGES = {"home": "/app", "investors": "/app/investors", "shortlist": "/app/shortlist", "tracker": "/app/funnel",
         "emails": "/app/sequences", "data_room": "/app/data-room", "settings": "/app/settings",
         "onboarding": "/onboarding", "billing": "/app/settings/billing"}


def _t(name: str, description: str, props: dict | None = None, required: list[str] | None = None) -> dict:
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": props or {}, "required": required or []}}


S, INT, B = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}
PRIOS = ["P1", "P2", "P3", "P4"]
IDS = {"type": "array", "items": S}

TOOLS = [
    _t("get_overview", "Snapshot of the raise: today's follow-ups, overdue, replies, tracker counts by stage, "
       "shortlist size, profile and data room completeness, plan and usage. Call this for 'how am I doing' questions."),
    _t("search_investors", "Search the investor database in plain language, e.g. 'angels in healthcare, 500k cheques, "
       "UK, active'. Returns up to 10 with match score.", {"query": S}, ["query"]),
    _t("recommended_investors", "Top matches for the company profile, best first.", {"limit": INT}),
    _t("get_investor", "Full profile of one investor (thesis, stages, cheque, portfolio, recent news, best angle) and "
       "any saved web research.", {"investor_id": S}, ["investor_id"]),
    _t("research_investor", "Run live web research on an investor's firm: thesis, portfolio, partners, recent news. "
       "Uses one research credit unless cached.", {"investor_id": S}, ["investor_id"]),
    _t("find_contact", "Find a person by name across the founder's tracker and the investor database. Use before "
       "acting on 'email X' or 'move X'. Returns every match so you can ask which one when there are several.",
       {"name": S}, ["name"]),
    _t("list_shortlist", "Investors saved to the shortlist."),
    _t("add_to_shortlist", "Save investors to the shortlist (applied now).", {"investor_ids": IDS}, ["investor_ids"]),
    _t("remove_from_shortlist", "Remove investors from the shortlist (applied now).", {"investor_ids": IDS},
       ["investor_ids"]),
    _t("add_to_tracker", "Add investors to the investor tracker at stage 1, removing them from the shortlist "
       "(applied now). Use investor_ids from search, or name/firm for someone not in the database.",
       {"investor_ids": IDS, "name": S, "firm": S}),
    _t("list_tracker", "List investor tracker cards with their numbers (#1, #2 ...), optionally by stage (1-9), "
       "status (Active, Inactive, Rejection, Ghosting) or overdue follow-ups.",
       {"stage": INT, "status": S, "overdue": B}),
    _t("show_tracker", "Filter the founder's investor tracker view so they see only matching investors, e.g. 'show "
       "only active investors', 'which ones are overdue', 'show P1s in deck requested'. Returns the matches and "
       "updates the tracker on screen. Use this for every 'show me ...' about the tracker.",
       {"statuses": {"type": "array", "items": {"type": "string", "enum": STATUSES}}, "overdue": B, "due_today": B,
        "needs_action": B, "starred": B, "stale": B, "stage": INT, "priority": {"type": "string", "enum": PRIOS},
        "query": S, "numbers": {"type": "array", "items": INT}}),
    _t("get_card", "One tracker card with latest notes and events. card is its number ('#10' or '10'), name or id.",
       {"card": S}, ["card"]),
    _t("update_card", "Change a tracker card (applied now). card is its number ('#10'), name or id. Only pass the "
       "fields the founder asked to change. stage is 1-9; next_contact is the follow-up date YYYY-MM-DD ('' clears it).",
       {"card": S, "stage": INT, "status": {"type": "string", "enum": STATUSES},
        "priority": {"type": "string", "enum": PRIOS}, "next_contact": S, "ticket_size": S, "referrer": S,
        "can_lead": {"type": "string", "enum": ["Yes", "No", "Maybe"]}, "starred": B}, ["card"]),
    _t("add_note", "Add a note to a tracker card (applied now), word for word as the founder gave it. card is its "
       "number ('#10'), name or id. A date in the note also sets the follow-up date.",
       {"card": S, "text": S}, ["card", "text"]),
    _t("create_reminder", "Create a reminder (applied now). due is YYYY-MM-DD.",
       {"title": S, "due": S, "card_id": S}, ["title", "due"]),
    _t("remember", "Save a durable fact about the company, the raise or what works.",
       {"text": S, "kind": {"type": "string", "enum": ["fact", "preference", "worked", "raise"]}}, ["text"]),
    _t("list_email_sequences", "The outreach list: every investor added to outreach (each has a drafted or live email "
       "sequence), with counts by status. Use this for any question about outreach.",
       {"investor_id": S}),
    _t("propose_email", "Propose drafting a personalised 3-email sequence to an investor. The founder taps to draft "
       "it, then reviews and confirms before anything is sent.", {"investor_id": S}, ["investor_id"]),
    _t("propose_send", "Offer to open an existing drafted sequence on its confirm screen, where the founder checks "
       "sender, recipient and times and confirms sending. Nothing is sent from chat.", {"sequence_id": S},
       ["sequence_id"]),
    _t("get_profile", "The company profile used for matching and personalising emails."),
    _t("update_profile", "Update company profile fields (applied now). Only pass fields the founder asked to change. "
       "sectors and investor_types are lists; investor_types use angel, vc, syndicate, family_office, cvc, "
       "accelerator.", {k: (IDS if k in ("sectors", "investor_types") else S) for k in PROFILE_FIELDS}),
    _t("update_settings", "Update the founder's settings (applied now): email signature, display name, timezone "
       "(IANA, e.g. Europe/London), the assistant's name.",
       {"signature": S, "name": S, "timezone": S, "agent_name": S}),
    _t("set_agent_instructions", "Change the standing instructions the assistant and email drafts follow "
       "(applied now). mode append adds a line; replace overwrites.",
       {"text": S, "mode": {"type": "string", "enum": ["append", "replace"]}}, ["text"]),
    _t("get_data_room", "The data room: completeness %, what's missing, each section's text, link and who can see it."),
    _t("update_data_room_section", "Write or replace one data room section's text (applied now; the old version is "
       "kept). section is one of " + ", ".join(ROOM_SECTIONS) + ".",
       {"section": S, "body": S}, ["section", "body"]),
    _t("propose_publish_data_room", "Offer to publish the data room. access public = anyone with the link; "
       "email = viewers enter their email first. The founder taps to publish.",
       {"access": {"type": "string", "enum": ["public", "email", "password", "magic"]}}),
    _t("open_page", "Give the founder a button to a page: " + ", ".join(PAGES) + ", or an investor/card id.",
       {"page": S, "investor_id": S, "card_id": S, "label": S}),
]


def _uuid(s) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(s))
    except ValueError:
        return None


def _act(actions: list, kind: str, label: str, args: dict | None = None, state: str = "applied",
         href: str | None = None) -> None:
    a = {"id": uuid.uuid4().hex[:8], "type": kind, "label": label[:160], "args": args or {}, "state": state}
    if href:
        a["href"] = href
    actions.append(a)


NUM_REF = re.compile(r"^\s*(?:tracker|investor|card|no\.?|number)?\s*#?\s*(\d{1,5})\s*$", re.I)


def find_cards(c: Ctx, ref: str) -> list[FunnelCard]:
    """Cards matching a number (#10, 10, tracker 10), an id, or a name. An exact name wins over partial matches."""
    q = select(FunnelCard).where(FunnelCard.workspace_id == c.ws_id, FunnelCard.deleted_at.is_(None))
    ref = (ref or "").strip()
    if not ref:
        return []
    if cid := _uuid(ref):
        return list(c.db.scalars(q.where(FunnelCard.id == cid)))
    if m := NUM_REF.match(ref):
        return list(c.db.scalars(q.where(FunnelCard.number == int(m.group(1)))))
    low = ref.lower()
    exact = list(c.db.scalars(q.where(func.lower(FunnelCard.name) == low)))
    if exact:
        return exact
    return list(c.db.scalars(q.where(func.lower(FunnelCard.name).contains(low)).order_by(FunnelCard.number).limit(10)))


def find_card(c: Ctx, ref: str) -> FunnelCard | None:
    hits = find_cards(c, ref)
    return hits[0] if hits else None


def _which(hits: list[FunnelCard], ref: str) -> str:
    if not hits:
        return f"No tracker card matches '{ref}'."
    return "Several cards match; ask which one: " + "; ".join(f"#{x.number} {x.name} ({x.firm})" for x in hits[:8])


def card_row(x: FunnelCard, today: date | None = None) -> dict:
    today = today or date.today()
    return {"number": x.number, "card_id": str(x.id), "name": x.name, "firm": x.firm, "stage": STAGES[x.stage - 1],
            "status": x.status, "priority": x.priority,
            "next_contact": str(x.next_contact_date or ""),
            "overdue": bool(x.next_contact_date and x.next_contact_date < today)}


def tracker_matches(c: Ctx, f: dict) -> list[FunnelCard]:
    """The same rules the tracker page applies for a show_tracker filter."""
    from ..routers.funnel import STALE_DAYS

    today = date.today()
    q = select(FunnelCard).where(FunnelCard.workspace_id == c.ws_id, FunnelCard.deleted_at.is_(None))
    if f.get("statuses"):
        q = q.where(FunnelCard.status.in_(f["statuses"]))
    if f.get("overdue"):
        q = q.where(FunnelCard.next_contact_date < today)
    if f.get("due_today"):
        q = q.where(FunnelCard.next_contact_date == today)
    if f.get("needs_action"):
        q = q.where(FunnelCard.next_contact_date <= today)
    if f.get("starred"):
        q = q.where(FunnelCard.starred.is_(True))
    if f.get("stage"):
        q = q.where(FunnelCard.stage == int(f["stage"]))
    if f.get("priority"):
        q = q.where(FunnelCard.priority == f["priority"])
    if f.get("numbers"):
        q = q.where(FunnelCard.number.in_([int(n) for n in f["numbers"]]))
    if f.get("query"):
        q = q.where(or_(FunnelCard.name.ilike(f"%{f['query']}%"), FunnelCard.firm.ilike(f"%{f['query']}%")))
    rows = list(c.db.scalars(q.order_by(FunnelCard.number)))
    if f.get("stale"):
        cut = datetime.now(UTC) - timedelta(days=STALE_DAYS)
        rows = [x for x in rows if x.status in ("Active", "Ghosting") and (x.updated_at or x.created_at) < cut]
    return rows


def filter_label(f: dict) -> str:
    parts = list(f.get("statuses") or [])
    for k, label in (("overdue", "Overdue"), ("due_today", "Due today"), ("needs_action", "Needs action"),
                     ("starred", "Starred"), ("stale", "No update in 7+ days")):
        if f.get(k):
            parts.append(label)
    if f.get("stage"):
        parts.append(STAGES[int(f["stage"]) - 1][3:])
    if f.get("priority"):
        parts.append(f["priority"])
    if f.get("numbers"):
        parts.append(", ".join(f"#{n}" for n in f["numbers"][:6]))
    if f.get("query"):
        parts.append(f"“{f['query']}”")
    return " · ".join(parts) or "All investors"


def _investor(c: Ctx, iid) -> Investor | None:
    inv = c.db.get(Investor, _uuid(iid) or uuid.uuid4())
    return inv if inv and not inv.suppressed else None


def _inv_row(i: Investor, p) -> dict:
    return {"investor_id": str(i.id), "name": i.name, "firm": i.current_firm or i.company, "type": i.investor_type,
            "country": i.country, "cheque": i.check_size_src or i.typical_check_size, "match": f"{fit(i, p)['score']}%"}


def overview(c: Ctx) -> dict:
    from ..routers.dataroom import ensure_room
    from ..routers.workspace import profile_complete
    from . import room_fill
    from .agent import brief_data
    from .entitlements import effective_tier_code, limit, usage

    b = brief_data(c.db, c.ws_id, c.user, date.today())
    stages = dict(c.db.execute(select(FunnelCard.stage, func.count()).where(
        FunnelCard.workspace_id == c.ws_id, FunnelCard.deleted_at.is_(None)).group_by(FunnelCard.stage)).all())
    room = ensure_room(c.db, c.ws_id, c.workspace.name)
    comp = room_fill.completeness(room.content or {})
    p = c.db.get(CompanyProfile, c.ws_id)
    month = datetime.now(UTC).strftime("%Y-%m")
    return {
        "today": str(date.today()), "follow_ups_due": [x.name for x in b["due"]][:10],
        "overdue": [x.name for x in b["overdue"]][:10], "unread_replies": b["replies"],
        "calls_soon": [x.name for x in b["calls"]], "going_cold": [x.name for x in b["cold"]][:10],
        "tracker_by_stage": {STAGES[k - 1]: v for k, v in sorted(stages.items())},
        "shortlist": c.db.scalar(select(func.count()).select_from(ShortlistItem).where(ShortlistItem.workspace_id == c.ws_id)),
        "outreach_list": dict(c.db.execute(select(Sequence.status, func.count()).where(
            Sequence.workspace_id == c.ws_id, Sequence.status != "stopped").group_by(Sequence.status)).all()),
        "profile_complete": profile_complete(p),
        "data_room": {"complete_pct": comp["pct"], "missing": [m["label"] for m in comp["missing"]],
                      "published": room.published, "access": room.access},
        "plan": effective_tier_code(c.db, c.workspace),
        "searches_used": usage(c.db, c.workspace, "searches", "all") or usage(c.db, c.workspace, "searches", month),
        "searches_limit": limit(c.db, c.workspace, "searches_total") or limit(c.db, c.workspace, "searches_month"),
    }


def run(c: Ctx, name: str, args: dict, actions: list) -> str:  # noqa: C901 - one branch per tool keeps it readable
    db, p = c.db, c.db.get(CompanyProfile, c.ws_id)
    if name == "get_overview":
        return json.dumps(overview(c), default=str)

    if name == "search_investors":
        from ..routers.investors import SearchParams, _base_filters, facets
        from . import search_parse
        from .entitlements import consume, limit

        f = facets(c)
        parsed = search_parse.parse(db, c.workspace, args.get("query", "")[:300], [s["value"] for s in f["sectors"]],
                                    [x["value"] for x in f["countries"]])
        sp = SearchParams(**{k: v for k, v in parsed.items() if k in SearchParams.model_fields and v not in (None, "")})
        try:
            total_cap = limit(db, c.workspace, "searches_total")
            if total_cap is not None:
                consume(db, c.workspace, "searches", "all", total_cap)
        except ApiError:
            return "The founder has used all searches on their plan. Suggest upgrading (open_page billing)."
        conds = _base_filters(c, sp)
        total = db.scalar(select(func.count()).select_from(Investor).where(*conds))
        rows = db.scalars(select(Investor).where(*conds).order_by(Investor.enriched.desc(),
                                                                  Investor.seed_fit.desc().nulls_last()).limit(60)).all()
        rows = sorted(rows, key=lambda i: -fit(i, p)["score"])[:10]
        return json.dumps({"filters": parsed.get("summary") or {k: v for k, v in sp.model_dump(exclude_defaults=True).items()},
                           "total": total, "top": [_inv_row(i, p) for i in rows]}, default=str)

    if name == "recommended_investors":
        from ..routers.investors import recommended

        r = recommended(c)
        if r["needs_profile"]:
            return "No company profile yet. Ask about the company or suggest open_page onboarding."
        return json.dumps([{"investor_id": x["id"], "name": x["name"], "firm": x.get("firm"),
                            "match": f"{x['fit']['score']}%", "why": x["fit"].get("reasons", [])[:2]}
                           for x in r["items"][: int(args.get("limit") or 8)]], default=str)

    if name == "get_investor":
        inv = _investor(c, args.get("investor_id"))
        if not inv:
            return "Investor not found."
        e = inv.enrichment or {}
        r = db.get(InvestorResearch, inv.id)
        return json.dumps({**_inv_row(inv, p), "role": inv.role_at_firm or inv.title, "location": inv.location,
                           "thesis": inv.investment_thesis, "sectors": inv.focus_sectors, "stages": inv.focus_stages,
                           "leads": inv.leads_rounds, "portfolio": (e.get("notable_portfolio") or inv.portfolio_sample),
                           "recent": e.get("recent_investments_12mo", [])[:5], "angle": e.get("best_email_angle", ""),
                           "why_match": fit(inv, p).get("reasons", []), "research": r.data if r else None},
                          default=str)[:6000]

    if name == "research_investor":
        from ..routers.investors import run_research

        try:
            r = run_research(args.get("investor_id", ""), c)
        except ApiError as e:
            return f"Research unavailable: {e.title}"
        return json.dumps(r["research"], default=str)[:6000]

    if name == "find_contact":
        q = (args.get("name") or "").strip()
        if len(q) < 2:
            return "Give at least two letters of the name."
        cards = db.scalars(select(FunnelCard).where(FunnelCard.workspace_id == c.ws_id, FunnelCard.deleted_at.is_(None),
                                                    or_(FunnelCard.name.ilike(f"%{q}%"), FunnelCard.firm.ilike(f"%{q}%")))
                           .limit(10)).all()
        invs = db.scalars(select(Investor).where(~Investor.suppressed, or_(Investor.name.ilike(f"%{q}%"),
                                                                           Investor.current_firm.ilike(f"%{q}%")))
                          .limit(8)).all()
        return json.dumps({
            "in_tracker": [{"number": x.number, "card_id": str(x.id), "name": x.name, "firm": x.firm, "stage": STAGES[x.stage - 1],
                            "investor_id": str(x.investor_id) if x.investor_id else None} for x in cards],
            "in_database": [_inv_row(i, p) for i in invs]})

    if name in ("list_shortlist", "add_to_shortlist", "remove_from_shortlist"):
        from ..routers import shortlist

        if name == "list_shortlist":
            return json.dumps([{"investor_id": x["id"], "name": x["name"], "firm": x.get("firm"),
                                "match": f"{x['fit']['score']}%"} for x in shortlist.list_shortlist(c)["items"][:40]],
                              default=str)
        done = []
        for iid in args.get("investor_ids", [])[:50]:
            inv = _investor(c, iid)
            if inv:
                (shortlist.add if name == "add_to_shortlist" else shortlist.remove)(str(inv.id), c)
                done.append(inv.name)
        if done:
            verb = "Shortlisted" if name == "add_to_shortlist" else "Removed from shortlist"
            _act(actions, "shortlist", f"{verb}: {', '.join(done[:4])}{'…' if len(done) > 4 else ''}",
                 href=PAGES["shortlist"])
        return f"Done for {len(done)}."

    if name == "add_to_tracker":
        from ..routers.funnel import CardIn, create_card
        from ..routers.shortlist import ToTrackerIn, to_tracker

        c.require_editor()
        ids = [str(i.id) for i in (_investor(c, x) for x in args.get("investor_ids", [])[:50]) if i]
        if ids:
            r = to_tracker(ToTrackerIn(investor_ids=ids), c)
            _act(actions, "tracker", f"Added {len(ids)} to your investor tracker", href=PAGES["tracker"])
            return f"Added {r['added']} new cards ({len(ids) - r['added']} were already there)."
        if args.get("name"):
            card = create_card(CardIn(name=args["name"][:200], firm=(args.get("firm") or "")[:200]), c)
            _act(actions, "tracker", f"Added {args['name']} to your investor tracker", href=f"/app/funnel/{card['id']}")
            return f"Card created: {card['id']}"
        return "Pass investor_ids or a name."

    if name == "list_tracker":
        f = {"stage": args.get("stage"), "statuses": [args["status"]] if args.get("status") else None,
             "overdue": args.get("overdue")}
        return json.dumps([card_row(x) for x in tracker_matches(c, f)[:80]])

    if name == "show_tracker":
        f = {k: v for k, v in args.items() if v not in (None, "", [], False)}
        f["statuses"] = [x for x in f.get("statuses", []) if x in STATUSES]
        if not f["statuses"]:
            f.pop("statuses")
        if f.get("stage") and not 1 <= int(f["stage"]) <= 9:
            f.pop("stage")
        rows = tracker_matches(c, f)
        label = filter_label(f)
        _act(actions, "tracker_filter", f"Tracker: {label} ({len(rows)})", f,
             href=f"{PAGES['tracker']}?agent={quote(json.dumps(f, separators=(',', ':')))}")
        return json.dumps({"count": len(rows), "showing": label, "cards": [card_row(x) for x in rows[:60]]})

    if name == "update_card":
        from ..routers.funnel import CardIn, _event, apply

        c.require_editor()
        hits = find_cards(c, args.get("card", ""))
        if len(hits) != 1:
            return _which(hits, args.get("card", ""))
        x = hits[0]
        data: dict = {k: args[k] for k in ("stage", "status", "priority", "ticket_size", "referrer", "can_lead", "starred")
                      if args.get(k) not in (None, "")}
        if "next_contact" in args:
            try:
                data["next_contact_date"] = date.fromisoformat(args["next_contact"]) if args["next_contact"] else None
            except ValueError:
                return "Invalid date; use YYYY-MM-DD."
        if not data:
            return "Nothing to change."
        try:
            body = CardIn(**data)
        except ValueError as e:
            return f"Invalid value: {e}"
        apply(c, x, body)
        if "next_contact_date" in data:
            d = data["next_contact_date"]
            _event(c, x, "follow_up", f"Follow-up set for {d:%d %b %Y}" if d else "Follow-up date cleared", agent=True)
        changes = []
        for k, v in data.items():
            if k == "next_contact_date":
                changes.append(f"follow-up {v:%a %d %b}" if v else "follow-up cleared")
            elif k == "stage":
                changes.append(f"stage {STAGES[int(v) - 1][3:]}")
            else:
                changes.append(f"{k.replace('_', ' ')} {v}")
        _act(actions, "card", f"#{x.number} {x.name}: {', '.join(changes)}", {"card_id": str(x.id)},
             href=f"/app/funnel/{x.id}")
        return f"Updated #{x.number} {x.name}: {', '.join(changes)}."

    if name == "add_note":
        from ..routers.funnel import NoteIn
        from ..routers.funnel import add_note as add_card_note

        c.require_editor()
        hits = find_cards(c, args.get("card", ""))
        if len(hits) != 1:
            return _which(hits, args.get("card", ""))
        x, text = hits[0], (args.get("text") or "").strip()
        if not text:
            return "The note is empty."
        r = add_card_note(str(x.id), NoteIn(body=text[:10000]), c)
        _act(actions, "card", f"Note on #{x.number} {x.name}: {text[:80]}", {"card_id": str(x.id)},
             href=f"/app/funnel/{x.id}")
        return "Note added." + (f" Follow-up set for {r['reminder_date']}." if r.get("reminder_date") else "")

    if name == "get_card":
        hits = find_cards(c, args.get("card", ""))
        if len(hits) != 1:
            return _which(hits, args.get("card", ""))
        x = hits[0]
        evs = db.scalars(select(CardEvent).where(CardEvent.card_id == x.id).order_by(CardEvent.created_at.desc()).limit(8))
        return json.dumps({**card_row(x), "ticket": x.ticket_size, "referrer": x.referrer,
                           "investor_id": str(x.investor_id) if x.investor_id else None,
                           "next_contact": str(x.next_contact_date or ""), "call_at": str(x.call_at or ""),
                           "events": [{"kind": e.kind, "body": e.body[:300], "at": str(e.created_at.date())} for e in evs]})

    if name == "create_reminder":
        try:
            due = date.fromisoformat(args["due"])
        except (KeyError, ValueError):
            return "Invalid date; use YYYY-MM-DD."
        x = find_card(c, args["card_id"]) if args.get("card_id") else None
        db.add(Reminder(workspace_id=c.ws_id, user_id=c.user.id, card_id=x.id if x else None, title=args["title"][:300],
                        due_at=datetime.combine(due, datetime.min.time(), UTC) + timedelta(hours=9)))
        _act(actions, "reminder", f"Reminder set: {args['title'][:80]} ({due})", args)
        return "Reminder created."

    if name == "remember":
        db.add(AgentMemory(workspace_id=c.ws_id, kind=args.get("kind", "fact"), text=args["text"][:500], source="chat"))
        _act(actions, "memory", f"Remembered: {args['text'][:80]}", args)
        return "Saved to memory."

    if name == "list_email_sequences":
        q = select(Sequence, Investor.name).join(Investor, Investor.id == Sequence.investor_id).where(
            Sequence.workspace_id == c.ws_id)
        if _uuid(args.get("investor_id")):
            q = q.where(Sequence.investor_id == _uuid(args["investor_id"]))
        rows = db.execute(q.where(Sequence.status != "stopped").order_by(Sequence.created_at.desc())).all()
        counts: dict[str, int] = {}
        for sq, _ in rows:
            counts[sq.status] = counts.get(sq.status, 0) + 1
        return json.dumps({"in_outreach": len(rows), "by_status": counts,  # draft = not sent yet, approved = scheduled/sending
                           "items": [{"sequence_id": str(sq.id), "investor": n, "status": sq.status,
                                      "drafted": str(sq.created_at.date())} for sq, n in rows[:20]]})

    if name == "propose_email":
        inv = _investor(c, args.get("investor_id"))
        if not inv:
            return "Investor not found. If they are a tracker card without a database match, emails need a database investor."
        _act(actions, "sequence", f"Draft personalised emails to {inv.name}", {"investor_id": str(inv.id)}, "pending")
        return "Proposed. When the founder taps, the drafts open for review; nothing sends until they confirm there."

    if name == "propose_send":
        s = db.get(Sequence, _uuid(args.get("sequence_id")) or uuid.uuid4())
        if not s or s.workspace_id != c.ws_id:
            return "Sequence not found."
        inv = db.get(Investor, s.investor_id)
        _act(actions, "open_sequence", f"Review and confirm emails to {inv.name if inv else 'investor'}",
             {"sequence_id": str(s.id)}, href=f"/app/sequences/{s.id}")
        return "Gave the founder a button to the confirm screen. Sending happens only after they confirm there."

    if name == "get_profile":
        from ..routers.workspace import _profile, _profile_out

        return json.dumps(_profile_out(_profile(c)), default=str)

    if name == "update_profile":
        from ..routers.workspace import _profile

        c.require_editor()
        prof = _profile(c)
        changed = []
        for k in PROFILE_FIELDS:
            if k in args and args[k] is not None:
                v = args[k]
                v = [str(x)[:80] for x in v][:10] if isinstance(v, list) else str(v)[:1000]
                setattr(prof, k, v)
                changed.append(k.replace("_", " "))
        if not changed:
            return "Nothing to change."
        _act(actions, "profile", f"Profile updated: {', '.join(changed)}", href=PAGES["settings"])
        return "Updated."

    if name == "update_settings":
        c.require_editor()
        changed = []
        if args.get("timezone"):
            from zoneinfo import ZoneInfo

            try:
                ZoneInfo(args["timezone"])
            except Exception:
                return "Unknown timezone; use an IANA name like Europe/London."
            c.user.timezone = args["timezone"]
            changed.append("timezone")
        for k in ("signature", "name"):
            if args.get(k) is not None:
                setattr(c.user, k, str(args[k])[:2000])
                changed.append(k)
        if args.get("agent_name"):
            c.workspace.agent_name = str(args["agent_name"]).strip()[:60]
            changed.append("assistant name")
        if not changed:
            return "Nothing to change."
        _act(actions, "settings", f"Settings updated: {', '.join(changed)}", href=PAGES["settings"])
        return "Updated."

    if name == "set_agent_instructions":
        c.require_editor()
        cur = db.scalar(select(AgentInstruction).where(AgentInstruction.workspace_id == c.ws_id)
                        .order_by(AgentInstruction.version.desc()))
        text = args["text"].strip()
        if args.get("mode", "append") == "append" and cur and cur.text:
            text = f"{cur.text}\n{text}"
        db.add(AgentInstruction(workspace_id=c.ws_id, version=(cur.version if cur else 0) + 1, text=text[:4000]))
        _act(actions, "instructions", f"Instructions updated: {args['text'][:80]}", href=PAGES["settings"])
        return "Saved."

    if name in ("get_data_room", "update_data_room_section", "propose_publish_data_room"):
        from ..routers.dataroom import ensure_room, room_out
        from . import room_fill

        room = ensure_room(db, c.ws_id, c.workspace.name)
        if name == "get_data_room":
            content = room.content or {}
            return json.dumps({**{k: v for k, v in room_out(room).items() if k in ("url", "published", "access")},
                               "completeness": room_fill.completeness(content),
                               "hero": content.get("hero"),
                               "sections": [{"id": s.get("id"), "title": s.get("title"), "body": (s.get("body") or "")[:600],
                                             "filled": room_fill.has_content(s)} for s in content.get("sections", [])]},
                              default=str)
        if name == "update_data_room_section":
            c.require_editor()
            sid = args.get("section", "")
            content = json.loads(json.dumps(room.content or {}))
            sec = next((s for s in content.get("sections", []) if s.get("id") == sid or s.get("type") == sid), None)
            if sec is None:
                if sid not in ROOM_SECTIONS:
                    return f"Unknown section; use one of {', '.join(ROOM_SECTIONS)}."
                sec = {"id": sid, "type": sid, "title": sid.replace("_", " ").capitalize(), "body": ""}
                content.setdefault("sections", []).append(sec)
            sec["body"] = args.get("body", "")[:4000]
            room.versions = ([{"at": datetime.now(UTC).isoformat(), "content": room.content}] + (room.versions or []))[:10]
            room.content = content
            _act(actions, "data_room", f"Data room: {sec.get('title', sid)} updated", href=PAGES["data_room"])
            return f"Saved. Data room is now {room_fill.completeness(content)['pct']}% complete."
        access = args.get("access") or "public"
        if access == "password" and not room.password_hash:
            return "Set a password on the data room page first (open_page data_room)."
        _act(actions, "publish_room", f"Publish data room ({'anyone with the link' if access == 'public' else access})",
             {"access": access}, "pending")
        return f"Proposed. Once published the link is {room_out(room)['url']}"

    if name == "open_page":
        if args.get("investor_id") and _investor(c, args["investor_id"]):
            href = f"/app/investors/{args['investor_id']}"
        elif args.get("card_id") and find_card(c, args["card_id"]):
            href = f"/app/funnel/{find_card(c, args['card_id']).id}"
        else:
            href = PAGES.get(args.get("page", ""), "/app")
        _act(actions, "link", args.get("label") or "Open", href=href)
        return "Button shown."

    return "Unknown tool."


# ---------- tracker commands without AI (the tracker's agent bar must work on servers with no AI key) ----------

CARD_NUM = re.compile(r"(?:\b(?:tracker|investor|card|no\.?|number)\s*#?\s*|#)(\d{1,5})\b", re.I)
QUOTED = re.compile(r"[\"“”'‘’](.+)[\"“”'‘’]", re.S)
STATUS_WORDS = {"active": "Active", "inactive": "Inactive", "ghosting": "Ghosting", "ghosted": "Ghosting",
                "rejected": "Rejection", "rejection": "Rejection", "passed": "Rejection"}


def _ref_in(c: Ctx, text: str) -> tuple[list[FunnelCard], str]:
    """Which card the founder means: a number ('#10', 'tracker 10') or a card name that appears in the text."""
    if m := CARD_NUM.search(text):
        return find_cards(c, m.group(1)), m.group(0)
    low = text.lower()
    cards = c.db.scalars(select(FunnelCard).where(FunnelCard.workspace_id == c.ws_id, FunnelCard.deleted_at.is_(None))
                         .limit(3000)).all()
    named = [x for x in cards if len(x.name) > 2 and re.search(r"\b" + re.escape(x.name.lower()) + r"\b", low)]
    if not named:
        return [], ""
    best = max(len(x.name) for x in named)
    return [x for x in named if len(x.name) == best], max(named, key=lambda x: len(x.name)).name


def _list_reply(rows: list[dict], label: str, total: int) -> str:
    if not total:
        return f"No investors match ({label})."
    head = f"{total} investor{'s' if total != 1 else ''}: {label}. Your tracker now shows just these."
    lines = [f"#{r['number']} {r['name']}" + (f" ({r['firm']})" if r["firm"] else "")
             + (f", follow-up {date.fromisoformat(r['next_contact']):%a %d %b}" if r["next_contact"] else "") for r in rows[:12]]
    return "\n".join([head, *lines] + ([f"…and {total - 12} more"] if total > 12 else []))


def tracker_command(c: Ctx, text: str, actions: list) -> str | None:  # noqa: C901
    from .notes import find_date

    low = text.lower().strip()
    hits, ref = _ref_in(c, text)

    # Add a note: 'add note on Paul Bartley "Need to ask Ben ..."'
    if re.search(r"\b(add|put|write|log|save)\b.{0,12}\bnotes?\b", low) and ref:
        if len(hits) != 1:
            return _which(hits, ref).replace("; ask which one", "")
        if m := QUOTED.search(text):
            note = m.group(1).strip()
        elif ":" in text:
            note = text.split(":", 1)[1].strip()
        else:
            note = text[text.lower().index(ref.lower()) + len(ref):].strip(" ,.-") if ref.lower() in text.lower() else ""
        if not note:
            return f"What should the note on #{hits[0].number} {hits[0].name} say?"
        run(c, "add_note", {"card": str(hits[0].id), "text": note}, actions)
        return f"Added the note to #{hits[0].number} {hits[0].name}."

    # Follow-up date: "set up a follow up date 02/Nov for #10"
    if re.search(r"follow[- ]?up|next contact|chase|remind", low) and ref:
        d = find_date(text.replace(ref, " "), date.today())
        if len(hits) != 1:
            return _which(hits, ref).replace("; ask which one", "")
        if not d:
            return f"Which date should I set for #{hits[0].number} {hits[0].name}? For example 02/Nov."
        run(c, "update_card", {"card": str(hits[0].id), "next_contact": d.isoformat()}, actions)
        return f"Follow-up for #{hits[0].number} {hits[0].name} set to {d:%a %d %b}. You'll get a reminder that morning."

    # Status or priority change on one card: "mark #10 as ghosting", "update tracker 10 to P1"
    if ref and re.search(r"\b(mark|set|update|change|make|move)\b", low):
        if len(hits) != 1:
            return _which(hits, ref).replace("; ask which one", "")
        args: dict = {"card": str(hits[0].id)}
        rest = low.replace(ref.lower(), " ")
        for w, st in STATUS_WORDS.items():
            if re.search(r"\b" + w + r"\b", rest):
                args["status"] = st
        if m := re.search(r"\bp([1-4])\b", rest):
            args["priority"] = f"P{m.group(1)}"
        for i, st in enumerate(STAGES):
            if st[3:].lower() in rest:
                args["stage"] = i + 1
        if len(args) > 1:
            out = run(c, "update_card", args, actions)
            return out.replace("Updated", "Done. Updated")
        return (f"What should I change on #{hits[0].number} {hits[0].name}? You can set the status, priority, stage, "
                "follow-up date or add a note.")

    # Filtered views: "show me only active investors", "which ones are overdue"
    if re.search(r"\b(show|which|who|list|only|filter|how many)\b", low):
        f: dict = {}
        sts = [st for w, st in STATUS_WORDS.items() if re.search(r"\b" + w + r"\b", low)]
        if sts:
            f["statuses"] = list(dict.fromkeys(sts))
        if re.search(r"overdue|late|missed", low):
            f["overdue"] = True
        if re.search(r"due today|today", low):
            f["due_today"] = True
        if "needs action" in low or "need action" in low:
            f["needs_action"] = True
        if re.search(r"\bstar(red)?\b|\bkey investors?\b", low):
            f["starred"] = True
        if re.search(r"\bquiet\b|no update|stale|gone cold", low):
            f["stale"] = True
        if m := re.search(r"\bp([1-4])s?\b", low):
            f["priority"] = f"P{m.group(1)}"
        for i, st in enumerate(STAGES):
            if st[3:].lower() in low:
                f["stage"] = i + 1
        if f:
            r = json.loads(run(c, "show_tracker", f, actions))
            return _list_reply(r["cards"], r["showing"], r["count"])
    return None
