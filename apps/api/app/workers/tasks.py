"""ARQ background task definitions.

Each function here is registered in WorkerSettings.functions and called by
the ARQ worker process.  Tasks receive a ``ctx`` dict populated by the
``on_startup`` hook; in particular ``ctx["session_factory"]`` gives them
access to the DB without going through the FastAPI request lifecycle.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Repo, RepoChunk, RepoStatus, Run, RunStatus
from app.retrieval.chunking import chunk_repo
from app.retrieval.cloning import CloneError, clone_repo, remove_clone
from app.retrieval.embeddings import EmbeddingError, embed_texts

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _set_failed(db: AsyncSession, repo: Repo, error: str) -> None:
    """Persist *error* on *repo*, transitioning it to ``failed`` status."""
    repo.status = RepoStatus.failed
    repo.error_message = error[:2048]
    try:
        await db.commit()
    except Exception:
        await db.rollback()


# ---------------------------------------------------------------------------
# Task: ingest_repo
# ---------------------------------------------------------------------------


async def ingest_repo(ctx: dict, repo_id: str) -> None:
    """Clone, chunk, embed, and store a repository's code in the vector store.

    This is the ARQ task function that replaces the former synchronous inline
    pipeline in the POST /api/v1/repos route handler.

    Status transitions committed to the DB as the job progresses:

        pending → cloning → chunking → embedding → ready
                                                  ↘ failed (on any error)

    Args:
        ctx: ARQ worker context.  Must contain ``"session_factory"``, an
             ``async_sessionmaker`` initialised in the worker's ``on_startup``
             hook.
        repo_id: String representation of the ``Repo.id`` UUID to ingest.
    """
    session_factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    rid = uuid.UUID(repo_id)

    async with session_factory() as db:
        repo = await db.get(Repo, rid)
        if repo is None:
            logger.warning("ingest_repo: repo not found", extra={"repo_id": repo_id})
            return

        # --- Clone -------------------------------------------------------
        repo.status = RepoStatus.cloning
        await db.commit()
        try:
            clone_path = await asyncio.to_thread(clone_repo, repo.clone_url, repo_id)
        except CloneError as exc:
            logger.error("Clone failed", extra={"repo_id": repo_id, "error": str(exc)})
            await _set_failed(db, repo, str(exc))
            return

        # --- Chunk -------------------------------------------------------
        repo.status = RepoStatus.chunking
        await db.commit()
        try:
            chunks = await asyncio.to_thread(chunk_repo, clone_path)
        except Exception as exc:
            logger.error(
                "Chunking failed", extra={"repo_id": repo_id, "error": str(exc)}
            )
            await _set_failed(db, repo, f"Chunking failed: {exc}")
            await asyncio.to_thread(remove_clone, repo_id)
            return

        # --- Embed -------------------------------------------------------
        repo.status = RepoStatus.embedding
        await db.commit()
        try:
            texts = [c.content for c in chunks]
            embeddings = await embed_texts(texts, input_type="document")
        except EmbeddingError as exc:
            logger.error(
                "Embedding failed", extra={"repo_id": repo_id, "error": str(exc)}
            )
            await _set_failed(db, repo, f"Embedding failed: {exc}")
            await asyncio.to_thread(remove_clone, repo_id)
            return
        except Exception as exc:
            logger.error(
                "Unexpected embedding error",
                extra={"repo_id": repo_id, "error": str(exc)},
            )
            await _set_failed(db, repo, f"Embedding failed unexpectedly: {exc}")
            await asyncio.to_thread(remove_clone, repo_id)
            return

        # --- Store -------------------------------------------------------
        try:
            for chunk, embedding in zip(chunks, embeddings):
                db.add(
                    RepoChunk(
                        repo_id=repo.id,
                        file_path=chunk.file_path,
                        symbol_name=chunk.symbol_name,
                        content=chunk.content,
                        embedding=embedding,
                    )
                )
            repo.status = RepoStatus.ready
            await db.commit()
        except Exception as exc:
            logger.error(
                "Storage failed", extra={"repo_id": repo_id, "error": str(exc)}
            )
            await _set_failed(db, repo, f"Storage failed: {exc}")
            await asyncio.to_thread(remove_clone, repo_id)
            return

        # --- Cleanup -----------------------------------------------------
        try:
            await asyncio.to_thread(remove_clone, repo_id)
        except Exception:
            logger.warning(
                "Failed to remove clone directory", extra={"repo_id": repo_id}
            )

        logger.info(
            "Repo ingestion complete",
            extra={"repo_id": repo_id, "chunk_count": len(chunks)},
        )


# ---------------------------------------------------------------------------
# Task: execute_run
# ---------------------------------------------------------------------------


async def _set_run_failed(db: AsyncSession, run: Run, error: str) -> None:
    """Transition *run* to ``failed`` and record completion time."""
    run.status = RunStatus.failed
    run.completed_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except Exception:
        logger.error(
            "Failed to mark run as failed",
            extra={"run_id": str(run.id), "error": error},
        )
        await db.rollback()


async def execute_run(ctx: dict, run_id: str) -> None:
    """Invoke the Foreman agent graph for a given run.

    Status transitions committed to the DB as execution progresses:

        pending → planning → awaiting_approval
                           ↘ failed (on any error)

    The graph itself (build_graph) creates its own DB sessions per node.
    This task only owns the status bookkeeping around the graph call.

    Args:
        ctx:    ARQ worker context.  Must contain ``"session_factory"``.
        run_id: String representation of the ``Run.id`` UUID to execute.
    """
    from app.agents.state import AgentState
    from app.orchestrator.graph import build_graph

    session_factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    rid = uuid.UUID(run_id)

    async with session_factory() as db:
        run = await db.get(Run, rid)
        if run is None:
            logger.warning("execute_run: run not found", extra={"run_id": run_id})
            return

        run.status = RunStatus.planning
        await db.commit()

        repo_id: uuid.UUID = run.repo_id
        issue_text: str = run.issue_text

    try:
        graph = build_graph()
        initial_state: AgentState = {
            "run_id": rid,
            "repo_id": repo_id,
            "issue_text": issue_text,
            "retrieved_context": [],
            "plan": None,
            "diffs": [],
            "current_agent": "",
            "retry_count": 0,
            "error": None,
        }
        final_state = await graph.ainvoke(initial_state)

        async with session_factory() as db:
            run = await db.get(Run, rid)
            if run is not None:
                run.status = RunStatus.awaiting_approval
                run.completed_at = datetime.now(timezone.utc)
                await db.commit()

        plan = final_state.get("plan") or {}
        diffs = final_state.get("diffs") or []
        logger.info(
            "execute_run complete",
            extra={
                "run_id": run_id,
                "plan_steps": len(plan.get("steps", [])),
                "diff_count": len(diffs),
            },
        )

    except Exception as exc:
        logger.error(
            "execute_run failed",
            extra={"run_id": run_id, "error": str(exc)},
        )
        async with session_factory() as db:
            run = await db.get(Run, rid)
            if run is not None:
                await _set_run_failed(db, run, str(exc))
