"""add_repo_status_and_ingestion_fields

Adds repo ingestion lifecycle:
- repo_status Postgres ENUM (pending / cloning / chunking / ready / failed)
- repos.status column (not null, default 'pending')
- repos.error_message column (nullable text)
- repo_chunks.embedding resized from vector(1536) to vector(1024) to match
  the voyage-code-3 default output dimension.

Revision ID: e7a4c9b3d2f1
Revises: da6f59bf55ea
Create Date: 2026-06-19

"""

from typing import Sequence, Union

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

revision: str = "e7a4c9b3d2f1"
down_revision: Union[str, Sequence[str], None] = "da6f59bf55ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply schema additions."""
    # 1. Create the repo_status Postgres ENUM type.
    op.execute(
        "CREATE TYPE repo_status AS ENUM "
        "('pending', 'cloning', 'chunking', 'ready', 'failed')"
    )

    # 2. Add status and error_message columns to the repos table.
    op.add_column(
        "repos",
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "cloning",
                "chunking",
                "ready",
                "failed",
                name="repo_status",
                create_type=False,  # type already created above
            ),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "repos",
        sa.Column("error_message", sa.Text(), nullable=True),
    )

    # 3. Resize the embedding column from vector(1536) to vector(1024).
    #    voyage-code-3 outputs 1024-dimensional embeddings by default.
    #    Drop-and-recreate is safe here because no embeddings have been
    #    stored yet (the ingestion feature is new in this migration).
    op.drop_column("repo_chunks", "embedding")
    op.add_column(
        "repo_chunks",
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.Vector(1024),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Revert schema additions."""
    # Revert embedding column back to vector(1536).
    op.drop_column("repo_chunks", "embedding")
    op.add_column(
        "repo_chunks",
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.Vector(1536),
            nullable=True,
        ),
    )

    # Remove status and error_message from repos.
    op.drop_column("repos", "error_message")
    op.drop_column("repos", "status")

    # Drop the enum type.
    op.execute("DROP TYPE repo_status")
