"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { X } from "lucide-react";
import { StatusBadge } from "@/components/status-badge";
import { Skeleton } from "@/components/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!token) return;
    api
      .listRuns(token)
      .then(setRuns)
      .catch(() => setError("Failed to load runs."))
      .finally(() => setLoading(false));
  }, [token]);

  const filteredRuns = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return runs;
    return runs.filter((r) => r.issue_text.toLowerCase().includes(q));
  }, [runs, query]);

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
    <div className="space-y-4">
      <div className="relative">
        <Input
          placeholder="Filter by issue text…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="pr-8"
          aria-label="Filter runs"
        />
        {query && (
          <button
            aria-label="Clear filter"
            onClick={() => setQuery("")}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
          >
            <X size={14} />
          </button>
        )}
      </div>

      {filteredRuns.length === 0 ? (
        <p className="text-sm text-muted-foreground">No runs match your filter.</p>
      ) : (
        <div className="space-y-2">
          {filteredRuns.map((run) => (
            <RunRow key={run.id} run={run} />
          ))}
        </div>
      )}
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
