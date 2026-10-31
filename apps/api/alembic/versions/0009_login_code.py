"""one-time email code after password sign-in

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-31 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('login_code_hash', sa.Text(), nullable=False, server_default=''))
    op.add_column('users', sa.Column('login_code_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('login_code_tries', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('users', 'login_code_tries')
    op.drop_column('users', 'login_code_expires_at')
    op.drop_column('users', 'login_code_hash')
