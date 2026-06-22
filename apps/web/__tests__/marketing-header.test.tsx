import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/",
}));

// Logged-out state
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    token: null,
    user: null,
    loading: false,
    logout: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

import { MarketingHeader } from "@/components/marketing-header";

describe("MarketingHeader (logged out)", () => {
  it("renders the Foreman logo link", () => {
    render(<MarketingHeader />);
    expect(screen.getByRole("link", { name: /foreman/i })).toBeInTheDocument();
  });

  it("includes Home, About, and Benchmark nav links", () => {
    render(<MarketingHeader />);
    expect(screen.getByRole("link", { name: /^home$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^about$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^benchmark$/i })).toBeInTheDocument();
  });

  it("shows 'Sign in' link pointing to /login", () => {
    render(<MarketingHeader />);
    const link = screen.getByRole("link", { name: /sign in/i });
    expect(link).toHaveAttribute("href", "/login");
  });

  it("shows 'Get started' link pointing to /register", () => {
    render(<MarketingHeader />);
    const link = screen.getByRole("link", { name: /get started/i });
    expect(link).toHaveAttribute("href", "/register");
  });

  it("includes a GitHub link", () => {
    render(<MarketingHeader />);
    expect(screen.getByRole("link", { name: /github/i })).toBeInTheDocument();
  });
});
