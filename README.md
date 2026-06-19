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
