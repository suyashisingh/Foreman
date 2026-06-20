"""Tester node: run the repository's test suite inside the shared e2b sandbox.

This is the third node in the Foreman agent graph.  It:

1. Transitions the run to ``testing`` status.
2. Ensures pytest is available in the sandbox (best-effort pip install).
3. Runs ``python -m pytest <repo_dir> --tb=short -q`` and captures the
   exit code, stdout, and stderr.
4. Determines pass/fail: ``exit_code == 0`` → passed.
5. Persists a ``TestAttempt`` row and logs the ``AgentStep`` telemetry row.

Returns a partial ``AgentState`` with ``test_passed`` and ``test_output``
updated.  The routing function in ``graph.py`` then decides whether to END
(pass or retries exhausted) or loop back to the Coder for a retry.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from e2b import AsyncSandbox
from e2b.sandbox_async.commands.command_handle import CommandExitException

from app.agents.state import AgentState
from app.db import session as _db_session
from app.db.models import AgentRole, Run, RunStatus, TestAttempt
from app.orchestrator.logging import log_agent_step

logger = logging.getLogger(__name__)

_REPO_DIR = "/home/user/repo"


async def tester_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: run pytest in the shared sandbox and record the result.

    Reads ``run_id``, ``sandbox``, and ``retry_count`` from *state*.

    Side effects committed to the DB:
    - ``Run.status`` → ``testing`` at start.
    - ``TestAttempt`` row with pass/fail, stdout, stderr, and duration.
    - ``AgentStep`` row for telemetry.

    Returns:
        Partial ``AgentState`` with ``test_passed``, ``test_output``, and
        ``current_agent`` updated.

    Raises:
        RuntimeError: If the DB session factory is missing or the Run is
            not found.
    """
    run_id: uuid.UUID = state["run_id"]
    sandbox: AsyncSandbox | None = state.get("sandbox")
    if sandbox is None:
        raise RuntimeError("sandbox missing from state — must be set in execute_run")
    retry_count: int = state.get("retry_count") or 0

    if _db_session.async_session_factory is None:
        raise RuntimeError("DB session factory not initialised in tester_node")

    # --- Transition to testing status ---------------------------------------
    async with _db_session.async_session_factory() as db:
        run: Run | None = await db.get(Run, run_id)
        if run is None:
            raise RuntimeError(f"Run {run_id} not found in tester_node")
        run.status = RunStatus.testing
        await db.commit()

    # --- Ensure pytest and the repo's own package are available (best-effort) -
    # Wrapping in try/except: a transient sandbox error here must not kill the
    # run before we can record a TestAttempt — we still want to try pytest.
    try:
        await sandbox.commands.run("pip install pytest -q", timeout=60)
    except Exception:
        logger.warning("pip install pytest raised — continuing", extra={"run_id": str(run_id)})
    try:
        # Install the repo's own package so test-suite imports resolve.
        await sandbox.commands.run(
            f"pip install -e {_REPO_DIR} -q", timeout=90,
        )
    except Exception:
        logger.warning("pip install -e repo raised — continuing", extra={"run_id": str(run_id)})

    # --- Run pytest ---------------------------------------------------------
    # e2b raises CommandExitException for non-zero exit codes (e.g. failing
    # tests) and a generic Exception for transient sandbox/network errors.
    t_start = time.perf_counter()
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    passed: bool = False
    try:
        result = await sandbox.commands.run(
            "python -m pytest --tb=short -q",
            cwd=_REPO_DIR,
            timeout=180,
        )
        exit_code = result.exit_code
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        passed = exit_code == 0
    except CommandExitException as exc:
        # pytest itself ran but exited non-zero — the exception carries output.
        exit_code = exc.exit_code
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        passed = False
    except Exception as exc:
        # Transient sandbox/network error — treat as failure so retry fires.
        exit_code = -1
        stderr = f"sandbox error: {exc}"
        logger.error(
            "sandbox.commands.run raised during pytest",
            exc_info=True,
            extra={"run_id": str(run_id)},
        )
    duration_ms = int((time.perf_counter() - t_start) * 1000)

    test_output = stdout + (f"\n{stderr}" if stderr.strip() else "")

    attempt_number = retry_count + 1
    step_index = 2 + 2 * retry_count

    logger.info(
        "Tester: pytest completed",
        extra={
            "run_id": str(run_id),
            "attempt_number": attempt_number,
            "passed": passed,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
        },
    )

    # --- Persist TestAttempt and log agent step (single commit) -------------
    async with _db_session.async_session_factory() as db:
        db.add(
            TestAttempt(
                run_id=run_id,
                attempt_number=attempt_number,
                passed=passed,
                stdout=stdout[:10_000] if stdout else None,
                stderr=stderr[:2_000] if stderr else None,
                duration_ms=duration_ms,
            )
        )

        await log_agent_step(
            db=db,
            run_id=run_id,
            agent=AgentRole.tester,
            step_index=step_index,
            input_data={
                "attempt_number": attempt_number,
                "repo_dir": _REPO_DIR,
            },
            output_data={
                "passed": passed,
                "exit_code": exit_code,
                "stdout_len": len(stdout),
                "stderr_len": len(stderr),
            },
            tool_calls=[],
            token_usage={"input_tokens": 0, "output_tokens": 0},
            latency_ms=duration_ms,
        )

    return {
        "test_passed": passed,
        "test_output": test_output,
        "current_agent": "tester",
    }
