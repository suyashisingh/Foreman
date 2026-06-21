"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, AlertCircle, CheckCircle2, XCircle } from "lucide-react";
import { AuthGuard } from "@/components/auth-guard";
import { AgentStepCard } from "@/components/AgentStepCard";
import { DiffViewer } from "@/components/DiffViewer";
import { LiveLogStream } from "@/components/LiveLogStream";
import type { TimelineEntry } from "@/components/LiveLogStream";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-context";
import { getRun, approveRun, rejectRun, ApiError } from "@/lib/api-client";
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

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const STATUS_STYLE: Record<
  string,
  { label: string; cls: string; ring?: string }
> = {
  pending: { label: "Pending", cls: "bg-secondary text-secondary-foreground" },
  planning: { label: "Planning…", cls: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200" },
  coding: { label: "Coding…", cls: "bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-200" },
  testing: { label: "Testing…", cls: "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200" },
  reviewing: { label: "Reviewing…", cls: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200" },
  awaiting_approval: {
    label: "Awaiting Approval",
    cls: "bg-amber-100 text-amber-900 border border-amber-300 dark:bg-amber-900/30 dark:text-amber-200",
    ring: "ring-2 ring-amber-300",
  },
  passed: { label: "Passed", cls: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200" },
  failed: { label: "Failed", cls: "bg-destructive/10 text-destructive" },
  rejected: { label: "Rejected", cls: "bg-destructive/10 text-destructive" },
};

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_STYLE[status] ?? { label: status, cls: "bg-secondary text-secondary-foreground" };
  return (
    <span
      className={`inline-block rounded-full px-3 py-0.5 text-sm font-medium ${cfg.cls} ${cfg.ring ?? ""}`}
    >
      {cfg.label}
    </span>
  );
}

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
      onApproved();
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        setError(
          "This run is no longer awaiting approval — it may have already been decided.",
        );
      } else {
        setError(err instanceof ApiError ? err.detail : "Approval failed.");
      }
      setAction("idle");
    }
  }

  async function handleReject() {
    setAction("rejecting");
    setError(null);
    try {
      await rejectRun(token, runId, reason || undefined);
      onRejected(reason);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        setError(
          "This run is no longer awaiting approval — it may have already been decided.",
        );
      } else {
        setError(err instanceof ApiError ? err.detail : "Rejection failed.");
      }
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
  return null;
}

// ---------------------------------------------------------------------------
// Main client component
// ---------------------------------------------------------------------------

function RunPageInner({ runId }: { runId: string }) {
  const { token } = useAuth();

  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [connState, setConnState] = useState<WsConnectionState>("connecting");
  const [connError, setConnError] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [liveStatus, setLiveStatus] = useState<string>("pending");

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

  // Single effect: initial REST load → then WS (if not terminal)
  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    let wsClient: RunWsClient | null = null;

    async function init() {
      // 1. Load initial run state
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

      // 2. Skip WS if run already terminal
      if (isTerminal(detail.status)) {
        setConnState("disconnected");
        return;
      }

      // 3. Connect WS — do a re-fetch after connect to catch any events that
      //    happened between the REST load and the WS subscribe.
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
          // Re-fetch for full step data (input/output/tool_calls)
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
          // For awaiting_approval, re-fetch to get review + diffs
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

      // Brief re-fetch to catch anything that happened between step 1 and WS subscribe
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

  // Approve / reject handlers — update local state without a refetch
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

  // ---- Render ---------------------------------------------------------------

  if (fetchError) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-10">
        <p className="text-sm text-destructive">{fetchError}</p>
        <Link href="/dashboard" className="text-sm underline mt-2 inline-block">
          ← Dashboard
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
              href="/dashboard"
              className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft size={13} />
              Dashboard
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
      </div>

      {/* Connection error banner (non-fatal) */}
      {connState === "error" && connError && (
        <div className="rounded-md bg-destructive/10 border border-destructive/30 px-4 py-2 text-sm text-destructive flex items-center gap-2">
          <AlertCircle size={14} />
          {connError} — live updates paused. Refresh the page to reconnect.
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

            {/* Diffs */}
            {runDetail.diffs.length > 0 && (
              <div className="space-y-2">
                <h2 className="text-sm font-semibold">
                  Diffs ({runDetail.diffs.length} file
                  {runDetail.diffs.length !== 1 ? "s" : ""})
                </h2>
                <DiffViewer diffs={runDetail.diffs} />
              </div>
            )}

            {/* Approve / Reject */}
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

      {/* Event timeline */}
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
  return (
    <AuthGuard>
      <RunPageInner runId={runId} />
    </AuthGuard>
  );
}
