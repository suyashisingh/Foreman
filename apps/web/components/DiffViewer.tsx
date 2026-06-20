"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, FileDiff } from "lucide-react";
import type { DiffOut } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Diff line parsing
// ---------------------------------------------------------------------------

type LineType = "add" | "remove" | "hunk" | "meta" | "context";

interface DiffLine {
  type: LineType;
  content: string;
  lineNum: number;
}

function parseLines(patch: string): { lines: DiffLine[]; adds: number; removes: number } {
  let adds = 0;
  let removes = 0;
  const lines: DiffLine[] = patch.split("\n").map((raw, i) => {
    let type: LineType = "context";
    if (raw.startsWith("+++") || raw.startsWith("---")) {
      type = "meta";
    } else if (raw.startsWith("@@")) {
      type = "hunk";
    } else if (raw.startsWith("+")) {
      type = "add";
      adds++;
    } else if (raw.startsWith("-")) {
      type = "remove";
      removes++;
    }
    return { type, content: raw, lineNum: i };
  });
  return { lines, adds, removes };
}

const LINE_CLASSES: Record<LineType, string> = {
  add: "bg-green-50 text-green-900 dark:bg-green-950/40 dark:text-green-200",
  remove: "bg-red-50 text-red-900 dark:bg-red-950/40 dark:text-red-200",
  hunk: "bg-blue-50/60 text-blue-700 dark:bg-blue-950/30 dark:text-blue-300 font-medium",
  meta: "text-muted-foreground",
  context: "text-foreground",
};

// ---------------------------------------------------------------------------
// Single file diff
// ---------------------------------------------------------------------------

interface FileDiffSectionProps {
  diff: DiffOut;
  defaultOpen?: boolean;
}

function FileDiffSection({ diff, defaultOpen = true }: FileDiffSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const { lines, adds, removes } = parseLines(diff.patch);

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 bg-muted/50 hover:bg-muted text-left transition-colors"
        aria-expanded={open}
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <FileDiff size={13} className="text-muted-foreground shrink-0" />
        <span className="font-mono text-xs font-medium truncate flex-1">
          {diff.file_path}
        </span>
        <div className="flex items-center gap-2 shrink-0 text-xs">
          {adds > 0 && (
            <span className="text-green-700 dark:text-green-400 font-medium">
              +{adds}
            </span>
          )}
          {removes > 0 && (
            <span className="text-red-600 dark:text-red-400 font-medium">
              -{removes}
            </span>
          )}
          {diff.approved && (
            <span className="text-xs bg-green-100 text-green-700 border border-green-200 rounded-full px-2 py-0.5">
              Approved
            </span>
          )}
        </div>
      </button>

      {/* Diff content */}
      {open && (
        <div className="overflow-x-auto">
          {diff.patch ? (
            <div className="font-mono text-xs leading-5">
              {lines.map((line) => (
                <div
                  key={line.lineNum}
                  className={`px-3 whitespace-pre ${LINE_CLASSES[line.type]}`}
                >
                  {line.content || " "}
                </div>
              ))}
            </div>
          ) : (
            <p className="px-4 py-3 text-xs text-muted-foreground">
              No diff content.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Multi-file viewer (exported)
// ---------------------------------------------------------------------------

export interface DiffViewerProps {
  diffs: DiffOut[];
}

export function DiffViewer({ diffs }: DiffViewerProps) {
  if (diffs.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No diffs to display.</p>
    );
  }

  return (
    <div className="space-y-3">
      {diffs.map((diff, idx) => (
        <FileDiffSection
          key={diff.id}
          diff={diff}
          defaultOpen={idx === 0}
        />
      ))}
    </div>
  );
}
