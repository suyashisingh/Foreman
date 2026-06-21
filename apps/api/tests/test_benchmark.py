"""Tests for the benchmark results endpoint and pass@k derivation logic."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio

from app.db.models import BenchmarkResult, BenchmarkRun


# ---------------------------------------------------------------------------
# Fixtures: seed benchmark data
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def bench_run(db) -> BenchmarkRun:
    """Seed a BenchmarkRun with 4 tasks: 2 pass@1, 1 pass@3, 1 fail."""
    br = BenchmarkRun(
        id=uuid.uuid4(),
        commit_sha="abc1234567890def1234567890abcdef12345678",
        created_at=datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc),
    )
    db.add(br)
    await db.flush()

    results = [
        # pass@1: passed on first attempt
        BenchmarkResult(
            benchmark_run_id=br.id,
            task_id="task-easy-1",
            passed=True,
            attempts_to_pass=1,
            time_to_green_s=45.0,
            token_cost_usd=Decimal("0.000150"),
        ),
        # pass@1 again
        BenchmarkResult(
            benchmark_run_id=br.id,
            task_id="task-easy-2",
            passed=True,
            attempts_to_pass=1,
            time_to_green_s=60.0,
            token_cost_usd=Decimal("0.000200"),
        ),
        # pass@3 only: passed on 3rd attempt
        BenchmarkResult(
            benchmark_run_id=br.id,
            task_id="task-medium-1",
            passed=True,
            attempts_to_pass=3,
            time_to_green_s=180.0,
            token_cost_usd=Decimal("0.000500"),
        ),
        # failed: never passed
        BenchmarkResult(
            benchmark_run_id=br.id,
            task_id="task-hard-1",
            passed=False,
            attempts_to_pass=None,
            time_to_green_s=None,
            token_cost_usd=Decimal("0.000300"),
        ),
    ]
    for r in results:
        db.add(r)
    await db.commit()
    await db.refresh(br)
    return br


# ---------------------------------------------------------------------------
# Unit tests: pass@1/pass@3 derivation logic
# ---------------------------------------------------------------------------


def _make_result(
    *,
    passed: bool,
    attempts_to_pass: int | None,
    time_to_green_s: float | None = None,
    token_cost_usd: float | None = None,
) -> dict:
    """Helper that mirrors the TaskResultOut field computation in the router."""
    at1 = passed and attempts_to_pass == 1
    at3 = passed and (attempts_to_pass is not None and attempts_to_pass <= 3)
    return {
        "passed": passed,
        "attempts_to_pass": attempts_to_pass,
        "pass_at_1": at1,
        "pass_at_3": at3,
        "time_to_green_s": time_to_green_s,
        "token_cost_usd": token_cost_usd,
    }


def test_pass_at_1_first_attempt() -> None:
    """Passed on attempt 1 → both pass@1 and pass@3 are True."""
    r = _make_result(passed=True, attempts_to_pass=1)
    assert r["pass_at_1"] is True
    assert r["pass_at_3"] is True


def test_pass_at_3_only() -> None:
    """Passed on attempt 3 → pass@1 False, pass@3 True."""
    r = _make_result(passed=True, attempts_to_pass=3)
    assert r["pass_at_1"] is False
    assert r["pass_at_3"] is True


def test_pass_at_2_is_pass_at_1_false_pass_at_3_true() -> None:
    """Passed on attempt 2 → pass@1 False, pass@3 True."""
    r = _make_result(passed=True, attempts_to_pass=2)
    assert r["pass_at_1"] is False
    assert r["pass_at_3"] is True


def test_failed_task_is_not_pass_at_1_or_3() -> None:
    """Failed task → both pass@1 and pass@3 False."""
    r = _make_result(passed=False, attempts_to_pass=None)
    assert r["pass_at_1"] is False
    assert r["pass_at_3"] is False


def test_passed_zero_attempts_not_pass_at_1() -> None:
    """Edge: passed=True but attempts_to_pass=0 → pass@1 False (0 != 1)."""
    r = _make_result(passed=True, attempts_to_pass=0)
    assert r["pass_at_1"] is False
    assert r["pass_at_3"] is True  # 0 <= 3


# ---------------------------------------------------------------------------
# Integration tests: GET /api/v1/benchmark/results
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_results_returns_200(client, bench_run: BenchmarkRun) -> None:
    """Endpoint returns 200 and a valid JSON body when runs exist."""
    resp = await client.get("/api/v1/benchmark/results")
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_count"] == 4
    assert body["commit_sha"] == bench_run.commit_sha


@pytest.mark.asyncio
async def test_get_results_pass_at_1_rate(client, bench_run: BenchmarkRun) -> None:
    """pass@1 rate = 2 out of 4 = 0.5."""
    resp = await client.get("/api/v1/benchmark/results")
    body = resp.json()
    assert body["pass_at_1_rate"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_get_results_pass_at_3_rate(client, bench_run: BenchmarkRun) -> None:
    """pass@3 rate = 3 out of 4 = 0.75."""
    resp = await client.get("/api/v1/benchmark/results")
    body = resp.json()
    assert body["pass_at_3_rate"] == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_get_results_avg_time_to_green(client, bench_run: BenchmarkRun) -> None:
    """avg time-to-green = mean of the 3 passed tasks: (45+60+180)/3 = 95s."""
    resp = await client.get("/api/v1/benchmark/results")
    body = resp.json()
    assert body["avg_time_to_green_s"] == pytest.approx(95.0)


@pytest.mark.asyncio
async def test_get_results_total_cost(client, bench_run: BenchmarkRun) -> None:
    """total cost = 0.000150 + 0.000200 + 0.000500 + 0.000300 = 0.001150."""
    resp = await client.get("/api/v1/benchmark/results")
    body = resp.json()
    assert body["total_token_cost_usd"] == pytest.approx(0.001150, rel=1e-4)


@pytest.mark.asyncio
async def test_get_results_per_task_breakdown(
    client, bench_run: BenchmarkRun
) -> None:
    """Per-task entries include pass_at_1 and pass_at_3 flags."""
    resp = await client.get("/api/v1/benchmark/results")
    body = resp.json()
    tasks = {t["task_id"]: t for t in body["tasks"]}

    assert tasks["task-easy-1"]["pass_at_1"] is True
    assert tasks["task-easy-1"]["pass_at_3"] is True
    assert tasks["task-medium-1"]["pass_at_1"] is False
    assert tasks["task-medium-1"]["pass_at_3"] is True
    assert tasks["task-hard-1"]["pass_at_1"] is False
    assert tasks["task-hard-1"]["pass_at_3"] is False


@pytest.mark.asyncio
async def test_get_results_404_when_no_runs(client) -> None:
    """Returns 404 when there are no benchmark runs in the DB."""
    # bench_run fixture NOT injected here — DB is empty after truncation
    resp = await client.get("/api/v1/benchmark/results")
    assert resp.status_code == 404
