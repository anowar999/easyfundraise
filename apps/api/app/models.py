"""Core tables (spec §21). Tenant tables carry workspace_id; queries are scoped via deps.WorkspaceCtx."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def updated() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def ws_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)


# ---------- identity ----------


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = pk()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    picture: Mapped[str] = mapped_column(Text, default="")
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signature: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = updated()


class AuthSession(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = pk()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    user_agent: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created()
    user: Mapped[User] = relationship()


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(200))
    agent_name: Mapped[str] = mapped_column(String(60), default="Raise")
    tier_code: Mapped[str] = mapped_column(ForeignKey("tiers.code"), default="trial")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = updated()


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), default="owner")  # owner | editor | viewer
    created_at: Mapped[datetime] = created()


# ---------- tiers & usage (spec §6) ----------


class Tier(Base):
    __tablename__ = "tiers"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    price_monthly: Mapped[int] = mapped_column(Integer, default=0)  # cents
    price_annual: Mapped[int] = mapped_column(Integer, default=0)
    # limits: searches_total | searches_month | reveals_month | emails_day | result_cap | workspaces | seats
    limits: Mapped[dict] = mapped_column(JSONB, default=dict)
    features: Mapped[dict] = mapped_column(JSONB, default=dict)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = updated()


class UsageCounter(Base):
    __tablename__ = "usage_counters"
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    metric: Mapped[str] = mapped_column(String(32), primary_key=True)
    period: Mapped[str] = mapped_column(String(10), primary_key=True)  # "all" | "2026-10" | "2026-10-30"
    count: Mapped[int] = mapped_column(Integer, default=0)


class RateLimit(Base):
    __tablename__ = "rate_limits"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


# ---------- investor data layer (spec §8) ----------


class Investor(Base):
    __tablename__ = "investors"
    id: Mapped[uuid.UUID] = pk()
    linkedin: Mapped[str] = mapped_column(Text, unique=True)  # dedup key (BUILD_BRIEF §4)
    name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(Text, default="")
    company: Mapped[str] = mapped_column(Text, default="")
    industries: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    stages_src: Mapped[str] = mapped_column(Text, default="")  # unreliable (DATA-01)
    check_size_src: Mapped[str] = mapped_column(Text, default="")  # unreliable (DATA-01)
    location: Mapped[str] = mapped_column(Text, default="")
    country: Mapped[str] = mapped_column(String(80), default="")
    timezone: Mapped[str] = mapped_column(String(64), default="")
    email: Mapped[str] = mapped_column(Text, default="")  # gated: never in list payloads (ASP-01)
    x_url: Mapped[str] = mapped_column(Text, default="")
    photo_url: Mapped[str] = mapped_column(Text, default="")
    portfolio_sample: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    more_portfolio: Mapped[int] = mapped_column(Integer, default=0)

    # Materialised from the latest enrichment version
    enriched: Mapped[bool] = mapped_column(Boolean, default=False)
    current_firm: Mapped[str] = mapped_column(Text, default="")
    firm_website: Mapped[str] = mapped_column(Text, default="")
    firm_type: Mapped[str] = mapped_column(Text, default="")
    role_at_firm: Mapped[str] = mapped_column(Text, default="")
    identity_confidence: Mapped[str] = mapped_column(String(10), default="")
    active_last_12mo: Mapped[str] = mapped_column(String(10), default="unknown")
    leads_rounds: Mapped[str] = mapped_column(String(20), default="unknown")
    instrument_preference: Mapped[str] = mapped_column(Text, default="unknown")
    focus_sectors: Mapped[str] = mapped_column(Text, default="")
    focus_stages: Mapped[str] = mapped_column(Text, default="")
    geography_focus: Mapped[str] = mapped_column(Text, default="")
    typical_check_size: Mapped[str] = mapped_column(Text, default="")
    investment_thesis: Mapped[str] = mapped_column(Text, default="")
    about: Mapped[str] = mapped_column(Text, default="")
    enrichment: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Derived (DATA-01)
    investor_type: Mapped[str] = mapped_column(String(32), default="other")
    seed_fit: Mapped[bool | None] = mapped_column(Boolean)
    is_decision_maker: Mapped[bool | None] = mapped_column(Boolean)

    is_honeypot: Mapped[bool] = mapped_column(Boolean, default=False)
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False)  # DATA-04
    source: Mapped[str] = mapped_column(String(40), default="directory")
    collected_at: Mapped[datetime] = created()
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = updated()

    search_tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(name,'') || ' ' || coalesce(company,'') || ' ' || "
            "coalesce(current_firm,'') || ' ' || coalesce(title,'') || ' ' || coalesce(focus_sectors,'') || ' ' || "
            "coalesce(investment_thesis,'') || ' ' || coalesce(about,'') || ' ' || coalesce(location,''))",
            persisted=True,
        ),
    )

    __table_args__ = (
        Index("ix_investors_tsv", "search_tsv", postgresql_using="gin"),
        Index("ix_investors_industries", "industries", postgresql_using="gin"),
        Index("ix_investors_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
    )


class InvestorEnrichmentVersion(Base):
    __tablename__ = "investor_enrichment_versions"
    id: Mapped[uuid.UUID] = pk()
    investor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("investors.id", ondelete="CASCADE"), index=True)
    data: Mapped[dict] = mapped_column(JSONB)
    data_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created()


class SuppressedInvestor(Base):
    """Global suppression list (DATA-04): blocks re-ingestion after a removal request."""

    __tablename__ = "suppressed_investors"
    linkedin: Mapped[str] = mapped_column(Text, primary_key=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = created()


class RemovalRequest(Base):
    __tablename__ = "investor_removal_requests"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    linkedin: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(10), default="remove")  # remove | update
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = created()


class Reveal(Base):
    __tablename__ = "investor_reveals"
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    investor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investors.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = created()


class DataAccessEvent(Base):
    """ASP-10: immutable record of every search / reveal / export."""

    __tablename__ = "data_access_events"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # search | reveal | profile | export
    investor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = created()


# ---------- workspace data ----------


class CompanyProfile(Base):
    __tablename__ = "company_profiles"
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    company_name: Mapped[str] = mapped_column(String(200), default="")
    one_liner: Mapped[str] = mapped_column(Text, default="")
    sectors: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    stage: Mapped[str] = mapped_column(String(32), default="")  # pre-seed | seed | series-a
    geography: Mapped[str] = mapped_column(Text, default="")
    round_size: Mapped[str] = mapped_column(Text, default="")
    instrument: Mapped[str] = mapped_column(String(32), default="")
    traction: Mapped[str] = mapped_column(Text, default="")
    business_model: Mapped[str] = mapped_column(Text, default="")
    deck_filename: Mapped[str] = mapped_column(Text, default="")
    deck_text: Mapped[str] = mapped_column(Text, default="")
    shareable: Mapped[dict] = mapped_column(JSONB, default=dict)  # DECK-04 per-field toggle
    updated_at: Mapped[datetime] = updated()


STAGES = [
    "01 Not started",
    "02 Intro requested",
    "03 In contact",
    "04 First call arranged",
    "05 Deck requested",
    "06 Deep dive / DD",
    "07 Term sheet / Offer",
    "08 Signed",
    "09 Payment received",
]
STATUSES = ["Active", "Inactive", "Rejection", "Ghosting"]
CARD_TYPES = [
    "Angel",
    "VC Partner",
    "General Partner",
    "Principal/Associate",
    "Family Office",
    "Corporate VC",
    "PE/Growth",
    "Junior/Analyst",
    "Other",
]


class FunnelCard(Base):
    __tablename__ = "funnel_cards"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    investor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("investors.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200))
    firm: Mapped[str] = mapped_column(Text, default="")
    investor_type: Mapped[str] = mapped_column(String(32), default="")
    priority: Mapped[str] = mapped_column(String(2), default="P3")
    status: Mapped[str] = mapped_column(String(16), default="Active")
    stage: Mapped[int] = mapped_column(Integer, default=1)  # 1..9 -> STAGES
    position: Mapped[float] = mapped_column(default=0.0)
    can_lead: Mapped[str] = mapped_column(String(8), default="")
    ticket_size: Mapped[str] = mapped_column(Text, default="")
    agreed_size: Mapped[str] = mapped_column(Text, default="")
    instrument: Mapped[str] = mapped_column(String(16), default="")
    contact_method: Mapped[str] = mapped_column(String(16), default="")
    email: Mapped[str] = mapped_column(Text, default="")  # user-entered (own data)
    referrer: Mapped[str] = mapped_column(Text, default="")
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_contact_date: Mapped[date | None] = mapped_column(Date)
    call_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    investor_timezone: Mapped[str] = mapped_column(String(64), default="")
    source: Mapped[str] = mapped_column(String(16), default="Manual")
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    shareable: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = updated()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_cards_ws_stage", "workspace_id", "stage", "position"),)


class CardEvent(Base):
    __tablename__ = "card_events"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("funnel_cards.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20))  # note | stage | status | call | contact | created
    body: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = created()


class Reminder(Base):
    __tablename__ = "reminders"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("funnel_cards.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created()


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(Text, default="")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created()


class Exclusion(Base):
    __tablename__ = "exclusions"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    kind: Mapped[str] = mapped_column(String(10))  # email | domain | firm | linkedin
    value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created()
    __table_args__ = (UniqueConstraint("workspace_id", "kind", "value"),)


class AgentInstruction(Base):
    __tablename__ = "agent_instructions"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    version: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created()


class Sequence(Base):
    __tablename__ = "sequences"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    investor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("investors.id", ondelete="CASCADE"))
    card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("funnel_cards.id", ondelete="SET NULL"))
    persona: Mapped[str] = mapped_column(String(32), default="momentum")
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | approved | stopped | done
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = updated()
    emails: Mapped[list["Email"]] = relationship(order_by="Email.step", cascade="all, delete-orphan")


class Email(Base):
    __tablename__ = "emails"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    sequence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sequences.id", ondelete="CASCADE"), index=True)
    step: Mapped[int] = mapped_column(Integer)  # 1..3
    hook: Mapped[str] = mapped_column(String(32), default="")
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    facts: Mapped[list] = mapped_column(JSONB, default=list)  # [{text, source}] "Why I wrote this"
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|scheduled|sent|cancelled
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gmail_thread_id: Mapped[str] = mapped_column(Text, default="")
    gmail_message_id: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = updated()


# ---------- platform ----------


class ConfigKV(Base):
    __tablename__ = "config_kv"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = updated()


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[uuid.UUID] = pk()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(60))
    target: Mapped[str] = mapped_column(Text, default="")
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = created()


class ErrorRecord(Base):
    """§18.3 Error Center: grouped by fingerprint."""

    __tablename__ = "errors"
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    error_type: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(Text, default="")
    stack: Mapped[str] = mapped_column(Text, default="")
    env: Mapped[str] = mapped_column(String(10), default="dev")
    count: Mapped[int] = mapped_column(Integer, default=1)
    users_affected: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    status: Mapped[str] = mapped_column(String(16), default="new")  # new|triaged|task_created|fixed|muted
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    first_seen: Mapped[datetime] = created()
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EngTask(Base):
    """§16.5 Agent Task Dashboard task."""

    __tablename__ = "eng_tasks"
    id: Mapped[uuid.UUID] = pk()
    type: Mapped[str] = mapped_column(String(16), default="feature")
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    requirement_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    source: Mapped[str] = mapped_column(String(16), default="admin")
    severity: Mapped[str] = mapped_column(String(10), default="medium")
    priority: Mapped[str] = mapped_column(String(4), default="P3")
    state: Mapped[str] = mapped_column(String(24), default="Idea")
    pr_urls: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = updated()
