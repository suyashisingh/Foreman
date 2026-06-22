"""Tests for the /api/v1/runs endpoints.

HTTP tests verify request validation and 202 enqueueing.
Direct DB tests verify GET detail returns seeded data correctly.
Approve/reject tests verify status transitions and diff approval.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db.models import (
    AgentRole,
    AgentStep,
    Diff,
    Repo,
    RepoStatus,
    Run,
    RunStatus,
    User,
)

RUNS_URL = "/api/v1/runs"
_AUTH_USER = {"email": "runstest@example.com", "password": "Passw0rd!", "name": "Runs"}
_AUTH_USER2 = {"email": "other@example.com", "password": "Passw0rd!", "name": "Other"}


# ---------------------------------------------------------------------------
# Fixtures — seed a ready repo directly in the DB
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def ready_repo(db, auth_client):
    """A User+Repo with status=ready seeded directly in the DB."""
    # The auth_client fixture already registered _AUTH_USER — retrieve that user
    result = await db.execute(select(User).where(User.email == _AUTH_USER["email"]))
    user = result.scalar_one()

    repo = Repo(
        user_id=user.id,
        name="test-ready-repo",
        clone_url="https://github.com/example/repo.git",
        default_branch="main",
        status=RepoStatus.ready,
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)
    return repo


@pytest_asyncio.fixture
async def auth_client(client):
    """AsyncClient with a registered+authenticated user."""
    reg = await client.post("/api/v1/auth/register", json=_AUTH_USER)
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest_asyncio.fixture
async def seeded_run(db, ready_repo):
    """A Run row seeded directly in the test DB with one AgentStep."""
    result = await db.execute(select(User).where(User.email == _AUTH_USER["email"]))
    user = result.scalar_one()

    run = Run(
        user_id=user.id,
        repo_id=ready_repo.id,
        issue_text="Fix the parser bug",
        status=RunStatus.awaiting_approval,
    )
    db.add(run)
    await db.flush()

    step = AgentStep(
        run_id=run.id,
        agent=AgentRole.planner,
        step_index=0,
        input={"issue_text": "Fix the parser bug", "retrieved_chunk_count": 3},
        output={"steps": [], "rationale": "Test rationale"},
        tool_calls=[],
        token_usage={"input_tokens": 100, "output_tokens": 50},
        latency_ms=1234,
    )
    db.add(step)
    await db.commit()
    await db.refresh(run)
    return run


# ---------------------------------------------------------------------------
# POST /runs tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_runs_requires_auth(client):
    """POST /runs without a token returns 401."""
    resp = await client.post(
        RUNS_URL, json={"repo_id": str(uuid.uuid4()), "issue_text": "x"}
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_post_runs_rejects_non_ready_repo(auth_client, mock_arq_pool, db):
    """POST /runs with a pending-status repo returns 422."""
    result = await db.execute(select(User).where(User.email == _AUTH_USER["email"]))
    user = result.scalar_one()

    pending_repo = Repo(
        user_id=user.id,
        name="pending-repo",
        clone_url="https://github.com/x/y.git",
        default_branch="main",
        status=RepoStatus.pending,
    )
    db.add(pending_repo)
    await db.commit()

    resp = await auth_client.post(
        RUNS_URL,
        json={"repo_id": str(pending_repo.id), "issue_text": "Fix something"},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_post_runs_rejects_other_users_repo(auth_client, mock_arq_pool, db):
    """POST /runs with another user's repo returns 404."""
    other_user = User(
        email="stranger@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$placeholder",
        name="Stranger",
    )
    db.add(other_user)
    await db.flush()

    other_repo = Repo(
        user_id=other_user.id,
        name="other-repo",
        clone_url="https://github.com/other/repo.git",
        default_branch="main",
        status=RepoStatus.ready,
    )
    db.add(other_repo)
    await db.commit()

    resp = await auth_client.post(
        RUNS_URL,
        json={"repo_id": str(other_repo.id), "issue_text": "Do something"},
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_post_runs_returns_202_for_ready_repo(
    auth_client, mock_arq_pool, ready_repo
):
    """POST /runs with a ready repo returns 202 and status=pending."""
    resp = await auth_client.post(
        RUNS_URL,
        json={"repo_id": str(ready_repo.id), "issue_text": "Fix the bug"},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["repo_id"] == str(ready_repo.id)
    assert body["issue_text"] == "Fix the bug"


@pytest.mark.asyncio
async def test_post_runs_enqueues_execute_run(auth_client, mock_arq_pool, ready_repo):
    """POST /runs calls enqueue_job with 'execute_run' and the run's UUID."""
    resp = await auth_client.post(
        RUNS_URL,
        json={"repo_id": str(ready_repo.id), "issue_text": "Fix the bug"},
    )
    run_id = resp.json()["id"]
    mock_arq_pool.enqueue_job.assert_called_once_with("execute_run", run_id)


# ---------------------------------------------------------------------------
# GET /runs tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_runs_requires_auth(client):
    """GET /runs without a token returns 401."""
    resp = await client.get(RUNS_URL)
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_runs_returns_user_runs(auth_client, mock_arq_pool, ready_repo):
    """GET /runs returns the runs created by the authenticated user."""
    await auth_client.post(
        RUNS_URL,
        json={"repo_id": str(ready_repo.id), "issue_text": "Issue A"},
    )
    await auth_client.post(
        RUNS_URL,
        json={"repo_id": str(ready_repo.id), "issue_text": "Issue B"},
    )

    resp = await auth_client.get(RUNS_URL)
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 2
    texts = {r["issue_text"] for r in runs}
    assert texts == {"Issue A", "Issue B"}


@pytest.mark.asyncio
async def test_get_run_requires_auth(client):
    """GET /runs/{id} without a token returns 401."""
    resp = await client.get(f"{RUNS_URL}/{uuid.uuid4()}")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_run_returns_detail_with_steps(auth_client, seeded_run):
    """GET /runs/{id} returns the run with its agent_steps."""
    resp = await auth_client.get(f"{RUNS_URL}/{seeded_run.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(seeded_run.id)
    assert body["status"] == "awaiting_approval"
    assert len(body["agent_steps"]) == 1

    step = body["agent_steps"][0]
    assert step["agent"] == "planner"
    assert step["step_index"] == 0
    assert step["latency_ms"] == 1234
    assert step["token_usage"] == {"input_tokens": 100, "output_tokens": 50}


@pytest.mark.asyncio
async def test_get_run_returns_404_for_other_user(auth_client, db):
    """GET /runs/{id} returns 404 for a run that belongs to another user."""
    other = User(
        email="other2@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$placeholder",
        name="Other",
    )
    db.add(other)
    await db.flush()

    other_repo = Repo(
        user_id=other.id,
        name="other-repo",
        clone_url="https://github.com/other/repo.git",
        default_branch="main",
        status=RepoStatus.ready,
    )
    db.add(other_repo)
    await db.flush()

    other_run = Run(
        user_id=other.id,
        repo_id=other_repo.id,
        issue_text="Private issue",
        status=RunStatus.pending,
    )
    db.add(other_run)
    await db.commit()

    resp = await auth_client.get(f"{RUNS_URL}/{other_run.id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /runs/{id} — review output
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seeded_run_with_review(db, ready_repo):
    """A run at awaiting_approval with a reviewer AgentStep seeded."""
    result = await db.execute(select(User).where(User.email == _AUTH_USER["email"]))
    user = result.scalar_one()

    run = Run(
        user_id=user.id,
        repo_id=ready_repo.id,
        issue_text="Fix the parser bug",
        status=RunStatus.awaiting_approval,
    )
    db.add(run)
    await db.flush()

    step = AgentStep(
        run_id=run.id,
        agent=AgentRole.reviewer,
        step_index=3,
        input={"issue_text": "Fix the parser bug", "plan_steps": 1, "diff_count": 1},
        output={
            "summary": "Adds subtract method correctly.",
            "risk_level": "low",
            "risk_notes": "None identified.",
            "pr_title": "feat: add subtract method",
            "pr_description": "- Adds subtract to Calculator",
        },
        tool_calls=[],
        token_usage={"input_tokens": 80, "output_tokens": 40},
        latency_ms=600,
    )
    db.add(step)
    await db.commit()
    await db.refresh(run)
    return run


@pytest.mark.asyncio
async def test_get_run_includes_review_when_reviewer_step_present(
    auth_client, seeded_run_with_review
):
    """GET /runs/{id} surfaces review output from the reviewer AgentStep."""
    resp = await auth_client.get(f"{RUNS_URL}/{seeded_run_with_review.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["review"] is not None
    assert body["review"]["risk_level"] == "low"
    assert body["review"]["pr_title"] == "feat: add subtract method"


@pytest.mark.asyncio
async def test_get_run_review_is_null_without_reviewer_step(auth_client, seeded_run):
    """GET /runs/{id} returns review=null when no reviewer step exists."""
    resp = await auth_client.get(f"{RUNS_URL}/{seeded_run.id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["review"] is None


# ---------------------------------------------------------------------------
# POST /runs/{id}/approve
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def awaiting_run(db, ready_repo):
    """A run at awaiting_approval status with one Diff row."""
    result = await db.execute(select(User).where(User.email == _AUTH_USER["email"]))
    user = result.scalar_one()

    run = Run(
        user_id=user.id,
        repo_id=ready_repo.id,
        issue_text="Add subtract",
        status=RunStatus.awaiting_approval,
    )
    db.add(run)
    await db.flush()

    diff = Diff(
        run_id=run.id,
        file_path="calc.py",
        patch="@@ -1,0 +1,3 @@\n+def subtract(a, b): return a - b\n",
        approved=False,
    )
    db.add(diff)
    await db.commit()
    await db.refresh(run)
    return run


@pytest.mark.asyncio
async def test_approve_run_transitions_to_passed(auth_client, awaiting_run, db):
    """POST /runs/{id}/approve sets status=passed."""
    resp = await auth_client.post(f"{RUNS_URL}/{awaiting_run.id}/approve")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "passed"

    await db.refresh(awaiting_run)
    assert awaiting_run.status == RunStatus.passed


@pytest.mark.asyncio
async def test_approve_run_sets_diffs_approved(auth_client, awaiting_run, db):
    """POST /runs/{id}/approve sets approved=True on all diffs."""
    resp = await auth_client.post(f"{RUNS_URL}/{awaiting_run.id}/approve")
    assert resp.status_code == 200, resp.text

    diffs = (
        (await db.execute(select(Diff).where(Diff.run_id == awaiting_run.id)))
        .scalars()
        .all()
    )
    assert all(d.approved for d in diffs)


@pytest.mark.asyncio
async def test_approve_run_requires_auth(client):
    """POST /runs/{id}/approve without a token returns 401."""
    resp = await client.post(f"{RUNS_URL}/{uuid.uuid4()}/approve")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_approve_run_returns_404_for_other_user(auth_client, db):
    """POST /runs/{id}/approve returns 404 for another user's run."""
    other = User(
        email="other_approve@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$placeholder",
        name="Other",
    )
    db.add(other)
    await db.flush()
    other_repo = Repo(
        user_id=other.id,
        name="repo",
        clone_url="https://github.com/x/y.git",
        default_branch="main",
        status=RepoStatus.ready,
    )
    db.add(other_repo)
    await db.flush()
    other_run = Run(
        user_id=other.id,
        repo_id=other_repo.id,
        issue_text="Private",
        status=RunStatus.awaiting_approval,
    )
    db.add(other_run)
    await db.commit()

    resp = await auth_client.post(f"{RUNS_URL}/{other_run.id}/approve")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_run_returns_422_if_wrong_status(
    auth_client, mock_arq_pool, ready_repo
):
    """POST /runs/{id}/approve returns 422 if run is not awaiting_approval."""
    create_resp = await auth_client.post(
        RUNS_URL,
        json={"repo_id": str(ready_repo.id), "issue_text": "Fix"},
    )
    run_id = create_resp.json()["id"]

    resp = await auth_client.post(f"{RUNS_URL}/{run_id}/approve")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /runs/{id}/reject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reject_run_transitions_to_rejected(auth_client, awaiting_run, db):
    """POST /runs/{id}/reject sets status=rejected."""
    resp = await auth_client.post(f"{RUNS_URL}/{awaiting_run.id}/reject", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rejected"

    await db.refresh(awaiting_run)
    assert awaiting_run.status == RunStatus.rejected


@pytest.mark.asyncio
async def test_reject_run_stores_reason(auth_client, awaiting_run, db):
    """POST /runs/{id}/reject stores the rejection_reason when provided."""
    resp = await auth_client.post(
        f"{RUNS_URL}/{awaiting_run.id}/reject",
        json={"reason": "Logic error in subtract"},
    )
    assert resp.status_code == 200, resp.text

    await db.refresh(awaiting_run)
    assert awaiting_run.rejection_reason == "Logic error in subtract"


@pytest.mark.asyncio
async def test_reject_run_no_reason(auth_client, awaiting_run, db):
    """POST /runs/{id}/reject with empty body leaves rejection_reason null."""
    resp = await auth_client.post(f"{RUNS_URL}/{awaiting_run.id}/reject", json={})
    assert resp.status_code == 200, resp.text

    await db.refresh(awaiting_run)
    assert awaiting_run.rejection_reason is None


@pytest.mark.asyncio
async def test_reject_run_requires_auth(client):
    """POST /runs/{id}/reject without a token returns 401."""
    resp = await client.post(f"{RUNS_URL}/{uuid.uuid4()}/reject", json={})
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_reject_run_returns_404_for_other_user(auth_client, db):
    """POST /runs/{id}/reject returns 404 for another user's run."""
    other = User(
        email="other_reject@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$placeholder",
        name="Other",
    )
    db.add(other)
    await db.flush()
    other_repo = Repo(
        user_id=other.id,
        name="repo",
        clone_url="https://github.com/x/y.git",
        default_branch="main",
        status=RepoStatus.ready,
    )
    db.add(other_repo)
    await db.flush()
    other_run = Run(
        user_id=other.id,
        repo_id=other_repo.id,
        issue_text="Private",
        status=RunStatus.awaiting_approval,
    )
    db.add(other_run)
    await db.commit()

    resp = await auth_client.post(f"{RUNS_URL}/{other_run.id}/reject", json={})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reject_run_returns_422_if_wrong_status(
    auth_client, mock_arq_pool, ready_repo
):
    """POST /runs/{id}/reject returns 422 if run is not awaiting_approval."""
    create_resp = await auth_client.post(
        RUNS_URL,
        json={"repo_id": str(ready_repo.id), "issue_text": "Fix"},
    )
    run_id = create_resp.json()["id"]

    resp = await auth_client.post(f"{RUNS_URL}/{run_id}/reject", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /runs/{id}/cancel
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def planning_run(db, ready_repo):
    """A run in 'planning' status (non-terminal, cancellable)."""
    result = await db.execute(select(User).where(User.email == _AUTH_USER["email"]))
    user = result.scalar_one()

    run = Run(
        user_id=user.id,
        repo_id=ready_repo.id,
        issue_text="Cancel me",
        status=RunStatus.planning,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


@pytest.mark.asyncio
async def test_cancel_run_transitions_to_cancelled(auth_client, planning_run, db):
    """POST /runs/{id}/cancel sets status=cancelled."""
    resp = await auth_client.post(f"{RUNS_URL}/{planning_run.id}/cancel")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"

    await db.refresh(planning_run)
    assert planning_run.status == RunStatus.cancelled


@pytest.mark.asyncio
async def test_cancel_run_requires_auth(client):
    """POST /runs/{id}/cancel without a token returns 401."""
    resp = await client.post(f"{RUNS_URL}/{uuid.uuid4()}/cancel")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_cancel_run_returns_404_for_other_user(auth_client, db, ready_repo):
    """POST /runs/{id}/cancel returns 404 for another user's run."""
    other = User(
        email="other_cancel@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$placeholder",
        name="Other",
    )
    db.add(other)
    await db.flush()
    other_repo = Repo(
        user_id=other.id,
        name="repo",
        clone_url="https://github.com/x/y.git",
        default_branch="main",
        status=RepoStatus.ready,
    )
    db.add(other_repo)
    await db.flush()
    other_run = Run(
        user_id=other.id,
        repo_id=other_repo.id,
        issue_text="Private",
        status=RunStatus.planning,
    )
    db.add(other_run)
    await db.commit()

    resp = await auth_client.post(f"{RUNS_URL}/{other_run.id}/cancel")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_run_returns_422_if_already_terminal(auth_client, awaiting_run, db):
    """POST /runs/{id}/cancel on an awaiting_approval run transitions to cancelled.
    Then a second cancel on the now-cancelled run returns 422.
    """
    # First cancel succeeds
    resp = await auth_client.post(f"{RUNS_URL}/{awaiting_run.id}/cancel")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"

    # Second cancel on already-terminal run returns 422
    resp2 = await auth_client.post(f"{RUNS_URL}/{awaiting_run.id}/cancel")
    assert resp2.status_code == 422


@pytest.mark.asyncio
async def test_cancel_run_returns_422_if_passed(auth_client, awaiting_run, db):
    """POST /runs/{id}/cancel returns 422 when the run is already passed."""
    # Approve first to set status=passed
    await auth_client.post(f"{RUNS_URL}/{awaiting_run.id}/approve")

    resp = await auth_client.post(f"{RUNS_URL}/{awaiting_run.id}/cancel")
    assert resp.status_code == 422
