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

# Agent / LLM
GEMINI_API_KEY=<your Google AI Studio key from aistudio.google.com>
GEMINI_MODEL=gemini-3.5-flash
LLM_PROVIDER=gemini
MAX_CODER_RETRIES=2
MAX_CODER_TOOL_ITERATIONS=15
# e2b sandbox — get a key at https://e2b.dev
E2B_API_KEY=<your e2b key>
```

`JWT_SECRET_KEY`, `VOYAGE_API_KEY`, and `GEMINI_API_KEY` have **no defaults** — the
API will refuse to start if any is missing.

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

## 5. Run the ARQ worker

The ingestion pipeline runs in a separate worker process. Start it in a second
terminal after the API and infrastructure are running:

```bash
cd apps/api
uv run arq app.workers.settings.WorkerSettings
```

The worker connects to Redis (from `REDIS_URL`) and pulls jobs off the queue as
they arrive.  You can run multiple worker processes for parallelism; the default
`max_jobs` cap is 4 concurrent ingestion jobs per worker.

> **Troubleshooting:** If a code or `.env` change doesn't seem to take effect,
> restart the ARQ worker process — it holds Python state in memory and won't
> pick up changes until restarted.

---

## 6. Run tests

```bash
cd apps/api
uv run pytest -v
```

Tests mock both Postgres and Redis — no live services required to run the suite.

---

## 7. API endpoints

### Auth

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/auth/register` | Create an account; returns a JWT. |
| `POST` | `/api/v1/auth/login` | Obtain a JWT with email + password. |
| `GET`  | `/api/v1/auth/me` | Return the authenticated user's profile. |

### Repos

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/repos` | Register a repo for ingestion (returns **202 Accepted**). |
| `GET`  | `/api/v1/repos` | List all repos owned by the caller. |
| `GET`  | `/api/v1/repos/{id}` | Get one repo's details, status, and chunk count. |
| `GET`  | `/api/v1/repos/{id}/search` | Search a ready repo by natural-language query. |

All `/repos` endpoints require `Authorization: Bearer <token>`.

### Runs

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/runs` | Start an agent run on a ready repo (returns **202 Accepted**). |
| `GET`  | `/api/v1/runs` | List all runs owned by the caller. |
| `GET`  | `/api/v1/runs/{id}` | Get run detail including all `agent_steps`. |

All `/runs` endpoints require `Authorization: Bearer <token>`.

#### Request body for `POST /api/v1/runs`

```json
{
  "repo_id": "<uuid of a ready repo>",
  "issue_text": "Add a subtract method to the Calculator class"
}
```

Returns `422 Unprocessable Entity` if the repo is not yet `ready`, or `404` if it
belongs to another user.

#### Async agent flow

`POST /api/v1/runs` returns **202 Accepted** immediately.  The agent graph runs in
the ARQ worker through these status transitions:

```
pending → planning → awaiting_approval
                   ↘ failed  (on any error)
```

Poll `GET /api/v1/runs/{id}` to observe progress.  Each node in the graph appends
an `AgentStep` record containing token usage, latency, and structured I/O.

#### LLM provider abstraction

All agent nodes call `get_llm_client()` (in `app/agents/llm_client.py`) rather than
importing any provider SDK directly.  The factory reads `LLM_PROVIDER` from settings
and returns the matching `LLMClient` implementation.  Swapping to a different
provider requires only a new subclass in that file — no node logic changes.

Currently implemented: **Gemini** (`LLM_PROVIDER=gemini`) via the `google-genai` SDK.

#### Agent graph: Planner → Coder ↔ Tester retry loop

```
pending → planning → coding → testing → awaiting_approval
                     ↑    ↘ (retry)       ↘ failed  (retries exhausted or error)
                     └──────────────────────┘
```

**Planner** (step 0): retrieves the top-8 most relevant code chunks via pgvector
cosine search and calls Gemini with `response_schema=Plan` to produce a structured
implementation plan (list of `{file_path, action, description}` steps).

**Sandbox lifecycle**: a single [e2b](https://e2b.dev) sandbox is created **once**
in `execute_run` (tasks.py) before the graph starts and is killed in its `finally`
block after the graph completes — regardless of whether the run passes, fails, or
raises an exception.  This shared sandbox lets the Tester see the exact filesystem
state that the Coder left, and lets retries continue editing the same clone rather
than starting from scratch.

**Coder** (odd steps: 1, 3, 5 …): uses the shared sandbox to implement the plan.

*First invocation:*
1. Shallow-clones the target repo into `/home/user/repo`.
2. Sends the Plan + issue text to Gemini with three tools: `read_file`,
   `write_file`, `list_files`.
3. Executes each tool call against the real sandbox filesystem.
4. Repeats until the model stops calling tools **or** `MAX_CODER_TOOL_ITERATIONS`
   is reached (default 15) — graceful stop, never a hard crash.
5. Runs `git diff` to capture a unified diff of all changes.
6. Persists one `Diff` row per changed file (`approved=False`).

*Retry invocations:* skips the git clone (repo is already in the sandbox with
the previous edits in place).  The prompt includes the pytest failure output
from the previous Tester run so the model knows exactly what to fix.  Old `Diff`
rows are deleted and replaced with the cumulative diff.

**Tester** (even steps: 2, 4, 6 …): runs the repository's test suite.

1. Sets `run.status = testing`.
2. Runs `pip install pytest -q` (best-effort) then
   `python -m pytest /home/user/repo --tb=short -q`.
3. `exit_code == 0` → `test_passed = True`; any non-zero exit → `test_passed = False`.
4. Persists a `TestAttempt` row (attempt_number, passed, stdout, stderr, duration_ms).
5. Logs an `AgentStep` row for telemetry.
6. Returns `test_passed` and `test_output` (stdout + stderr) to the graph.

**Routing after Tester:**

| Condition | Next step |
|---|---|
| `test_passed = True` | END → `awaiting_approval` |
| `test_passed = False` AND `retry_count < MAX_CODER_RETRIES` | Coder (retry) |
| `test_passed = False` AND retries exhausted | END → `failed` |

`MAX_CODER_RETRIES = 2` (default) means up to 2 Coder retries (3 total Coder
invocations) before the run is marked `failed`.

New env vars:

| Variable | Default | Description |
|---|---|---|
| `E2B_API_KEY` | *(required)* | e2b sandbox key — get one at e2b.dev |
| `MAX_CODER_RETRIES` | `2` | Max Coder↔Tester retry iterations |
| `MAX_CODER_TOOL_ITERATIONS` | `15` | Max tool-call iterations within one Coder run |

---

### Repos

#### Async ingestion flow

`POST /api/v1/repos` returns **202 Accepted** immediately.  The heavy work runs
in the ARQ worker process through these status transitions:

```
pending → cloning → chunking → embedding → ready
                                          ↘ failed  (on any error)
```

Poll `GET /api/v1/repos/{id}` to observe the status.  When `status` is `"ready"`,
`chunk_count` reflects the number of indexed code symbols and search is available.
On `"failed"`, `error_message` contains a human-readable reason.

Pipeline steps:

1. **Clone** — shallow clone (`depth=1`) into `REPO_CLONE_DIR/<repo_id>` via GitPython.
2. **Chunk** — walk every `.py` file with `ast`; extract each `FunctionDef`,
   `AsyncFunctionDef`, and `ClassDef` (including class methods) as its own chunk.
   Files that fail to parse or have no symbols fall back to a whole-file chunk.
3. **Embed** — batch chunks in groups of 128, send to `voyage-code-3` via Voyage AI
   with `input_type="document"` for asymmetric retrieval.
4. **Store** — persist `RepoChunk` rows (file path, symbol name, content, 1024-dim
   embedding vector) to Postgres via pgvector.

#### Search endpoint

```
GET /api/v1/repos/{id}/search?q=<query>&top_k=5
```

Returns `422 Unprocessable Entity` if the repo is not yet `ready`.

On success, returns a JSON array of ranked results ordered by cosine similarity
(highest first):

```json
[
  {
    "file_path": "calculator.py",
    "symbol_name": "Calculator.add",
    "content": "def add(self, a, b):\n    return a + b",
    "similarity": 0.87
  }
]
```

`similarity` is `1 − cosine_distance`, ranging from `1.0` (identical direction)
to `-1.0` (opposite).  The query is embedded with `input_type="query"` for
asymmetric retrieval against the `"document"` indexed chunks.
