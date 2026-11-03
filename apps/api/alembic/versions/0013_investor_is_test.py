"""test investors: only shown in dev/UAT, or on live to the listed test accounts

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-03 13:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('investors', sa.Column('is_test', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column('investors', 'is_test')
