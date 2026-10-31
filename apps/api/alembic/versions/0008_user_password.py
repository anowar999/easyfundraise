"""optional password sign-in alongside Google and email links

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-31 20:50:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('password_hash', sa.Text(), nullable=False, server_default=''))
    op.add_column('users', sa.Column('password_set_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'password_set_at')
    op.drop_column('users', 'password_hash')
