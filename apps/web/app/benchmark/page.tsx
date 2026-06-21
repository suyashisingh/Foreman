"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface TaskResult {
  task_id: string;
  passed: boolean;
  attempts_to_pass: number | null;
  time_to_green_s: number | null;
  token_cost_usd: number | null;
  pass_at_1: boolean;
  pass_at_3: boolean;
}

interface BenchmarkResults {
  benchmark_run_id: string;
  commit_sha: string;
  created_at: string;
  task_count: number;
  pass_at_1_rate: number;
  pass_at_3_rate: number;
  avg_time_to_green_s: number | null;
  total_token_cost_usd: number;
  tasks: TaskResult[];
}

function pct(rate: number): string {
  return `${(rate * 100).toFixed(0)}%`;
}

function fmtTime(s: number | null): string {
  if (s === null) return "—";
  return s >= 60 ? `${(s / 60).toFixed(1)}m` : `${s.toFixed(0)}s`;
}

function fmtCost(usd: number | null): string {
  if (usd === null) return "—";
  return `$${usd.toFixed(4)}`;
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardHeader className="pb-1">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-bold">{value}</p>
      </CardContent>
    </Card>
  );
}

const EASY_TASKS = new Set([
  "iniconfig-get-default",
  "iniconfig-as-dict",
  "iniconfig-section-names",
  "humanize-clamp",
]);
const HARD_TASKS = new Set(["natsort-keygen-reversed"]);

function difficultyFor(taskId: string): string {
  if (EASY_TASKS.has(taskId)) return "easy";
  if (HARD_TASKS.has(taskId)) return "hard";
  return "medium";
}

export default function BenchmarkPage() {
  const [data, setData] = useState<BenchmarkResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/v1/benchmark/results")
      .then((r) => {
        if (!r.ok) {
          if (r.status === 404) throw new Error("No benchmark runs yet.");
          throw new Error(`HTTP ${r.status}`);
        }
        return r.json() as Promise<BenchmarkResults>;
      })
      .then(setData)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Unknown error")
      )
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-10">
        <h1 className="text-2xl font-bold mb-4">Benchmark</h1>
        <p className="text-muted-foreground">Loading results&hellip;</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-10 space-y-4">
        <h1 className="text-2xl font-bold">Benchmark</h1>
        <Card className="border-destructive">
          <CardContent className="pt-4 text-destructive text-sm">
            {error ?? "No data"}
          </CardContent>
        </Card>
      </div>
    );
  }

  const sortedTasks = [...data.tasks].sort((a, b) =>
    a.task_id.localeCompare(b.task_id)
  );

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Benchmark</h1>
        <p className="text-sm text-muted-foreground mt-1">
          commit{" "}
          <code className="font-mono">{data.commit_sha.slice(0, 8)}</code>
          {" · "}
          {new Date(data.created_at).toLocaleDateString()}
          {" · "}
          {data.task_count} tasks
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="pass@1" value={pct(data.pass_at_1_rate)} />
        <StatCard label="pass@3" value={pct(data.pass_at_3_rate)} />
        <StatCard
          label="avg time-to-green"
          value={fmtTime(data.avg_time_to_green_s)}
        />
        <StatCard
          label="total token cost"
          value={`$${data.total_token_cost_usd.toFixed(3)}`}
        />
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-3">Per-task results</h2>
        <div className="rounded-md border overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40">
                <th className="px-4 py-2 text-left font-medium">Task</th>
                <th className="px-4 py-2 text-center font-medium">
                  Difficulty
                </th>
                <th className="px-4 py-2 text-center font-medium">Result</th>
                <th className="px-4 py-2 text-center font-medium">pass@1</th>
                <th className="px-4 py-2 text-center font-medium">pass@3</th>
                <th className="px-4 py-2 text-right font-medium">Attempts</th>
                <th className="px-4 py-2 text-right font-medium">Time</th>
                <th className="px-4 py-2 text-right font-medium">Cost</th>
              </tr>
            </thead>
            <tbody>
              {sortedTasks.map((t) => (
                <tr
                  key={t.task_id}
                  className="border-b last:border-0 hover:bg-muted/30"
                >
                  <td className="px-4 py-2 font-mono text-xs">{t.task_id}</td>
                  <td className="px-4 py-2 text-center">
                    <Badge variant="outline" className="text-xs">
                      {difficultyFor(t.task_id)}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 text-center">
                    <Badge variant={t.passed ? "default" : "destructive"}>
                      {t.passed ? "pass" : "fail"}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 text-center text-muted-foreground">
                    {t.pass_at_1 ? "yes" : "—"}
                  </td>
                  <td className="px-4 py-2 text-center text-muted-foreground">
                    {t.pass_at_3 ? "yes" : "—"}
                  </td>
                  <td className="px-4 py-2 text-right">
                    {t.attempts_to_pass ?? "—"}
                  </td>
                  <td className="px-4 py-2 text-right">
                    {fmtTime(t.time_to_green_s)}
                  </td>
                  <td className="px-4 py-2 text-right font-mono text-xs">
                    {fmtCost(t.token_cost_usd)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
