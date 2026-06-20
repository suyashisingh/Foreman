"use client";

import { useEffect, useRef } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TimelineEntry {
  id: string;
  timestamp: string;
  text: string;
  variant?: "default" | "muted" | "success" | "warning" | "error";
}

export interface LiveLogStreamProps {
  entries: TimelineEntry[];
  title?: string;
  emptyText?: string;
}

// ---------------------------------------------------------------------------
// Styling
// ---------------------------------------------------------------------------

const VARIANT_CLASS: Record<NonNullable<TimelineEntry["variant"]>, string> = {
  default: "text-foreground",
  muted: "text-muted-foreground",
  success: "text-green-700 dark:text-green-400",
  warning: "text-amber-600 dark:text-amber-400",
  error: "text-red-600 dark:text-red-400",
};

function fmtTs(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LiveLogStream({
  entries,
  title = "Event Timeline",
  emptyText = "Waiting for events…",
}: LiveLogStreamProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);

  function onScroll() {
    const el = containerRef.current;
    if (!el) return;
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    isAtBottomRef.current = distFromBottom < 24;
  }

  useEffect(() => {
    if (isAtBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [entries]);

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="bg-muted/50 px-3 py-2 border-b border-border">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          {title}
        </p>
      </div>

      <div
        ref={containerRef}
        onScroll={onScroll}
        className="max-h-56 overflow-y-auto bg-background font-mono text-xs"
      >
        {entries.length === 0 ? (
          <p className="px-3 py-4 text-muted-foreground">{emptyText}</p>
        ) : (
          <div className="py-1">
            {entries.map((entry) => (
              <div
                key={entry.id}
                className={`flex gap-2 px-3 py-0.5 hover:bg-muted/40 ${
                  VARIANT_CLASS[entry.variant ?? "default"]
                }`}
              >
                <span className="shrink-0 text-muted-foreground select-none">
                  {fmtTs(entry.timestamp)}
                </span>
                <span className="break-all">{entry.text}</span>
              </div>
            ))}
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
