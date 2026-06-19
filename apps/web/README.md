# Foreman Web

Next.js frontend for the Foreman autonomous agent platform.

**Stack choices:**
- **Framework:** Next.js 16 (App Router, TypeScript strict)
- **Styling:** Tailwind CSS **v4** — chosen as the latest stable release (out since January 2025).  
  v4 uses `@import "tailwindcss"` in CSS instead of `tailwind.config.js`, handled via `@tailwindcss/postcss`.
- **Component library:** shadcn/ui "base-nova" style (uses `@base-ui/react` instead of Radix UI)
- **Package manager:** **npm** — pnpm was not installed in this environment

---

## Prerequisites

- Node.js ≥ 22
- npm ≥ 10

---

## 1. Install dependencies

```bash
cd apps/web
npm install
```

---

## 2. Configure environment

```bash
cp .env.local.example .env.local
```

Edit `.env.local` if the backend runs on a different host/port:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

---

## 3. Start the dev server

```bash
npm run dev
# → http://localhost:3000
```

The FastAPI backend (from `apps/api`) must be running for the `/ready` endpoint
to return healthy. Start it with:

```bash
# From infra/ — starts Postgres + Redis
docker compose up -d

# From apps/api/ — starts FastAPI
uv run uvicorn app.main:app --reload --port 8000
```

---

## 4. Production build

```bash
npm run build   # type-checks + compiles
npm run start   # serves the production build
```

`next build` runs the TypeScript compiler and will fail on any type error.

---

## 5. Run tests

```bash
npm test             # vitest run (single pass)
npm run test:watch   # vitest (watch mode)
```

Tests use Vitest + React Testing Library + jsdom. No live services needed.

---

## Route structure

| Route | File | Notes |
|---|---|---|
| `/` | `app/page.tsx` | Landing / dashboard |
| `/login` | `app/(auth)/login/page.tsx` | Form UI only — no backend (Day 2) |
| `/register` | `app/(auth)/register/page.tsx` | Form UI only — no backend (Day 2) |
| `/runs/[id]` | `app/runs/[id]/page.tsx` | Placeholder — live trace added Day 5 |
| `/benchmark` | `app/benchmark/page.tsx` | Placeholder — dashboard added Day 6 |

## Stub components

| Component | Props defined | Implementation |
|---|---|---|
| `AgentStepCard` | ✓ (mirrors `agent_steps` schema) | Day 5 |
| `DiffViewer` | ✓ (filePath, patch, approved) | Day 5 |
| `LiveLogStream` | ✓ (lines: LogLine[]) | Day 5 |

## Lib modules

| Module | Status |
|---|---|
| `lib/api-client.ts` | `getHealth()` wired; other endpoints added per day |
| `lib/ws-client.ts` | Types + interface defined; implementation Day 5 |
