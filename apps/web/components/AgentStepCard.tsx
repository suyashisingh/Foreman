"use client";

import { useState } from "react";
import {
  BrainCircuit,
  Code2,
  FlaskConical,
  Eye,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { AgentStepOut } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Agent config
// ---------------------------------------------------------------------------

const AGENT_CONFIG = {
  planner: {
    label: "Planner",
    Icon: BrainCircuit,
    pill: "bg-blue-100 text-blue-800 border border-blue-200",
    border: "border-l-blue-400",
  },
  coder: {
    label: "Coder",
    Icon: Code2,
    pill: "bg-purple-100 text-purple-800 border border-purple-200",
    border: "border-l-purple-400",
  },
  tester: {
    label: "Tester",
    Icon: FlaskConical,
    pill: "bg-orange-100 text-orange-800 border border-orange-200",
    border: "border-l-orange-400",
  },
  reviewer: {
    label: "Reviewer",
    Icon: Eye,
    pill: "bg-green-100 text-green-800 border border-green-200",
    border: "border-l-green-400",
  },
} as const satisfies Record<
  string,
  { label: string; Icon: React.ElementType; pill: string; border: string }
>;

const FALLBACK_CONFIG = {
  label: "Agent",
  Icon: BrainCircuit,
  pill: "bg-secondary text-secondary-foreground border border-border",
  border: "border-l-border",
};

function getConfig(agent: string) {
  return (
    (AGENT_CONFIG as Record<string, (typeof AGENT_CONFIG)[keyof typeof AGENT_CONFIG]>)[agent] ??
    FALLBACK_CONFIG
  );
}

// ---------------------------------------------------------------------------
// Token / latency helpers
// ---------------------------------------------------------------------------

function fmtTokens(usage: Record<string, unknown>): string {
  const inp = (usage.input_tokens as number | undefined) ?? 0;
  const out = (usage.output_tokens as number | undefined) ?? 0;
  const total = inp + out;
  return total > 0 ? `${total.toLocaleString()} tokens` : "—";
}

function fmtLatency(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

/** Best-effort one-line summary for the card collapsed view. */
function extractSummary(agent: string, output: Record<string, unknown>): string {
  if (agent === "planner") {
    const steps = output.steps as { description?: string }[] | undefined;
    if (Array.isArray(steps) && steps.length > 0) {
      return `${steps.length}-step plan — ${steps[0].description ?? ""}`;
    }
  }
  if (agent === "reviewer") {
    const summary = output.summary as string | undefined;
    if (summary) return summary;
  }
  if (agent === "coder") {
    const explanation = output.explanation as string | undefined;
    if (explanation) return explanation;
  }
  if (agent === "tester") {
    const passed = output.passed as boolean | undefined;
    if (passed !== undefined) return passed ? "Tests passed ✓" : "Tests failed ✗";
  }
  // Fallback: first string value
  const first = Object.values(output).find((v) => typeof v === "string" && (v as string).length > 0);
  return typeof first === "string" ? first : "—";
}

// ---------------------------------------------------------------------------
// Expandable JSON block
// ---------------------------------------------------------------------------

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  const [open, setOpen] = useState(false);
  const json = JSON.stringify(value, null, 2);
  const preview = json.length > 120 ? json.slice(0, 120) + "…" : json;

  return (
    <div className="border border-border rounded text-xs overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-1 px-3 py-1.5 text-left bg-muted/50 hover:bg-muted transition-colors font-medium text-muted-foreground"
        aria-expanded={open}
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        {label}
        {!open && (
          <span className="ml-1 font-normal opacity-60 truncate">{preview}</span>
        )}
      </button>
      {open && (
        <pre className="px-3 py-2 bg-muted/30 overflow-x-auto font-mono text-xs leading-relaxed">
          {json}
        </pre>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export type { AgentStepOut };

export interface AgentStepCardProps {
  step: AgentStepOut;
}

export function AgentStepCard({ step }: AgentStepCardProps) {
  const [expanded, setExpanded] = useState(false);
  const { label, Icon, pill, border } = getConfig(step.agent);
  const summary = extractSummary(step.agent, step.output);
  const hasDetails =
    Object.keys(step.input).length > 0 ||
    Object.keys(step.output).length > 0 ||
    step.tool_calls.length > 0;

  return (
    <Card className={`border-l-4 ${border}`}>
      <CardHeader className="pb-2 pt-3 px-4">
        <div className="flex items-start justify-between gap-3">
          {/* Left: agent pill + step index */}
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${pill}`}
            >
              <Icon size={11} />
              {label}
            </span>
            <span className="text-xs text-muted-foreground">
              Step {step.step_index + 1}
            </span>
          </div>

          {/* Right: latency + tokens */}
          <div className="flex items-center gap-3 text-xs text-muted-foreground shrink-0">
            <span>{fmtLatency(step.latency_ms)}</span>
            <span>{fmtTokens(step.token_usage)}</span>
            {step.tool_calls.length > 0 && (
              <span className="text-xs bg-secondary rounded px-1.5 py-0.5">
                {step.tool_calls.length} tool call{step.tool_calls.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>

        {/* Summary line */}
        <p className="text-sm text-foreground mt-1.5 line-clamp-2 leading-snug">
          {summary}
        </p>
      </CardHeader>

      {hasDetails && (
        <CardContent className="px-4 pb-3 space-y-2">
          <button
            onClick={() => setExpanded((e) => !e)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            aria-expanded={expanded}
          >
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {expanded ? "Hide details" : "Show details"}
          </button>

          {expanded && (
            <div className="space-y-2 pt-1">
              {Object.keys(step.input).length > 0 && (
                <JsonBlock label="Input" value={step.input} />
              )}
              {Object.keys(step.output).length > 0 && (
                <JsonBlock label="Output" value={step.output} />
              )}
              {step.tool_calls.length > 0 && (
                <JsonBlock label={`Tool calls (${step.tool_calls.length})`} value={step.tool_calls} />
              )}
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}
