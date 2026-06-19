"""Tests for the ARQ worker and the ingest_repo task function.

HTTP tests verify that POST /repos returns 202 immediately and enqueues the
correct job.  Task tests call ingest_repo directly (bypassing ARQ's queue)
with mocked retrieval functions to verify status transitions.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.db.models import Repo, RepoChunk, RepoStatus, User
from app.retrieval.chunking import chunk_repo
from app.workers.tasks import ingest_repo

REPOS_URL = "/api/v1/repos"

_FAKE_EMBED_DIM = 1024


def _fake_embeddings(n: int) -> list[list[float]]:
    return [[0.1] * _FAKE_EMBED_DIM for _ in range(n)]


# ---------------------------------------------------------------------------
# Fixtures: seed a User+Repo directly in the test DB (no HTTP)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def pending_repo(db, session_factory):
    """A User and a Repo with status=pending seeded directly in the test DB."""
    user = User(
        email="worker@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$placeholder",
        name="Worker",
    )
    db.add(user)
    await db.flush()

    repo = Repo(
        user_id=user.id,
        name="worker-test-repo",
        clone_url="https://github.com/example/repo.git",
        default_branch="main",
        status=RepoStatus.pending,
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)
    return repo


# ---------------------------------------------------------------------------
# HTTP endpoint tests: POST /repos → 202 + enqueue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_repos_returns_202(auth_client, mock_arq_pool):
    """POST /repos returns 202 Accepted immediately."""
    resp = await auth_client.post(
        REPOS_URL,
        json={"name": "my-repo", "clone_url": "https://github.com/x/y.git"},
    )
    assert resp.status_code == 202, resp.text


@pytest.mark.asyncio
async def test_post_repos_response_has_pending_status(auth_client, mock_arq_pool):
    """POST /repos response body has status=pending and chunk_count=0."""
    resp = await auth_client.post(
        REPOS_URL,
        json={"name": "my-repo", "clone_url": "https://github.com/x/y.git"},
    )
    body = resp.json()
    assert body["status"] == "pending"
    assert body["chunk_count"] == 0
    assert body["error_message"] is None


@pytest.mark.asyncio
async def test_post_repos_enqueues_ingest_job(auth_client, mock_arq_pool):
    """POST /repos calls enqueue_job with 'ingest_repo' and the repo's UUID."""
    resp = await auth_client.post(
        REPOS_URL,
        json={"name": "my-repo", "clone_url": "https://github.com/x/y.git"},
    )
    repo_id = resp.json()["id"]

    mock_arq_pool.enqueue_job.assert_called_once_with("ingest_repo", repo_id)


@pytest.mark.asyncio
async def test_post_repos_row_exists_with_pending_status(
    auth_client, mock_arq_pool, db
):
    """The Repo row exists in the DB with status=pending right after POST."""
    resp = await auth_client.post(
        REPOS_URL,
        json={"name": "check-db", "clone_url": "https://github.com/x/y.git"},
    )
    repo_id = uuid.UUID(resp.json()["id"])

    repo = await db.get(Repo, repo_id)
    assert repo is not None
    assert repo.status == RepoStatus.pending


# ---------------------------------------------------------------------------
# Task function tests: ingest_repo called directly (no HTTP, no ARQ queue)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_repo_success(
    pending_repo: Repo, db, session_factory, mocker, fake_repo_dir
):
    """Successful ingest transitions status to ready and stores chunk rows."""
    expected_chunks = chunk_repo(fake_repo_dir)

    mocker.patch("app.workers.tasks.clone_repo", return_value=fake_repo_dir)
    mocker.patch("app.workers.tasks.remove_clone")
    mocker.patch(
        "app.workers.tasks.embed_texts",
        return_value=_fake_embeddings(len(expected_chunks)),
    )

    await ingest_repo({"session_factory": session_factory}, str(pending_repo.id))

    await db.refresh(pending_repo)
    assert pending_repo.status == RepoStatus.ready
    assert pending_repo.error_message is None

    count = await db.scalar(
        select(func.count(RepoChunk.id)).where(RepoChunk.repo_id == pending_repo.id)
    )
    assert count == len(expected_chunks)


@pytest.mark.asyncio
async def test_ingest_repo_clone_failure(
    pending_repo: Repo, db, session_factory, mocker
):
    """A clone error transitions status to failed and stores error_message."""
    from app.retrieval.cloning import CloneError

    mocker.patch(
        "app.workers.tasks.clone_repo",
        side_effect=CloneError("connection refused"),
    )
    mocker.patch("app.workers.tasks.remove_clone")

    await ingest_repo({"session_factory": session_factory}, str(pending_repo.id))

    await db.refresh(pending_repo)
    assert pending_repo.status == RepoStatus.failed
    assert pending_repo.error_message is not None
    assert "connection refused" in pending_repo.error_message


@pytest.mark.asyncio
async def test_ingest_repo_embed_failure(
    pending_repo: Repo, db, session_factory, mocker, fake_repo_dir
):
    """An embedding error transitions status to failed after chunking."""
    from app.retrieval.embeddings import EmbeddingError

    mocker.patch("app.workers.tasks.clone_repo", return_value=fake_repo_dir)
    mocker.patch("app.workers.tasks.remove_clone")
    mocker.patch(
        "app.workers.tasks.embed_texts",
        side_effect=EmbeddingError("rate limited"),
    )

    await ingest_repo({"session_factory": session_factory}, str(pending_repo.id))

    await db.refresh(pending_repo)
    assert pending_repo.status == RepoStatus.failed
    assert pending_repo.error_message is not None
    assert "rate limited" in pending_repo.error_message


@pytest.mark.asyncio
async def test_ingest_repo_missing_repo_is_noop(session_factory):
    """Task exits gracefully when the repo_id doesn't exist in the DB."""
    nonexistent_id = str(uuid.uuid4())
    # Should not raise — just log a warning and return.
    await ingest_repo({"session_factory": session_factory}, nonexistent_id)
