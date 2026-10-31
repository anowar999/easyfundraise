"""§9.5 round updates (FOMO) and §12 investor updates: audience selection, truthful content, per-recipient
personal line, warmest-first staggered scheduling."""

import json
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Broadcast, CardEvent, CompanyProfile, Email, FunnelCard, User, Workspace
from . import ai
from .mailer import excluded
from .outreach import OPT_OUT, first_name, next_send_slot

ROUND_TEMPLATES = {
    "first_close": "First close done",
    "lead_secured": "Lead secured",
    "oversubscribed": "Oversubscribed: final allocation",
    "closing_friday": "Closing Friday",
}
IR_TEMPLATES = {"monthly": "Monthly update", "quarterly": "Quarterly update"}


class Invalid(ValueError):
    pass


def audience(db: Session, ws_id, aud: dict) -> list[FunnelCard]:
    q = select(FunnelCard).where(FunnelCard.workspace_id == ws_id, FunnelCard.deleted_at.is_(None), FunnelCard.email != "")
    if aud.get("card_ids"):
        q = q.where(FunnelCard.id.in_(aud["card_ids"]))
    else:
        lo, hi = aud.get("stages", [2, 7])
        q = q.where(FunnelCard.stage >= int(lo), FunnelCard.stage <= int(hi),
                    FunnelCard.status.in_(aud.get("statuses", ["Active"])))
    cards = [c for c in db.scalars(q) if str(c.id) not in set(aud.get("exclude_card_ids", []))
             and c.status != "Rejection" and not excluded(db, ws_id, c.email)]
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    cards.sort(key=lambda c: (-c.stage, -(c.last_contacted_at or epoch).timestamp()))  # FOMO-02 warmest first
    return cards


def named_backers(db: Session, ws_id, card_ids: list[str]) -> list[FunnelCard]:
    """FOMO-01 truthfulness: only investors who committed (stage 08+) and agreed to be named (shareable)."""
    if not card_ids:
        return []
    cards = db.scalars(select(FunnelCard).where(FunnelCard.workspace_id == ws_id, FunnelCard.id.in_(card_ids))).all()
    bad = [c.name for c in cards if not (c.shareable and c.stage >= 8)]
    if bad or len(cards) != len(card_ids):
        raise Invalid(f"Only committed investors who agreed to be named can be mentioned: {', '.join(bad) or 'unknown card'}")
    return list(cards)


def committed_total(db: Session, ws_id) -> int:
    return db.scalar(select(func.count()).select_from(FunnelCard).where(
        FunnelCard.workspace_id == ws_id, FunnelCard.stage >= 8, FunnelCard.deleted_at.is_(None))) or 0


def _last_touch(db: Session, card: FunnelCard) -> str:
    ev = db.scalar(select(CardEvent).where(CardEvent.card_id == card.id, CardEvent.kind.in_(["note", "reply", "call"]))
                   .order_by(CardEvent.created_at.desc()).limit(1))
    return ev.body[:400] if ev else ""


def personal_line(db: Session, ws: Workspace, card: FunnelCard) -> str:
    touch = _last_touch(db, card)
    if touch:
        out, _ = ai.json_call(db, ws, "polish",
                              "Write one short sentence (max 22 words) a founder would open an update with, referring "
                              "to their last interaction with this investor. Use only the note given; no new facts.",
                              json.dumps({"investor_first_name": first_name(card.name), "last_note": touch}),
                              {"type": "object", "additionalProperties": False, "required": ["line"],
                               "properties": {"line": {"type": "string"}}}, max_tokens=200, effort="low")
        if out and len(out["line"].split()) <= 26:
            return out["line"].strip()
    if card.last_contacted_at:
        return f"Thanks again for your time in {card.last_contacted_at:%B}."
    return ""


def round_update_body(prof: CompanyProfile | None, template: str, inputs: dict, backers: list[FunnelCard],
                      line: str, fn: str) -> tuple[str, str]:
    company = (prof.company_name if prof else "") or "our company"
    rs = inputs.get("round_size") or (prof.round_size if prof else "")
    committed = inputs.get("amount_committed", "")
    pct = inputs.get("pct_allocated")
    close = inputs.get("closing_date", "")
    names = ", ".join(f"{b.name}{' (' + b.firm + ')' if b.firm else ''}" for b in backers)
    facts = []
    if template == "lead_secured" and names:
        facts.append(f"{names} {'is' if len(backers) == 1 else 'are'} leading our round.")
    elif names:
        facts.append(f"{names} {'has' if len(backers) == 1 else 'have'} committed.")
    if committed:
        facts.append(f"We have {committed} committed{' of our ' + rs + ' round' if rs else ''}"
                     f"{f' ({pct}% allocated)' if pct else ''}.")
    elif pct:
        facts.append(f"The round is {pct}% allocated.")
    if close:
        facts.append(f"We plan to close on {close}.")
    head = {"first_close": f"Quick update from {company}: we've completed our first close.",
            "lead_secured": f"Quick update from {company}: our round has a lead.",
            "oversubscribed": f"Quick update from {company}: the round is oversubscribed and we're finalising allocations.",
            "closing_friday": f"Quick update from {company}: we're closing the round this Friday."}[template]
    ask = {"oversubscribed": "If you'd like an allocation, let me know this week and I'll do my best to hold space.",
           "closing_friday": "If you'd like to join, reply before Friday and I'll send the docs."}.get(
        template, "If you'd like to take a look before we close, I can send the deck and data room today.")
    extra = (inputs.get("extra") or "").strip()
    body = "\n\n".join(x for x in [f"Hi {fn},", line, head, " ".join(facts), extra, ask, OPT_OUT] if x)
    subject = {"first_close": f"{company}: first close done", "lead_secured": f"{company}: lead secured",
               "oversubscribed": f"{company}: final allocations", "closing_friday": f"{company}: closing Friday"}[template]
    return subject, body


def ir_body(prof: CompanyProfile | None, inputs: dict, line: str, fn: str) -> tuple[str, str]:
    company = (prof.company_name if prof else "") or "our company"
    period = inputs.get("period") or datetime.now(UTC).strftime("%B %Y")
    parts = [f"Hi {fn},", line, f"Here is the {company} update for {period}."]
    metrics = [m for m in inputs.get("metrics", []) if m.get("label") and m.get("value")]
    if metrics:
        parts.append("Numbers\n" + "\n".join(f"- {m['label']}: {m['value']}" for m in metrics[:8]))
    for label, key in (("Wins", "wins"), ("Asks", "asks")):
        items = [x for x in inputs.get(key, []) if str(x).strip()]
        if items:
            parts.append(f"{label}\n" + "\n".join(f"- {x}" for x in items[:6]))
    for label, key in (("Hiring", "hiring"), ("Runway", "runway")):
        if inputs.get(key):
            parts.append(f"{label}: {inputs[key]}")
    parts.append("Reply 'unsubscribe' to stop these updates.")
    return f"{company} update: {period}", "\n\n".join(x for x in parts if x)


def build(db: Session, ws: Workspace, user: User, b: Broadcast) -> int:
    prof = db.get(CompanyProfile, ws.id)
    backers = named_backers(db, ws.id, b.inputs.get("lead_card_ids", [])) if b.kind == "round_update" else []
    cards = audience(db, ws.id, b.audience)
    for card in cards:
        fn = first_name(card.name)
        line = personal_line(db, ws, card)
        subj, body = (round_update_body(prof, b.template, b.inputs, backers, line, fn) if b.kind == "round_update"
                      else ir_body(prof, b.inputs, line, fn))
        if user.signature:
            body = f"{body}\n\n{user.signature}"
        db.add(Email(workspace_id=ws.id, broadcast_id=b.id, card_id=card.id, user_id=user.id, to_email=card.email,
                     step=1, hook=b.template, subject=subj, body=body, facts=[{"text": "Commitments from your funnel",
                                                                                "source": "funnel (shareable)"}]))
    return len(cards)


def schedule(db: Session, b: Broadcast, now: datetime) -> None:
    """FOMO-02: stagger over the day (sender pacing still applies); optional single follow-up after 4 days."""
    t = now
    for em in [e for e in b.emails if e.status == "draft" and e.step == 1]:
        card = db.get(FunnelCard, em.card_id) if em.card_id else None
        tz = (card.investor_timezone if card else "") or "UTC"
        if b.kind == "investor_update":
            em.scheduled_for = t
        else:
            em.scheduled_for = next_send_slot(t, tz)
        em.status = "scheduled"
        t += timedelta(minutes=random.randint(3, 9))
        if b.follow_up and b.kind == "round_update":
            fn = first_name(card.name) if card else "there"
            db.add(Email(workspace_id=em.workspace_id, broadcast_id=b.id, card_id=em.card_id, user_id=em.user_id,
                         to_email=em.to_email, step=2, hook="follow-up", subject=em.subject, status="scheduled",
                         scheduled_for=next_send_slot(em.scheduled_for + timedelta(days=4), tz),
                         body=f"Hi {fn},\n\nBumping this in case it got buried. Happy to send the deck today.\n\n{OPT_OUT}"))
