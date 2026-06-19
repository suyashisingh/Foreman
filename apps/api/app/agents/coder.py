"""Coder node: implement the plan by editing files in a real e2b sandbox.

This is the second node in the Foreman agent graph.  It:

1. Resolves the repository clone URL from the DB and transitions the run to
   ``coding`` status.
2. Opens a fresh e2b sandbox, shallow-clones the target repo into it (the
   host-side ingestion clone no longer exists; this is a separate, isolated
   environment).
3. Runs a bounded tool-use loop: sends the Plan + issue to Gemini with
   ``read_file`` / ``write_file`` / ``list_files`` tools available, executes
   each tool call against the real sandbox, feeds results back, and repeats
   until the model stops calling tools OR ``MAX_CODER_TOOL_ITERATIONS`` is
   reached (graceful stop — whatever edits exist are captured, not discarded).
4. Runs ``git diff`` inside the sandbox to capture the resulting unified diff.
5. Persists per-file ``Diff`` rows (``approved=False``) and logs the
   ``AgentStep`` telemetry row, both inside a single DB commit.
6. Always kills the sandbox in a ``finally`` block — even on failure — so
   billable sandbox time doesn't leak.

Returns a partial ``AgentState`` dict with ``diffs`` populated.
On any exception, the error propagates to ``execute_run`` in tasks.py, which
transitions the run to ``failed``.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any

from e2b import AsyncSandbox
from google import genai
from google.genai import types as genai_types

from app.agents.state import AgentState
from app.agents.tools import CODER_TOOLS, execute_tool
from app.core.config import settings
from app.db import session as _db_session
from app.db.models import AgentRole, Diff, Repo, Run, RunStatus
from app.orchestrator.logging import log_agent_step

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _build_coder_prompt(
    issue_text: str,
    plan: dict[str, Any],
    repo_dir: str,
) -> str:
    """Assemble the Coder's initial prompt from the issue and the Planner's plan."""
    steps_text = "\n".join(
        f"  - [{s.get('action', '?').upper()}] {s.get('file_path', '?')}: "
        f"{s.get('description', '')}"
        for s in plan.get("steps", [])
    )
    rationale = plan.get("rationale", "(no rationale)")

    return f"""You are an expert software engineer implementing a code change.

The repository has been cloned to {repo_dir!r}.

## Issue
{issue_text}

## Implementation Plan
{steps_text or "(no steps — use your judgment)"}

Rationale: {rationale}

## Instructions
Use the available tools to implement every step in the plan:
- Call read_file before editing any file so you can make targeted changes.
- Call write_file with the *complete* new file contents (no partial writes).
- Call list_files if you need to explore the repository layout.
- Only modify files that are part of the plan.
- When you have finished ALL changes, stop calling tools.

Begin implementing now.
"""


# ---------------------------------------------------------------------------
# Diff parser
# ---------------------------------------------------------------------------


def _parse_diff(raw_diff: str) -> list[dict[str, str]]:
    """Split a raw ``git diff`` output into per-file ``{file_path, patch}`` records."""
    sections = re.split(r"(?=^diff --git )", raw_diff, flags=re.MULTILINE)
    diffs: list[dict[str, str]] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        # "diff --git a/<path> b/<path>" — extract the path from group 1.
        m = re.match(r"^diff --git a/(.+) b/\1$", section, flags=re.MULTILINE)
        file_path = m.group(1) if m else "unknown"
        diffs.append({"file_path": file_path, "patch": section})
    return diffs


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------


async def coder_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: implement the Planner's plan in a real e2b sandbox.

    Reads ``run_id``, ``repo_id``, ``issue_text``, and ``plan`` from *state*.

    Side effects committed to the DB:
    - ``Run.status`` → ``coding`` at start; ``Run.sandbox_id`` updated once
      the sandbox is created.
    - ``Diff`` rows (one per changed file) persisted after the tool-use loop.
    - ``AgentStep`` row for the Coder's telemetry.

    Returns:
        Partial ``AgentState`` with ``diffs`` and ``current_agent`` updated.

    Raises:
        RuntimeError: If required state or DB rows are missing.
        Any exception from the e2b / Gemini API propagates to ``execute_run``,
        which handles the ``failed`` status transition.
    """
    run_id: uuid.UUID = state["run_id"]
    repo_id: uuid.UUID = state["repo_id"]
    issue_text: str = state["issue_text"]
    plan: dict[str, Any] = state.get("plan") or {}

    if _db_session.async_session_factory is None:
        raise RuntimeError("DB session factory not initialised in coder_node")

    # --- Resolve clone URL and transition to coding -------------------------
    async with _db_session.async_session_factory() as db:
        repo: Repo | None = await db.get(Repo, repo_id)
        if repo is None:
            raise RuntimeError(f"Repo {repo_id} not found in coder_node")
        clone_url: str = repo.clone_url

        run: Run | None = await db.get(Run, run_id)
        if run is None:
            raise RuntimeError(f"Run {run_id} not found in coder_node")
        run.status = RunStatus.coding
        await db.commit()

    sandbox: AsyncSandbox | None = None
    repo_dir = "/home/user/repo"
    t_start = time.perf_counter()
    total_input_tokens = 0
    total_output_tokens = 0
    tool_calls_log: list[dict[str, Any]] = []

    try:
        # --- Create sandbox and clone repo ----------------------------------
        sandbox = await AsyncSandbox.create(
            api_key=settings.E2B_API_KEY,
            timeout=300,
        )

        async with _db_session.async_session_factory() as db:
            run = await db.get(Run, run_id)
            if run is not None:
                run.sandbox_id = sandbox.sandbox_id
                await db.commit()

        clone_result = await sandbox.commands.run(
            f"git clone --depth=1 {clone_url} {repo_dir}",
            timeout=120,
        )
        if clone_result.exit_code != 0:
            raise RuntimeError(
                f"git clone failed (exit {clone_result.exit_code}): "
                f"{clone_result.stderr[:500]}"
            )

        logger.info(
            "Coder: repo cloned into sandbox",
            extra={"run_id": str(run_id), "sandbox_id": sandbox.sandbox_id},
        )

        # --- Tool-use loop --------------------------------------------------
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        prompt = _build_coder_prompt(issue_text, plan, repo_dir)
        contents: list[genai_types.Content] = [
            genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])
        ]
        config = genai_types.GenerateContentConfig(tools=CODER_TOOLS)

        for iteration in range(settings.MAX_CODER_TOOL_ITERATIONS):
            response = await client.aio.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=contents,  # type: ignore[arg-type]
                config=config,
            )

            usage = response.usage_metadata
            if usage:
                total_input_tokens += int(usage.prompt_token_count or 0)
                total_output_tokens += int(usage.candidates_token_count or 0)

            if not response.candidates:
                break
            candidate_content = response.candidates[0].content
            if candidate_content is None:
                break
            parts = candidate_content.parts or []
            fn_call_parts = [p for p in parts if p.function_call]

            if not fn_call_parts:
                # No function calls → model has finished making edits.
                logger.info(
                    "Coder: tool-use loop complete (model done)",
                    extra={"run_id": str(run_id), "iterations": iteration + 1},
                )
                break

            # Append the model's content, execute all tool calls, feed results back.
            contents.append(candidate_content)
            fn_response_parts: list[genai_types.Part] = []

            for part in fn_call_parts:
                fc = part.function_call
                if fc is None:
                    continue
                result = await execute_tool(sandbox, fc.name or "", fc.args or {})
                tool_calls_log.append(
                    {"name": fc.name, "args": fc.args, "result": result}
                )
                fn_response_parts.append(
                    genai_types.Part(
                        function_response=genai_types.FunctionResponse(
                            name=fc.name or "",
                            id=fc.id,
                            response=result,
                        )
                    )
                )
                logger.debug(
                    "Coder: tool executed",
                    extra={
                        "run_id": str(run_id),
                        "tool": fc.name,
                        "iteration": iteration,
                        "args": fc.args,
                    },
                )

            contents.append(genai_types.Content(role="user", parts=fn_response_parts))

        else:
            # for-loop exhausted without break → hit MAX_CODER_TOOL_ITERATIONS.
            # Proceed with whatever edits exist rather than failing the run.
            logger.warning(
                "Coder: hit MAX_CODER_TOOL_ITERATIONS — stopping loop",
                extra={
                    "run_id": str(run_id),
                    "max": settings.MAX_CODER_TOOL_ITERATIONS,
                },
            )

        # --- Capture diff ---------------------------------------------------
        diff_result = await sandbox.commands.run(
            f"git -C {repo_dir} diff",
            timeout=30,
        )
        raw_diff = diff_result.stdout
        diffs = _parse_diff(raw_diff) if raw_diff.strip() else []

        latency_ms = int((time.perf_counter() - t_start) * 1000)

        # --- Persist diffs and log agent step (single commit) ---------------
        async with _db_session.async_session_factory() as db:
            for diff in diffs:
                db.add(
                    Diff(
                        run_id=run_id,
                        file_path=diff["file_path"],
                        patch=diff["patch"],
                        approved=False,
                    )
                )

            # log_agent_step flushes and commits all pending rows (Diffs above
            # and the new AgentStep) in one transaction.
            await log_agent_step(
                db=db,
                run_id=run_id,
                agent=AgentRole.coder,
                step_index=1,
                input_data={
                    "issue_text": issue_text,
                    "plan_steps": len(plan.get("steps", [])),
                    "clone_url": clone_url,
                    "tool_iterations": len(tool_calls_log),
                },
                output_data={
                    "diff_count": len(diffs),
                    "files_changed": [d["file_path"] for d in diffs],
                },
                tool_calls=tool_calls_log,
                token_usage={
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                },
                latency_ms=latency_ms,
            )

        logger.info(
            "Coder node complete",
            extra={
                "run_id": str(run_id),
                "diff_count": len(diffs),
                "tool_iterations": len(tool_calls_log),
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "latency_ms": latency_ms,
            },
        )

        return {
            "diffs": diffs,
            "current_agent": "coder",
        }

    finally:
        if sandbox is not None:
            try:
                await sandbox.kill()
            except Exception:
                # Sandbox may have already exited; don't mask a successful run.
                logger.warning(
                    "Coder: failed to kill sandbox — may have already exited",
                    extra={"run_id": str(run_id)},
                )
