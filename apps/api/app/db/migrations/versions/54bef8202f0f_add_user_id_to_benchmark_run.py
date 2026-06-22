"""add_user_id_to_benchmark_run

Revision ID: 54bef8202f0f
Revises: 6f3c0f0fda0d
Create Date: 2026-06-22 16:55:50.343579

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "54bef8202f0f"
down_revision: Union[str, Sequence[str], None] = "6f3c0f0fda0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add user_id FK to benchmark_runs.

    Three-step approach handles existing rows safely:
      1. Add the column as nullable (so existing rows don't violate NOT NULL).
      2. Back-fill existing rows to the oldest user's id; rows with no user
         in the DB (fresh installs) are left NULL and the ALTER below is a
         no-op safe operation on an empty table.
      3. Alter the column to NOT NULL once all rows have a value.
    """
    # Step 1 — add nullable first so existing rows survive.
    op.add_column(
        "benchmark_runs",
        sa.Column("user_id", sa.UUID(), nullable=True),
    )

    # Step 2 — back-fill: assign any existing benchmark_run rows to the first
    # (oldest) user. On a fresh install there are no rows, so this is a no-op.
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE benchmark_runs
            SET user_id = (
                SELECT id FROM users ORDER BY created_at ASC LIMIT 1
            )
            WHERE user_id IS NULL
              AND EXISTS (SELECT 1 FROM users LIMIT 1)
            """
        )
    )

    # Step 3 — add the FK constraint (still nullable at this point is fine).
    op.create_foreign_key(
        "fk_benchmark_runs_user_id_users",
        "benchmark_runs",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Step 4 — flip to NOT NULL now that every row has a value.
    op.alter_column("benchmark_runs", "user_id", nullable=False)


def downgrade() -> None:
    """Remove user_id FK and column from benchmark_runs."""
    op.drop_constraint(
        "fk_benchmark_runs_user_id_users", "benchmark_runs", type_="foreignkey"
    )
    op.drop_column("benchmark_runs", "user_id")
