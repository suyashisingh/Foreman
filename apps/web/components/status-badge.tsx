"use client";

import { cn } from "@/lib/utils";

interface StatusCfg {
  label: string;
  className: string;
  pulse?: boolean;
}

// Single color/icon language for every status surface in the app.
// ready/passed = green, in-progress/pending = blue with pulse, failed/rejected = red,
// awaiting_approval = amber.
const STATUS_CONFIG: Record<string, StatusCfg> = {
  // Shared terminal
  passed: {
    label: "Passed",
    className:
      "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200",
  },
  failed: { label: "Failed", className: "bg-destructive/10 text-destructive" },
  rejected: {
    label: "Rejected",
    className: "bg-destructive/10 text-destructive",
  },
  // Shared idle
  pending: {
    label: "Pending",
    className: "bg-secondary text-secondary-foreground",
  },
  // Repo-specific in-progress
  cloning: {
    label: "Cloning…",
    className:
      "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200",
    pulse: true,
  },
  chunking: {
    label: "Chunking…",
    className:
      "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200",
    pulse: true,
  },
  embedding: {
    label: "Embedding…",
    className:
      "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200",
    pulse: true,
  },
  ready: {
    label: "Ready",
    className:
      "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200",
  },
  // Run-specific in-progress
  planning: {
    label: "Planning…",
    className:
      "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200",
    pulse: true,
  },
  coding: {
    label: "Coding…",
    className:
      "bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-200",
    pulse: true,
  },
  testing: {
    label: "Testing…",
    className:
      "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200",
    pulse: true,
  },
  reviewing: {
    label: "Reviewing…",
    className:
      "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200",
    pulse: true,
  },
  awaiting_approval: {
    label: "Awaiting Approval",
    className:
      "bg-amber-100 text-amber-900 border border-amber-300 dark:bg-amber-900/30 dark:text-amber-200",
  },
  cancelled: {
    label: "Cancelled",
    className:
      "bg-secondary text-secondary-foreground border border-border",
  },
};

export function StatusBadge({
  status,
  className,
}: {
  status: string;
  className?: string;
}) {
  const cfg: StatusCfg = STATUS_CONFIG[status] ?? {
    label: status,
    className: "bg-secondary text-secondary-foreground",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
        cfg.className,
        className,
      )}
    >
      {cfg.pulse && (
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-current animate-pulse shrink-0" />
      )}
      {cfg.label}
    </span>
  );
}
