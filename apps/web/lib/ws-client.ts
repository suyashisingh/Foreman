/**
 * WebSocket client for the Foreman run event stream.
 *
 * Protocol:
 *   1. Client connects to ws(s)://{host}/api/v1/runs/{id}/ws
 *   2. Client sends first message: {"token": "<jwt>"}
 *   3. Server validates JWT; closes with 4001 on failure, 4003 on ownership mismatch
 *   4. Server streams events until run reaches a terminal state:
 *        {"type": "agent_step",    "data": {...}, "timestamp": "..."}
 *        {"type": "status_change", "data": {"status": "..."}, "timestamp": "..."}
 *        {"type": "run_complete",  "data": {"status": "..."}, "timestamp": "..."}
 *   5. On terminal status, server sends run_complete then closes cleanly
 */

const _API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** Derive ws(s):// from http(s)://. */
function toWsUrl(httpBase: string, path: string): string {
  return httpBase.replace(/^http/, "ws") + path;
}

const MAX_RETRIES = 3;
const RETRY_DELAYS_MS = [1_000, 2_000, 4_000] as const;

/** Close codes that mean "don't retry" (auth/ownership failure). */
const NO_RECONNECT_CODES = new Set([4001, 4003]);

// ---------------------------------------------------------------------------
// Event data types — mirror what the backend publishes
// ---------------------------------------------------------------------------

export interface WsAgentStepData {
  agent: string;
  step_index: number;
  latency_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
}

export interface WsStatusChangeData {
  status: string;
}

export interface WsRunCompleteData {
  status: string;
}

export type WsConnectionState =
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected"
  | "error";

// ---------------------------------------------------------------------------
// Client options
// ---------------------------------------------------------------------------

export interface RunWsOptions {
  token: string;
  runId: string;
  onAgentStep?: (data: WsAgentStepData, timestamp: string) => void;
  onStatusChange?: (data: WsStatusChangeData, timestamp: string) => void;
  onRunComplete?: (data: WsRunCompleteData, timestamp: string) => void;
  onConnectionChange?: (state: WsConnectionState) => void;
  onError?: (message: string) => void;
}

// ---------------------------------------------------------------------------
// Client implementation
// ---------------------------------------------------------------------------

export class RunWsClient {
  private ws: WebSocket | null = null;
  private retryCount = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private intentionalClose = false;
  private terminated = false;

  constructor(private readonly opts: RunWsOptions) {}

  connect(): void {
    this._open();
  }

  disconnect(): void {
    this.intentionalClose = true;
    this._clearRetry();
    if (this.ws) {
      this.ws.close(1000, "client disconnect");
      this.ws = null;
    }
    this.opts.onConnectionChange?.("disconnected");
  }

  private _open(): void {
    const url = toWsUrl(
      _API_BASE,
      `/api/v1/runs/${this.opts.runId}/ws`,
    );

    this.opts.onConnectionChange?.(
      this.retryCount > 0 ? "reconnecting" : "connecting",
    );

    const ws = new WebSocket(url);
    this.ws = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ token: this.opts.token }));
      this.retryCount = 0;
      this.opts.onConnectionChange?.("connected");
    };

    ws.onmessage = (evt: MessageEvent<string>) => {
      let envelope: {
        type: string;
        data: Record<string, unknown>;
        timestamp: string;
      };
      try {
        envelope = JSON.parse(evt.data) as typeof envelope;
      } catch {
        return;
      }

      const { type, data, timestamp } = envelope;

      if (type === "agent_step") {
        this.opts.onAgentStep?.(data as unknown as WsAgentStepData, timestamp);
      } else if (type === "status_change") {
        const d = data as unknown as WsStatusChangeData;
        this.opts.onStatusChange?.(d, timestamp);
        // Backend closes after forwarding a terminal status_change, so we
        // track here to suppress reconnect on the subsequent onclose.
        if (_isTerminal(d.status)) {
          this.terminated = true;
        }
      } else if (type === "run_complete") {
        const d = data as unknown as WsRunCompleteData;
        this.opts.onRunComplete?.(d, timestamp);
        this.terminated = true;
      }
    };

    // onerror is always paired with onclose; handle reconnect logic there.
    ws.onerror = () => {};

    ws.onclose = (evt: CloseEvent) => {
      if (this.ws !== ws) return; // superseded by a newer connection
      this.ws = null;

      if (this.intentionalClose) {
        return; // caller called disconnect()
      }
      if (this.terminated) {
        this.opts.onConnectionChange?.("disconnected");
        return;
      }
      if (NO_RECONNECT_CODES.has(evt.code)) {
        this.opts.onConnectionChange?.("error");
        this.opts.onError?.(
          `WebSocket auth failure (${evt.code}): ${evt.reason || "check token"}`,
        );
        return;
      }

      if (this.retryCount >= MAX_RETRIES) {
        this.opts.onConnectionChange?.("error");
        this.opts.onError?.("Connection lost. Max reconnect attempts reached.");
        return;
      }

      const delay = RETRY_DELAYS_MS[this.retryCount] ?? 4_000;
      this.retryCount++;
      this.opts.onConnectionChange?.("reconnecting");
      this.retryTimer = setTimeout(() => this._open(), delay);
    };
  }

  private _clearRetry(): void {
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const _TERMINAL_STATUSES = new Set([
  "passed",
  "failed",
  "rejected",
  "awaiting_approval",
]);

function _isTerminal(status: string): boolean {
  return _TERMINAL_STATUSES.has(status);
}
