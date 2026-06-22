"""Tests for the benchmark results endpoint and pass@k derivation logic."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio

from app.core.security import hash_password
from app.db.models import BenchmarkResult, BenchmarkRun, User

# ---------------------------------------------------------------------------
# Fixtures: seed users and benchmark data
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def bench_user(db) -> User:
    """Seed a primary user who owns the benchmark run."""
    user = User(
        id=uuid.uuid4(),
        email="bench@example.com",
        password_hash=hash_password("benchpass1"),
        name="Bench",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def bench_run(db, bench_user: User) -> BenchmarkRun:
    """Seed a BenchmarkRun with 4 tasks: 2 pass@1, 1 pass@3, 1 fail."""
    br = BenchmarkRun(
        id=uuid.uuid4(),
        user_id=bench_user.id,
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
async def test_get_results_per_task_breakdown(client, bench_run: BenchmarkRun) -> None:
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
    """Unauthenticated request returns 404 when there are no benchmark runs."""
    # bench_run fixture NOT injected here — DB is empty after truncation
    resp = await client.get("/api/v1/benchmark/results")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Integration tests: per-user filtering (authenticated)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authenticated_user_sees_own_results(
    auth_client, bench_run: BenchmarkRun, bench_user: User
) -> None:
    """An authenticated user sees only their own benchmark results.

    auth_client belongs to testuser@example.com (not bench_user), so they
    should get an empty-results response even though bench_run exists in the DB.
    """
    resp = await auth_client.get("/api/v1/benchmark/results")
    assert resp.status_code == 200
    body = resp.json()
    # auth_client's user has no runs — empty results, not 404
    assert body["task_count"] == 0
    assert body["tasks"] == []


@pytest.mark.asyncio
async def test_authenticated_user_with_own_run_sees_it(
    auth_client, db, bench_user: User
) -> None:
    """When a user runs the benchmark themselves, the endpoint returns their data."""
    from sqlalchemy import select as _select

    result = await db.execute(_select(User).where(User.email == "testuser@example.com"))
    me: User = result.scalar_one()

    br = BenchmarkRun(
        id=uuid.uuid4(),
        user_id=me.id,  # type: ignore[union-attr]
        commit_sha="deadbeef00000000000000000000000000000000",
        created_at=datetime(2026, 6, 22, 10, 0, 0, tzinfo=timezone.utc),
    )
    db.add(br)
    await db.flush()
    db.add(
        BenchmarkResult(
            benchmark_run_id=br.id,
            task_id="my-task-1",
            passed=True,
            attempts_to_pass=1,
            time_to_green_s=30.0,
            token_cost_usd=Decimal("0.0001"),
        )
    )
    await db.commit()

    resp = await auth_client.get("/api/v1/benchmark/results")
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_count"] == 1
    assert body["tasks"][0]["task_id"] == "my-task-1"
    assert body["commit_sha"] == "deadbeef00000000000000000000000000000000"


@pytest.mark.asyncio
async def test_user_a_results_not_visible_to_user_b(
    auth_client, other_auth_client, db
) -> None:
    """User A's benchmark run is invisible to User B."""
    from sqlalchemy import select as _select

    result = await db.execute(_select(User).where(User.email == "testuser@example.com"))
    user_a: User = result.scalar_one()

    br = BenchmarkRun(
        id=uuid.uuid4(),
        user_id=user_a.id,  # type: ignore[union-attr]
        commit_sha="aaa0000000000000000000000000000000000000",
        created_at=datetime(2026, 6, 22, 11, 0, 0, tzinfo=timezone.utc),
    )
    db.add(br)
    await db.flush()
    db.add(
        BenchmarkResult(
            benchmark_run_id=br.id,
            task_id="user-a-task",
            passed=True,
            attempts_to_pass=1,
            time_to_green_s=20.0,
            token_cost_usd=Decimal("0.00005"),
        )
    )
    await db.commit()

    # User B (other_auth_client) should see empty results
    resp = await other_auth_client.get("/api/v1/benchmark/results")
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_count"] == 0
    assert body["tasks"] == []


@pytest.mark.asyncio
async def test_unauthenticated_sees_global_aggregate(
    client, bench_run: BenchmarkRun
) -> None:
    """An unauthenticated request returns the global (latest) benchmark run."""
    resp = await client.get("/api/v1/benchmark/results")
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_count"] == 4


@pytest.mark.asyncio
async def test_authenticated_empty_state_returns_200_not_404(auth_client) -> None:
    """Authenticated user with no runs gets 200 with task_count=0, not 404."""
    resp = await auth_client.get("/api/v1/benchmark/results")
    assert resp.status_code == 200
    assert resp.json()["task_count"] == 0
