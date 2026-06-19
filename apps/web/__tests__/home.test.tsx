import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HomePage from "@/app/page";

describe("HomePage", () => {
  it("renders without crashing and displays the Foreman heading", () => {
    render(<HomePage />);
    expect(
      screen.getByRole("heading", { name: /foreman/i }),
    ).toBeInTheDocument();
  });

  it("renders the View Runs link", () => {
    render(<HomePage />);
    expect(screen.getByRole("link", { name: /view runs/i })).toBeInTheDocument();
  });

  it("renders the Benchmark Results link", () => {
    render(<HomePage />);
    expect(
      screen.getByRole("link", { name: /benchmark results/i }),
    ).toBeInTheDocument();
  });
});
