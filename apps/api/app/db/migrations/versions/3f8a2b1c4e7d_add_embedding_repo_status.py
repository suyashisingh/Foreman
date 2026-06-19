"""add_embedding_repo_status

Adds the 'embedding' value to the repo_status Postgres ENUM, inserted
between 'chunking' and 'ready' to reflect the new explicit embedding
phase introduced by the ARQ background task.

Revision ID: 3f8a2b1c4e7d
Revises: e7a4c9b3d2f1
Create Date: 2026-06-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3f8a2b1c4e7d"
down_revision: Union[str, Sequence[str], None] = "e7a4c9b3d2f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 'embedding' to the repo_status enum."""
    # ALTER TYPE … ADD VALUE is transactional in PostgreSQL 12+.
    # The new value is visible to other transactions after this transaction
    # commits; it cannot be referenced within the same transaction.
    op.execute(
        sa.text("ALTER TYPE repo_status ADD VALUE 'embedding' BEFORE 'ready'")
    )


def downgrade() -> None:
    """Removing individual enum values from a Postgres ENUM requires
    recreating the type, which is operationally risky and rarely
    necessary.  Down-migrations are not supported for this change."""
    pass
