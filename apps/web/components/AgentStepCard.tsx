// TODO (Day 5): Populate with real data streamed from the WS client.
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

/** A single tool call emitted by an agent during a run. */
export interface ToolCall {
  name: string;
  input: Record<string, unknown>;
  output?: string;
}

/** Token usage counters returned by the LLM for a single step. */
export interface TokenUsage {
  prompt: number;
  completion: number;
  total: number;
}

/** Props mirror the `agent_steps` table schema (minus run_id / timestamps). */
export interface AgentStepCardProps {
  /** Zero-based index of this step within the run. */
  stepIndex: number;
  /** Name of the agent that produced this step. */
  agent: string;
  /** Prompt or context sent to the agent. */
  input: string;
  /** The agent's text response. */
  output: string;
  /** Tool calls made during this step, if any. */
  toolCalls: ToolCall[];
  /** Token usage breakdown for the underlying LLM call. */
  tokenUsage: TokenUsage;
  /** Wall-clock latency for this step in milliseconds. */
  latencyMs: number;
}

/** Renders a single agent step as a card shell. Real content added Day 5. */
export function AgentStepCard({
  stepIndex,
  agent,
  output,
  toolCalls,
  tokenUsage,
  latencyMs,
}: AgentStepCardProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">
            Step {stepIndex + 1} — {agent}
          </CardTitle>
          <div className="flex gap-2 text-xs text-muted-foreground">
            <span>{latencyMs} ms</span>
            <span>{tokenUsage.total} tokens</span>
            {toolCalls.length > 0 && (
              <Badge variant="secondary">{toolCalls.length} tool calls</Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground line-clamp-3">{output}</p>
      </CardContent>
    </Card>
  );
}
