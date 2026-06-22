import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  login,
  register,
  listRepos,
  createRun,
  registerRepo,
  rejectRun,
  approveRun,
  getBenchmarkResults,
  ApiError,
} from "@/lib/api-client";

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

// ---------------------------------------------------------------------------
// Regression: Content-Type must survive when Authorization header is also present
// Bug: apiFetch spread order was { headers: {CT,...init.headers}, ...init }
// which caused ...init to overwrite headers, dropping Content-Type for any
// call that passes both auth headers AND a body (registerRepo, createRun,
// rejectRun). FastAPI then received Content-Type: text/plain and passed raw
// bytes to Pydantic → "Input should be a valid dictionary or object".
// ---------------------------------------------------------------------------

describe("Content-Type: application/json is always sent", () => {
  const repo = {
    id: "r1",
    name: "iniconfig",
    clone_url: "https://github.com/pytest-dev/iniconfig.git",
    default_branch: "main",
    status: "pending",
    error_message: null,
    created_at: new Date().toISOString(),
    chunk_count: 0,
  };

  it("registerRepo sends Content-Type alongside Authorization", async () => {
    mockOk(repo);
    await registerRepo("mytoken", {
      name: "iniconfig",
      clone_url: "https://github.com/pytest-dev/iniconfig.git",
    });
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/repos"),
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          Authorization: "Bearer mytoken",
        }),
      }),
    );
  });

  it("createRun sends Content-Type alongside Authorization", async () => {
    mockOk({
      id: "run-1",
      repo_id: "r1",
      status: "pending",
      issue_text: "fix bug",
      created_at: new Date().toISOString(),
      completed_at: null,
      rejection_reason: null,
    });
    await createRun("mytoken", { repo_id: "r1", issue_text: "fix bug" });
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/runs"),
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          Authorization: "Bearer mytoken",
        }),
      }),
    );
  });

  it("rejectRun sends Content-Type alongside Authorization", async () => {
    mockOk({ ...repo, status: "rejected", rejection_reason: "bad code" });
    await rejectRun("mytoken", "run-1", "bad code");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/runs/run-1/reject"),
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          Authorization: "Bearer mytoken",
        }),
      }),
    );
  });

  it("approveRun sends Authorization (no body, Content-Type irrelevant but present)", async () => {
    mockOk({ ...repo, status: "passed" });
    await approveRun("mytoken", "run-1");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/runs/run-1/approve"),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer mytoken",
        }),
      }),
    );
  });

  it("login sends Content-Type even without an Authorization header", async () => {
    mockOk({ access_token: "tok", token_type: "bearer" });
    await login("u@test.com", "pass");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/login"),
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
        }),
      }),
    );
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

// ---------------------------------------------------------------------------
// Regression: getBenchmarkResults must call the full backend URL, not a
// relative path. A relative /api/v1/... would hit the Next.js server
// (port 3000) and 404 instead of reaching FastAPI (port 8000).
// ---------------------------------------------------------------------------

describe("getBenchmarkResults", () => {
  const payload = {
    benchmark_run_id: "abc-123",
    commit_sha: "deadbeef1234567890abcdef1234567890abcdef",
    created_at: new Date().toISOString(),
    task_count: 2,
    pass_at_1_rate: 1.0,
    pass_at_3_rate: 1.0,
    avg_time_to_green_s: 44.0,
    total_token_cost_usd: 0.011,
    tasks: [
      {
        task_id: "iniconfig-as-dict",
        passed: true,
        attempts_to_pass: 1,
        time_to_green_s: 45.3,
        token_cost_usd: 0.0056,
        pass_at_1: true,
        pass_at_3: true,
      },
      {
        task_id: "iniconfig-section-names",
        passed: true,
        attempts_to_pass: 1,
        time_to_green_s: 44.2,
        token_cost_usd: 0.0052,
        pass_at_1: true,
        pass_at_3: true,
      },
    ],
  };

  it("GETs the full backend URL, not a relative path", async () => {
    mockOk(payload);
    await getBenchmarkResults();
    // lastCall[0] is the URL string passed to fetch()
    const calledUrl: string = mockFetch.mock.lastCall![0] as string;
    // Must be an absolute URL pointing at the backend host, not a relative /api/...
    expect(calledUrl).toMatch(/^https?:\/\//);
    expect(calledUrl).toContain("/api/v1/benchmark/results");
  });

  it("returns typed BenchmarkResultsOut on success", async () => {
    mockOk(payload);
    const result = await getBenchmarkResults();
    expect(result.task_count).toBe(2);
    expect(result.pass_at_1_rate).toBe(1.0);
    expect(result.tasks).toHaveLength(2);
    expect(result.tasks[0].task_id).toBe("iniconfig-as-dict");
  });

  it("throws ApiError with status 404 when no runs exist", async () => {
    mockError(404, "No benchmark runs found");
    await expect(getBenchmarkResults()).rejects.toBeInstanceOf(ApiError);
    try {
      await getBenchmarkResults();
    } catch {
      // second call needed to inspect — re-mock
    }
    mockError(404, "No benchmark runs found");
    try {
      await getBenchmarkResults();
    } catch (err) {
      if (err instanceof ApiError) {
        expect(err.status).toBe(404);
        expect(err.detail).toContain("No benchmark runs found");
      }
    }
  });
});
