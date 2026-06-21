"""Pydantic schemas for the benchmark results endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class TaskResultOut(BaseModel):
    task_id: str
    passed: bool
    attempts_to_pass: int | None
    time_to_green_s: float | None
    token_cost_usd: float | None

    # Derived convenience fields
    pass_at_1: bool = False
    pass_at_3: bool = False

    model_config = {"from_attributes": True}


class BenchmarkResultsOut(BaseModel):
    benchmark_run_id: uuid.UUID
    commit_sha: str
    created_at: datetime
    task_count: int
    pass_at_1_rate: float  # fraction 0..1
    pass_at_3_rate: float  # fraction 0..1
    avg_time_to_green_s: float | None
    total_token_cost_usd: float
    tasks: list[TaskResultOut]
