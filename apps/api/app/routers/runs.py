"""Agent run lifecycle endpoints.

POST /api/v1/runs                  — create a run and enqueue the agent graph.
GET  /api/v1/runs                  — list the caller's runs.
GET  /api/v1/runs/{run_id}         — run detail with all agent steps and review output.
POST /api/v1/runs/{run_id}/approve — approve diffs and mark the run passed.
POST /api/v1/runs/{run_id}/reject  — reject the run with an optional reason.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_arq_pool, get_current_user, get_db
from app.db.models import AgentRole, Repo, RepoStatus, Run, RunStatus, User
from app.schemas.runs import ReviewOut, RunCreate, RunDetail, RunOut, RunRejectBody

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
    load_diffs: bool = False,
) -> Run:
    """Fetch a run by ID, ensuring it belongs to ``current_user``."""
    q = select(Run).where(Run.id == run_id, Run.user_id == current_user.id)
    if load_steps:
        q = q.options(selectinload(Run.agent_steps))
    if load_diffs:
        q = q.options(selectinload(Run.diffs))
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
    Returns HTTP 202 immediately; the agent graph runs asynchronously in the
    ARQ worker.  Poll ``GET /api/v1/runs/{id}`` for status updates.

    Status flow: ``pending → planning → coding → testing → reviewing →
    awaiting_approval`` (or ``failed``).
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
    summary="Get a run's status, agent steps, and reviewer output",
)
async def get_run(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RunDetail:
    """Return full run detail including all logged agent steps in order.

    The ``review`` field is populated when the Reviewer node has completed
    (i.e. when a ``reviewer`` AgentStep exists for this run).
    """
    run = await _get_run_or_404(run_id, current_user, db, load_steps=True)
    detail = RunDetail.model_validate(run)
    for step in reversed(run.agent_steps):
        if step.agent == AgentRole.reviewer:
            detail.review = ReviewOut.model_validate(step.output)
            break
    return detail


@router.post(
    "/{run_id}/approve",
    response_model=RunOut,
    summary="Approve a run's diffs and mark it passed",
)
async def approve_run(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RunOut:
    """Mark all diffs as approved and transition the run to ``passed``.

    Only valid when ``status == awaiting_approval``; returns 422 otherwise.
    """
    run = await _get_run_or_404(run_id, current_user, db, load_diffs=True)
    if run.status != RunStatus.awaiting_approval:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Run is not awaiting approval (current status: {run.status.value})."
            ),
        )
    for diff in run.diffs:
        diff.approved = True
    run.status = RunStatus.passed
    await db.commit()
    await db.refresh(run)
    return RunOut.model_validate(run)


@router.post(
    "/{run_id}/reject",
    response_model=RunOut,
    summary="Reject a run with an optional reason",
)
async def reject_run(
    run_id: uuid.UUID,
    body: RunRejectBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RunOut:
    """Transition the run to ``rejected`` and optionally store a reason.

    Only valid when ``status == awaiting_approval``; returns 422 otherwise.
    """
    run = await _get_run_or_404(run_id, current_user, db)
    if run.status != RunStatus.awaiting_approval:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Run is not awaiting approval (current status: {run.status.value})."
            ),
        )
    run.status = RunStatus.rejected
    if body.reason:
        run.rejection_reason = body.reason
    await db.commit()
    await db.refresh(run)
    return RunOut.model_validate(run)
