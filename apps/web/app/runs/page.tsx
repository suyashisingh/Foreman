"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AuthGuard } from "@/components/auth-guard";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import * as api from "@/lib/api-client";
import type { RunOut } from "@/lib/api-client";

function statusVariant(
  status: string,
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "passed") return "default";
  if (status === "failed" || status === "rejected") return "destructive";
  if (status === "awaiting_approval") return "secondary";
  return "outline";
}

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
          <Badge variant={statusVariant(run.status)}>
            {run.status.replace("_", " ")}
          </Badge>
        </CardContent>
      </Card>
    </Link>
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
      <p className="text-sm text-muted-foreground">Loading…</p>
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
    return (
      <p className="text-sm text-muted-foreground">
        No runs yet. Go to the{" "}
        <Link href="/dashboard" className="underline underline-offset-2">
          dashboard
        </Link>{" "}
        to create one.
      </p>
    );
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
    <AuthGuard>
      <div className="mx-auto max-w-4xl px-4 py-8 space-y-6">
        <h1 className="text-2xl font-semibold">Run History</h1>
        <RunsContent />
      </div>
    </AuthGuard>
  );
}
