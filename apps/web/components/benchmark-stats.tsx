"use client";

import { useEffect, useState } from "react";
import { getBenchmarkResults, type BenchmarkResultsOut } from "@/lib/api-client";

// Displays live benchmark numbers from the public results endpoint.
// Returns null (renders nothing) while loading or on error so the home page
// is never blocked by a failed API call.
export function BenchmarkStats() {
  const [data, setData] = useState<BenchmarkResultsOut | null>(null);

  useEffect(() => {
    getBenchmarkResults()
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data) return null;

  return (
    <p className="text-sm text-muted-foreground">
      Latest benchmark:{" "}
      <span className="font-semibold text-foreground">
        {(data.pass_at_1_rate * 100).toFixed(0)}% pass@1
      </span>
      {" across "}
      <span className="font-semibold text-foreground">{data.task_count}</span>
      {" real tasks · avg "}
      <span className="font-semibold text-foreground">
        {data.avg_time_to_green_s !== null
          ? `${data.avg_time_to_green_s.toFixed(0)}s`
          : "—"}
      </span>
      {" to green"}
    </p>
  );
}
