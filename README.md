# Foreman

Autonomous multi-agent software engineering platform.

**Stack:** Next.js 15 · FastAPI · PostgreSQL + pgvector · Redis + ARQ · LangGraph · e2b sandboxes

## Monorepo layout

```
apps/web/       Next.js frontend (scaffolded in a later task)
apps/api/       FastAPI backend
infra/          Docker Compose + Dockerfiles for local dev
benchmark/      Evaluation harness (scaffolded in a later task)
.github/        CI workflows (added in a later task)
```

## Quick start

See `apps/api/README.md` for API setup and `infra/` for Docker Compose details.

## Running the full benchmark

The benchmark suite covers 8 curated tasks across three small Python repos.
Register all three repos on the Dashboard before running the CLI — the runner
will reuse any repos already in ready state.

**Required repos:**

| Repo | URL |
|------|-----|
| iniconfig | `https://github.com/pytest-dev/iniconfig.git` |
| humanize | `https://github.com/jmoiron/humanize.git` |
| natsort | `https://github.com/SethMMorton/natsort.git` |

**Run the CLI** (after all three repos show "Ready" status):

```bash
cd apps/api
uv run python -m benchmark.runner \
  --email your@email.com \
  --password yourpassword
```

Results are scoped per user — navigate to `/benchmark` in the app to see your
results. The public landing page shows a global aggregate across all users.
