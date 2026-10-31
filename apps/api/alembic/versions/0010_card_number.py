"""tracker card numbers (#1, #2 ...) per workspace

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-31 21:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('funnel_cards', sa.Column('number', sa.Integer(), nullable=False, server_default='0'))
    op.execute("""
        UPDATE funnel_cards f SET number = n.rn
        FROM (SELECT id, row_number() OVER (PARTITION BY workspace_id ORDER BY created_at, id) AS rn
              FROM funnel_cards) n
        WHERE f.id = n.id
    """)
    op.create_index('ix_cards_ws_number', 'funnel_cards', ['workspace_id', 'number'])


def downgrade() -> None:
    op.drop_index('ix_cards_ws_number', table_name='funnel_cards')
    op.drop_column('funnel_cards', 'number')
