import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AgentStepCard } from "@/components/AgentStepCard";
import type { AgentStepOut } from "@/lib/api-client";

function makeStep(overrides: Partial<AgentStepOut> = {}): AgentStepOut {
  return {
    id: "step-1",
    agent: "planner",
    step_index: 0,
    input: { query: "add subtract method" },
    output: { steps: [{ description: "Modify calculator.py", action: "modify", file_path: "calculator.py" }], rationale: "Simple change." },
    tool_calls: [],
    token_usage: { input_tokens: 100, output_tokens: 50 },
    latency_ms: 1200,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe("AgentStepCard", () => {
  it("renders step index and agent name", () => {
    render(<AgentStepCard step={makeStep()} />);
    expect(screen.getByText(/Step 1/i)).toBeInTheDocument();
    expect(screen.getByText(/Planner/i)).toBeInTheDocument();
  });

  it("shows latency and token count", () => {
    render(<AgentStepCard step={makeStep({ latency_ms: 2500, token_usage: { input_tokens: 200, output_tokens: 100 } })} />);
    expect(screen.getByText(/2\.5s/)).toBeInTheDocument();
    expect(screen.getByText(/300.*tokens/i)).toBeInTheDocument();
  });

  it("renders coder agent with different label", () => {
    render(<AgentStepCard step={makeStep({ agent: "coder", step_index: 1, output: { explanation: "Added subtract." } })} />);
    expect(screen.getByText(/Coder/i)).toBeInTheDocument();
    expect(screen.getByText(/Step 2/i)).toBeInTheDocument();
  });

  it("renders reviewer summary in output", () => {
    render(
      <AgentStepCard
        step={makeStep({
          agent: "reviewer",
          output: {
            summary: "The implementation looks correct.",
            risk_level: "low",
            risk_notes: "",
            pr_title: "Add subtract",
            pr_description: "",
          },
        })}
      />,
    );
    expect(screen.getByText(/The implementation looks correct\./)).toBeInTheDocument();
  });

  it("shows 'Show details' toggle when input/output present", () => {
    render(<AgentStepCard step={makeStep()} />);
    const toggle = screen.getByText(/Show details/i);
    expect(toggle).toBeInTheDocument();
    fireEvent.click(toggle);
    expect(screen.getByText(/Hide details/i)).toBeInTheDocument();
  });

  it("shows tool call count badge when tool calls present", () => {
    render(
      <AgentStepCard
        step={makeStep({
          tool_calls: [
            { name: "read_file", input: { path: "foo.py" } },
            { name: "write_file", input: { path: "foo.py", content: "..." } },
          ],
        })}
      />,
    );
    expect(screen.getByText(/2 tool calls/)).toBeInTheDocument();
  });

  it("renders latency under 1000ms as ms", () => {
    render(<AgentStepCard step={makeStep({ latency_ms: 850 })} />);
    expect(screen.getByText(/850ms/)).toBeInTheDocument();
  });
});
