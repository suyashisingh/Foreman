"""Benchmark results endpoint.

GET /api/v1/benchmark/results
  - Authenticated: returns the latest BenchmarkRun for the requesting user.
    Returns an empty-results response (task_count=0) if the user has no runs
    yet, rather than 404 — the frontend uses task_count==0 to show an
    onboarding empty state.
  - Unauthenticated: returns the latest BenchmarkRun across ALL users,
    intended for the public landing page / BenchmarkStats component.
    Returns 404 if no runs exist globally.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user_optional, get_db
from app.db.models import BenchmarkResult, BenchmarkRun, User
from app.schemas.benchmark import BenchmarkResultsOut, TaskResultOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/benchmark", tags=["benchmark"])

_MAX_CODER_ATTEMPTS_FOR_PASS3 = 3


def _aggregate(bench_run: BenchmarkRun) -> BenchmarkResultsOut:
    """Build BenchmarkResultsOut from an ORM BenchmarkRun (with .results loaded)."""
    raw_results: list[BenchmarkResult] = bench_run.results
    task_count = len(raw_results)

    task_outs: list[TaskResultOut] = []
    for r in raw_results:
        cost = float(r.token_cost_usd) if r.token_cost_usd is not None else None
        at1 = r.passed and r.attempts_to_pass == 1
        at3 = r.passed and (
            r.attempts_to_pass is not None
            and r.attempts_to_pass <= _MAX_CODER_ATTEMPTS_FOR_PASS3
        )
        task_outs.append(
            TaskResultOut(
                task_id=r.task_id,
                passed=r.passed,
                attempts_to_pass=r.attempts_to_pass,
                time_to_green_s=r.time_to_green_s,
                token_cost_usd=cost,
                pass_at_1=at1,
                pass_at_3=at3,
            )
        )

    if task_count == 0:
        pass_at_1_rate = 0.0
        pass_at_3_rate = 0.0
        avg_time: float | None = None
        total_cost = 0.0
    else:
        pass_at_1_count = sum(1 for t in task_outs if t.pass_at_1)
        pass_at_3_count = sum(1 for t in task_outs if t.pass_at_3)
        pass_at_1_rate = pass_at_1_count / task_count
        pass_at_3_rate = pass_at_3_count / task_count

        green_times = [
            t.time_to_green_s for t in task_outs if t.time_to_green_s is not None
        ]
        avg_time = sum(green_times) / len(green_times) if green_times else None

        total_cost = sum(t.token_cost_usd or 0.0 for t in task_outs)

    return BenchmarkResultsOut(
        benchmark_run_id=bench_run.id,
        commit_sha=bench_run.commit_sha,
        created_at=bench_run.created_at,
        task_count=task_count,
        pass_at_1_rate=pass_at_1_rate,
        pass_at_3_rate=pass_at_3_rate,
        avg_time_to_green_s=avg_time,
        total_token_cost_usd=total_cost,
        tasks=task_outs,
    )


def _empty_results() -> BenchmarkResultsOut:
    """Return an empty (task_count=0) response for users with no runs yet."""
    return BenchmarkResultsOut(
        benchmark_run_id=uuid.uuid4(),
        commit_sha="",
        created_at=datetime.now(timezone.utc),
        task_count=0,
        pass_at_1_rate=0.0,
        pass_at_3_rate=0.0,
        avg_time_to_green_s=None,
        total_token_cost_usd=0.0,
        tasks=[],
    )


@router.get("/results", response_model=BenchmarkResultsOut)
async def get_benchmark_results(
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
) -> BenchmarkResultsOut:
    """Return benchmark results, scoped per user when authenticated.

    pass@1 = task passed on the first Coder attempt (attempts_to_pass == 1).
    pass@3 = task passed within 3 Coder attempts (attempts_to_pass <= 3).
    """
    if current_user is not None:
        # Authenticated: return the caller's latest benchmark run.
        result = await db.execute(
            select(BenchmarkRun)
            .where(BenchmarkRun.user_id == current_user.id)
            .options(selectinload(BenchmarkRun.results))
            .order_by(BenchmarkRun.created_at.desc())
            .limit(1)
        )
        bench_run: BenchmarkRun | None = result.scalar_one_or_none()

        # Return empty (not 404) so the FE can show an onboarding state.
        if bench_run is None:
            return _empty_results()

        return _aggregate(bench_run)

    # Unauthenticated: global aggregate for the public landing page.
    result = await db.execute(
        select(BenchmarkRun)
        .options(selectinload(BenchmarkRun.results))
        .order_by(BenchmarkRun.created_at.desc())
        .limit(1)
    )
    bench_run = result.scalar_one_or_none()

    if bench_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No benchmark runs found",
        )

    return _aggregate(bench_run)
