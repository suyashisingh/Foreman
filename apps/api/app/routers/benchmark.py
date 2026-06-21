"""Benchmark results endpoint.

GET /api/v1/benchmark/results  — returns the latest benchmark run's
aggregated metrics (pass@1, pass@3, avg time-to-green, total cost)
plus a per-task breakdown.  No authentication required — this is
aggregate, non-sensitive data intended for portfolio display.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_db
from app.db.models import BenchmarkResult, BenchmarkRun
from app.schemas.benchmark import BenchmarkResultsOut, TaskResultOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/benchmark", tags=["benchmark"])

_MAX_CODER_ATTEMPTS_FOR_PASS3 = 3


@router.get("/results", response_model=BenchmarkResultsOut)
async def get_benchmark_results(
    db: AsyncSession = Depends(get_db),
) -> BenchmarkResultsOut:
    """Return the latest benchmark run with aggregate metrics.

    pass@1 = task passed on the first Coder attempt (attempts_to_pass == 1).
    pass@3 = task passed within 3 Coder attempts (attempts_to_pass <= 3).
    """
    bench_run_result = await db.execute(
        select(BenchmarkRun)
        .options(selectinload(BenchmarkRun.results))
        .order_by(BenchmarkRun.created_at.desc())
        .limit(1)
    )
    bench_run: BenchmarkRun | None = bench_run_result.scalar_one_or_none()

    if bench_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No benchmark runs found",
        )

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
