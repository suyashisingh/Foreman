"""Repo registration, ingestion, and retrieval endpoints.

POST /api/v1/repos   — clone, chunk, embed, and store a repository.
GET  /api/v1/repos   — list the current user's repos with chunk counts.
GET  /api/v1/repos/{id} — single repo detail + chunk count.

NOTE: The ingestion pipeline (clone → chunk → embed) runs synchronously
inside the request handler for this initial implementation.  Cloning large
repos can take tens of seconds; this will move to an ARQ background task in
the next iteration.
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.db.models import Repo, RepoChunk, RepoStatus, User
from app.retrieval.chunking import chunk_repo
from app.retrieval.cloning import CloneError, clone_repo, remove_clone
from app.retrieval.embeddings import EmbeddingError, embed_texts
from app.schemas.repos import RepoCreate, RepoDetail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/repos", tags=["repos"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _set_failed(db: AsyncSession, repo: Repo, error: str) -> None:
    """Mark *repo* as failed, storing the error message, then commit."""
    repo.status = RepoStatus.failed
    repo.error_message = error[:2048]  # guard against absurdly long messages
    try:
        await db.commit()
    except Exception:
        await db.rollback()


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
    status_code=status.HTTP_201_CREATED,
    summary="Register a repository and ingest its code into the vector store",
)
async def register_repo(
    body: RepoCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepoDetail:
    """Clone, chunk, embed, and store a repository synchronously.

    Returns the created Repo with a ``chunk_count`` reflecting the number
    of code chunks stored.  On any pipeline failure the repo row is kept
    with ``status=failed`` and an ``error_message`` for debugging.
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
    repo_id = str(repo.id)

    # --- Clone ----------------------------------------------------------
    repo.status = RepoStatus.cloning
    await db.commit()
    try:
        # asyncio.to_thread keeps the event loop unblocked during the network
        # I/O of cloning.  The request still awaits completion synchronously.
        clone_path = await asyncio.to_thread(clone_repo, body.clone_url, repo_id)
    except CloneError as exc:
        await _set_failed(db, repo, str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Repository clone failed: {exc}",
        ) from exc

    # --- Chunk ----------------------------------------------------------
    repo.status = RepoStatus.chunking
    await db.commit()
    try:
        chunks = await asyncio.to_thread(chunk_repo, clone_path)
    except Exception as exc:
        await _set_failed(db, repo, f"Chunking failed: {exc}")
        await asyncio.to_thread(remove_clone, repo_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chunking failed unexpectedly.",
        ) from exc

    # --- Embed & store --------------------------------------------------
    try:
        texts = [c.content for c in chunks]
        embeddings = await embed_texts(texts)
        for chunk, embedding in zip(chunks, embeddings):
            db.add(
                RepoChunk(
                    repo_id=repo.id,
                    file_path=chunk.file_path,
                    symbol_name=chunk.symbol_name,
                    content=chunk.content,
                    embedding=embedding,
                )
            )
        repo.status = RepoStatus.ready
        await db.commit()
    except EmbeddingError as exc:
        await _set_failed(db, repo, f"Embedding failed: {exc}")
        await asyncio.to_thread(remove_clone, repo_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Embedding failed — see server logs.",
        ) from exc
    except Exception as exc:
        await _set_failed(db, repo, f"Storage failed: {exc}")
        await asyncio.to_thread(remove_clone, repo_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Storing chunks failed unexpectedly.",
        ) from exc
    finally:
        await asyncio.to_thread(remove_clone, repo_id)

    chunk_count = len(chunks)
    logger.info(
        "Repo registered",
        extra={"repo_id": repo_id, "chunk_count": chunk_count},
    )
    return RepoDetail(
        id=repo.id,
        name=repo.name,
        clone_url=repo.clone_url,
        default_branch=repo.default_branch,
        status=repo.status,
        error_message=repo.error_message,
        created_at=repo.created_at,
        chunk_count=chunk_count,
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
