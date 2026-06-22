"use client";

import { useEffect, useState } from "react";
import { getBenchmarkResults, type BenchmarkResultsOut } from "@/lib/api-client";

// Displays live benchmark numbers from the public results endpoint.
// Returns null while loading or on error — never blocks the page.
export function BenchmarkStats({
  variant = "inline",
}: {
  variant?: "inline" | "grid";
}) {
  const [data, setData] = useState<BenchmarkResultsOut | null>(null);

  useEffect(() => {
    getBenchmarkResults()
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data) return null;

  const pass1 = `${(data.pass_at_1_rate * 100).toFixed(0)}%`;
  const pass3 = `${(data.pass_at_3_rate * 100).toFixed(0)}%`;
  const avgTime =
    data.avg_time_to_green_s !== null
      ? `${data.avg_time_to_green_s.toFixed(0)}s`
      : "—";

  if (variant === "grid") {
    return (
      <div className="flex flex-wrap gap-8">
        <StatCell value={pass1} label="pass@1" />
        <StatCell value={pass3} label="pass@3" />
        <StatCell value={avgTime} label="avg to green" />
        <StatCell value={String(data.task_count)} label="real tasks" />
      </div>
    );
  }

  return (
    <p className="text-sm text-muted-foreground">
      Latest benchmark:{" "}
      <span className="font-semibold text-foreground">{pass1} pass@1</span>
      {" across "}
      <span className="font-semibold text-foreground">{data.task_count}</span>
      {" real tasks · avg "}
      <span className="font-semibold text-foreground">{avgTime}</span>
      {" to green"}
    </p>
  );
}

function StatCell({ value, label }: { value: string; label: string }) {
  return (
    <div className="space-y-0.5">
      <p className="text-3xl font-bold tracking-tight">{value}</p>
      <p className="text-xs text-muted-foreground uppercase tracking-wide">
        {label}
      </p>
    </div>
  );
}
