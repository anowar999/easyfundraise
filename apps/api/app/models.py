"""Core tables (spec §21). Tenant tables carry workspace_id; queries are scoped via deps.WorkspaceCtx."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
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
    # §10.5: {"<kind>": {"in_app": bool, "email": bool}, "quiet_hours": ["22:00", "07:00"], "brief_time": "08:00"}
    notify_prefs: Mapped[dict] = mapped_column(JSONB, default=dict)
    totp_secret_enc: Mapped[str] = mapped_column(Text, default="")  # AUTH-08 admin MFA
    last_brief_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = updated()


class AuthSession(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = pk()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    user_agent: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created()
    user: Mapped[User] = relationship()


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(200))
    agent_name: Mapped[str] = mapped_column(String(60), default="Raise Agent")
    tier_code: Mapped[str] = mapped_column(ForeignKey("tiers.code"), default="trial")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tracking_enabled: Mapped[bool] = mapped_column(Boolean, default=True)  # TRK-01 per-workspace opt-out
    # AGT-08 consent level: "approved_sequences" (auto-send approved) | "ask_every_send"
    consent_level: Mapped[str] = mapped_column(String(24), default="approved_sequences")
    automations: Mapped[dict] = mapped_column(JSONB, default=dict)  # §10.4 toggles, missing key = on
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
    stripe_price_monthly: Mapped[str] = mapped_column(String(80), default="")
    stripe_price_annual: Mapped[str] = mapped_column(String(80), default="")
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


class ShortlistItem(Base):
    """Investors a workspace has saved while browsing, before adding them to the funnel."""

    __tablename__ = "shortlist_items"
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    investor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("investors.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = created()


class InvestorResearch(Base):
    """Live web research on an investor (thesis, portfolio, partners, news). Public facts, shared by all workspaces
    and refreshed when older than RESEARCH_TTL."""

    __tablename__ = "investor_research"
    investor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("investors.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    model: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
    investor_types: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)  # angel | vc | ... (who they want)
    looking_for: Mapped[str] = mapped_column(Text, default="")  # e.g. "a lead with healthcare distribution"
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
    starred: Mapped[bool] = mapped_column(Boolean, default=False)  # a key investor: can lead, great intros, ...
    star_reason: Mapped[str] = mapped_column(String(200), default="")
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


class FounderTask(Base):
    """Founder Tasks board: a sticky note moving To do -> In progress -> Done (-> Archive, hidden)."""

    __tablename__ = "founder_tasks"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))  # created by
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="todo")  # todo | doing | done | archived
    priority: Mapped[int] = mapped_column(Integer, default=2)  # 1 top .. 3 low
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)  # pinned on every screen until done
    progress: Mapped[int] = mapped_column(Integer, default=0)  # percent done
    deadline: Mapped[date | None] = mapped_column(Date)
    follow_ups: Mapped[list] = mapped_column(JSONB, default=list)  # ["2026-11-05", ...] dates to check back
    owner: Mapped[str] = mapped_column(Text, default="")  # responsible person
    depends_on: Mapped[str] = mapped_column(Text, default="")  # what it's waiting on
    position: Mapped[float] = mapped_column(Float, default=0)  # order within its column
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = updated()


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
    reason: Mapped[str] = mapped_column(String(20), default="manual")  # manual | opt_out | bounced | rejection
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
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))  # sender
    persona: Mapped[str] = mapped_column(String(32), default="momentum")
    engine: Mapped[str] = mapped_column(String(32), default="template")  # template | claude model id
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | approved | stopped | replied | done
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = updated()
    emails: Mapped[list["Email"]] = relationship(order_by="Email.step", cascade="all, delete-orphan")


class Email(Base):
    """Every outbound email: sequence steps (§9.3) and broadcast messages (round updates §9.5, IR updates §12)."""

    __tablename__ = "emails"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    sequence_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sequences.id", ondelete="CASCADE"), index=True)
    broadcast_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("broadcasts.id", ondelete="CASCADE"), index=True)
    card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("funnel_cards.id", ondelete="SET NULL"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))  # sender
    to_email: Mapped[str] = mapped_column(Text, default="")
    cc: Mapped[str] = mapped_column(Text, default="")  # reply-all on a card's Gmail thread: everyone else on it
    step: Mapped[int] = mapped_column(Integer, default=1)  # 1..3 for sequences
    hook: Mapped[str] = mapped_column(String(32), default="")
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    facts: Mapped[list] = mapped_column(JSONB, default=list)  # [{text, source}] "Why I wrote this"
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|scheduled|sending|sent|cancelled|failed
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    gmail_thread_id: Mapped[str] = mapped_column(Text, default="")
    gmail_message_id: Mapped[str] = mapped_column(Text, default="")
    rfc_message_id: Mapped[str] = mapped_column(Text, default="")  # MAIL-02 In-Reply-To / References
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str] = mapped_column(Text, default="")
    # Tracking (§9.4)
    open_token: Mapped[str | None] = mapped_column(String(40), unique=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    open_count: Mapped[int] = mapped_column(Integer, default=0)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reply_kind: Mapped[str] = mapped_column(String(16), default="")  # positive|neutral|negative|auto|bounce|opt_out
    bounced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = updated()


class EmailEvent(Base):
    __tablename__ = "email_events"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    email_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("emails.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # open | reply | bounce | click
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = created()


class GmailAccount(Base):
    """MAIL-01 / AUTH-03: the user's own mailbox. Tokens are AES-256-GCM encrypted at rest."""

    __tablename__ = "gmail_accounts"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    email: Mapped[str] = mapped_column(String(320))
    refresh_token_enc: Mapped[str] = mapped_column(Text, default="")
    access_token_enc: Mapped[str] = mapped_column(Text, default="")
    access_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[str] = mapped_column(Text, default="")
    history_id: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(16), default="connected")  # connected | revoked
    mode: Mapped[str] = mapped_column(String(8), default="google")  # google | fake (dev/test only)
    next_send_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # MAIL-06 pacing
    # Send safety: nothing leaves this mailbox until then (paused by the user, or automatically on a burst)
    paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_reason: Mapped[str] = mapped_column(Text, default="")
    connected_at: Mapped[datetime] = created()


class Broadcast(Base):
    """§9.5 round updates (FOMO) and §12 investor updates. One Email row per recipient."""

    __tablename__ = "broadcasts"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(16))  # round_update | investor_update
    template: Mapped[str] = mapped_column(String(32), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    inputs: Mapped[dict] = mapped_column(JSONB, default=dict)  # commitments / metrics / wins / asks
    audience: Mapped[dict] = mapped_column(JSONB, default=dict)  # {stages, statuses, exclude_card_ids, card_ids}
    follow_up: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | scheduled | done | cancelled
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = updated()
    emails: Mapped[list["Email"]] = relationship(cascade="all, delete-orphan")


# ---------- agent (§9.1) ----------


class AgentMemory(Base):
    """AGT-07: summarised facts the agent keeps for a workspace; user can view/delete."""

    __tablename__ = "agent_memory"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    kind: Mapped[str] = mapped_column(String(16), default="fact")  # fact | preference | worked | raise
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = created()


class ChatMessage(Base):
    """AGT-05 chat history. `actions` holds tool proposals that need a click before they are applied."""

    __tablename__ = "agent_chat"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    text: Mapped[str] = mapped_column(Text, default="")
    actions: Mapped[list] = mapped_column(JSONB, default=list)  # [{id, type, label, args, state}]
    created_at: Mapped[datetime] = created()


class MeetingBrief(Base):
    __tablename__ = "meeting_briefs"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("funnel_cards.id", ondelete="CASCADE"), index=True)
    content: Mapped[dict] = mapped_column(JSONB)
    engine: Mapped[str] = mapped_column(String(32), default="template")
    created_at: Mapped[datetime] = created()


class Feedback(Base):
    """§9.8 thumbs up/down on agent artefacts: learning signals."""

    __tablename__ = "agent_feedback"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    target: Mapped[str] = mapped_column(String(16))  # email | brief | suggestion | chat
    target_id: Mapped[str] = mapped_column(String(64))
    rating: Mapped[int] = mapped_column(Integer)  # 1 | -1
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = created()


# ---------- data room (§14) ----------


class DataRoom(Base):
    __tablename__ = "data_rooms"
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    access: Mapped[str] = mapped_column(String(10), default="magic")  # public | password | email | magic
    password_hash: Mapped[str] = mapped_column(Text, default="")
    indexable: Mapped[bool] = mapped_column(Boolean, default=False)  # DR-05
    content: Mapped[dict] = mapped_column(JSONB, default=dict)  # {hero, sections:[{id,type,title,body,items}]}
    versions: Mapped[list] = mapped_column(JSONB, default=list)  # DR-04 last N snapshots
    updated_at: Mapped[datetime] = updated()


class DataRoomDoc(Base):
    __tablename__ = "data_room_docs"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    label: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(120), default="application/pdf")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    gated: Mapped[bool] = mapped_column(Boolean, default=True)  # needs a viewer identity to download
    created_at: Mapped[datetime] = created()


class DataRoomLink(Base):
    """DR-02 per-investor magic link."""

    __tablename__ = "data_room_links"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    token: Mapped[str] = mapped_column(String(40), unique=True)
    card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("funnel_cards.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created()


class DataRoomView(Base):
    """DR-03 analytics: one row per visit; sections holds seconds per section id."""

    __tablename__ = "data_room_views"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("funnel_cards.id", ondelete="SET NULL"), index=True)
    link_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_room_links.id", ondelete="SET NULL"))
    viewer_email: Mapped[str] = mapped_column(Text, default="")
    seconds: Mapped[int] = mapped_column(Integer, default=0)
    sections: Mapped[dict] = mapped_column(JSONB, default=dict)
    downloads: Mapped[list] = mapped_column(JSONB, default=list)
    started_at: Mapped[datetime] = created()
    last_ping_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------- team & billing ----------


class Invite(Base):
    __tablename__ = "workspace_invites"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = ws_fk()
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(16), default="editor")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created()


class Subscription(Base):
    __tablename__ = "subscriptions"
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    stripe_customer_id: Mapped[str] = mapped_column(String(80), default="")
    stripe_subscription_id: Mapped[str] = mapped_column(String(80), default="")
    tier_code: Mapped[str] = mapped_column(String(32), default="")
    interval: Mapped[str] = mapped_column(String(8), default="month")
    status: Mapped[str] = mapped_column(String(24), default="")  # active | past_due | canceled | ...
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
