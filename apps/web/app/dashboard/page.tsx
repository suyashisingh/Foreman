"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthGuard } from "@/components/auth-guard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-context";
import * as api from "@/lib/api-client";
import type { RepoDetail } from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";

const POLL_INTERVAL_MS = 5000;

function statusVariant(
  status: string,
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "ready") return "default";
  if (status === "failed") return "destructive";
  return "secondary";
}

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
          <CardTitle className="text-base">{repo.name}</CardTitle>
          <Badge variant={statusVariant(repo.status)}>{repo.status}</Badge>
        </div>
        <CardDescription className="truncate text-xs">
          {repo.clone_url}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-xs text-muted-foreground mb-3">
          {repo.chunk_count} chunks indexed
        </p>
        {repo.status === "ready" && (
          <Button size="sm" onClick={() => onCreateRun(repo)}>
            Create Run
          </Button>
        )}
        {repo.status === "failed" && repo.error_message && (
          <p className="text-xs text-destructive">{repo.error_message}</p>
        )}
      </CardContent>
    </Card>
  );
}

function RegisterRepoForm({
  token,
  onRegistered,
}: {
  token: string;
  onRegistered: () => void;
}) {
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
      onRegistered();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail : "Failed to register repository.",
      );
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
      onCreated(run.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create run.");
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
// Dashboard
// ---------------------------------------------------------------------------

function DashboardContent() {
  const { token, user, logout } = useAuth();
  const router = useRouter();

  const [repos, setRepos] = useState<RepoDetail[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedRepo, setSelectedRepo] = useState<RepoDetail | null>(null);

  // Stable refresh callback for the "Register" form's onRegistered prop.
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
        if (active) { setRepos(data); setLoadError(null); }
      } catch {
        if (active) setLoadError("Failed to load repositories.");
      }
    }

    void load();
    const id = setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => { active = false; clearInterval(id); };
  }, [token]);

  function handleRunCreated(runId: string) {
    setSelectedRepo(null);
    router.push(`/runs/${runId}`);
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          {user && (
            <p className="text-sm text-muted-foreground">{user.email}</p>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={logout}>
          Sign out
        </Button>
      </div>

      <RegisterRepoForm token={token!} onRegistered={refreshRepos} />

      <section>
        <h2 className="text-lg font-medium mb-4">Repositories</h2>
        {loadError && (
          <p className="text-sm text-destructive mb-4">{loadError}</p>
        )}
        {repos.length === 0 && !loadError ? (
          <p className="text-sm text-muted-foreground">
            No repositories registered yet.
          </p>
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
