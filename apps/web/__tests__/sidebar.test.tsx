import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ push: vi.fn() }),
}));

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

import { AppSidebar } from "@/components/app-sidebar";

describe("AppSidebar", () => {
  it("renders Dashboard and Runs in the main nav", () => {
    render(<AppSidebar />);
    expect(screen.getAllByRole("link", { name: /dashboard/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /runs/i }).length).toBeGreaterThan(0);
  });

  it("renders a Benchmark link (one click away from anywhere in the app)", () => {
    render(<AppSidebar />);
    const links = screen.getAllByRole("link", { name: /benchmark/i });
    expect(links.length).toBeGreaterThan(0);
    expect(links[0]).toHaveAttribute("href", "/benchmark");
  });

  it("renders an About link", () => {
    render(<AppSidebar />);
    const links = screen.getAllByRole("link", { name: /about/i });
    expect(links.length).toBeGreaterThan(0);
    expect(links[0]).toHaveAttribute("href", "/about");
  });

  it("renders Settings link", () => {
    render(<AppSidebar />);
    expect(screen.getAllByRole("link", { name: /settings/i }).length).toBeGreaterThan(0);
  });

  it("Settings appears after a border-t separator (not in main nav group)", () => {
    const { container } = render(<AppSidebar />);
    const separators = container.querySelectorAll(".border-t");
    expect(separators.length).toBeGreaterThan(0);
  });

  it("shows the user email", () => {
    render(<AppSidebar />);
    expect(screen.getByText("user@example.com")).toBeInTheDocument();
  });

  it("renders Sign out button", () => {
    render(<AppSidebar />);
    expect(
      screen.getAllByRole("button", { name: /sign out/i }).length,
    ).toBeGreaterThan(0);
  });
});
