import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const AGENTS = [
  {
    name: "Planner",
    role: "Reads the issue, finds relevant code",
    detail:
      "Uses pgvector to search a semantic index of the repository's source files. Returns a step-by-step implementation plan — which files to touch and why.",
  },
  {
    name: "Coder",
    role: "Writes the code",
    detail:
      "Receives the plan and iteratively edits files inside an isolated e2b cloud sandbox using read_file / write_file tool calls. Never touches your local machine.",
  },
  {
    name: "Tester",
    role: "Runs pytest and feeds failure back",
    detail:
      "Executes the test suite inside the same sandbox. On failure, the full pytest output goes back to Coder as context — up to 3 retry loops before the run is marked failed.",
  },
  {
    name: "Reviewer",
    role: "Assesses risk, writes the PR description",
    detail:
      "Reads the final diff, rates risk (low / medium / high), writes a PR title and description. Presents everything for your approval before anything merges.",
  },
];

const STACK = [
  { layer: "Agents", value: "LangGraph state machine · Gemini 2.5 Flash" },
  { layer: "Sandbox", value: "e2b cloud sandboxes (no local code execution)" },
  { layer: "RAG", value: "pgvector · Voyage AI embeddings · Postgres" },
  { layer: "Backend", value: "FastAPI · SQLAlchemy 2.0 · Alembic · ARQ" },
  { layer: "Realtime", value: "WebSocket stream of agent events" },
  { layer: "Frontend", value: "Next.js 16 · Tailwind 4 · shadcn/ui" },
];

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 space-y-12">
      {/* Header */}
      <section className="space-y-3">
        <h1 className="text-3xl font-bold tracking-tight">About Foreman</h1>
        <p className="text-lg text-muted-foreground">
          Foreman is an autonomous software engineering platform. Give it a
          GitHub issue or feature description — it plans, codes, tests, and
          reviews changes in an isolated cloud environment, then asks for your
          approval before anything merges.
        </p>
        <p className="text-sm text-muted-foreground">
          Built as a portfolio project to demonstrate end-to-end agentic
          systems engineering: multi-agent orchestration, vector RAG, live
          WebSocket streaming, and human-in-the-loop review.
        </p>
      </section>

      {/* How the agents work */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold tracking-tight">The agents</h2>
        <p className="text-muted-foreground text-sm">
          Four specialised agents run in sequence inside a LangGraph graph.
          Each one has a single responsibility — and they share state through a
          typed <code className="font-mono text-xs bg-muted px-1 rounded">AgentState</code> dict.
        </p>
        <div className="space-y-3">
          {AGENTS.map(({ name, role, detail }, i) => (
            <div
              key={name}
              className="flex gap-4 p-4 rounded-lg border border-border"
            >
              <span className="shrink-0 text-xs font-mono text-muted-foreground bg-muted rounded px-1.5 py-0.5 h-fit mt-0.5">
                {i + 1}
              </span>
              <div className="space-y-1">
                <p className="text-sm font-semibold">
                  {name}{" "}
                  <span className="font-normal text-muted-foreground">
                    — {role}
                  </span>
                </p>
                <p className="text-sm text-muted-foreground">{detail}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Self-correction loop */}
      <section className="space-y-3">
        <h2 className="text-xl font-semibold tracking-tight">
          Self-correction loop
        </h2>
        <p className="text-sm text-muted-foreground">
          When Tester finds failures, it doesn&apos;t give up — it sends the
          full pytest output back to Coder as context and retries (up to 3
          attempts). The sandbox persists between loops, so prior edits are
          still in place and the model can read them before making targeted
          fixes. This is what enables pass@3 to be meaningfully higher than
          pass@1 on harder tasks.
        </p>
      </section>

      {/* Stack table */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold tracking-tight">Stack</h2>
        <div className="rounded-lg border border-border overflow-hidden">
          {STACK.map(({ layer, value }, i) => (
            <div
              key={layer}
              className={`flex gap-4 px-4 py-3 text-sm ${
                i < STACK.length - 1 ? "border-b border-border" : ""
              }`}
            >
              <span className="w-24 shrink-0 text-muted-foreground font-medium">
                {layer}
              </span>
              <span>{value}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Design decisions */}
      <section className="space-y-3">
        <h2 className="text-xl font-semibold tracking-tight">
          Key design decisions
        </h2>
        <ul className="space-y-2 text-sm text-muted-foreground list-none">
          {[
            "Sandboxed execution — the Coder never runs code on your machine. e2b creates a fresh cloud VM per run and kills it after.",
            "Human-in-the-loop review — the Reviewer agent halts the pipeline at awaiting_approval. Nothing merges without an explicit approve click.",
            "Async throughout — ARQ workers process runs asynchronously so the API stays responsive while long agent chains run in the background.",
            "WebSocket streaming — status changes and agent step completions arrive in real time without polling.",
            "No mocked tests for the core pipeline — the benchmark runner submits real tasks to the live stack and measures actual pass rates.",
          ].map((point) => (
            <li key={point} className="flex gap-2">
              <span className="text-muted-foreground/40 mt-0.5">—</span>
              <span>{point}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* CTA */}
      <div className="flex gap-3 pt-2">
        <Link href="/benchmark" className={cn(buttonVariants())}>
          See benchmark results
        </Link>
        <a
          href="https://github.com/suyashisingh/Foreman"
          target="_blank"
          rel="noopener noreferrer"
          className={cn(buttonVariants({ variant: "outline" }))}
        >
          View source
        </a>
      </div>
    </div>
  );
}
