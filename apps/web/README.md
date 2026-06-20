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
| `/login` | `app/(auth)/login/page.tsx` | Auth login form |
| `/register` | `app/(auth)/register/page.tsx` | Auth register form |
| `/runs/[id]` | `app/runs/[id]/page.tsx` | Live run viewer (real-time WebSocket) |
| `/benchmark` | `app/benchmark/page.tsx` | Placeholder — dashboard added Day 6 |

---

## Run viewer page (`/runs/[id]`)

The run viewer is the centrepiece of the portfolio demo. It shows a live
trace of the multi-agent pipeline as it executes.

### Architecture

```
page.tsx (server shell — awaits Next.js params Promise)
  └── RunPageClient (client component, wrapped in AuthGuard)
        ├── Initial REST fetch: GET /api/v1/runs/{id}
        ├── Opens WebSocket if run is not yet terminal
        └── REST re-fetch after each WS event for full step data
```

### What you see

| Section | When shown |
|---|---|
| Status badge (colour-coded) | Always |
| WS connection indicator (● Live / Reconnecting…) | While agent is running |
| Reviewer assessment + risk level | Status ≥ `awaiting_approval` |
| Diffs (multi-file, collapsible) | Status ≥ `awaiting_approval` |
| Approve / Reject panel | Status = `awaiting_approval` |
| Outcome banner (Passed / Rejected / Failed) | After terminal status |
| Agent step cards (expandable input/output/tool_calls) | As steps complete |
| Event timeline (terminal-log feel, auto-scrolls) | Always |

### Local test — watch a run live

```bash
# 1. Register and get a token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"dev@test.com","password":"testpass123"}' \
  | jq -r .access_token)

# 2. Create a repo and attach an issue
REPO_ID=$(curl -s -X POST http://localhost:8000/api/v1/repos \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://github.com/test/calc","name":"calc"}' \
  | jq -r .id)

RUN_ID=$(curl -s -X POST http://localhost:8000/api/v1/runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"repo_id\":\"$REPO_ID\",\"issue_text\":\"Add a subtract method\"}" \
  | jq -r .id)

# 3. Open the browser
open "http://localhost:3000/runs/$RUN_ID"
```

---

## WebSocket event protocol

**Endpoint:** `ws://{host}/api/v1/runs/{run_id}/ws`

**Authentication:** Send the JWT as the first text message after the connection
opens. Never pass it as a URL query parameter (it would appear in logs and
browser history).

```json
// First message sent by client
{ "token": "<JWT>" }
```

**Server close codes:**

| Code | Meaning |
|---|---|
| 4001 | Bad or expired token — do not reconnect |
| 4003 | Run belongs to a different user — do not reconnect |
| 1000 | Normal close (run reached terminal status) |

**Event shapes** (all messages from the server):

```jsonc
// Agent step completed (lightweight — re-fetch REST for full input/output)
{
  "type": "agent_step",
  "data": {
    "agent": "planner" | "coder" | "tester" | "reviewer",
    "step_index": 0,
    "latency_ms": 1234,
    "input_tokens": 100,
    "output_tokens": 50
  },
  "timestamp": "2026-06-20T12:00:00Z"
}

// Run status changed
{
  "type": "status_change",
  "data": { "status": "planning" | "coding" | "testing" | "reviewing" | "awaiting_approval" | "failed" },
  "timestamp": "2026-06-20T12:00:00Z"
}

// Run reached a terminal status — server closes the connection after this
{
  "type": "run_complete",
  "data": { "status": "awaiting_approval" | "passed" | "failed" | "rejected" },
  "timestamp": "2026-06-20T12:00:00Z"
}
```

**Reconnect strategy:** Max 3 attempts with delays of 1 s, 2 s, 4 s. No
reconnect on codes 4001 / 4003 or after `run_complete`.

---

## Components

| Component | Props | Description |
|---|---|---|
| `AgentStepCard` | `step: AgentStepOut` | Card with agent colour-coding (Planner=blue, Coder=purple, Tester=orange, Reviewer=green), latency + token badge, expandable input/output/tool_calls |
| `DiffViewer` | `diffs: DiffOut[]` | Multi-file unified diff with line-level colours (+ green, - red, @@ blue) |
| `LiveLogStream` | `entries: TimelineEntry[]` | Terminal-style event timeline; auto-scrolls only when user is already at bottom |

## Lib modules

| Module | Status |
|---|---|
| `lib/api-client.ts` | Full REST client — auth, runs, repos, approve/reject |
| `lib/ws-client.ts` | `RunWsClient` class — JWT auth handshake, typed events, reconnect with backoff |
| `lib/auth-context.tsx` | React auth context (JWT stored in localStorage) |
