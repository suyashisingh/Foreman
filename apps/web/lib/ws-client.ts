// TODO (Day 5): Implement the WebSocket client.
// This module defines the message shape and client interface only.
// The real implementation is added when the real-time UI is built.

// ---------------------------------------------------------------------------
// Message types — mirror the WS protocol the FastAPI backend will emit.
// ---------------------------------------------------------------------------

/** An agent step was completed. */
export interface AgentStepMessage {
  type: "agent_step";
  runId: string;
  stepIndex: number;
  agent: string;
  input: string;
  output: string;
  toolCalls: ToolCallPayload[];
  tokenUsage: { prompt: number; completion: number; total: number };
  latencyMs: number;
}

/** A single tool was invoked and returned a result. */
export interface ToolCallMessage {
  type: "tool_call";
  runId: string;
  stepIndex: number;
  name: string;
  input: Record<string, unknown>;
  output: string;
}

/** A structured log line was emitted. */
export interface LogMessage {
  type: "log";
  runId: string;
  seq: number;
  timestamp: string;
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR";
  message: string;
}

/** A file diff is ready for review. */
export interface DiffMessage {
  type: "diff";
  runId: string;
  filePath: string;
  patch: string;
  approved: boolean;
}

/** Run reached a terminal state. */
export interface RunCompleteMessage {
  type: "run_complete";
  runId: string;
  status: "success" | "failure" | "cancelled";
}

export type WsMessage =
  | AgentStepMessage
  | ToolCallMessage
  | LogMessage
  | DiffMessage
  | RunCompleteMessage;

/** Inline type for tool call payloads within agent step messages. */
export interface ToolCallPayload {
  name: string;
  input: Record<string, unknown>;
  output?: string;
}

// ---------------------------------------------------------------------------
// Client interface
// ---------------------------------------------------------------------------

/** Handler invoked whenever a message arrives from the server. */
export type MessageHandler = (message: WsMessage) => void;

/** Handler invoked when the connection closes (with optional error). */
export type CloseHandler = (event: CloseEvent) => void;

/** Typed stub for the Foreman WebSocket client. */
export interface WsClient {
  /** Open a WebSocket connection for the given run. */
  connect(runId: string): void;
  /** Close the active connection, if any. */
  disconnect(): void;
  /** Register a handler that is called for every inbound message. */
  onMessage(handler: MessageHandler): void;
  /** Register a handler that is called when the connection closes. */
  onClose(handler: CloseHandler): void;
}

// ---------------------------------------------------------------------------
// Factory — not implemented yet
// ---------------------------------------------------------------------------

/**
 * Create a new WsClient instance.
 *
 * @throws {Error} Always — real implementation is added in Day 5.
 */
export function createWsClient(): WsClient {
  throw new Error(
    "createWsClient is not implemented yet. " +
      "The WebSocket client will be built in Day 5 (real-time UI).",
  );
}
