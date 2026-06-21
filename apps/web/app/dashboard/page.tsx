"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AuthGuard } from "@/components/auth-guard";
import { StatusBadge } from "@/components/status-badge";
import { Skeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";
import * as api from "@/lib/api-client";
import type { RepoDetail } from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";

const POLL_INTERVAL_MS = 5000;

// ---------------------------------------------------------------------------
// Repo card
// ---------------------------------------------------------------------------

function RepoCard({
  repo,
  onCreateRun,
}: {
  repo: RepoDetail;
  onCreateRun: (repo: RepoDetail) => void;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base truncate">{repo.name}</CardTitle>
          <StatusBadge status={repo.status} />
        </div>
        <CardDescription className="truncate text-xs">
          {repo.clone_url}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          {repo.chunk_count > 0
            ? `${repo.chunk_count} chunks indexed`
            : "Indexing…"}
        </p>

        <div className="flex gap-2">
          {repo.status === "ready" && (
            <Button size="sm" onClick={() => onCreateRun(repo)}>
              Create Run
            </Button>
          )}
          {/* Per-repo run filtering requires a new backend endpoint (GET /runs?repo_id=…).
              Until then, link to the global runs list. */}
          <Link
            href="/runs"
            className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}
          >
            View runs →
          </Link>
        </div>

        {repo.status === "failed" && repo.error_message && (
          <p className="text-xs text-destructive">{repo.error_message}</p>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Repo skeleton (loading state)
// ---------------------------------------------------------------------------

function RepoCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-5 w-16 rounded-full" />
        </div>
        <Skeleton className="h-3 w-3/4 mt-1" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-3 w-1/3 mb-3" />
        <Skeleton className="h-8 w-24 rounded-md" />
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Register repo form
// ---------------------------------------------------------------------------

function RegisterRepoForm({
  token,
  onRegistered,
}: {
  token: string;
  onRegistered: () => void;
}) {
  const { addToast } = useToast();
  const [name, setName] = useState("");
  const [cloneUrl, setCloneUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      await api.registerRepo(token, { name, clone_url: cloneUrl });
      setName("");
      setCloneUrl("");
      addToast(`Repository "${name}" registered — ingestion starting.`, "success");
      onRegistered();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail : "Failed to register repository.";
      setError(msg);
      addToast(msg, "error");
    } finally {
      setPending(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Register a repository</CardTitle>
        <CardDescription>
          Paste a public clone URL to start ingestion.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-3" onSubmit={handleSubmit}>
          <div className="space-y-1">
            <label htmlFor="repo-name" className="text-sm font-medium">
              Name
            </label>
            <Input
              id="repo-name"
              required
              placeholder="my-project"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="repo-url" className="text-sm font-medium">
              Clone URL
            </label>
            <Input
              id="repo-url"
              required
              placeholder="https://github.com/owner/repo.git"
              value={cloneUrl}
              onChange={(e) => setCloneUrl(e.target.value)}
            />
          </div>
          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
          <Button type="submit" disabled={pending}>
            {pending ? "Registering…" : "Register"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Create run modal
// ---------------------------------------------------------------------------

function CreateRunModal({
  repo,
  token,
  onClose,
  onCreated,
}: {
  repo: RepoDetail;
  token: string;
  onClose: () => void;
  onCreated: (runId: string) => void;
}) {
  const { addToast } = useToast();
  const [issueText, setIssueText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const run = await api.createRun(token, {
        repo_id: repo.id,
        issue_text: issueText,
      });
      addToast("Run started — agents are queued.", "success");
      onCreated(run.id);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail : "Failed to create run.";
      setError(msg);
      addToast(msg, "error");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 px-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Create run on {repo.name}</CardTitle>
          <CardDescription>
            Describe the issue or feature for the agent to implement.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="space-y-1">
              <label htmlFor="issue-text" className="text-sm font-medium">
                Issue / task description
              </label>
              <textarea
                id="issue-text"
                className="w-full min-h-[100px] rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                required
                placeholder="Add a subtract method to the Calculator class…"
                value={issueText}
                onChange={(e) => setIssueText(e.target.value)}
              />
            </div>
            {error && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}
            <div className="flex gap-2">
              <Button type="submit" disabled={pending}>
                {pending ? "Starting…" : "Start run"}
              </Button>
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyRepos() {
  return (
    <div className="rounded-lg border border-dashed border-border p-10 text-center space-y-3">
      <p className="text-sm font-medium">No repositories yet</p>
      <p className="text-sm text-muted-foreground max-w-xs mx-auto">
        Register a public GitHub repository above to start indexing its code and
        creating runs.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

function DashboardContent() {
  const { token, user } = useAuth();
  const router = useRouter();

  const [repos, setRepos] = useState<RepoDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedRepo, setSelectedRepo] = useState<RepoDetail | null>(null);

  const refreshRepos = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.listRepos(token);
      setRepos(data);
      setLoadError(null);
    } catch {
      setLoadError("Failed to load repositories.");
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    let active = true;

    async function load() {
      try {
        const data = await api.listRepos(token!);
        if (active) {
          setRepos(data);
          setLoadError(null);
          setLoading(false);
        }
      } catch {
        if (active) {
          setLoadError("Failed to load repositories.");
          setLoading(false);
        }
      }
    }

    void load();
    const id = setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [token]);

  function handleRunCreated(runId: string) {
    setSelectedRepo(null);
    router.push(`/runs/${runId}`);
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 space-y-8">
      {/* Header — user menu is in the global nav; just show email context here */}
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        {user && (
          <p className="text-sm text-muted-foreground">{user.email}</p>
        )}
      </div>

      <RegisterRepoForm token={token!} onRegistered={refreshRepos} />

      <section>
        <h2 className="text-lg font-medium mb-4">Repositories</h2>

        {loadError && (
          <p className="text-sm text-destructive mb-4" role="alert">
            {loadError}
          </p>
        )}

        {loading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((n) => (
              <RepoCardSkeleton key={n} />
            ))}
          </div>
        ) : repos.length === 0 && !loadError ? (
          <EmptyRepos />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {repos.map((repo) => (
              <RepoCard
                key={repo.id}
                repo={repo}
                onCreateRun={setSelectedRepo}
              />
            ))}
          </div>
        )}

        {/* Note: no DELETE /repos endpoint exists yet. Once added, each card
            can expose a delete/re-ingest action without requiring new UI work. */}
      </section>

      {selectedRepo && (
        <CreateRunModal
          repo={selectedRepo}
          token={token!}
          onClose={() => setSelectedRepo(null)}
          onCreated={handleRunCreated}
        />
      )}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <AuthGuard>
      <DashboardContent />
    </AuthGuard>
  );
}
