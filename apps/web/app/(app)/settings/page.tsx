"use client";

import { useEffect, useState } from "react";
import { Info } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import { getSystemStatus } from "@/lib/api-client";
import type { SystemStatusOut } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Service status badge
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

// ---------------------------------------------------------------------------
// Individual service cards
// ---------------------------------------------------------------------------

function StatusCard({ label, ok }: { label: string; ok: boolean }) {
  return (
    <Card size="sm">
      <CardContent className="flex items-center justify-between py-1">
        <span className="text-sm font-medium">{label}</span>
        <ServiceBadge ok={ok} />
      </CardContent>
    </Card>
  );
}

function ModelCard({ model }: { model: string }) {
  return (
    <Card size="sm">
      <CardContent className="flex items-center justify-between py-1">
        <span className="text-sm font-medium">Model</span>
        <code className="text-xs font-mono bg-muted px-2 py-0.5 rounded">
          {model}
        </code>
      </CardContent>
    </Card>
  );
}

function StatusSkeleton() {
  return (
    <div className="space-y-2">
      {[1, 2, 3, 4, 5, 6].map((n) => (
        <div key={n} className="h-[52px] rounded-xl bg-muted/50 animate-pulse" />
      ))}
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

  const services = status
    ? [
        { label: "Database", ok: status.database_ok },
        { label: "Redis", ok: status.redis_ok },
        { label: "Gemini API key", ok: status.gemini_key_configured },
        { label: "Voyage AI key", ok: status.voyage_key_configured },
        { label: "E2B API key", ok: status.e2b_key_configured },
      ]
    : [];

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 space-y-8">
      <div>
        <h1 className="font-heading text-2xl font-bold">Settings</h1>
        {user && (
          <p className="text-sm text-muted-foreground mt-1">{user.email}</p>
        )}
      </div>

      {/* System status — each service is its own card */}
      <section className="space-y-3">
        <div>
          <h2 className="text-base font-semibold">System Status</h2>
          <p className="text-sm text-muted-foreground">
            Infrastructure connectivity and API key configuration.
          </p>
        </div>

        {status ? (
          <div className="space-y-2">
            {services.map(({ label, ok }) => (
              <StatusCard key={label} label={label} ok={ok} />
            ))}
            <ModelCard model={status.gemini_model} />
          </div>
        ) : (
          <StatusSkeleton />
        )}
      </section>

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
