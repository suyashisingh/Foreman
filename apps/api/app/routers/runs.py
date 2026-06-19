"""Agent run lifecycle endpoints.

POST /api/v1/runs            — create a run and enqueue the agent graph.
GET  /api/v1/runs            — list the caller's runs.
GET  /api/v1/runs/{run_id}   — run detail with all agent steps.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_arq_pool, get_current_user, get_db
from app.db.models import Repo, RepoStatus, Run, RunStatus, User
from app.schemas.runs import RunCreate, RunDetail, RunOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_run_or_404(
    run_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
    *,
    load_steps: bool = False,
) -> Run:
    """Fetch a run by ID, ensuring it belongs to ``current_user``."""
    q = select(Run).where(Run.id == run_id, Run.user_id == current_user.id)
    if load_steps:
        q = q.options(selectinload(Run.agent_steps))
    result = await db.execute(q)
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found."
        )
    return run


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=RunOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create an agent run and queue it for execution",
)
async def create_run(
    body: RunCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    arq_pool: object = Depends(get_arq_pool),
) -> RunOut:
    """Validate the repo, create a Run row, and enqueue ``execute_run``.

    The repo must belong to the current user and have ``status=ready``.
    Returns HTTP 202 immediately; the Planner agent runs asynchronously in
    the ARQ worker.  Poll ``GET /api/v1/runs/{id}`` for status updates.

    Status flow: ``pending → planning → awaiting_approval`` (or ``failed``).
    """
    repo = await db.get(Repo, body.repo_id)
    if repo is None or repo.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Repo not found."
        )
    if repo.status != RepoStatus.ready:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Repo is not ready for a run (current status: {repo.status.value}). "
                "Wait for ingestion to complete."
            ),
        )

    run = Run(
        user_id=current_user.id,
        repo_id=body.repo_id,
        issue_text=body.issue_text,
        status=RunStatus.pending,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    await arq_pool.enqueue_job("execute_run", str(run.id))  # type: ignore[union-attr]

    logger.info("Run enqueued", extra={"run_id": str(run.id)})
    return RunOut.model_validate(run)


@router.get(
    "",
    response_model=list[RunOut],
    summary="List the current user's agent runs",
)
async def list_runs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RunOut]:
    """Return all runs owned by the authenticated user, newest first."""
    result = await db.execute(
        select(Run)
        .where(Run.user_id == current_user.id)
        .order_by(Run.created_at.desc())
    )
    return [RunOut.model_validate(r) for r in result.scalars()]


@router.get(
    "/{run_id}",
    response_model=RunDetail,
    summary="Get a run's status and agent steps",
)
async def get_run(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RunDetail:
    """Return full run detail including all logged agent steps in order."""
    run = await _get_run_or_404(run_id, current_user, db, load_steps=True)
    return RunDetail.model_validate(run)
