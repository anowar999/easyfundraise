"""Outreach and the Investor tracker: emailing someone doesn't put them in the tracker. They join it when the
founder presses "Add to tracker" or when they reply positively; their outreach emails then hang off the new card,
with the history so far written onto it."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import CardEvent, Email, FunnelCard, Investor, Sequence

TYPE_FROM_INVESTOR = {"angel": "Angel", "vc": "VC Partner", "pe": "PE/Growth", "growth": "PE/Growth",
                      "cvc": "Corporate VC", "family_office": "Family Office", "syndicate": "Angel"}


def card_of(db: Session, ws_id, investor_id) -> FunnelCard | None:
    return db.scalar(select(FunnelCard).where(FunnelCard.workspace_id == ws_id, FunnelCard.investor_id == investor_id,
                                              FunnelCard.deleted_at.is_(None)))


def new_card(db: Session, ws_id, inv: Investor, source: str, stage: int = 1) -> FunnelCard:
    pos = (db.scalar(select(func.max(FunnelCard.position)).where(FunnelCard.workspace_id == ws_id,
                                                                 FunnelCard.stage == stage)) or 0) + 1
    card = FunnelCard(workspace_id=ws_id, investor_id=inv.id, name=inv.name, firm=inv.current_firm or inv.company,
                      investor_type=TYPE_FROM_INVESTOR.get(inv.investor_type, "Other"), stage=stage, position=pos,
                      source=source, tags=[], investor_timezone=inv.timezone)
    db.add(card)
    db.flush()
    return card


def attach(db: Session, card: FunnelCard, user_id: uuid.UUID | None = None, skip_reply_of=None) -> int:
    """Link this investor's outreach (sequences and their emails) to the card and copy the sent emails and replies
    onto its history. Returns how many emails were linked."""
    if card.investor_id is None:
        return 0
    n = 0
    for s in db.scalars(select(Sequence).where(Sequence.workspace_id == card.workspace_id,
                                               Sequence.investor_id == card.investor_id)).all():
        s.card_id = s.card_id or card.id
        for em in sorted(s.emails, key=lambda e: e.step):
            old = db.get(FunnelCard, em.card_id) if em.card_id else None
            if em.card_id == card.id or (old is not None and old.deleted_at is None):
                continue  # already on this card, or on another live one
            em.card_id = card.id
            n += 1
            if em.status == "sent" and em.sent_at:
                db.add(CardEvent(workspace_id=card.workspace_id, card_id=card.id, user_id=user_id or em.user_id,
                                 kind="email", body=f"Email {em.step} sent: {em.subject}",
                                 meta={"email_id": str(em.id), "from_outreach": True}, created_at=em.sent_at))
                if card.last_contacted_at is None or em.sent_at > card.last_contacted_at:
                    card.last_contacted_at = em.sent_at
            if em.replied_at and em.id != skip_reply_of:  # the reply being handled now is logged by the mailer
                db.add(CardEvent(workspace_id=card.workspace_id, card_id=card.id, kind="reply",
                                 body=f"Replied ({em.reply_kind or 'reply'})", meta={"kind": em.reply_kind},
                                 created_at=em.replied_at))
    return n


def for_positive_reply(db: Session, em: Email) -> FunnelCard | None:
    """A positive reply to outreach: the investor joins the tracker (or their existing card is used)."""
    s = db.get(Sequence, em.sequence_id) if em.sequence_id else None
    if s is None or s.investor_id is None:
        return None
    inv = db.get(Investor, s.investor_id)
    card = card_of(db, em.workspace_id, s.investor_id)
    if card is None and inv is not None:
        card = new_card(db, em.workspace_id, inv, "Outreach")
        db.add(CardEvent(workspace_id=em.workspace_id, card_id=card.id, kind="created",
                         body="Added to investor tracker after a positive reply", meta={"source": "Outreach"}))
    if card is not None:
        attach(db, card, skip_reply_of=em.id)
    return card
