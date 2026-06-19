import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";
import Link from "next/link";

export default function HomePage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-12 space-y-10">
      <section className="space-y-4">
        <div className="flex items-center gap-3">
          <h1 className="text-4xl font-bold tracking-tight">Foreman</h1>
          <Badge variant="secondary">Alpha</Badge>
        </div>
        <p className="text-lg text-muted-foreground max-w-xl">
          Autonomous multi-agent software engineering platform. Describe a task,
          watch agents plan, code, and verify in real time.
        </p>
        <div className="flex gap-3">
          <Link href="/runs" className={cn(buttonVariants())}>
            View Runs
          </Link>
          <Link
            href="/benchmark"
            className={cn(buttonVariants({ variant: "outline" }))}
          >
            Benchmark Results
          </Link>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Plan &amp; Execute</CardTitle>
            <CardDescription>
              LangGraph agents decompose tasks and run them inside isolated e2b
              sandboxes.
            </CardDescription>
          </CardHeader>
          <CardContent />
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Live Trace</CardTitle>
            <CardDescription>
              Stream agent steps, tool calls, and diffs in real time over
              WebSocket.
            </CardDescription>
          </CardHeader>
          <CardContent />
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Benchmark</CardTitle>
            <CardDescription>
              Evaluate task completion quality against the SWE-bench dataset.
            </CardDescription>
          </CardHeader>
          <CardContent />
        </Card>
      </section>
    </div>
  );
}
