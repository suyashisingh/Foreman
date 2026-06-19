# Foreman API

FastAPI backend for the Foreman autonomous agent platform.

**Runtime:** Python 3.12 · **Package manager:** uv · **Server:** Uvicorn

---

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (`pip install uv` or `irm https://astral.sh/uv/install.ps1 | iex` on Windows)
- Docker + Docker Compose (for Postgres and Redis)

---

## 1. Start infrastructure

```bash
# From the repo root
cd infra
cp .env.example .env          # edit values if you like — defaults work for local dev
docker compose up -d

# Confirm both services are healthy
docker compose ps
```

Expected output shows `postgres` and `redis` both reporting `healthy`.

To verify pgvector was enabled automatically:

```bash
docker compose exec postgres psql -U foreman -d foreman -c "\dx vector"
```

You should see the `vector` extension listed. The `infra/init-scripts/01-vector.sql`
script runs on first container start and creates it automatically — no manual step needed.

---

## 2. Install API dependencies

```bash
cd apps/api
uv sync                       # installs all deps including dev extras into .venv
```

---

## 3. Configure environment

Create `apps/api/.env` (or export variables in your shell):

```dotenv
DATABASE_URL=postgresql+asyncpg://foreman:foreman_secret@localhost:5434/foreman
REDIS_URL=redis://localhost:6380
ENVIRONMENT=development
LOG_LEVEL=INFO
JWT_SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
VOYAGE_API_KEY=<your Voyage AI key from dash.voyageai.com>
VOYAGE_MODEL=voyage-code-3
REPO_CLONE_DIR=/tmp/foreman-repos
```

`JWT_SECRET_KEY` and `VOYAGE_API_KEY` have **no defaults** — the API will refuse
to start if either is missing.

---

## 4. Run the API

```bash
cd apps/api
uv run uvicorn app.main:app --reload --port 8000
```

- Liveness:   <http://localhost:8000/health>
- Readiness:  <http://localhost:8000/ready>
- Docs:       <http://localhost:8000/docs>

---

## 5. Run tests

```bash
cd apps/api
uv run pytest -v
```

Tests mock both Postgres and Redis — no live services required to run the suite.

---

## 6. API endpoints

### Auth

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/auth/register` | Create an account; returns a JWT. |
| `POST` | `/api/v1/auth/login` | Obtain a JWT with email + password. |
| `GET`  | `/api/v1/auth/me` | Return the authenticated user's profile. |

### Repos

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/repos` | Register a repo: clone → chunk → embed → store. |
| `GET`  | `/api/v1/repos` | List all repos owned by the caller. |
| `GET`  | `/api/v1/repos/{id}` | Get one repo's details and chunk count. |

All `/repos` endpoints require `Authorization: Bearer <token>`.

#### Ingestion pipeline

`POST /api/v1/repos` runs synchronously in the request handler (ARQ background
task coming next):

1. **Clone** — shallow clone (`depth=1`) into `REPO_CLONE_DIR/<repo_id>` via GitPython.
2. **Chunk** — walk every `.py` file with `ast`; extract each `FunctionDef`,
   `AsyncFunctionDef`, and `ClassDef` (including class methods) as its own chunk.
   Files that fail to parse or have no symbols fall back to a whole-file chunk.
3. **Embed** — batch chunks in groups of 128, send to `voyage-code-3` via Voyage AI.
4. **Store** — persist `RepoChunk` rows (file path, symbol name, content, 1024-dim
   embedding vector) to Postgres via pgvector.

On failure, the `Repo` row remains in the database with `status=failed` and an
`error_message` for debugging.
