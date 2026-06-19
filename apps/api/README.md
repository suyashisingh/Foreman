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
```

The defaults in `app/core/config.py` match the docker-compose defaults, so this
step is optional for local dev if you used the `.env.example` values unchanged.

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
