"""add_pending_run_status

Adds the ``pending`` value to the ``run_status`` Postgres ENUM so that newly
created Run rows can be marked pending while the job waits in the ARQ queue.

Revision ID: b9e1f2a3c4d5
Revises: 3f8a2b1c4e7d
Create Date: 2026-06-19 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b9e1f2a3c4d5"
down_revision: Union[str, Sequence[str], None] = "3f8a2b1c4e7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE run_status ADD VALUE 'pending' BEFORE 'planning'"))


def downgrade() -> None:
    # Postgres does not support removing enum values; a full type recreate
    # would require rewriting all dependent columns — operationally risky.
    pass
