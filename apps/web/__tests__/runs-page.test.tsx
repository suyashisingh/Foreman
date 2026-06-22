import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    listRuns: vi.fn(),
  };
});

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    token: "test-token",
    user: { email: "t@t.com" },
    loading: false,
    logout: vi.fn(),
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

import { listRuns } from "@/lib/api-client";
import RunsPage from "@/app/(app)/runs/page";

const mockListRuns = vi.mocked(listRuns);

const SAMPLE_RUN = {
  id: "run-abc",
  repo_id: "repo-1",
  status: "passed",
  issue_text: "Add subtract method",
  created_at: new Date().toISOString(),
  completed_at: new Date().toISOString(),
  rejection_reason: null,
  error_message: null,
};

beforeEach(() => {
  mockListRuns.mockReset();
});

describe("RunsPage", () => {
  it("shows 'Run History' heading", async () => {
    mockListRuns.mockResolvedValueOnce([]);
    render(<RunsPage />);
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /run history/i }),
      ).toBeInTheDocument();
    });
  });

  it("shows empty state when there are no runs", async () => {
    mockListRuns.mockResolvedValueOnce([]);
    render(<RunsPage />);
    await waitFor(() => {
      expect(screen.getByText(/no runs yet/i)).toBeInTheDocument();
    });
  });

  it("renders each run's issue text and status badge", async () => {
    mockListRuns.mockResolvedValueOnce([
      SAMPLE_RUN,
      {
        ...SAMPLE_RUN,
        id: "run-def",
        status: "failed",
        issue_text: "Fix the parser bug",
        error_message: "Coder made no file changes",
      },
    ]);
    render(<RunsPage />);
    await waitFor(() => {
      expect(screen.getByText("Add subtract method")).toBeInTheDocument();
      expect(screen.getByText("Fix the parser bug")).toBeInTheDocument();
    });
    expect(screen.getByText("passed")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("links each run to its detail page", async () => {
    mockListRuns.mockResolvedValueOnce([SAMPLE_RUN]);
    render(<RunsPage />);
    await waitFor(() => {
      const link = screen.getByRole("link", { name: /add subtract method/i });
      expect(link).toHaveAttribute("href", "/runs/run-abc");
    });
  });

  it("shows error alert when listRuns rejects", async () => {
    mockListRuns.mockRejectedValueOnce(new Error("network failure"));
    render(<RunsPage />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByRole("alert").textContent).toContain(
        "Failed to load runs",
      );
    });
  });
});
