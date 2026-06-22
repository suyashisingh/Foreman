import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import LoginPage from "@/app/(marketing)/login/page";
import { ApiError } from "@/lib/api-client";

// Mock next/navigation
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
}));

// Mock auth context
const mockLogin = vi.fn();
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    token: null,
    user: null,
    loading: false,
    login: mockLogin,
    logout: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("LoginPage", () => {
  it("renders email and password inputs", () => {
    render(<LoginPage />);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("calls login and redirects on success", async () => {
    mockLogin.mockResolvedValueOnce(undefined);
    render(<LoginPage />);

    await userEvent.type(screen.getByLabelText(/email/i), "a@b.com");
    await userEvent.type(screen.getByLabelText(/password/i), "password1");
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    });

    await waitFor(() => expect(mockLogin).toHaveBeenCalledWith("a@b.com", "password1"));
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/dashboard"));
  });

  it("shows error message on login failure", async () => {
    mockLogin.mockRejectedValueOnce(new ApiError(401, "Invalid credentials."));
    render(<LoginPage />);

    await userEvent.type(screen.getByLabelText(/email/i), "bad@b.com");
    await userEvent.type(screen.getByLabelText(/password/i), "wrongpass");
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    });

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Invalid credentials."),
    );
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("disables submit button while pending", async () => {
    let resolve!: () => void;
    mockLogin.mockReturnValueOnce(
      new Promise<void>((r) => {
        resolve = r;
      }),
    );

    render(<LoginPage />);
    await userEvent.type(screen.getByLabelText(/email/i), "a@b.com");
    await userEvent.type(screen.getByLabelText(/password/i), "password1");

    const btn = screen.getByRole("button", { name: /sign in/i });
    await act(async () => {
      await userEvent.click(btn);
    });

    expect(btn).toBeDisabled();
    resolve();
    await waitFor(() => expect(btn).not.toBeDisabled());
  });
});
