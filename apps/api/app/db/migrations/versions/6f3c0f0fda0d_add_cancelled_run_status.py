"""add_cancelled_run_status

Revision ID: 6f3c0f0fda0d
Revises: 98fde155bafe
Create Date: 2026-06-21 20:49:31.362631

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6f3c0f0fda0d'
down_revision: Union[str, Sequence[str], None] = '98fde155bafe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # autogenerate cannot detect Python-enum → PG-enum additions, so we use raw SQL.
    op.execute(sa.text("ALTER TYPE run_status ADD VALUE IF NOT EXISTS 'cancelled'"))


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL does not support removing enum values without a full type recreate.
    pass
