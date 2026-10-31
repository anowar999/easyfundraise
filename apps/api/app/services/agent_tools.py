"""The founder assistant's tools (AGT-05): everything the founder can do on the site, reachable from chat.

Reversible changes (profile, settings, shortlist, tracker, data room text, reminders, memory) apply at once and show
up as "Done" chips. Anything that reaches outside the workspace waits for the founder's tap: drafting emails,
publishing the data room, and above all sending, which always goes through the sequence confirm screen.
"""

import json
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, or_, select

from ..deps import Ctx
from ..errors import ApiError
from ..models import (
    STAGES,
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


S, INT = {"type": "string"}, {"type": "integer"}
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
    _t("list_tracker", "List investor tracker cards, optionally by stage (1-9) or status.", {"stage": INT, "status": S}),
    _t("get_card", "One tracker card with latest notes and events. Accepts a card id or a name.", {"card": S},
       ["card"]),
    _t("propose_move", "Propose moving a tracker card to a stage (1-9). The founder taps to apply.",
       {"card_id": S, "stage": INT}, ["card_id", "stage"]),
    _t("propose_note", "Propose adding a note to a tracker card. The founder taps to apply.",
       {"card_id": S, "text": S}, ["card_id", "text"]),
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


def find_card(c: Ctx, ref: str) -> FunnelCard | None:
    q = select(FunnelCard).where(FunnelCard.workspace_id == c.ws_id, FunnelCard.deleted_at.is_(None))
    cid = _uuid(ref)
    if cid:
        return c.db.scalar(q.where(FunnelCard.id == cid))
    return c.db.scalar(q.where(func.lower(FunnelCard.name).contains(ref.lower().strip())).limit(1))


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
            "in_tracker": [{"card_id": str(x.id), "name": x.name, "firm": x.firm, "stage": STAGES[x.stage - 1],
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
        q = select(FunnelCard).where(FunnelCard.workspace_id == c.ws_id, FunnelCard.deleted_at.is_(None))
        if args.get("stage"):
            q = q.where(FunnelCard.stage == int(args["stage"]))
        if args.get("status"):
            q = q.where(FunnelCard.status == args["status"])
        return json.dumps([{"card_id": str(x.id), "name": x.name, "firm": x.firm, "stage": STAGES[x.stage - 1],
                            "status": x.status, "next_contact": str(x.next_contact_date or "")}
                           for x in db.scalars(q.order_by(FunnelCard.stage.desc()).limit(60))])

    if name == "get_card":
        x = find_card(c, args.get("card", ""))
        if not x:
            return "No matching card."
        evs = db.scalars(select(CardEvent).where(CardEvent.card_id == x.id).order_by(CardEvent.created_at.desc()).limit(8))
        return json.dumps({"card_id": str(x.id), "name": x.name, "firm": x.firm, "stage": STAGES[x.stage - 1],
                           "status": x.status, "ticket": x.ticket_size, "referrer": x.referrer,
                           "investor_id": str(x.investor_id) if x.investor_id else None,
                           "next_contact": str(x.next_contact_date or ""), "call_at": str(x.call_at or ""),
                           "events": [{"kind": e.kind, "body": e.body[:300], "at": str(e.created_at.date())} for e in evs]})

    if name in ("propose_move", "propose_note"):
        x = find_card(c, args.get("card_id", ""))
        if not x:
            return "No matching card."
        if name == "propose_move":
            st = int(args.get("stage", 0))
            if not 1 <= st <= 9:
                return "Stage must be 1-9."
            label = f"Move {x.name} to {STAGES[st - 1]}"
        else:
            label = f"Add note to {x.name}: {args.get('text', '')[:80]}"
        _act(actions, name.removeprefix("propose_"), label, {**args, "card_id": str(x.id)}, "pending")
        return "Proposed; the founder will tap to apply."

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
