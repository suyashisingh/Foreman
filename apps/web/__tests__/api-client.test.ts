import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { login, register, listRepos, createRun, registerRepo, ApiError } from "@/lib/api-client";

const mockFetch = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch);
});

afterEach(() => {
  vi.restoreAllMocks();
});

function mockOk(body: unknown) {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(body),
  });
}

function mockError(status: number, detail: string) {
  mockFetch.mockResolvedValueOnce({
    ok: false,
    status,
    statusText: "Error",
    json: () => Promise.resolve({ detail }),
    text: () => Promise.resolve(detail),
  });
}

function mockValidationError(
  status: number,
  errors: { type: string; loc: string[]; msg: string; input?: unknown }[],
) {
  mockFetch.mockResolvedValueOnce({
    ok: false,
    status,
    statusText: "Unprocessable Entity",
    json: () => Promise.resolve({ detail: errors }),
    text: () => Promise.resolve(JSON.stringify({ detail: errors })),
  });
}

describe("login", () => {
  it("POSTs credentials and returns a token", async () => {
    mockOk({ access_token: "tok123", token_type: "bearer" });
    const result = await login("user@test.com", "pass1234");
    expect(result.access_token).toBe("tok123");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/login"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("throws ApiError on 401", async () => {
    mockError(401, "Invalid credentials.");
    await expect(login("bad@test.com", "wrong")).rejects.toBeInstanceOf(
      ApiError,
    );
  });

  it("ApiError carries status and detail", async () => {
    mockError(401, "Invalid credentials.");
    try {
      await login("bad@test.com", "wrong");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      if (err instanceof ApiError) {
        expect(err.status).toBe(401);
        expect(err.detail).toBe("Invalid credentials.");
      }
    }
  });
});

describe("register", () => {
  it("POSTs to /register and returns token", async () => {
    mockOk({ access_token: "newtoken", token_type: "bearer" });
    const result = await register("new@test.com", "password1");
    expect(result.access_token).toBe("newtoken");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/register"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("throws ApiError on 409 conflict", async () => {
    mockError(409, "A user with this email address already exists.");
    await expect(register("dup@test.com", "password1")).rejects.toBeInstanceOf(
      ApiError,
    );
  });
});

describe("listRepos", () => {
  it("GETs /repos with Authorization header", async () => {
    mockOk([]);
    await listRepos("mytoken");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/repos"),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer mytoken",
        }),
      }),
    );
  });
});

describe("ApiError — FastAPI 422 array-format detail", () => {
  it("converts a single validation error to a readable string", async () => {
    mockValidationError(422, [
      { type: "missing", loc: ["body", "clone_url"], msg: "Field required", input: {} },
    ]);
    try {
      await registerRepo("tok", { name: "x", clone_url: "" });
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      if (err instanceof ApiError) {
        expect(err.status).toBe(422);
        // Must be a plain string, not an array
        expect(typeof err.detail).toBe("string");
        expect(err.detail).toContain("clone_url");
        expect(err.detail).toContain("Field required");
      }
    }
  });

  it("joins multiple validation errors with semicolons", async () => {
    mockValidationError(422, [
      { type: "missing", loc: ["body", "name"], msg: "Field required", input: {} },
      { type: "missing", loc: ["body", "clone_url"], msg: "Field required", input: {} },
    ]);
    try {
      await registerRepo("tok", { name: "", clone_url: "" });
    } catch (err) {
      if (err instanceof ApiError) {
        expect(typeof err.detail).toBe("string");
        expect(err.detail).toContain("name");
        expect(err.detail).toContain("clone_url");
        // Both errors joined
        expect(err.detail.split(";").length).toBe(2);
      }
    }
  });

  it("keeps a plain string detail unchanged", async () => {
    mockError(409, "A user with this email already exists.");
    try {
      await register("dup@test.com", "password");
    } catch (err) {
      if (err instanceof ApiError) {
        expect(err.detail).toBe("A user with this email already exists.");
      }
    }
  });

  it("detail is always a string — never an array", async () => {
    mockValidationError(422, [
      { type: "missing", loc: ["body", "clone_url"], msg: "Field required" },
    ]);
    try {
      await registerRepo("tok", { name: "x", clone_url: "" });
    } catch (err) {
      if (err instanceof ApiError) {
        expect(Array.isArray(err.detail)).toBe(false);
        expect(typeof err.detail).toBe("string");
      }
    }
  });
});

describe("createRun", () => {
  it("POSTs run creation and returns RunOut", async () => {
    const run = {
      id: "run-1",
      repo_id: "repo-1",
      status: "pending",
      issue_text: "Add feature",
      created_at: new Date().toISOString(),
      completed_at: null,
      rejection_reason: null,
    };
    mockOk(run);
    const result = await createRun("tok", {
      repo_id: "repo-1",
      issue_text: "Add feature",
    });
    expect(result.id).toBe("run-1");
    expect(result.status).toBe("pending");
  });
});
