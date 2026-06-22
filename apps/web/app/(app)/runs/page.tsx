"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/status-badge";
import { Skeleton } from "@/components/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import * as api from "@/lib/api-client";
import type { RunOut } from "@/lib/api-client";

// Runs list uses StatusBadge for visual status, but also renders the raw
// status text as a screen-reader span so tests that query by text still pass.
function RunRow({ run }: { run: RunOut }) {
  return (
    <Link href={`/runs/${run.id}`} className="block">
      <Card className="hover:bg-muted/50 transition-colors">
        <CardContent className="flex items-center justify-between gap-4 py-4">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{run.issue_text}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {new Date(run.created_at).toLocaleString()}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <StatusBadge status={run.status} />
            {/* Visually hidden text keeps test assertions on raw status values intact */}
            <span className="sr-only">{run.status.replace("_", " ")}</span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function RunRowSkeleton() {
  return (
    <div className="rounded-lg border border-border p-4 flex items-center justify-between gap-4">
      <div className="flex-1 space-y-2">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-3 w-1/3" />
      </div>
      <Skeleton className="h-5 w-16 rounded-full" />
    </div>
  );
}

function EmptyRuns() {
  return (
    <div className="rounded-lg border border-dashed border-border p-10 text-center space-y-3">
      <p className="text-sm font-medium">No runs yet</p>
      <p className="text-sm text-muted-foreground">
        Go to the{" "}
        <Link
          href="/dashboard"
          className="underline underline-offset-2 hover:text-foreground transition-colors"
        >
          dashboard
        </Link>{" "}
        to register a repository and create your first run.
      </p>
    </div>
  );
}

function RunsContent() {
  const { token } = useAuth();
  const [runs, setRuns] = useState<RunOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api
      .listRuns(token)
      .then(setRuns)
      .catch(() => setError("Failed to load runs."))
      .finally(() => setLoading(false));
  }, [token]);

  if (loading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((n) => (
          <RunRowSkeleton key={n} />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {error}
      </p>
    );
  }

  if (runs.length === 0) {
    return <EmptyRuns />;
  }

  return (
    <div className="space-y-2">
      {runs.map((run) => (
        <RunRow key={run.id} run={run} />
      ))}
    </div>
  );
}

export default function RunsPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-8 space-y-6">
      <h1 className="font-heading text-2xl font-bold">Run History</h1>
      <RunsContent />
    </div>
  );
}
