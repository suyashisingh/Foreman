import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AuthProvider, useAuth } from "@/lib/auth-context";

// Mock the api-client module
vi.mock("@/lib/api-client", () => ({
  login: vi.fn(),
  register: vi.fn(),
  getCurrentUser: vi.fn(),
}));

import * as api from "@/lib/api-client";

const mockLogin = vi.mocked(api.login);
const mockRegister = vi.mocked(api.register);
const mockGetCurrentUser = vi.mocked(api.getCurrentUser);

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();
Object.defineProperty(window, "localStorage", { value: localStorageMock });

beforeEach(() => {
  localStorageMock.clear();
  vi.clearAllMocks();
  // Default: getCurrentUser returns a user
  mockGetCurrentUser.mockResolvedValue({
    id: "u1",
    email: "test@test.com",
    name: "Test",
    created_at: new Date().toISOString(),
  });
});

function AuthDisplay() {
  const { token, user, loading, login, logout } = useAuth();
  if (loading) return <div>loading</div>;
  return (
    <div>
      <div data-testid="token">{token ?? "none"}</div>
      <div data-testid="email">{user?.email ?? "none"}</div>
      <button onClick={() => login("a@b.com", "pass1234")}>login</button>
      <button onClick={logout}>logout</button>
    </div>
  );
}

describe("AuthProvider", () => {
  it("starts with no user when localStorage is empty", async () => {
    render(
      <AuthProvider>
        <AuthDisplay />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("token")).toHaveTextContent("none"),
    );
    expect(screen.getByTestId("email")).toHaveTextContent("none");
  });

  it("login stores token and fetches user", async () => {
    mockLogin.mockResolvedValueOnce({
      access_token: "tok-abc",
      token_type: "bearer",
    });

    render(
      <AuthProvider>
        <AuthDisplay />
      </AuthProvider>,
    );

    await waitFor(() =>
      expect(screen.queryByText("loading")).not.toBeInTheDocument(),
    );

    await act(async () => {
      await userEvent.click(screen.getByText("login"));
    });

    await waitFor(() =>
      expect(screen.getByTestId("token")).toHaveTextContent("tok-abc"),
    );
    expect(localStorageMock.getItem("foreman_token")).toBe("tok-abc");
    expect(screen.getByTestId("email")).toHaveTextContent("test@test.com");
  });

  it("logout clears token and user", async () => {
    mockLogin.mockResolvedValueOnce({
      access_token: "tok-abc",
      token_type: "bearer",
    });

    render(
      <AuthProvider>
        <AuthDisplay />
      </AuthProvider>,
    );

    await waitFor(() =>
      expect(screen.queryByText("loading")).not.toBeInTheDocument(),
    );

    await act(async () => {
      await userEvent.click(screen.getByText("login"));
    });
    await waitFor(() =>
      expect(screen.getByTestId("token")).toHaveTextContent("tok-abc"),
    );

    await act(async () => {
      await userEvent.click(screen.getByText("logout"));
    });

    expect(screen.getByTestId("token")).toHaveTextContent("none");
    expect(screen.getByTestId("email")).toHaveTextContent("none");
    expect(localStorageMock.getItem("foreman_token")).toBeNull();
  });
});
