"""performance: indexes for the hot paths (search, sender queue, reply polling, tracker, notifications)

Every index is built CONCURRENTLY, so running this on a live database never locks a table: reads and writes
carry on while each index builds. IF NOT EXISTS makes a rerun after an interrupted upgrade safe.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-04 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

T = sa.text
TRGM = ["company", "current_firm", "location", "geography_focus", "focus_stages", "stages_src", "focus_sectors"]

# (name, table, columns, extra kwargs)
INDEXES = [
    ("ix_sessions_expires_at", "sessions", ["expires_at"], {}),
    ("ix_workspace_members_user", "workspace_members", ["user_id"], {}),
    ("ix_rate_limits_window", "rate_limits", ["window_start"], {}),
    *[(f"ix_investors_{c}_trgm", "investors", [c], {"postgresql_using": "gin", "postgresql_ops": {c: "gin_trgm_ops"}})
      for c in TRGM],
    ("ix_investors_country_lower", "investors", [T("lower(country)")], {}),
    ("ix_investors_email_lower", "investors", [T("lower(email)")], {}),
    ("ix_investors_type", "investors", ["investor_type"], {}),
    ("ix_investors_browse", "investors", [T("enriched DESC"), T("seed_fit DESC NULLS LAST"), "name"],
     {"postgresql_where": T("NOT suppressed")}),
    ("ix_access_user_kind_created", "data_access_events", ["user_id", "kind", "created_at"], {}),
    ("ix_access_ws_created", "data_access_events", ["workspace_id", "created_at"], {}),
    ("ix_cards_ws_investor", "funnel_cards", ["workspace_id", "investor_id"], {"postgresql_where": T("deleted_at IS NULL")}),
    ("ix_cards_call_at", "funnel_cards", ["call_at"], {"postgresql_where": T("call_at IS NOT NULL AND deleted_at IS NULL")}),
    ("ix_card_events_card_created", "card_events", ["card_id", "created_at"], {}),
    ("ix_card_events_ws_card_created", "card_events", ["workspace_id", "card_id", "created_at"], {}),
    ("ix_founder_tasks_ws_status", "founder_tasks", ["workspace_id", "status"], {}),
    ("ix_reminders_pending", "reminders", ["due_at"], {"postgresql_where": T("notified_at IS NULL AND done_at IS NULL")}),
    ("ix_reminders_card", "reminders", ["card_id"], {}),
    ("ix_notifications_user_ws_created", "notifications", ["user_id", "workspace_id", "created_at"], {}),
    ("ix_notifications_unread", "notifications", ["user_id", "workspace_id"], {"postgresql_where": T("read_at IS NULL")}),
    ("ix_sequences_ws_created", "sequences", ["workspace_id", "created_at"], {}),
    ("ix_sequences_ws_investor", "sequences", ["workspace_id", "investor_id"], {}),
    ("ix_sequences_card", "sequences", ["card_id"], {}),
    ("ix_emails_due", "emails", ["scheduled_for"], {"postgresql_where": T("status = 'scheduled'")}),
    ("ix_emails_ws_sent", "emails", ["workspace_id", "sent_at"], {}),
    ("ix_emails_user_sent", "emails", ["user_id", "sent_at"], {"postgresql_where": T("status = 'sent'")}),
    ("ix_emails_card", "emails", ["card_id"], {}),
    ("ix_emails_ws_to_lower", "emails", ["workspace_id", T("lower(to_email)")], {}),
    ("ix_agent_chat_ws_user_created", "agent_chat", ["workspace_id", "user_id", "created_at"], {}),
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    with op.get_context().autocommit_block():
        for name, table, cols, kw in INDEXES:
            op.create_index(name, table, cols, postgresql_concurrently=True, if_not_exists=True, **kw)
        # Superseded by ix_card_events_card_created (card_id is its leading column)
        op.drop_index("ix_card_events_card_id", table_name="card_events", postgresql_concurrently=True, if_exists=True)
    op.execute("ANALYZE")  # fresh planner statistics so the new indexes are used straight away


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index("ix_card_events_card_id", "card_events", ["card_id"], postgresql_concurrently=True,
                        if_not_exists=True)
        for name, table, _cols, _kw in reversed(INDEXES):
            op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)
