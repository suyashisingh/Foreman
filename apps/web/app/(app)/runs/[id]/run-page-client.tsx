"use client";

import { startTransition, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, AlertCircle, CheckCircle2, XCircle } from "lucide-react";
import { AgentStepCard } from "@/components/AgentStepCard";
import { DiffViewer } from "@/components/DiffViewer";
import { LiveLogStream } from "@/components/LiveLogStream";
import { StatusBadge } from "@/components/status-badge";
import { useToast } from "@/components/toast";
import type { TimelineEntry } from "@/components/LiveLogStream";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-context";
import { getRun, approveRun, rejectRun, createRun, cancelRun, ApiError } from "@/lib/api-client";
import type { RunDetail } from "@/lib/api-client";
import { RunWsClient } from "@/lib/ws-client";
import type { WsConnectionState } from "@/lib/ws-client";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TERMINAL = new Set([
  "passed",
  "failed",
  "rejected",
  "awaiting_approval",
  "cancelled",
]);

function isTerminal(s: string) {
  return TERMINAL.has(s);
}

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function shortId(id: string) {
  return id.slice(0, 8);
}

// Thresholds (ms) before showing the "taking longer than usual" notice.
// Based on observed timings: Planner/Reviewer are quick; Coder can take 20-60s.
const STUCK_THRESHOLDS: Record<string, number> = {
  planning: 90_000,
  reviewing: 90_000,
  coding: 180_000,
  testing: 180_000,
};

// ---------------------------------------------------------------------------
// Connection indicator
// ---------------------------------------------------------------------------

const CONN_STYLE: Record<WsConnectionState, { text: string; cls: string }> = {
  connecting: { text: "Connecting…", cls: "text-muted-foreground" },
  connected: { text: "● Live", cls: "text-green-600 dark:text-green-400" },
  reconnecting: { text: "↺ Reconnecting…", cls: "text-amber-600 dark:text-amber-400" },
  disconnected: { text: "Disconnected", cls: "text-muted-foreground" },
  error: { text: "Connection lost", cls: "text-destructive" },
};

function ConnectionIndicator({
  state,
  error,
}: {
  state: WsConnectionState;
  error: string | null;
}) {
  const { text, cls } = CONN_STYLE[state];
  return (
    <span className={`text-xs font-mono ${cls}`} title={error ?? undefined}>
      {text}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Risk level badge for reviewer output
// ---------------------------------------------------------------------------

const RISK_STYLE = {
  low: "bg-green-100 text-green-800 border border-green-200",
  medium: "bg-amber-100 text-amber-800 border border-amber-200",
  high: "bg-red-100 text-red-800 border border-red-200",
} as const;

function RiskBadge({ level }: { level: string }) {
  const cls =
    (RISK_STYLE as Record<string, string>)[level.toLowerCase()] ??
    "bg-secondary text-secondary-foreground border border-border";
  return (
    <span className={`text-xs font-medium rounded-full px-2 py-0.5 ${cls}`}>
      {capitalize(level)} risk
    </span>
  );
}

// ---------------------------------------------------------------------------
// Approve / Reject panel
// ---------------------------------------------------------------------------

function ApprovalPanel({
  runId,
  token,
  onApproved,
  onRejected,
}: {
  runId: string;
  token: string;
  onApproved: () => void;
  onRejected: (reason: string) => void;
}) {
  const { addToast } = useToast();
  const [action, setAction] = useState<"idle" | "approving" | "rejecting">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  async function handleApprove() {
    setAction("approving");
    setError(null);
    try {
      await approveRun(token, runId);
      addToast("Run approved.", "success");
      onApproved();
    } catch (err) {
      const msg =
        err instanceof ApiError && err.status === 422
          ? "This run is no longer awaiting approval — it may have already been decided."
          : err instanceof ApiError
            ? err.detail
            : "Approval failed.";
      setError(msg);
      addToast(msg, "error");
      setAction("idle");
    }
  }

  async function handleReject() {
    setAction("rejecting");
    setError(null);
    try {
      await rejectRun(token, runId, reason || undefined);
      addToast("Run rejected.", "info");
      onRejected(reason);
    } catch (err) {
      const msg =
        err instanceof ApiError && err.status === 422
          ? "This run is no longer awaiting approval — it may have already been decided."
          : err instanceof ApiError
            ? err.detail
            : "Rejection failed.";
      setError(msg);
      addToast(msg, "error");
      setAction("idle");
    }
  }

  const busy = action !== "idle";

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50/50 dark:bg-amber-950/20 dark:border-amber-800 p-4 space-y-3">
      <p className="text-sm font-medium">Ready for your review</p>

      <div className="flex flex-wrap gap-3 items-start">
        <Button
          onClick={handleApprove}
          disabled={busy}
          className="bg-green-600 hover:bg-green-700 text-white"
        >
          {action === "approving" ? "Approving…" : "Approve"}
        </Button>

        <div className="flex gap-2 items-center flex-1 min-w-[200px]">
          <Input
            placeholder="Rejection reason (optional)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            disabled={busy}
            className="text-sm"
          />
          <Button
            variant="outline"
            onClick={handleReject}
            disabled={busy}
            className="shrink-0 text-destructive border-destructive/40 hover:bg-destructive/5"
          >
            {action === "rejecting" ? "Rejecting…" : "Reject"}
          </Button>
        </div>
      </div>

      {error && (
        <p className="text-sm text-destructive flex items-center gap-1.5">
          <AlertCircle size={13} />
          {error}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Outcome banners
// ---------------------------------------------------------------------------

function OutcomeBanner({
  status,
  reason,
  errorMessage,
}: {
  status: string;
  reason?: string | null;
  errorMessage?: string | null;
}) {
  if (status === "passed") {
    return (
      <div className="rounded-lg bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 p-4 flex items-start gap-3">
        <CheckCircle2 className="text-green-600 mt-0.5 shrink-0" size={18} />
        <div>
          <p className="text-sm font-medium text-green-800 dark:text-green-200">
            Run approved and passed
          </p>
          <p className="text-xs text-green-700/70 dark:text-green-300/70 mt-0.5">
            Diffs approved and marked complete.
          </p>
        </div>
      </div>
    );
  }
  if (status === "rejected") {
    return (
      <div className="rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 p-4 flex items-start gap-3">
        <XCircle className="text-red-600 mt-0.5 shrink-0" size={18} />
        <div>
          <p className="text-sm font-medium text-red-800 dark:text-red-200">
            Run rejected
          </p>
          {reason && (
            <p className="text-xs text-red-700/80 dark:text-red-300/80 mt-0.5">
              {reason}
            </p>
          )}
        </div>
      </div>
    );
  }
  if (status === "failed") {
    return (
      <div className="rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 p-4 flex items-start gap-3">
        <AlertCircle className="text-red-600 mt-0.5 shrink-0" size={18} />
        <div>
          <p className="text-sm font-medium text-red-800 dark:text-red-200">
            Run failed
          </p>
          {errorMessage ? (
            <p className="text-xs text-red-700/80 dark:text-red-300/80 mt-0.5">
              {errorMessage}
            </p>
          ) : (
            <p className="text-xs text-red-700/80 dark:text-red-300/80 mt-0.5">
              See agent steps for details.
            </p>
          )}
        </div>
      </div>
    );
  }
  if (status === "cancelled") {
    return (
      <div className="rounded-lg bg-secondary border border-border p-4 flex items-start gap-3">
        <AlertCircle className="text-muted-foreground mt-0.5 shrink-0" size={18} />
        <p className="text-sm text-muted-foreground">Run was cancelled.</p>
      </div>
    );
  }
  return null;
}

// ---------------------------------------------------------------------------
// Main client component
// ---------------------------------------------------------------------------

function RunPageInner({ runId }: { runId: string }) {
  const { token } = useAuth();
  const router = useRouter();
  const { addToast } = useToast();

  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [connState, setConnState] = useState<WsConnectionState>("connecting");
  const [connError, setConnError] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [liveStatus, setLiveStatus] = useState<string>("pending");
  const [cancelling, setCancelling] = useState(false);
  const [retrying, setRetrying] = useState(false);

  // Stuck-run indicator: track how long the current status has been observed
  const statusSinceRef = useRef<{ status: string; since: number } | null>(null);
  const [isStuck, setIsStuck] = useState(false);

  // Page visibility notification
  const wasHiddenRef = useRef(false);
  const completedWhileHiddenRef = useRef<string | null>(null);

  function pushEntry(
    text: string,
    timestamp: string,
    variant?: TimelineEntry["variant"],
  ) {
    setTimeline((prev) => [
      ...prev,
      { id: `${timestamp}-${Math.random().toString(36).slice(2)}`, timestamp, text, variant },
    ]);
  }

  // Stuck-run check: reset and restart interval whenever liveStatus changes
  useEffect(() => {
    startTransition(() => { setIsStuck(false); });
    if (isTerminal(liveStatus)) {
      statusSinceRef.current = null;
      return;
    }

    const threshold = STUCK_THRESHOLDS[liveStatus] ?? null;
    if (!threshold) return;

    statusSinceRef.current = { status: liveStatus, since: Date.now() };

    const id = setInterval(() => {
      if (statusSinceRef.current?.status !== liveStatus) return;
      if (Date.now() - statusSinceRef.current.since > threshold) {
        setIsStuck(true);
      }
    }, 5_000);

    return () => clearInterval(id);
  }, [liveStatus]);

  // Mark when run goes terminal while tab is hidden
  useEffect(() => {
    if (isTerminal(liveStatus) && wasHiddenRef.current) {
      completedWhileHiddenRef.current = liveStatus;
    }
  }, [liveStatus]);

  // Page visibility handler — show toast when user returns to a completed tab
  useEffect(() => {
    function onVisibility() {
      if (document.hidden) {
        wasHiddenRef.current = true;
      } else {
        wasHiddenRef.current = false;
        const completed = completedWhileHiddenRef.current;
        if (completed) {
          completedWhileHiddenRef.current = null;
          addToast(
            `Run ${completed.replace("_", " ")} while you were away.`,
            completed === "passed" ? "success" : "info",
          );
        }
      }
    }
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [addToast]);

  // Single effect: initial REST load → WS (if not terminal)
  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    let wsClient: RunWsClient | null = null;

    async function init() {
      let detail: RunDetail;
      try {
        detail = await getRun(token!, runId);
      } catch (err) {
        if (cancelled) return;
        setFetchError(
          err instanceof ApiError ? err.detail : "Failed to load run.",
        );
        setConnState("disconnected");
        return;
      }
      if (cancelled) return;

      setRunDetail(detail);
      setLiveStatus(detail.status);

      if (isTerminal(detail.status)) {
        setConnState("disconnected");
        return;
      }

      wsClient = new RunWsClient({
        token: token!,
        runId,

        onAgentStep: (data, ts) => {
          if (cancelled) return;
          const tokens =
            (data.input_tokens ?? 0) + (data.output_tokens ?? 0);
          pushEntry(
            `${capitalize(data.agent)} step ${data.step_index + 1} completed · ${data.latency_ms}ms · ${tokens} tokens`,
            ts,
          );
          getRun(token!, runId)
            .then((d) => { if (!cancelled) { setRunDetail(d); setLiveStatus(d.status); } })
            .catch(() => {});
        },

        onStatusChange: (data, ts) => {
          if (cancelled) return;
          setLiveStatus(data.status);
          pushEntry(
            `Status → ${data.status}`,
            ts,
            data.status === "failed" ? "error" : "muted",
          );
          if (data.status === "awaiting_approval") {
            getRun(token!, runId)
              .then((d) => { if (!cancelled) { setRunDetail(d); setLiveStatus(d.status); } })
              .catch(() => {});
          }
        },

        onRunComplete: (data, ts) => {
          if (cancelled) return;
          const isOk = data.status !== "failed";
          pushEntry(
            `Run complete — ${data.status}`,
            ts,
            isOk ? "success" : "error",
          );
          setLiveStatus(data.status);
          getRun(token!, runId)
            .then((d) => { if (!cancelled) { setRunDetail(d); setLiveStatus(d.status); } })
            .catch(() => {});
        },

        onConnectionChange: (state) => {
          if (!cancelled) setConnState(state);
        },
        onError: (msg) => {
          if (!cancelled) setConnError(msg);
        },
      });

      wsClient.connect();

      getRun(token!, runId)
        .then((d) => {
          if (cancelled) return;
          setRunDetail(d);
          setLiveStatus(d.status);
          if (isTerminal(d.status)) {
            wsClient?.disconnect();
            setConnState("disconnected");
          }
        })
        .catch(() => {});
    }

    void init();

    return () => {
      cancelled = true;
      wsClient?.disconnect();
    };
  }, [token, runId]);

  // Approve / reject handlers
  function handleApproved() {
    setRunDetail((prev) =>
      prev ? { ...prev, status: "passed", diffs: prev.diffs.map((d) => ({ ...d, approved: true })) } : prev,
    );
    setLiveStatus("passed");
    pushEntry("Approved by you", new Date().toISOString(), "success");
  }

  function handleRejected(reason: string) {
    setRunDetail((prev) =>
      prev ? { ...prev, status: "rejected", rejection_reason: reason || null } : prev,
    );
    setLiveStatus("rejected");
    pushEntry("Rejected by you", new Date().toISOString(), "warning");
  }

  // Cancel handler (cooperative/best-effort — does not kill in-flight sandbox)
  async function handleCancel() {
    if (!token) return;
    setCancelling(true);
    try {
      await cancelRun(token, runId);
      setRunDetail((prev) => prev ? { ...prev, status: "cancelled" } : prev);
      setLiveStatus("cancelled");
      pushEntry("Cancelled by you", new Date().toISOString(), "muted");
      addToast("Run cancelled.", "info");
    } catch (err) {
      addToast(
        err instanceof ApiError ? err.detail : "Failed to cancel run.",
        "error",
      );
    } finally {
      setCancelling(false);
    }
  }

  // Retry handler — resubmits with same repo + issue, navigates to new run
  async function handleRetry() {
    if (!token || !runDetail) return;
    setRetrying(true);
    try {
      const newRun = await createRun(token, {
        repo_id: runDetail.repo_id,
        issue_text: runDetail.issue_text,
      });
      addToast("New run started.", "success");
      router.push(`/runs/${newRun.id}`);
    } catch (err) {
      addToast(
        err instanceof ApiError ? err.detail : "Failed to start retry run.",
        "error",
      );
      setRetrying(false);
    }
  }

  // ---- Render ---------------------------------------------------------------

  if (fetchError) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-10">
        <p className="text-sm text-destructive">{fetchError}</p>
        <Link href="/runs" className="text-sm underline mt-2 inline-block">
          ← Runs
        </Link>
      </div>
    );
  }

  const status = liveStatus;
  const inProgress = !isTerminal(status);

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Link
              href="/runs"
              className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft size={13} />
              Runs
            </Link>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-xl font-semibold font-mono">
              Run {shortId(runId)}…
            </h1>
            <StatusBadge status={status} />
            {inProgress && (
              <ConnectionIndicator state={connState} error={connError} />
            )}
          </div>
          {runDetail && (
            <p className="text-sm text-muted-foreground">
              {runDetail.issue_text}
            </p>
          )}
          {runDetail && (
            <p className="text-xs text-muted-foreground">
              Started {fmtDate(runDetail.created_at)}
            </p>
          )}
        </div>

        {/* Cancel / Retry actions */}
        <div className="flex gap-2 shrink-0">
          {inProgress && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleCancel}
              disabled={cancelling}
              className="text-destructive border-destructive/30 hover:bg-destructive/5"
            >
              {cancelling ? "Cancelling…" : "Cancel run"}
            </Button>
          )}
          {status === "failed" && runDetail && (
            <Button size="sm" onClick={handleRetry} disabled={retrying}>
              {retrying ? "Starting…" : "Retry"}
            </Button>
          )}
        </div>
      </div>

      {/* Connection error banner (non-fatal) */}
      {connState === "error" && connError && (
        <div className="rounded-md bg-destructive/10 border border-destructive/30 px-4 py-2 text-sm text-destructive flex items-center gap-2">
          <AlertCircle size={14} />
          {connError} — live updates paused. Refresh the page to reconnect.
        </div>
      )}

      {/* Stuck-run notice */}
      {isStuck && inProgress && (
        <div className="rounded-md bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 px-4 py-2 text-sm text-amber-800 dark:text-amber-200">
          This is taking longer than usual — the agent is still working.
          Gemini free-tier rate limits (15 req/min) can cause delays between
          calls. You can wait or cancel and retry.
        </div>
      )}

      {/* Outcome banners */}
      <OutcomeBanner
        status={status}
        reason={runDetail?.rejection_reason}
        errorMessage={runDetail?.error_message}
      />

      {/* In-progress progress indicator */}
      {inProgress && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="inline-block w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
          Agent is running…
        </div>
      )}

      {/* Reviewer output + approval UI */}
      {(status === "awaiting_approval" || status === "passed" || status === "rejected") &&
        runDetail?.review && (
          <div className="space-y-4">
            <div className="rounded-lg border border-border p-4 space-y-3">
              <div className="flex items-start justify-between gap-2">
                <h2 className="text-sm font-semibold">Reviewer Assessment</h2>
                <RiskBadge level={runDetail.review.risk_level} />
              </div>
              <p className="text-sm">{runDetail.review.summary}</p>
              {runDetail.review.risk_notes && (
                <p className="text-xs text-muted-foreground border-l-2 border-border pl-3">
                  {runDetail.review.risk_notes}
                </p>
              )}
              <div className="space-y-0.5">
                <p className="text-xs font-medium">PR title</p>
                <p className="text-sm font-mono bg-muted rounded px-2 py-1">
                  {runDetail.review.pr_title}
                </p>
              </div>
              {runDetail.review.pr_description && (
                <div className="space-y-0.5">
                  <p className="text-xs font-medium">Description</p>
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                    {runDetail.review.pr_description}
                  </p>
                </div>
              )}
            </div>

            {runDetail.diffs.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold">
                    Diffs ({runDetail.diffs.length} file
                    {runDetail.diffs.length !== 1 ? "s" : ""})
                  </h2>
                  <button
                    onClick={() => {
                      const patch = runDetail.diffs.map((d) => d.patch).join("\n");
                      navigator.clipboard.writeText(patch).then(() => {
                        addToast("Patch copied to clipboard", "success");
                      });
                    }}
                    className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    Copy patch
                  </button>
                </div>
                <DiffViewer diffs={runDetail.diffs} />
                {(status === "awaiting_approval" || status === "passed") && (
                  <p className="text-xs text-muted-foreground bg-muted/50 rounded-md px-3 py-2">
                    The diff above shows what the agents changed. Use{" "}
                    <span className="font-mono">Copy patch</span> to apply it
                    locally with{" "}
                    <code className="font-mono">git apply</code>. The sandbox
                    environment is cleaned up after approval.
                  </p>
                )}
              </div>
            )}

            {status === "awaiting_approval" && token && (
              <ApprovalPanel
                runId={runId}
                token={token}
                onApproved={handleApproved}
                onRejected={handleRejected}
              />
            )}
          </div>
        )}

      {/* Agent steps */}
      {runDetail && runDetail.agent_steps.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold">
            Agent Steps ({runDetail.agent_steps.length})
          </h2>
          <div className="space-y-2">
            {runDetail.agent_steps.map((step) => (
              <AgentStepCard key={step.id} step={step} />
            ))}
          </div>
        </div>
      )}

      {/* Loading skeleton while awaiting first data */}
      {!runDetail && !fetchError && (
        <div className="space-y-2">
          {[1, 2, 3].map((n) => (
            <div
              key={n}
              className="h-20 rounded-lg bg-muted/50 animate-pulse"
            />
          ))}
        </div>
      )}

      <LiveLogStream
        entries={timeline}
        title="Run Events"
        emptyText={
          isTerminal(status)
            ? "No live events recorded."
            : "Waiting for agent events…"
        }
      />
    </div>
  );
}

export function RunPageClient({ runId }: { runId: string }) {
  return <RunPageInner runId={runId} />;
}
