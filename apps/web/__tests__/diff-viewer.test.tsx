import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DiffViewer } from "@/components/DiffViewer";
import type { DiffOut } from "@/lib/api-client";

const PATCH = `--- a/calculator.py
+++ b/calculator.py
@@ -1,5 +1,9 @@
 class Calculator:
     def add(self, a: int, b: int) -> int:
         return a + b
+
+    def subtract(self, a: int, b: int) -> int:
+        return a - b`;

function makeDiff(overrides: Partial<DiffOut> = {}): DiffOut {
  return {
    id: "diff-1",
    file_path: "calculator.py",
    patch: PATCH,
    approved: false,
    ...overrides,
  };
}

describe("DiffViewer", () => {
  it("renders file path", () => {
    render(<DiffViewer diffs={[makeDiff()]} />);
    expect(screen.getByText("calculator.py")).toBeInTheDocument();
  });

  it("shows addition count in header", () => {
    render(<DiffViewer diffs={[makeDiff()]} />);
    expect(screen.getByText("+3")).toBeInTheDocument();
  });

  it("shows removal count when present", () => {
    const patchWithRemoval = PATCH + "\n-    pass";
    render(<DiffViewer diffs={[makeDiff({ patch: patchWithRemoval })]} />);
    expect(screen.getByText("-1")).toBeInTheDocument();
  });

  it("shows 'Approved' badge when approved=true", () => {
    render(<DiffViewer diffs={[makeDiff({ approved: true })]} />);
    expect(screen.getByText("Approved")).toBeInTheDocument();
  });

  it("renders empty message when no diffs", () => {
    render(<DiffViewer diffs={[]} />);
    expect(screen.getByText(/No diffs to display/i)).toBeInTheDocument();
  });

  it("collapses and expands file section on click", () => {
    render(<DiffViewer diffs={[makeDiff()]} />);
    // First file is open by default — diff content visible
    expect(screen.getByText(/\+\+\+ b\/calculator\.py/)).toBeInTheDocument();

    // Toggle closed
    fireEvent.click(screen.getByRole("button", { name: /calculator\.py/i }));
    expect(screen.queryByText(/\+\+\+ b\/calculator\.py/)).not.toBeInTheDocument();
  });

  it("renders multiple files", () => {
    render(
      <DiffViewer
        diffs={[
          makeDiff({ id: "d1", file_path: "a.py" }),
          makeDiff({ id: "d2", file_path: "b.py", approved: true }),
        ]}
      />,
    );
    expect(screen.getByText("a.py")).toBeInTheDocument();
    expect(screen.getByText("b.py")).toBeInTheDocument();
  });
});
