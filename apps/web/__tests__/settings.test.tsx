import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    getSystemStatus: vi.fn(),
  };
});

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    token: "test-token",
    user: { email: "user@example.com" },
    loading: false,
    logout: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

import { getSystemStatus } from "@/lib/api-client";
import SettingsPage from "@/app/(app)/settings/page";

const mockGetSystemStatus = vi.mocked(getSystemStatus);

const OK_STATUS = {
  database_ok: true,
  redis_ok: true,
  gemini_key_configured: true,
  voyage_key_configured: true,
  e2b_key_configured: true,
  gemini_model: "gemini-2.5-flash",
};

beforeEach(() => {
  mockGetSystemStatus.mockReset();
});

describe("SettingsPage", () => {
  it("renders the Settings heading", async () => {
    mockGetSystemStatus.mockResolvedValueOnce(OK_STATUS);
    render(<SettingsPage />);
    expect(screen.getByRole("heading", { name: /settings/i })).toBeInTheDocument();
  });

  it("shows the user email", async () => {
    mockGetSystemStatus.mockResolvedValueOnce(OK_STATUS);
    render(<SettingsPage />);
    expect(screen.getByText("user@example.com")).toBeInTheDocument();
  });

  it("renders status badges after data loads", async () => {
    mockGetSystemStatus.mockResolvedValueOnce(OK_STATUS);
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Database")).toBeInTheDocument();
      expect(screen.getByText("Redis")).toBeInTheDocument();
      expect(screen.getByText("Gemini API key")).toBeInTheDocument();
    });
  });

  it("shows model name after data loads", async () => {
    mockGetSystemStatus.mockResolvedValueOnce(OK_STATUS);
    render(<SettingsPage />);
    await waitFor(() => {
      // Model name appears in both the status table and the rate-limit note
      expect(screen.getAllByText("gemini-2.5-flash").length).toBeGreaterThan(0);
    });
  });

  it("renders the rate limit notice", async () => {
    mockGetSystemStatus.mockResolvedValueOnce(OK_STATUS);
    render(<SettingsPage />);
    expect(screen.getByText(/gemini free.tier rate limit/i)).toBeInTheDocument();
  });

  it("shows OK badges when all services are healthy", async () => {
    mockGetSystemStatus.mockResolvedValueOnce(OK_STATUS);
    render(<SettingsPage />);
    await waitFor(() => {
      const okBadges = screen.getAllByText("OK");
      expect(okBadges.length).toBe(5); // db, redis, gemini key, voyage key, e2b key
    });
  });

  it("shows 'Not configured' when a service is unhealthy", async () => {
    mockGetSystemStatus.mockResolvedValueOnce({
      ...OK_STATUS,
      redis_ok: false,
      voyage_key_configured: false,
    });
    render(<SettingsPage />);
    await waitFor(() => {
      const notCfg = screen.getAllByText("Not configured");
      expect(notCfg.length).toBe(2);
    });
  });
});
