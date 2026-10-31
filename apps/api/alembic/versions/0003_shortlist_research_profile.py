"""shortlist, investor research cache, investor-type preference and goals on the company profile

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-31 06:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('company_profiles', sa.Column('investor_types', postgresql.ARRAY(sa.Text()), nullable=False,
                                                server_default='{}'))
    op.add_column('company_profiles', sa.Column('looking_for', sa.Text(), nullable=False, server_default=''))
    op.create_table('shortlist_items',
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('investor_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['investor_id'], ['investors.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('workspace_id', 'investor_id')
    )
    op.create_table('investor_research',
    sa.Column('investor_id', sa.UUID(), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('model', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['investor_id'], ['investors.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('investor_id')
    )
    op.execute("update workspaces set agent_name = 'Raise Agent' where agent_name = 'Raise'")


def downgrade() -> None:
    op.drop_table('investor_research')
    op.drop_table('shortlist_items')
    op.drop_column('company_profiles', 'looking_for')
    op.drop_column('company_profiles', 'investor_types')
