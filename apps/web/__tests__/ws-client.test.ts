import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { RunWsClient } from "@/lib/ws-client";
import type { WsConnectionState } from "@/lib/ws-client";

// ---------------------------------------------------------------------------
// Mock WebSocket
// ---------------------------------------------------------------------------

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  url: string;
  readyState = 0; // CONNECTING
  onopen: ((e: Event) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;

  sentMessages: string[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sentMessages.push(data);
  }

  close(code = 1000, reason = "") {
    this.readyState = 3; // CLOSED
    this.onclose?.({ code, reason } as CloseEvent);
  }

  // Test helpers
  simulateOpen() {
    this.readyState = 1; // OPEN
    this.onopen?.(new Event("open"));
  }

  simulateMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }

  simulateClose(code = 1000, reason = "") {
    this.readyState = 3;
    this.onclose?.({ code, reason } as CloseEvent);
  }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket);
});

afterEach(() => {
  vi.restoreAllMocks();
});

function latestWs(): MockWebSocket {
  const ws = MockWebSocket.instances.at(-1);
  if (!ws) throw new Error("No MockWebSocket instance");
  return ws;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("RunWsClient.connect", () => {
  it("creates a WebSocket to the correct URL", () => {
    const client = new RunWsClient({ token: "tok", runId: "run-1" });
    client.connect();
    const ws = latestWs();
    expect(ws.url).toContain("/api/v1/runs/run-1/ws");
    expect(ws.url).toMatch(/^ws/);
  });

  it("sends auth handshake on open", () => {
    const client = new RunWsClient({ token: "my-token", runId: "run-1" });
    client.connect();
    const ws = latestWs();
    ws.simulateOpen();
    expect(ws.sentMessages).toHaveLength(1);
    const msg = JSON.parse(ws.sentMessages[0]) as { token: string };
    expect(msg.token).toBe("my-token");
  });

  it("fires onConnectionChange('connected') after open", () => {
    const states: WsConnectionState[] = [];
    const client = new RunWsClient({
      token: "tok",
      runId: "run-1",
      onConnectionChange: (s) => states.push(s),
    });
    client.connect();
    latestWs().simulateOpen();
    expect(states).toContain("connected");
  });
});

describe("RunWsClient message dispatch", () => {
  it("calls onAgentStep for agent_step messages", () => {
    const onAgentStep = vi.fn();
    const client = new RunWsClient({ token: "tok", runId: "run-1", onAgentStep });
    client.connect();
    const ws = latestWs();
    ws.simulateOpen();
    ws.simulateMessage({
      type: "agent_step",
      data: { agent: "planner", step_index: 0, latency_ms: 500, input_tokens: 100, output_tokens: 50 },
      timestamp: "2026-01-01T00:00:00Z",
    });
    expect(onAgentStep).toHaveBeenCalledOnce();
    expect(onAgentStep.mock.calls[0][0]).toMatchObject({ agent: "planner", step_index: 0 });
  });

  it("calls onStatusChange for status_change messages", () => {
    const onStatusChange = vi.fn();
    const client = new RunWsClient({ token: "tok", runId: "run-1", onStatusChange });
    client.connect();
    const ws = latestWs();
    ws.simulateOpen();
    ws.simulateMessage({ type: "status_change", data: { status: "planning" }, timestamp: "2026-01-01T00:00:00Z" });
    expect(onStatusChange).toHaveBeenCalledOnce();
    expect(onStatusChange.mock.calls[0][0]).toEqual({ status: "planning" });
  });

  it("calls onRunComplete for run_complete messages", () => {
    const onRunComplete = vi.fn();
    const client = new RunWsClient({ token: "tok", runId: "run-1", onRunComplete });
    client.connect();
    const ws = latestWs();
    ws.simulateOpen();
    ws.simulateMessage({ type: "run_complete", data: { status: "awaiting_approval" }, timestamp: "2026-01-01T00:00:00Z" });
    expect(onRunComplete).toHaveBeenCalledOnce();
  });
});

describe("RunWsClient.disconnect", () => {
  it("closes the WebSocket and fires disconnected state", () => {
    const states: WsConnectionState[] = [];
    const client = new RunWsClient({
      token: "tok",
      runId: "run-1",
      onConnectionChange: (s) => states.push(s),
    });
    client.connect();
    latestWs().simulateOpen();
    client.disconnect();
    expect(states).toContain("disconnected");
  });

  it("does not reconnect after intentional disconnect", () => {
    vi.useFakeTimers();
    const client = new RunWsClient({ token: "tok", runId: "run-1" });
    client.connect();
    const ws = latestWs();
    ws.simulateOpen();
    client.disconnect();
    // Advance timers — no reconnect attempt expected
    vi.advanceTimersByTime(10_000);
    expect(MockWebSocket.instances).toHaveLength(1);
    vi.useRealTimers();
  });
});

describe("RunWsClient reconnect", () => {
  it("does NOT reconnect on auth failure (4001)", () => {
    vi.useFakeTimers();
    const states: WsConnectionState[] = [];
    const client = new RunWsClient({
      token: "tok",
      runId: "run-1",
      onConnectionChange: (s) => states.push(s),
    });
    client.connect();
    latestWs().simulateOpen();
    latestWs().simulateClose(4001, "auth failure");
    vi.advanceTimersByTime(10_000);
    expect(MockWebSocket.instances).toHaveLength(1); // no retry
    expect(states).toContain("error");
    vi.useRealTimers();
  });

  it("does NOT reconnect after run_complete", () => {
    vi.useFakeTimers();
    const client = new RunWsClient({ token: "tok", runId: "run-1" });
    client.connect();
    const ws = latestWs();
    ws.simulateOpen();
    ws.simulateMessage({ type: "run_complete", data: { status: "passed" }, timestamp: "2026-01-01T00:00:00Z" });
    ws.simulateClose(1000, "server closed");
    vi.advanceTimersByTime(10_000);
    expect(MockWebSocket.instances).toHaveLength(1); // no retry
    vi.useRealTimers();
  });
});
