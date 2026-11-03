"""keep a follow-up's original body while a round/progress update replaces it

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-03 12:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('emails', sa.Column('pre_update_body', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('emails', 'pre_update_body')
