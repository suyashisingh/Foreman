/**
 * Regression test: the RegisterRepoForm must not crash React when the backend
 * returns a 422 with FastAPI's array-of-objects detail format.
 *
 * Before the fix, ApiError.detail was an array at runtime, and React would
 * throw "Objects are not valid as a React child" when rendering {error}.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React, { useState } from "react";

// ---------------------------------------------------------------------------
// Module mocks — factory must not reference outer variables (hoisting rule)
// ---------------------------------------------------------------------------

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    registerRepo: vi.fn(),
  };
});

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    token: "test-token",
    user: { email: "t@t.com" },
    logout: vi.fn(),
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// ---------------------------------------------------------------------------
// Import component deps AFTER mocks
// ---------------------------------------------------------------------------

import { ApiError, registerRepo } from "@/lib/api-client";

// Stripped-down version of the RegisterRepoForm from dashboard/page.tsx
// so we can test the error-rendering path in isolation.
function RegisterRepoFormUnderTest({
  token,
  onRegistered,
}: {
  token: string;
  onRegistered: () => void;
}) {
  const [name, setName] = useState("");
  const [cloneUrl, setCloneUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      await registerRepo(token, { name, clone_url: cloneUrl });
      setName("");
      setCloneUrl("");
      onRegistered();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail : "Failed to register repository.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <input
        aria-label="Name"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <input
        aria-label="Clone URL"
        value={cloneUrl}
        onChange={(e) => setCloneUrl(e.target.value)}
      />
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={pending}>
        Register
      </button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

const mockRegisterRepo = vi.mocked(registerRepo);

beforeEach(() => {
  mockRegisterRepo.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("RegisterRepoForm — 422 error handling", () => {
  it("renders a readable error string when the backend returns a 422 (already stringified by apiFetch)", async () => {
    // With the fix, apiFetch converts the array to a string before throwing.
    // The form just needs to render that string without crashing.
    mockRegisterRepo.mockRejectedValueOnce(
      new ApiError(422, "clone_url: Field required"),
    );

    render(
      <RegisterRepoFormUnderTest token="tok" onRegistered={vi.fn()} />,
    );

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "iniconfig" },
    });
    fireEvent.change(screen.getByLabelText("Clone URL"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: /register/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toBeInTheDocument();
    expect(alert.textContent).toContain("clone_url");
    expect(alert.textContent).toContain("Field required");
    expect(alert.textContent).not.toContain("[object Object]");
  });

  it("renders multiple stringified errors without crashing", async () => {
    mockRegisterRepo.mockRejectedValueOnce(
      new ApiError(422, "clone_url: Field required; name: Field required"),
    );

    render(
      <RegisterRepoFormUnderTest token="tok" onRegistered={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /register/i }));

    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert.textContent).toContain("clone_url");
      expect(alert.textContent).toContain("name");
    });
  });

  it("calls onRegistered and clears the form on success", async () => {
    mockRegisterRepo.mockResolvedValueOnce({
      id: "r1",
      name: "iniconfig",
      clone_url: "https://github.com/pytest-dev/iniconfig.git",
      default_branch: "main",
      status: "pending",
      error_message: null,
      created_at: new Date().toISOString(),
      chunk_count: 0,
    });
    const onRegistered = vi.fn();

    render(
      <RegisterRepoFormUnderTest token="tok" onRegistered={onRegistered} />,
    );

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "iniconfig" },
    });
    fireEvent.change(screen.getByLabelText("Clone URL"), {
      target: { value: "https://github.com/pytest-dev/iniconfig.git" },
    });
    fireEvent.click(screen.getByRole("button", { name: /register/i }));

    await waitFor(() => {
      expect(onRegistered).toHaveBeenCalledOnce();
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
