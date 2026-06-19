"""Repo registration, status, and retrieval endpoints.

POST /api/v1/repos            — create a Repo row and enqueue ingestion.
GET  /api/v1/repos            — list the current user's repos with chunk counts.
GET  /api/v1/repos/{id}       — single repo detail + chunk count.
GET  /api/v1/repos/{id}/search — cosine-similarity search over stored chunks.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_arq_pool, get_current_user, get_db
from app.db.models import Repo, RepoChunk, RepoStatus, User
from app.retrieval.search import ChunkSearchResult, search_repo_chunks
from app.schemas.repos import RepoCreate, RepoDetail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/repos", tags=["repos"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_repo_or_404(
    repo_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Repo:
    repo = await db.get(Repo, repo_id)
    if repo is None or repo.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Repo not found."
        )
    return repo


async def _chunk_count(repo_id: uuid.UUID, db: AsyncSession) -> int:
    result = await db.scalar(
        select(func.count(RepoChunk.id)).where(RepoChunk.repo_id == repo_id)
    )
    return int(result or 0)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=RepoDetail,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Register a repository and queue it for background ingestion",
)
async def register_repo(
    body: RepoCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    arq_pool: object = Depends(get_arq_pool),
) -> RepoDetail:
    """Create a Repo row and enqueue the clone→chunk→embed pipeline.

    Returns HTTP 202 immediately with ``status="pending"``.  The ingestion
    pipeline runs asynchronously in the ARQ worker process.  Poll
    ``GET /api/v1/repos/{id}`` to watch the status transition:

        pending → cloning → chunking → embedding → ready  (or → failed)
    """
    repo = Repo(
        user_id=current_user.id,
        name=body.name,
        clone_url=body.clone_url,
        default_branch=body.default_branch,
        status=RepoStatus.pending,
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)

    await arq_pool.enqueue_job("ingest_repo", str(repo.id))  # type: ignore[union-attr]

    logger.info("Repo registration enqueued", extra={"repo_id": str(repo.id)})

    return RepoDetail(
        id=repo.id,
        name=repo.name,
        clone_url=repo.clone_url,
        default_branch=repo.default_branch,
        status=repo.status,
        error_message=repo.error_message,
        created_at=repo.created_at,
        chunk_count=0,
    )


@router.get(
    "",
    response_model=list[RepoDetail],
    summary="List the current user's registered repositories",
)
async def list_repos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RepoDetail]:
    """Return all repos owned by the authenticated user, newest first."""
    rows = await db.execute(
        select(Repo, func.count(RepoChunk.id).label("chunk_count"))
        .outerjoin(RepoChunk, RepoChunk.repo_id == Repo.id)
        .where(Repo.user_id == current_user.id)
        .group_by(Repo.id)
        .order_by(Repo.created_at.desc())
    )
    return [
        RepoDetail(
            id=repo.id,
            name=repo.name,
            clone_url=repo.clone_url,
            default_branch=repo.default_branch,
            status=repo.status,
            error_message=repo.error_message,
            created_at=repo.created_at,
            chunk_count=count,
        )
        for repo, count in rows
    ]


@router.get(
    "/{repo_id}/search",
    response_model=list[ChunkSearchResult],
    summary="Cosine-similarity search over a repo's stored code chunks",
)
async def search_repo(
    repo_id: uuid.UUID,
    q: str = Query(..., min_length=1, description="Natural-language or code query"),
    top_k: int = Query(5, ge=1, le=20, description="Number of results to return"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChunkSearchResult]:
    """Embed *q* and return the *top_k* most similar chunks from *repo_id*.

    The repo must have ``status=ready`` (ingestion complete).  Results are
    ordered from most to least similar (``similarity`` field: 1.0 = identical,
    -1.0 = opposite direction).
    """
    repo = await _get_repo_or_404(repo_id, current_user, db)
    if repo.status != RepoStatus.ready:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Repo is not ready for search (current status: {repo.status}).",
        )
    return await search_repo_chunks(db, repo_id, q, top_k)


@router.get(
    "/{repo_id}",
    response_model=RepoDetail,
    summary="Get one repo's details and chunk count",
)
async def get_repo(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepoDetail:
    """Return details and chunk count for a single repo owned by the caller."""
    repo = await _get_repo_or_404(repo_id, current_user, db)
    count = await _chunk_count(repo.id, db)
    return RepoDetail(
        id=repo.id,
        name=repo.name,
        clone_url=repo.clone_url,
        default_branch=repo.default_branch,
        status=repo.status,
        error_message=repo.error_message,
        created_at=repo.created_at,
        chunk_count=count,
    )
