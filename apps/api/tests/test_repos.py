"""Tests for chunking logic and /api/v1/repos HTTP endpoints.

The POST /repos endpoint now returns 202 immediately and enqueues an ARQ job;
it no longer runs the pipeline synchronously.  Pipeline execution is tested in
test_workers.py.
"""

import ast
import textwrap
from pathlib import Path

import pytest

from app.retrieval.chunking import _extract_symbols, chunk_repo

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPOS_URL = "/api/v1/repos"

# ---------------------------------------------------------------------------
# Unit tests: chunking logic
# ---------------------------------------------------------------------------


def test_chunking_extracts_class_and_methods():
    """Class-level and method-level chunks are both extracted."""
    source = textwrap.dedent("""\
        class MyClass:
            def method_a(self) -> None:
                pass

            def method_b(self) -> int:
                return 42

        def standalone(x: int) -> str:
            return str(x)
    """)
    tree = ast.parse(source)
    chunks = _extract_symbols(source, tree, "test.py")
    names = {c.symbol_name for c in chunks}

    assert "MyClass" in names
    assert "MyClass.method_a" in names
    assert "MyClass.method_b" in names
    assert "standalone" in names
    assert len(chunks) == 4


def test_chunking_skips_unparseable_file(tmp_path: Path):
    """Files with SyntaxError fall back to a whole-file chunk."""
    bad = tmp_path / "bad.py"
    bad.write_text("def broken(\n")  # deliberate syntax error
    chunks = chunk_repo(tmp_path)
    assert len(chunks) == 1
    assert chunks[0].symbol_name is None
    assert chunks[0].file_path == "bad.py"


def test_chunking_whole_file_fallback_for_no_symbols(tmp_path: Path):
    """Files with only imports produce one whole-file chunk."""
    init = tmp_path / "__init__.py"
    init.write_text("from .foo import Bar\n")
    chunks = chunk_repo(tmp_path)
    assert len(chunks) == 1
    assert chunks[0].symbol_name is None


def test_chunking_skips_empty_file(tmp_path: Path):
    """Empty files produce no chunks."""
    (tmp_path / "empty.py").write_text("")
    chunks = chunk_repo(tmp_path)
    assert chunks == []


def test_chunking_skips_venv_dir(tmp_path: Path):
    """Files under venv/ are excluded."""
    venv_dir = tmp_path / "venv" / "lib"
    venv_dir.mkdir(parents=True)
    (venv_dir / "helper.py").write_text("def helper(): pass\n")
    (tmp_path / "real.py").write_text("def real(): pass\n")
    chunks = chunk_repo(tmp_path)
    assert all("venv" not in c.file_path for c in chunks)
    assert any(c.file_path == "real.py" for c in chunks)


def test_chunk_repo_fake_dir(fake_repo_dir: Path):
    """chunk_repo on the fake fixture yields expected symbols."""
    chunks = chunk_repo(fake_repo_dir)
    names = {c.symbol_name for c in chunks}
    assert "Calculator" in names
    assert "Calculator.add" in names
    assert "Calculator.subtract" in names
    assert "greet" in names
    assert "get_env" in names


# ---------------------------------------------------------------------------
# Endpoint tests: auth guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_repos_requires_auth(client):
    """POST /repos without a token returns 401."""
    resp = await client.post(REPOS_URL, json={"name": "x", "clone_url": "http://x"})
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_repos_requires_auth(client):
    """GET /repos without a token returns 401."""
    resp = await client.get(REPOS_URL)
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Endpoint tests: GET list and detail against in-flight repos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_repos_lists_pending_repo(auth_client, mock_arq_pool):
    """A repo in status=pending is visible in GET /repos immediately."""
    resp = await auth_client.post(
        REPOS_URL,
        json={"name": "pending-repo", "clone_url": "https://github.com/x/y.git"},
    )
    assert resp.status_code == 202

    list_resp = await auth_client.get(REPOS_URL)
    assert list_resp.status_code == 200
    names = [r["name"] for r in list_resp.json()]
    assert "pending-repo" in names


@pytest.mark.asyncio
async def test_get_repo_detail_works_for_pending(auth_client, mock_arq_pool):
    """GET /repos/{id} returns correct data for a repo still being ingested."""
    post_resp = await auth_client.post(
        REPOS_URL,
        json={"name": "in-flight", "clone_url": "https://github.com/x/y.git"},
    )
    assert post_resp.status_code == 202
    repo_id = post_resp.json()["id"]

    get_resp = await auth_client.get(f"{REPOS_URL}/{repo_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["status"] == "pending"
    assert body["chunk_count"] == 0
    assert body["error_message"] is None


@pytest.mark.asyncio
async def test_post_repos_only_name_and_clone_url_defaults_branch(
    auth_client, mock_arq_pool
):
    """POST /repos with only name + clone_url (no default_branch) returns 202
    and the created repo's default_branch is 'main'."""
    resp = await auth_client.post(
        REPOS_URL,
        json={
            "name": "iniconfig",
            "clone_url": "https://github.com/pytest-dev/iniconfig.git",
        },
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["name"] == "iniconfig"
    assert body["clone_url"] == "https://github.com/pytest-dev/iniconfig.git"
    assert body["default_branch"] == "main"
    assert body["status"] == "pending"


@pytest.mark.asyncio
async def test_post_repos_rejects_missing_clone_url(auth_client, mock_arq_pool):
    """POST /repos without clone_url returns 422 (FastAPI validation error)."""
    resp = await auth_client.post(REPOS_URL, json={"name": "missing-url"})
    assert resp.status_code == 422
    body = resp.json()
    # FastAPI returns detail as a list of validation error objects
    assert isinstance(body["detail"], list)
    assert any(e["loc"][-1] == "clone_url" for e in body["detail"])


@pytest.mark.asyncio
async def test_search_requires_ready_status(auth_client, mock_arq_pool):
    """GET /repos/{id}/search returns 422 if the repo is not ready."""
    post_resp = await auth_client.post(
        REPOS_URL,
        json={"name": "not-ready", "clone_url": "https://github.com/x/y.git"},
    )
    repo_id = post_resp.json()["id"]

    search_resp = await auth_client.get(
        f"{REPOS_URL}/{repo_id}/search", params={"q": "hello"}
    )
    assert search_resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /repos/{id} — owner deletes, 404 for another user's repo, 401 unauthed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_repo_204_owner(auth_client, mock_arq_pool):
    """Owner can delete their own repo; endpoint returns 204 No Content."""
    post_resp = await auth_client.post(
        REPOS_URL,
        json={"name": "to-delete", "clone_url": "https://github.com/x/y.git"},
    )
    assert post_resp.status_code == 202
    repo_id = post_resp.json()["id"]

    del_resp = await auth_client.delete(f"{REPOS_URL}/{repo_id}")
    assert del_resp.status_code == 204

    # Confirm the repo is gone
    get_resp = await auth_client.get(f"{REPOS_URL}/{repo_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_repo_404_other_user(
    auth_client, other_auth_client, mock_arq_pool
):
    """Another user's repo returns 404 from DELETE (same as GET isolation)."""
    post_resp = await auth_client.post(
        REPOS_URL,
        json={"name": "private-repo", "clone_url": "https://github.com/x/y.git"},
    )
    repo_id = post_resp.json()["id"]

    del_resp = await other_auth_client.delete(f"{REPOS_URL}/{repo_id}")
    assert del_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_repo_401_no_auth(client):
    """DELETE without a token returns 401 regardless of resource existence."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    del_resp = await client.delete(f"{REPOS_URL}/{fake_id}")
    assert del_resp.status_code in (401, 403)
