"""Founder Tasks board

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-31 09:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'founder_tasks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='todo'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('urgent', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('progress', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('deadline', sa.Date(), nullable=True),
        sa.Column('follow_ups', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('owner', sa.Text(), nullable=False, server_default=''),
        sa.Column('depends_on', sa.Text(), nullable=False, server_default=''),
        sa.Column('position', sa.Float(), nullable=False, server_default='0'),
        sa.Column('done_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_founder_tasks_workspace_id', 'founder_tasks', ['workspace_id'])


def downgrade() -> None:
    op.drop_index('ix_founder_tasks_workspace_id', table_name='founder_tasks')
    op.drop_table('founder_tasks')
