"""Cosine-similarity search over stored repository chunks.

This is the primary retrieval function used by Planner agents to find
relevant code context before generating a plan.
"""

import logging
import uuid

from pgvector.sqlalchemy import Vector
from pydantic import BaseModel
from sqlalchemy import Float, select, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RepoChunk
from app.retrieval.embeddings import embed_texts

logger = logging.getLogger(__name__)


class ChunkSearchResult(BaseModel):
    """A single ranked result from a similarity search over repo chunks."""

    file_path: str
    symbol_name: str | None
    content: str
    # 1.0 = identical direction, -1.0 = opposite; higher is more relevant
    similarity: float


async def search_repo_chunks(
    db: AsyncSession,
    repo_id: uuid.UUID,
    query: str,
    top_k: int = 5,
) -> list[ChunkSearchResult]:
    """Return the *top_k* chunks from *repo_id* most similar to *query*.

    Embeds the query with ``input_type="query"`` (asymmetric retrieval),
    then orders chunks in *repo_id* by pgvector cosine distance ascending
    (i.e. closer = more similar).  Chunks without an embedding are excluded.

    The returned similarity score is ``1 - cosine_distance``, so:
    - ``1.0``  — identical direction (maximum relevance)
    - ``0.0``  — orthogonal
    - ``-1.0`` — opposite direction (minimum relevance)

    Args:
        db:      Active ``AsyncSession``.
        repo_id: Filter results to this repository.
        query:   Natural-language or code query string.
        top_k:   Maximum number of results to return (default 5).

    Returns:
        List of :class:`ChunkSearchResult` ordered from most to least similar.
    """
    query_embeddings = await embed_texts([query], input_type="query")
    query_vec = query_embeddings[0]

    # pgvector's <=> is cosine *distance* (0 = identical, 2 = opposite).
    # type_coerce(query_vec, Vector) annotates the bind param so pgvector's
    # processor serialises the list correctly without emitting a SQL CAST.
    # The outer type_coerce(..., Float) tells SQLAlchemy the result column is a
    # plain float, preventing pgvector's result processor from trying to
    # deserialise the scalar distance value as a vector string.
    distance_col = type_coerce(
        RepoChunk.embedding.op("<=>")(type_coerce(query_vec, Vector(1024))),
        Float,
    ).label("distance")

    rows = await db.execute(
        select(
            RepoChunk.file_path,
            RepoChunk.symbol_name,
            RepoChunk.content,
            distance_col,
        )
        .where(RepoChunk.repo_id == repo_id)
        .where(RepoChunk.embedding.is_not(None))
        .order_by(distance_col)
        .limit(top_k)
    )

    return [
        ChunkSearchResult(
            file_path=row.file_path,
            symbol_name=row.symbol_name,
            content=row.content,
            similarity=1.0 - float(row.distance),
        )
        for row in rows.all()
    ]
