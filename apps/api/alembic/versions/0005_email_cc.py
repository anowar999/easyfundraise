"""cc on emails, for reply-all from a tracker card

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-31 08:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('emails', sa.Column('cc', sa.Text(), nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('emails', 'cc')
