# Foreman

Autonomous multi-agent software engineering platform. Give it a GitHub issue — four specialized AI agents plan, write, test, and review code in an isolated cloud environment. You approve the diff before anything merges.

**Live demo:** https://foreman-gcokyb54y-suyashi.vercel.app
**Source:** https://github.com/suyashisingh/Foreman

---

## What it does

Foreman takes a natural-language task description and a registered GitHub repository, then runs a four-agent pipeline entirely in the cloud:

1. **Planner** — searches the codebase via pgvector RAG, produces a step-by-step implementation plan
2. **Coder** — implements the plan with file-editing tool calls inside an isolated e2b sandbox. Never touches your machine.
3. **Tester** — runs pytest inside the same sandbox. On failure, sends the full output back to Coder for targeted fixes — up to 3 retry loops.
4. **Reviewer** — reads the final diff, rates risk (low/medium/high), writes a PR title and description, and halts the pipeline for your approval.

Nothing merges without an explicit approve click.

---

## Architecture

```
User → Next.js frontend
         ↓ REST + WebSocket
       FastAPI backend
         ↓ ARQ job queue
       Background worker
         ↓
       LangGraph state machine
       (Planner → Coder → Tester → Reviewer)
         ↓
       e2b cloud sandbox (isolated VM per run)
         ↓
       pgvector RAG (Voyage AI embeddings + Postgres)
```

**Stack:**

| Layer | Technology |
|-------|------------|
| Agents | LangGraph state machine · Gemini 2.5 Flash |
| Sandbox | e2b cloud (no local code execution) |
| RAG | pgvector · Voyage AI voyage-code-3 · Postgres |
| Backend | FastAPI · SQLAlchemy 2.0 · Alembic · ARQ |
| Realtime | WebSocket stream of agent events |
| Frontend | Next.js 16 · Tailwind 4 · shadcn/ui · Framer Motion |
| Infra | Render · Neon · Upstash · Vercel |

---

## Key design decisions

- **Sandboxed execution** — the Coder never runs code on your machine. e2b creates a fresh cloud VM per run and kills it after.
- **Human-in-the-loop review** — the Reviewer agent halts the pipeline at `awaiting_approval`. Nothing merges without an explicit click.
- **Async throughout** — ARQ workers process runs asynchronously so the API stays responsive while long agent chains run in the background.
- **WebSocket streaming** — status changes and agent step completions arrive in real time without polling.
- **No mocked tests** — the benchmark runner submits real tasks to the live stack and measures actual pass rates.

---

## Benchmark

Foreman is evaluated against a curated suite of real open-source issues (SWE-bench style). Results are measured automatically — not self-reported.

| Metric | Result |
|--------|--------|
| pass@1 | 100% (3/3 attempted) |
| pass@3 | 100% |
| Avg time-to-green | ~90s |
| Avg cost per task | ~$0.009 |

5 tasks were skipped due to Voyage AI free-tier rate limits during evaluation — not agent failures. The 3 tasks that ran all passed on the first attempt.

To run the full benchmark yourself:

```bash
# Register these repos in the dashboard first:
# https://github.com/pytest-dev/iniconfig.git
# https://github.com/python-humanize/humanize.git
# https://github.com/SethMMorton/natsort.git

cd apps/api
uv run python -m benchmark.runner \
  --email your@email.com \
  --password yourpassword
```

---

## Running locally

**Prerequisites:** Docker Desktop, Node.js 18+, Python 3.12+, uv

```bash
# 1. Clone
git clone https://github.com/suyashisingh/Foreman.git
cd Foreman

# 2. Start Postgres + Redis
cd infra && docker compose up -d && cd ..

# 3. Backend
cd apps/api
cp .env.example .env
# Fill in GEMINI_API_KEY, VOYAGE_API_KEY, E2B_API_KEY, JWT_SECRET_KEY
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# 4. Frontend (new terminal)
cd apps/web
cp .env.local.example .env.local
npm install
npm run dev

# 5. Open http://localhost:3000
```

**Environment variables needed:**

| Variable | Where to get it |
|----------|-----------------|
| `GEMINI_API_KEY` | aistudio.google.com |
| `VOYAGE_API_KEY` | dash.voyageai.com |
| `E2B_API_KEY` | e2b.dev |
| `JWT_SECRET_KEY` | any long random string |

---

## Tests

```bash
# Backend (184 tests)
cd apps/api && uv run pytest

# Frontend (90 tests)
cd apps/web && npm run test
```

CI runs on every push via GitHub Actions.

---

## Deployment

| Service | Platform |
|---------|----------|
| Frontend | Vercel |
| API + Worker | Render |
| Postgres | Neon |
| Redis | Upstash |

See `.env.production.example` for all required environment variables.

---

## Built by

Suyash Singh — portfolio project demonstrating end-to-end agentic systems engineering.

[GitHub](https://github.com/suyashisingh/Foreman) · [LinkedIn](https://linkedin.com/in/yourprofile) · [Live Demo](https://foreman-gcokyb54y-suyashi.vercel.app)
