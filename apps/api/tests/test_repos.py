"""Tests for repo registration, chunking logic, and /api/v1/repos endpoints.

Network calls (GitPython clone, Voyage API) are fully mocked so no live
services are needed beyond the test Postgres instance wired up in conftest.py.
"""

import ast
import textwrap
from pathlib import Path

import pytest
import pytest_asyncio

from app.retrieval.chunking import _extract_symbols, chunk_repo

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
REPOS_URL = "/api/v1/repos"

_USER = {"email": "repouser@example.com", "password": "repopassword1", "name": "Repo"}

# Fake 1024-dim embeddings (matches voyage-code-3 output dimension).
_FAKE_EMBED_DIM = 1024


def _fake_embeddings(n: int) -> list[list[float]]:
    return [[0.1] * _FAKE_EMBED_DIM for _ in range(n)]


@pytest_asyncio.fixture
async def auth_client(client):
    """Return an AsyncClient pre-loaded with a valid Bearer token."""
    reg = await client.post(REGISTER_URL, json=_USER)
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture
def fake_repo_dir(tmp_path: Path) -> Path:
    """A tiny fake cloned repo with two Python source files."""
    (tmp_path / "calculator.py").write_text(
        textwrap.dedent("""\
            class Calculator:
                \"\"\"A simple calculator.\"\"\"

                def add(self, a: int, b: int) -> int:
                    return a + b

                def subtract(self, a: int, b: int) -> int:
                    return a - b

            def greet(name: str) -> str:
                return f"Hello, {name}!"
        """)
    )
    (tmp_path / "utils.py").write_text(
        textwrap.dedent("""\
            import os

            def get_env(key: str, default: str = "") -> str:
                return os.environ.get(key, default)
        """)
    )
    return tmp_path


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
# Endpoint tests: happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_repo_success(auth_client, fake_repo_dir, mocker):
    """POST /repos clones, chunks, embeds, and returns a ready repo."""
    expected_chunks = chunk_repo(fake_repo_dir)

    mocker.patch(
        "app.routers.repos.clone_repo",
        return_value=fake_repo_dir,
    )
    mocker.patch(
        "app.routers.repos.remove_clone",
    )
    mocker.patch(
        "app.routers.repos.embed_texts",
        return_value=_fake_embeddings(len(expected_chunks)),
    )

    resp = await auth_client.post(
        REPOS_URL,
        json={
            "name": "my-repo",
            "clone_url": "https://github.com/example/repo.git",
            "default_branch": "main",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    assert body["name"] == "my-repo"
    assert body["chunk_count"] == len(expected_chunks)
    assert body["error_message"] is None


@pytest.mark.asyncio
async def test_register_repo_stores_chunks_in_db(auth_client, fake_repo_dir, mocker):
    """Chunk rows are actually persisted to the database."""
    expected_chunks = chunk_repo(fake_repo_dir)

    mocker.patch("app.routers.repos.clone_repo", return_value=fake_repo_dir)
    mocker.patch("app.routers.repos.remove_clone")
    mocker.patch(
        "app.routers.repos.embed_texts",
        return_value=_fake_embeddings(len(expected_chunks)),
    )

    post_resp = await auth_client.post(
        REPOS_URL,
        json={"name": "stored-repo", "clone_url": "https://github.com/x/y.git"},
    )
    assert post_resp.status_code == 201
    repo_id = post_resp.json()["id"]

    get_resp = await auth_client.get(f"{REPOS_URL}/{repo_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["chunk_count"] == len(expected_chunks)


@pytest.mark.asyncio
async def test_list_repos_returns_registered_repo(auth_client, fake_repo_dir, mocker):
    """GET /repos returns the repo after it has been registered."""
    chunks = chunk_repo(fake_repo_dir)
    mocker.patch("app.routers.repos.clone_repo", return_value=fake_repo_dir)
    mocker.patch("app.routers.repos.remove_clone")
    mocker.patch(
        "app.routers.repos.embed_texts", return_value=_fake_embeddings(len(chunks))
    )

    await auth_client.post(
        REPOS_URL,
        json={"name": "listed-repo", "clone_url": "https://github.com/a/b.git"},
    )

    list_resp = await auth_client.get(REPOS_URL)
    assert list_resp.status_code == 200
    names = [r["name"] for r in list_resp.json()]
    assert "listed-repo" in names


# ---------------------------------------------------------------------------
# Endpoint tests: failure path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clone_failure_sets_repo_failed(auth_client, mocker):
    """A clone error returns 422 and leaves the repo with status=failed."""
    from app.retrieval.cloning import CloneError

    mocker.patch(
        "app.routers.repos.clone_repo",
        side_effect=CloneError("invalid URL"),
    )
    mocker.patch("app.routers.repos.remove_clone")

    resp = await auth_client.post(
        REPOS_URL,
        json={"name": "bad-repo", "clone_url": "not-a-url"},
    )
    assert resp.status_code == 422
    assert "clone" in resp.json()["detail"].lower()

    # The repo row must exist with status=failed.
    list_resp = await auth_client.get(REPOS_URL)
    repos = list_resp.json()
    bad = next((r for r in repos if r["name"] == "bad-repo"), None)
    assert bad is not None
    assert bad["status"] == "failed"
    assert bad["error_message"] is not None
