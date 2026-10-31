"""star investors on the tracker, with an optional reason

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-31 07:35:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('funnel_cards', sa.Column('starred', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('funnel_cards', sa.Column('star_reason', sa.String(length=200), nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('funnel_cards', 'star_reason')
    op.drop_column('funnel_cards', 'starred')
