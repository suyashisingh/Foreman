"""Benchmark runner CLI.

Submits each curated task to the live Foreman API, polls until terminal,
derives pass@1/pass@3 metrics from agent_step and test_attempt data,
and persists results to the benchmark_runs / benchmark_results tables.

Usage
-----
    cd apps/api
    uv run python -m benchmark.runner \\
        --email user@example.com \\
        --password secret \\
        [--base-url http://localhost:8000] \\
        [--task-delay 5] \\
        [--tasks iniconfig-get-default iniconfig-as-dict]

pass@1  = the run passed and needed only 1 Coder attempt (no retries).
pass@3  = the run passed within MAX_CODER_RETRIES (≤ 3 total Coder
          attempts), derived from the count of TestAttempt rows for the run.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.models import AgentStep, BenchmarkResult, BenchmarkRun, TestAttempt
from benchmark.pricing import cost_usd
from benchmark.tasks import TASK_MAP, TASKS, BenchmarkTask

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("benchmark")

_TERMINAL = {"passed", "failed", "rejected", "awaiting_approval"}
_POLL_INTERVAL_S = 15
_INGEST_TIMEOUT_S = 300  # max wait for repo to reach ready status
_RUN_TIMEOUT_S = 900  # max wait for a single run (15 min)


# ---------------------------------------------------------------------------
# Typed result container
# ---------------------------------------------------------------------------


@dataclass
class TaskResult:
    task_id: str
    run_id: str | None
    passed: bool
    attempts_to_pass: int | None  # None = failed before any test ran
    time_to_green_s: float | None  # None if failed
    token_cost_usd: float
    error: str | None = None  # set when we couldn't even submit the run


# ---------------------------------------------------------------------------
# API helpers (thin httpx wrappers)
# ---------------------------------------------------------------------------


def _login(client: httpx.Client, base_url: str, email: str, password: str) -> str:
    resp = client.post(
        f"{base_url}/api/v1/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _list_repos(client: httpx.Client, base_url: str, token: str) -> list[dict]:
    resp = client.get(
        f"{base_url}/api/v1/repos",
        headers=_auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _register_repo(
    client: httpx.Client, base_url: str, token: str, task: BenchmarkTask
) -> str:
    resp = client.post(
        f"{base_url}/api/v1/repos",
        headers=_auth_headers(token),
        json={
            "name": task.repo_name,
            "clone_url": task.clone_url,
            "default_branch": task.default_branch,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def _get_repo(client: httpx.Client, base_url: str, token: str, repo_id: str) -> dict:
    resp = client.get(
        f"{base_url}/api/v1/repos/{repo_id}",
        headers=_auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _create_run(
    client: httpx.Client, base_url: str, token: str, repo_id: str, issue_text: str
) -> str:
    resp = client.post(
        f"{base_url}/api/v1/runs",
        headers=_auth_headers(token),
        json={"repo_id": repo_id, "issue_text": issue_text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def _get_run(client: httpx.Client, base_url: str, token: str, run_id: str) -> dict:
    resp = client.get(
        f"{base_url}/api/v1/runs/{run_id}",
        headers=_auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Repo management (get existing or register+wait)
# ---------------------------------------------------------------------------


def ensure_repo(
    client: httpx.Client,
    base_url: str,
    token: str,
    task: BenchmarkTask,
    cache: dict[str, str],  # clone_url → repo_id
) -> str:
    """Return the repo_id for the task, registering + waiting if needed."""
    if task.clone_url in cache:
        log.info("  repo cached: %s (%s)", task.repo_name, cache[task.clone_url][:8])
        return cache[task.clone_url]

    # Check if already registered by this user
    for repo in _list_repos(client, base_url, token):
        if repo["clone_url"] == task.clone_url:
            repo_id = repo["id"]
            status = repo["status"]
            log.info(
                "  repo exists: %s [%s] chunks=%s",
                task.repo_name,
                status,
                repo.get("chunk_count", 0),
            )
            if status == "ready":
                cache[task.clone_url] = repo_id
                return repo_id
            if status == "failed":
                raise RuntimeError(
                    f"Repo {task.repo_name!r} is in failed state"
                    " — remove and re-register"
                )
            # Still ingesting — fall through to poll loop below
            break
    else:
        # Not registered yet
        repo_id = _register_repo(client, base_url, token, task)
        log.info("  repo registered: %s (%s)", task.repo_name, repo_id[:8])

    # Poll until ready
    deadline = time.monotonic() + _INGEST_TIMEOUT_S
    while time.monotonic() < deadline:
        time.sleep(10)
        repo = _get_repo(client, base_url, token, repo_id)
        log.info(
            "  ingesting %s: status=%s chunks=%s",
            task.repo_name,
            repo["status"],
            repo.get("chunk_count", 0),
        )
        if repo["status"] == "ready":
            cache[task.clone_url] = repo_id
            return repo_id
        if repo["status"] == "failed":
            msg = repo.get("error_message", "")
            raise RuntimeError(f"Ingestion failed for {task.repo_name}: {msg}")

    raise TimeoutError(
        f"Repo {task.repo_name!r} did not reach ready within {_INGEST_TIMEOUT_S}s"
    )


# ---------------------------------------------------------------------------
# Metric derivation from DB data
# ---------------------------------------------------------------------------


async def _derive_metrics(
    session_factory: async_sessionmaker,
    run_id_str: str,
    run_started_at: datetime,
    run_completed_at: datetime | None,
    passed: bool,
) -> tuple[int | None, float | None, float]:
    """Query DB for this run and derive (attempts_to_pass, time_to_green_s, cost)."""
    run_id = uuid.UUID(run_id_str)

    async with session_factory() as db:
        # Load TestAttempt rows ordered by attempt_number
        ta_result = await db.execute(
            select(TestAttempt)
            .where(TestAttempt.run_id == run_id)
            .order_by(TestAttempt.attempt_number)
        )
        test_attempts = ta_result.scalars().all()

        # Load AgentStep rows for token cost
        as_result = await db.execute(
            select(AgentStep).where(AgentStep.run_id == run_id)
        )
        agent_steps = as_result.scalars().all()

    # attempts_to_pass: which TestAttempt first passed?
    attempts_to_pass: int | None = None
    time_to_green_s: float | None = None
    first_pass_ta: TestAttempt | None = None

    for ta in test_attempts:
        if ta.passed:
            first_pass_ta = ta
            attempts_to_pass = ta.attempt_number
            break

    if first_pass_ta is not None:
        delta = first_pass_ta.created_at - run_started_at
        time_to_green_s = delta.total_seconds()
    elif run_completed_at is not None and not passed:
        # Failed run — record wall-clock to failure
        delta = run_completed_at - run_started_at
        time_to_green_s = delta.total_seconds()

    # Token cost: sum across all agent steps
    total_input = sum(int(s.token_usage.get("input_tokens", 0)) for s in agent_steps)
    total_output = sum(int(s.token_usage.get("output_tokens", 0)) for s in agent_steps)
    model = settings.GEMINI_MODEL
    token_cost = cost_usd(model, total_input, total_output)

    return attempts_to_pass, time_to_green_s, token_cost


# ---------------------------------------------------------------------------
# Single task execution
# ---------------------------------------------------------------------------


async def run_task(
    client: httpx.Client,
    base_url: str,
    token: str,
    task: BenchmarkTask,
    repo_cache: dict[str, str],
    session_factory: async_sessionmaker,
) -> TaskResult:
    log.info("[%s] starting (%s)", task.task_id, task.difficulty)

    try:
        repo_id = ensure_repo(client, base_url, token, task, repo_cache)
    except Exception as exc:
        log.error("[%s] repo setup failed: %s", task.task_id, exc)
        return TaskResult(
            task_id=task.task_id,
            run_id=None,
            passed=False,
            attempts_to_pass=None,
            time_to_green_s=None,
            token_cost_usd=0.0,
            error=str(exc),
        )

    # Submit run
    try:
        run_id = _create_run(client, base_url, token, repo_id, task.issue_text)
    except Exception as exc:
        log.error("[%s] run creation failed: %s", task.task_id, exc)
        return TaskResult(
            task_id=task.task_id,
            run_id=None,
            passed=False,
            attempts_to_pass=None,
            time_to_green_s=None,
            token_cost_usd=0.0,
            error=str(exc),
        )

    log.info("[%s] run submitted: %s", task.task_id, run_id[:8])
    run_started_at = datetime.now(timezone.utc)

    # Poll until terminal
    deadline = time.monotonic() + _RUN_TIMEOUT_S
    run_data: dict = {}
    while time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL_S)
        try:
            run_data = _get_run(client, base_url, token, run_id)
        except Exception as exc:
            log.warning("[%s] poll error: %s", task.task_id, exc)
            continue

        status = run_data.get("status", "")
        log.info("[%s] status=%s", task.task_id, status)
        if status in _TERMINAL:
            break
    else:
        log.error("[%s] timed out waiting for terminal status", task.task_id)
        return TaskResult(
            task_id=task.task_id,
            run_id=run_id,
            passed=False,
            attempts_to_pass=None,
            time_to_green_s=None,
            token_cost_usd=0.0,
            error="timed out",
        )

    final_status = run_data.get("status", "")
    passed = final_status == "awaiting_approval"

    # Parse completed_at from the API response
    completed_at: datetime | None = None
    if run_data.get("completed_at"):
        try:
            completed_at = datetime.fromisoformat(
                run_data["completed_at"].replace("Z", "+00:00")
            )
        except ValueError:
            pass

    # Derive metrics from DB
    attempts_to_pass, time_to_green_s, token_cost = await _derive_metrics(
        session_factory, run_id, run_started_at, completed_at, passed
    )

    log.info(
        "[%s] done: passed=%s attempts=%s time=%.1fs cost=$%.6f",
        task.task_id,
        passed,
        attempts_to_pass,
        time_to_green_s or 0,
        token_cost,
    )

    return TaskResult(
        task_id=task.task_id,
        run_id=run_id,
        passed=passed,
        attempts_to_pass=attempts_to_pass,
        time_to_green_s=time_to_green_s,
        token_cost_usd=token_cost,
    )


# ---------------------------------------------------------------------------
# DB persistence
# ---------------------------------------------------------------------------


async def save_results(
    session_factory: async_sessionmaker,
    benchmark_run_id: uuid.UUID,
    results: list[TaskResult],
) -> None:
    async with session_factory() as db:
        for r in results:
            db.add(
                BenchmarkResult(
                    benchmark_run_id=benchmark_run_id,
                    task_id=r.task_id,
                    passed=r.passed,
                    attempts_to_pass=r.attempts_to_pass,
                    time_to_green_s=r.time_to_green_s,
                    token_cost_usd=(
                        Decimal(str(round(r.token_cost_usd, 6)))
                        if r.token_cost_usd is not None
                        else None
                    ),
                )
            )
        await db.commit()


# ---------------------------------------------------------------------------
# Summary printing
# ---------------------------------------------------------------------------


def print_summary(results: list[TaskResult], commit_sha: str) -> None:
    total = len(results)
    passed_tasks = [r for r in results if r.passed]
    pass_at_1 = [r for r in passed_tasks if r.attempts_to_pass == 1]
    pass_at_3 = [
        r
        for r in passed_tasks
        if r.attempts_to_pass is not None and r.attempts_to_pass <= 3
    ]

    times = [r.time_to_green_s for r in passed_tasks if r.time_to_green_s is not None]
    avg_time = sum(times) / len(times) if times else 0.0
    total_cost = sum(r.token_cost_usd for r in results)

    print("\n" + "=" * 64)
    print(f"  Benchmark summary  |  commit {commit_sha[:8]}")
    print("=" * 64)
    print(f"  Tasks run:    {total}")
    p1 = len(pass_at_1)
    p3 = len(pass_at_3)
    print(f"  pass@1:       {p1}/{total}  ({100 * p1 / total:.0f}%)")
    print(f"  pass@3:       {p3}/{total}  ({100 * p3 / total:.0f}%)")
    print(f"  avg time:     {avg_time:.1f}s  (passed tasks only)")
    print(f"  total cost:   ${total_cost:.4f}")
    print()
    print(f"  {'task_id':<30} {'pass':<6} {'attempts':<10} {'time(s)':<10} cost")
    print(f"  {'-' * 30} {'-' * 6} {'-' * 10} {'-' * 10} ----")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        att = str(r.attempts_to_pass) if r.attempts_to_pass else "-"
        t = f"{r.time_to_green_s:.0f}" if r.time_to_green_s is not None else "-"
        cost_str = f"${r.token_cost_usd:.4f}"
        print(f"  {r.task_id:<30} {status:<6} {att:<10} {t:<10} {cost_str}")
        if r.error:
            print(f"    -> error: {r.error}")
    print("=" * 64 + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def async_main(args: argparse.Namespace) -> None:
    # Build a DB session factory using the same DATABASE_URL as the app
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Determine which tasks to run
    if args.tasks:
        unknown = set(args.tasks) - set(TASK_MAP)
        if unknown:
            log.error("Unknown task IDs: %s", sorted(unknown))
            log.error("Valid IDs: %s", sorted(TASK_MAP))
            sys.exit(1)
        selected = [TASK_MAP[t] for t in args.tasks]
    else:
        selected = list(TASKS)

    log.info("Running %d benchmark task(s)", len(selected))

    # Record current HEAD commit SHA
    import subprocess

    try:
        commit_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        commit_sha = "unknown"

    # Create a BenchmarkRun record
    bench_run_id = uuid.uuid4()
    async with session_factory() as db:
        db.add(BenchmarkRun(id=bench_run_id, commit_sha=commit_sha))
        await db.commit()

    log.info("Benchmark run ID: %s", bench_run_id)

    # Login to the API
    with httpx.Client() as http:
        try:
            token = _login(http, args.base_url, args.email, args.password)
        except Exception as exc:
            log.error("Login failed: %s", exc)
            sys.exit(1)

        log.info("Logged in as %s", args.email)

        repo_cache: dict[str, str] = {}
        results: list[TaskResult] = []

        for i, task in enumerate(selected):
            if i > 0:
                log.info("Waiting %ss before next task…", args.task_delay)
                time.sleep(args.task_delay)

            result = await run_task(
                http, args.base_url, token, task, repo_cache, session_factory
            )
            results.append(result)

    # Persist all results
    await save_results(session_factory, bench_run_id, results)
    await engine.dispose()

    # Print summary
    print_summary(results, commit_sha)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Foreman benchmark suite against a live API instance"
    )
    parser.add_argument(
        "--base-url", default="http://localhost:8000", help="API base URL"
    )
    parser.add_argument("--email", required=True, help="User email for API login")
    parser.add_argument("--password", required=True, help="User password for API login")
    parser.add_argument(
        "--task-delay",
        type=float,
        default=8.0,
        help="Seconds to wait between task submissions (default: 8)",
    )
    parser.add_argument(
        "--tasks",
        nargs="+",
        metavar="TASK_ID",
        help="Subset of task IDs to run (default: all)",
    )
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
