import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    listRepos: vi.fn(),
    getCostEstimate: vi.fn(),
  };
});

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    token: "test-token",
    user: { email: "t@t.com" },
    loading: false,
    logout: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

vi.mock("@/components/toast", () => ({
  useToast: () => ({ addToast: vi.fn() }),
  ToastProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

import { listRepos } from "@/lib/api-client";
import DashboardPage from "@/app/(app)/dashboard/page";

const mockListRepos = vi.mocked(listRepos);

const BASE_REPO = {
  id: "repo-1",
  name: "my-repo",
  clone_url: "https://github.com/x/y.git",
  default_branch: "main",
  error_message: null as string | null,
  created_at: new Date().toISOString(),
  chunk_count: 0,
};

beforeEach(() => {
  mockListRepos.mockReset();
});

describe("DashboardPage — RepoCard status consistency", () => {
  it("shows 'Indexing…' when status is cloning and chunk_count is 0", async () => {
    mockListRepos.mockResolvedValueOnce([
      { ...BASE_REPO, status: "cloning" },
    ]);
    render(<DashboardPage />);
    await waitFor(() =>
      expect(screen.queryByText(/indexing/i)).toBeInTheDocument(),
    );
  });

  it("does NOT show 'Indexing…' when status is failed (chunk_count=0)", async () => {
    mockListRepos.mockResolvedValueOnce([
      {
        ...BASE_REPO,
        status: "failed",
        error_message: "Clone failed: repository not found",
      },
    ]);
    render(<DashboardPage />);
    // Wait for loading skeleton to disappear (repo name appears)
    await waitFor(() =>
      expect(screen.getByText("my-repo")).toBeInTheDocument(),
    );
    expect(screen.queryByText(/indexing/i)).not.toBeInTheDocument();
  });

  it("shows error message when status is failed", async () => {
    mockListRepos.mockResolvedValueOnce([
      {
        ...BASE_REPO,
        status: "failed",
        error_message: "Clone failed: repository not found",
      },
    ]);
    render(<DashboardPage />);
    await waitFor(() =>
      expect(
        screen.getByText("Clone failed: repository not found"),
      ).toBeInTheDocument(),
    );
  });

  it("shows chunk count when status is ready", async () => {
    mockListRepos.mockResolvedValueOnce([
      { ...BASE_REPO, status: "ready", chunk_count: 142 },
    ]);
    render(<DashboardPage />);
    await waitFor(() =>
      expect(screen.getByText("142 chunks indexed")).toBeInTheDocument(),
    );
  });

  it("shows empty state when no repos exist", async () => {
    mockListRepos.mockResolvedValueOnce([]);
    render(<DashboardPage />);
    await waitFor(() =>
      expect(screen.getByText(/no repositories yet/i)).toBeInTheDocument(),
    );
  });
});
