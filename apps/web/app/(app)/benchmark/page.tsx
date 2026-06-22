"use client";

// Pagination note: once task_count grows beyond the curated set, add
// ?page=N&per_page=25 params to GET /api/v1/benchmark/results and render
// prev/next controls here — the backend schema already returns task_count.

import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/status-badge";
import { Skeleton } from "@/components/skeleton";
import { getBenchmarkResults, type BenchmarkResultsOut, type TaskResultOut } from "@/lib/api-client";

const GOLD = "#C9A227";

function Eyebrow({ code, label }: { code: string; label: string }) {
  return (
    <div className="flex items-center gap-3 mb-3">
      <div className="h-px w-8 shrink-0 bg-primary/30" />
      <span className="font-mono text-xs uppercase tracking-widest text-primary">
        {code} · {label}
      </span>
    </div>
  );
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

// ---------------------------------------------------------------------------
// Difficulty derivation (mirrors benchmark/tasks.py)
// ---------------------------------------------------------------------------

const EASY_TASKS = new Set([
  "iniconfig-get-default",
  "iniconfig-as-dict",
  "iniconfig-section-names",
  "humanize-clamp",
]);
const HARD_TASKS = new Set(["natsort-keygen-reversed"]);

type Difficulty = "easy" | "medium" | "hard";

function difficultyFor(taskId: string): Difficulty {
  if (EASY_TASKS.has(taskId)) return "easy";
  if (HARD_TASKS.has(taskId)) return "hard";
  return "medium";
}

const DIFFICULTY_ORDER: Record<Difficulty, number> = { easy: 0, medium: 1, hard: 2 };

// ---------------------------------------------------------------------------
// Stat card with monospace label
// ---------------------------------------------------------------------------

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardHeader className="pb-1">
        <CardTitle className="font-mono text-xs font-medium text-muted-foreground uppercase tracking-widest">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="font-heading text-3xl font-bold">{value}</p>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Skeleton loading state
// ---------------------------------------------------------------------------

function BenchmarkSkeleton() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-10 space-y-8">
      <div className="space-y-2">
        <Skeleton className="h-7 w-32" />
        <Skeleton className="h-4 w-56" />
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[1, 2, 3, 4].map((n) => (
          <Card key={n}>
            <CardHeader className="pb-1">
              <Skeleton className="h-3 w-20" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="rounded-md border overflow-hidden">
        {[1, 2, 3, 4, 5].map((n) => (
          <div key={n} className="flex gap-4 px-4 py-3 border-b last:border-0">
            <Skeleton className="h-4 w-36" />
            <Skeleton className="h-4 w-12" />
            <Skeleton className="h-4 w-14" />
            <Skeleton className="h-4 w-10 ml-auto" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sortable column header
// ---------------------------------------------------------------------------

type SortField = "task_id" | "difficulty" | "passed" | "attempts" | "time" | "cost";

function SortHeader({
  field,
  label,
  currentField,
  currentDir,
  onSort,
  className,
}: {
  field: SortField;
  label: string;
  currentField: SortField;
  currentDir: "asc" | "desc";
  onSort: (f: SortField) => void;
  className?: string;
}) {
  const active = currentField === field;
  return (
    <th className={`px-4 py-2 font-medium cursor-pointer select-none ${className ?? ""}`}>
      <button
        className="inline-flex items-center gap-1 hover:text-foreground transition-colors"
        onClick={() => onSort(field)}
      >
        {label}
        {active ? (
          currentDir === "asc" ? (
            <ChevronUp size={13} />
          ) : (
            <ChevronDown size={13} />
          )
        ) : (
          <ChevronDown size={13} className="opacity-30" />
        )}
      </button>
    </th>
  );
}

// ---------------------------------------------------------------------------
// Task row — monospace task_id, color-coded difficulty
// ---------------------------------------------------------------------------

function TaskRow({ t }: { t: TaskResultOut & { difficulty: Difficulty } }) {
  return (
    <tr className="border-b last:border-0 hover:bg-muted/30">
      <td className="px-4 py-2 font-mono text-xs">{t.task_id}</td>
      <td className="px-4 py-2 text-center">
        <span className="text-xs text-muted-foreground capitalize">
          {t.difficulty}
        </span>
      </td>
      <td className="px-4 py-2 text-center">
        <StatusBadge status={t.passed ? "passed" : "failed"} />
      </td>
      <td className="px-4 py-2 text-center text-sm">
        {t.pass_at_1 ? (
          <span className="font-medium" style={{ color: GOLD }}>✓</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-4 py-2 text-center text-sm">
        {t.pass_at_3 ? (
          <span className="font-medium" style={{ color: GOLD }}>✓</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-4 py-2 text-right text-sm">
        {t.attempts_to_pass ?? "—"}
      </td>
      <td className="px-4 py-2 text-right text-sm">{fmtTime(t.time_to_green_s)}</td>
      <td className="px-4 py-2 text-right font-mono text-xs">
        {fmtCost(t.token_cost_usd)}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function BenchmarkPage() {
  const [data, setData] = useState<BenchmarkResultsOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [sortField, setSortField] = useState<SortField>("difficulty");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [groupByDifficulty, setGroupByDifficulty] = useState(false);

  useEffect(() => {
    getBenchmarkResults()
      .then(setData)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Unknown error"),
      )
      .finally(() => setLoading(false));
  }, []);

  function handleSort(field: SortField) {
    if (field === sortField) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("asc");
    }
  }

  const enrichedTasks = useMemo(() => {
    if (!data) return [];
    return data.tasks.map((t) => ({ ...t, difficulty: difficultyFor(t.task_id) }));
  }, [data]);

  const sortedTasks = useMemo(() => {
    const copy = [...enrichedTasks];
    copy.sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case "task_id":
          cmp = a.task_id.localeCompare(b.task_id);
          break;
        case "difficulty":
          cmp = DIFFICULTY_ORDER[a.difficulty] - DIFFICULTY_ORDER[b.difficulty];
          break;
        case "passed":
          cmp = Number(b.passed) - Number(a.passed);
          break;
        case "attempts":
          cmp = (a.attempts_to_pass ?? 999) - (b.attempts_to_pass ?? 999);
          break;
        case "time":
          cmp = (a.time_to_green_s ?? 9999) - (b.time_to_green_s ?? 9999);
          break;
        case "cost":
          cmp = (a.token_cost_usd ?? 9999) - (b.token_cost_usd ?? 9999);
          break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [enrichedTasks, sortField, sortDir]);

  const groupedTasks = useMemo(() => {
    if (!groupByDifficulty) return null;
    const groups: Record<Difficulty, typeof sortedTasks> = { easy: [], medium: [], hard: [] };
    for (const t of sortedTasks) groups[t.difficulty].push(t);
    return groups;
  }, [groupByDifficulty, sortedTasks]);

  if (loading) return <BenchmarkSkeleton />;

  if (error || !data) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-10 space-y-4">
        <h1 className="font-heading font-bold text-2xl">Benchmark</h1>
        <Card className="border-destructive">
          <CardContent className="pt-4 text-destructive text-sm">
            {error ?? "No benchmark data available yet."}
          </CardContent>
        </Card>
      </div>
    );
  }

  const tableHeaderProps = {
    currentField: sortField,
    currentDir: sortDir,
    onSort: handleSort,
  };

  const tableHead = (
    <thead>
      <tr className="border-b bg-muted/40">
        <SortHeader field="task_id" label="Task" {...tableHeaderProps} className="text-left" />
        <SortHeader field="difficulty" label="Difficulty" {...tableHeaderProps} className="text-center" />
        <SortHeader field="passed" label="Result" {...tableHeaderProps} className="text-center" />
        <th className="px-4 py-2 text-center font-medium text-sm">pass@1</th>
        <th className="px-4 py-2 text-center font-medium text-sm">pass@3</th>
        <SortHeader field="attempts" label="Attempts" {...tableHeaderProps} className="text-right" />
        <SortHeader field="time" label="Time" {...tableHeaderProps} className="text-right" />
        <SortHeader field="cost" label="Cost" {...tableHeaderProps} className="text-right" />
      </tr>
    </thead>
  );

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 space-y-8">
      {/* Header */}
      <div>
        <Eyebrow code="BM-00" label="BENCHMARK RESULTS" />
        <h1 className="font-heading font-bold text-2xl tracking-tight">Benchmark</h1>
        <p className="text-sm text-muted-foreground mt-1">
          commit{" "}
          <code className="font-mono">{data.commit_sha.slice(0, 8)}</code>
          {" · "}
          {new Date(data.created_at).toLocaleDateString()}
          {" · "}
          {data.task_count} task{data.task_count !== 1 ? "s" : ""}
        </p>
      </div>

      {/* Stat cards */}
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

      {/* Table controls */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-heading text-lg font-semibold">Per-task results</h2>
          <button
            onClick={() => setGroupByDifficulty((v) => !v)}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors underline underline-offset-2"
          >
            {groupByDifficulty ? "Flat view" : "Group by difficulty"}
          </button>
        </div>

        <div className="rounded-md border overflow-x-auto">
          {groupedTasks ? (
            (["easy", "medium", "hard"] as Difficulty[]).map((level) => {
              const tasks = groupedTasks[level];
              if (tasks.length === 0) return null;
              return (
                <div key={level}>
                  <div className="px-4 py-1.5 bg-muted/60 text-xs font-medium text-muted-foreground capitalize border-b">
                    {level} · {tasks.length} task{tasks.length !== 1 ? "s" : ""}
                  </div>
                  <table className="w-full text-sm">
                    {tableHead}
                    <tbody>
                      {tasks.map((t) => (
                        <TaskRow key={t.task_id} t={t} />
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })
          ) : (
            <table className="w-full text-sm">
              {tableHead}
              <tbody>
                {sortedTasks.map((t) => (
                  <TaskRow key={t.task_id} t={t} />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
