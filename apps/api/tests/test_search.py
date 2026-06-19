"""Tests for the cosine-similarity search function and search endpoint.

Vector arithmetic is used to construct embeddings where the expected ranking
is derivable by inspection, making assertions concrete rather than probabilistic.
"""

import uuid

import pytest
import pytest_asyncio

from app.db.models import Repo, RepoChunk, RepoStatus, User
from app.retrieval.search import ChunkSearchResult, search_repo_chunks

REPOS_URL = "/api/v1/repos"

_DIM = 1024

# Unit vectors for three orthogonal directions (first two dims only).
_VEC_A = [1.0] + [0.0] * (_DIM - 1)  # cosine sim to query [1, 0, …]: 1.0
_VEC_B = [0.0, 1.0] + [0.0] * (_DIM - 2)  # cosine sim: 0.0
_VEC_C = [-1.0] + [0.0] * (_DIM - 1)  # cosine sim: -1.0

_QUERY_VEC = _VEC_A  # query aligned with chunk A


# ---------------------------------------------------------------------------
# Fixtures: seed repo + chunks directly
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seeded(db) -> tuple[uuid.UUID, list[str]]:
    """Seed a User, Repo, and 3 RepoChunk rows with known unit embeddings."""
    user = User(
        email="search-test@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$placeholder",
        name="Search",
    )
    db.add(user)
    await db.flush()

    repo = Repo(
        user_id=user.id,
        name="search-repo",
        clone_url="https://github.com/example/repo.git",
        status=RepoStatus.ready,
    )
    db.add(repo)
    await db.flush()

    chunks = [
        ("ChunkA", _VEC_A),
        ("ChunkB", _VEC_B),
        ("ChunkC", _VEC_C),
    ]
    for symbol, vec in chunks:
        db.add(
            RepoChunk(
                repo_id=repo.id,
                file_path="test.py",
                symbol_name=symbol,
                content=f"def {symbol}(): pass",
                embedding=vec,
            )
        )
    await db.commit()
    return repo.id, [s for s, _ in chunks]


# ---------------------------------------------------------------------------
# Unit tests: search_repo_chunks function
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_orders_by_cosine_similarity(seeded, db, mocker):
    """Results are ordered from most to least similar."""
    repo_id, _ = seeded

    mocker.patch(
        "app.retrieval.search.embed_texts",
        return_value=[_QUERY_VEC],
    )

    results = await search_repo_chunks(db, repo_id, "some query", top_k=3)

    assert len(results) == 3
    assert results[0].symbol_name == "ChunkA"
    assert results[1].symbol_name == "ChunkB"
    assert results[2].symbol_name == "ChunkC"


@pytest.mark.asyncio
async def test_search_similarity_scores_are_correct(seeded, db, mocker):
    """Similarity scores are 1.0, 0.0, and -1.0 for our unit vectors."""
    repo_id, _ = seeded

    mocker.patch(
        "app.retrieval.search.embed_texts",
        return_value=[_QUERY_VEC],
    )

    results = await search_repo_chunks(db, repo_id, "q", top_k=3)

    assert abs(results[0].similarity - 1.0) < 1e-4
    assert abs(results[1].similarity - 0.0) < 1e-4
    assert abs(results[2].similarity - (-1.0)) < 1e-4


@pytest.mark.asyncio
async def test_search_respects_top_k(seeded, db, mocker):
    """top_k limits the number of returned results."""
    repo_id, _ = seeded

    mocker.patch("app.retrieval.search.embed_texts", return_value=[_QUERY_VEC])

    results = await search_repo_chunks(db, repo_id, "q", top_k=1)
    assert len(results) == 1
    assert results[0].symbol_name == "ChunkA"


@pytest.mark.asyncio
async def test_search_returns_chunk_search_result_objects(seeded, db, mocker):
    """Each returned item is a ChunkSearchResult with all fields populated."""
    repo_id, _ = seeded

    mocker.patch("app.retrieval.search.embed_texts", return_value=[_QUERY_VEC])

    results = await search_repo_chunks(db, repo_id, "q", top_k=1)
    r = results[0]

    assert isinstance(r, ChunkSearchResult)
    assert r.file_path == "test.py"
    assert r.symbol_name is not None
    assert r.content != ""
    assert isinstance(r.similarity, float)


@pytest.mark.asyncio
async def test_search_excludes_chunks_without_embedding(db, mocker):
    """Chunks with embedding=NULL are excluded from results."""
    user = User(
        email="nullvec@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$placeholder",
        name="NullVec",
    )
    db.add(user)
    await db.flush()

    repo = Repo(
        user_id=user.id,
        name="null-embed-repo",
        clone_url="http://x",
        status=RepoStatus.ready,
    )
    db.add(repo)
    await db.flush()

    db.add(
        RepoChunk(
            repo_id=repo.id,
            file_path="f.py",
            symbol_name="fn",
            content="def fn(): pass",
            embedding=None,  # no embedding
        )
    )
    await db.commit()

    mocker.patch("app.retrieval.search.embed_texts", return_value=[_QUERY_VEC])

    results = await search_repo_chunks(db, repo.id, "q", top_k=5)
    assert results == []


# ---------------------------------------------------------------------------
# Endpoint tests: GET /api/v1/repos/{id}/search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_endpoint_requires_auth(client, seeded):
    """GET /repos/{id}/search without a token returns 401."""
    repo_id, _ = seeded
    resp = await client.get(f"{REPOS_URL}/{repo_id}/search", params={"q": "test"})
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_search_endpoint_returns_ranked_results(auth_client, mocker, db):
    """GET /repos/{id}/search returns results ranked by similarity."""
    # We need a repo owned by the authenticated user, so use POST /repos to
    # create one, then manually flip it to ready and seed chunks.
    from app.db.models import Repo, RepoChunk, RepoStatus

    post_resp = await auth_client.post(
        REPOS_URL,
        json={"name": "search-e2e", "clone_url": "https://github.com/x/y.git"},
    )
    repo_id = uuid.UUID(post_resp.json()["id"])

    # Flip to ready and seed chunks directly (bypassing the ARQ worker).
    repo = await db.get(Repo, repo_id)
    assert repo is not None
    repo.status = RepoStatus.ready
    for symbol, vec in [("ChunkA", _VEC_A), ("ChunkB", _VEC_B)]:
        db.add(
            RepoChunk(
                repo_id=repo_id,
                file_path="f.py",
                symbol_name=symbol,
                content=f"def {symbol}(): pass",
                embedding=vec,
            )
        )
    await db.commit()

    mocker.patch("app.retrieval.search.embed_texts", return_value=[_QUERY_VEC])

    resp = await auth_client.get(
        f"{REPOS_URL}/{repo_id}/search", params={"q": "query", "top_k": 2}
    )
    assert resp.status_code == 200, resp.text
    results = resp.json()
    assert len(results) == 2
    assert results[0]["symbol_name"] == "ChunkA"
    assert results[0]["similarity"] > results[1]["similarity"]
