"""send safety: pause a user's sending (by them, or automatically on unusual volume)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-31 08:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('gmail_accounts', sa.Column('paused_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('gmail_accounts', sa.Column('paused_reason', sa.Text(), nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('gmail_accounts', 'paused_reason')
    op.drop_column('gmail_accounts', 'paused_until')
