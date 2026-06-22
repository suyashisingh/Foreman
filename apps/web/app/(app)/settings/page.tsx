"use client";

import { useEffect, useState } from "react";
import { Info } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import { getSystemStatus } from "@/lib/api-client";
import type { SystemStatusOut } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Status badge (separate from run StatusBadge — these are infra checks)
// ---------------------------------------------------------------------------

function ServiceBadge({ ok }: { ok: boolean }) {
  return (
    <span
      className={`text-xs font-medium rounded-full px-2.5 py-0.5 ${
        ok
          ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200"
          : "bg-secondary text-secondary-foreground border border-border"
      }`}
    >
      {ok ? "OK" : "Not configured"}
    </span>
  );
}

function StatusTable({ status }: { status: SystemStatusOut }) {
  const rows = [
    { label: "Database", ok: status.database_ok },
    { label: "Redis", ok: status.redis_ok },
    { label: "Gemini API key", ok: status.gemini_key_configured },
    { label: "Voyage AI key", ok: status.voyage_key_configured },
    { label: "E2B API key", ok: status.e2b_key_configured },
  ];

  return (
    <div className="space-y-2">
      {rows.map(({ label, ok }) => (
        <div
          key={label}
          className="flex items-center justify-between py-1.5 border-b border-border last:border-0"
        >
          <span className="text-sm">{label}</span>
          <ServiceBadge ok={ok} />
        </div>
      ))}
      <div className="flex items-center justify-between py-1.5">
        <span className="text-sm">Model</span>
        <code className="text-xs font-mono bg-muted px-2 py-0.5 rounded">
          {status.gemini_model}
        </code>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Settings page
// ---------------------------------------------------------------------------

export default function SettingsPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState<SystemStatusOut | null>(null);

  useEffect(() => {
    getSystemStatus()
      .then(setStatus)
      .catch(() => {}); // non-fatal — show empty state
  }, []);

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 space-y-8">
      <div>
        <h1 className="font-heading text-2xl font-bold">Settings</h1>
        {user && (
          <p className="text-sm text-muted-foreground mt-1">{user.email}</p>
        )}
      </div>

      {/* System status */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">System Status</CardTitle>
          <CardDescription>
            Infrastructure connectivity and API key configuration.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {status ? (
            <StatusTable status={status} />
          ) : (
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((n) => (
                <div
                  key={n}
                  className="h-8 rounded bg-muted/50 animate-pulse"
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Rate limit notice */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Info size={14} className="text-muted-foreground" />
            Gemini Free-Tier Rate Limit
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>
            The Gemini free tier allows ~15 requests per minute. The agent
            pipeline makes several LLM calls per run (Planner, Coder
            iterations, Tester, Reviewer), so back-to-back runs can hit this
            limit.
          </p>
          <p>
            If you see 429 errors in a run, wait 60 seconds before submitting
            another. Paid tier accounts have much higher quotas and can process
            multiple runs concurrently.
          </p>
          {status && (
            <p className="text-xs pt-1">
              Current model:{" "}
              <code className="font-mono bg-muted px-1 rounded">
                {status.gemini_model}
              </code>
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
