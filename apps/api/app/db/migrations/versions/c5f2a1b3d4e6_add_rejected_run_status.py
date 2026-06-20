"""add_rejected_run_status

Adds ``rejected`` value to the ``run_status`` Postgres ENUM and adds the
``rejection_reason`` column to the ``runs`` table.

Revision ID: c5f2a1b3d4e6
Revises: b9e1f2a3c4d5
Create Date: 2026-06-20 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5f2a1b3d4e6"
down_revision: Union[str, Sequence[str], None] = "b9e1f2a3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE run_status ADD VALUE 'rejected'"))
    op.add_column("runs", sa.Column("rejection_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "rejection_reason")
    # Postgres does not support removing enum values without a full type recreate.
