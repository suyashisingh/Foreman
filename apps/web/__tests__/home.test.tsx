import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HomePage from "@/app/(marketing)/page";

describe("HomePage", () => {
  it("renders the Foreman heading", () => {
    render(<HomePage />);
    expect(
      screen.getByRole("heading", { name: /foreman/i }),
    ).toBeInTheDocument();
  });

  it("renders 'Get started' as the primary CTA pointing to /register", () => {
    render(<HomePage />);
    const link = screen.getByRole("link", { name: /get started/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/register");
  });

  it("renders 'Sign in' link pointing to /login", () => {
    render(<HomePage />);
    const link = screen.getByRole("link", { name: /sign in/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/login");
  });

  it("renders the Benchmark Results link", () => {
    render(<HomePage />);
    expect(
      screen.getByRole("link", { name: /benchmark results/i }),
    ).toBeInTheDocument();
  });

  it("renders the How it works section", () => {
    render(<HomePage />);
    expect(
      screen.getByRole("heading", { name: /how it works/i }),
    ).toBeInTheDocument();
  });

  it("describes all four agents", () => {
    render(<HomePage />);
    expect(screen.getAllByText(/planner/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/coder/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/tester/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/reviewer/i).length).toBeGreaterThan(0);
  });
});
