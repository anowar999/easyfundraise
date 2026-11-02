"""email playbook per workspace (email 1-3 angles, special line, quick update)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-02 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workspaces', sa.Column('email_playbook', postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                                          server_default=sa.text("'{}'::jsonb")))


def downgrade() -> None:
    op.drop_column('workspaces', 'email_playbook')
