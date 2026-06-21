import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { BenchmarkStats } from "@/components/benchmark-stats";
import { cn } from "@/lib/utils";
import { Bot, BarChart3, Radio } from "lucide-react";
import Link from "next/link";

const FEATURES = [
  {
    Icon: Bot,
    title: "Plan & Execute",
    description:
      "LangGraph agents decompose issues into plans, implement them in isolated e2b sandboxes, then iterate on test failures — no human in the loop until review.",
  },
  {
    Icon: Radio,
    title: "Live Trace",
    description:
      "Stream agent steps, tool calls, and diffs in real time over WebSocket. Watch the model think, write, and self-correct.",
  },
  {
    Icon: BarChart3,
    title: "Benchmark",
    description:
      "Evaluated against real open-source repositories. pass@1 and pass@3 rates measured from actual test runs — not self-reported.",
  },
] as const;

export default function HomePage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-12 space-y-16">
      {/* Hero */}
      <section className="space-y-5">
        <div className="flex items-center gap-3">
          <h1 className="text-4xl font-bold tracking-tight">Foreman</h1>
          <Badge variant="secondary">Alpha</Badge>
        </div>
        <p className="text-lg text-muted-foreground max-w-xl">
          Autonomous multi-agent software engineering platform. Describe a task,
          watch agents plan, code, and verify in real time.
        </p>

        {/* Live benchmark numbers — fetched client-side from the public endpoint */}
        <BenchmarkStats />

        <div className="flex gap-3 flex-wrap">
          {/* Primary CTA */}
          <Link href="/runs" className={cn(buttonVariants())}>
            View Runs
          </Link>
          {/* Secondary CTA */}
          <Link
            href="/benchmark"
            className={cn(buttonVariants({ variant: "outline" }))}
          >
            Benchmark Results
          </Link>
        </div>
      </section>

      {/* Feature cards */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {FEATURES.map(({ Icon, title, description }) => (
          <Card
            key={title}
            className="group hover:shadow-md transition-shadow duration-200"
          >
            <CardHeader>
              <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-md bg-primary/10">
                <Icon size={16} className="text-primary" />
              </div>
              <CardTitle className="text-base">{title}</CardTitle>
              <CardDescription>{description}</CardDescription>
            </CardHeader>
            <CardContent />
          </Card>
        ))}
      </section>

      {/* How it works */}
      <section className="space-y-5">
        <div className="space-y-1">
          <h2 className="text-xl font-semibold tracking-tight">How it works</h2>
          <p className="text-sm text-muted-foreground">
            Four specialised agents run in sequence. Each has a single job.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {[
            {
              n: "1",
              name: "Planner",
              desc: "Retrieves relevant code via pgvector RAG and produces a step-by-step implementation plan.",
            },
            {
              n: "2",
              name: "Coder",
              desc: "Implements the plan with file-editing tool calls inside an isolated e2b cloud sandbox.",
            },
            {
              n: "3",
              name: "Tester",
              desc: "Runs pytest. On failure, sends output back to Coder for up to 3 self-correction loops.",
            },
            {
              n: "4",
              name: "Reviewer",
              desc: "Assesses risk, writes the PR description, and presents diffs for human approval.",
            },
          ].map(({ n, name, desc }) => (
            <div
              key={n}
              className="flex gap-3 rounded-lg border border-border p-4"
            >
              <span className="mt-0.5 h-fit shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
                {n}
              </span>
              <div>
                <p className="text-sm font-medium">{name}</p>
                <p className="mt-0.5 text-sm text-muted-foreground">{desc}</p>
              </div>
            </div>
          ))}
        </div>

        <p className="text-sm text-muted-foreground">
          <Link
            href="/about"
            className="underline underline-offset-2 hover:text-foreground transition-colors"
          >
            Full architecture walkthrough →
          </Link>
        </p>
      </section>
    </div>
  );
}
