/**
 * Typed fetch wrapper for the Foreman FastAPI backend.
 *
 * Base URL is read from NEXT_PUBLIC_API_BASE_URL so the same bundle works in
 * local dev (http://localhost:8000) and deployed environments.
 */

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types — mirror the backend Pydantic schemas
// ---------------------------------------------------------------------------

export interface Token {
  access_token: string;
  token_type: string;
}

export interface UserOut {
  id: string;
  email: string;
  name: string | null;
  created_at: string;
}

export interface RepoDetail {
  id: string;
  name: string;
  clone_url: string;
  default_branch: string;
  status: string;
  error_message: string | null;
  created_at: string;
  chunk_count: number;
}

export interface AgentStepOut {
  id: string;
  agent: string;
  step_index: number;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  tool_calls: Record<string, unknown>[];
  token_usage: Record<string, unknown>;
  latency_ms: number;
  created_at: string;
}

export interface ReviewOut {
  summary: string;
  risk_level: string;
  risk_notes: string;
  pr_title: string;
  pr_description: string;
}

export interface RunOut {
  id: string;
  repo_id: string;
  status: string;
  issue_text: string;
  created_at: string;
  completed_at: string | null;
  rejection_reason: string | null;
}

export interface DiffOut {
  id: string;
  file_path: string;
  patch: string;
  approved: boolean;
}

export interface RunDetail extends RunOut {
  agent_steps: AgentStepOut[];
  review: ReviewOut | null;
  diffs: DiffOut[];
}

export interface HealthResponse {
  status: string;
}

export interface ReadyResponse {
  status: string;
  errors?: string[];
}

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`API error ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      detail = (await res.text().catch(() => res.statusText)) || res.statusText;
    }
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<T>;
}

function authHeader(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

export function getReady(): Promise<ReadyResponse> {
  return apiFetch<ReadyResponse>("/ready");
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export function register(
  email: string,
  password: string,
  name?: string,
): Promise<Token> {
  return apiFetch<Token>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, name }),
  });
}

export function login(email: string, password: string): Promise<Token> {
  return apiFetch<Token>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function getCurrentUser(token: string): Promise<UserOut> {
  return apiFetch<UserOut>("/api/v1/auth/me", {
    headers: authHeader(token),
  });
}

// ---------------------------------------------------------------------------
// Repos
// ---------------------------------------------------------------------------

export function listRepos(token: string): Promise<RepoDetail[]> {
  return apiFetch<RepoDetail[]>("/api/v1/repos", {
    headers: authHeader(token),
  });
}

export function getRepo(token: string, id: string): Promise<RepoDetail> {
  return apiFetch<RepoDetail>(`/api/v1/repos/${id}`, {
    headers: authHeader(token),
  });
}

export function registerRepo(
  token: string,
  body: { name: string; clone_url: string; default_branch?: string },
): Promise<RepoDetail> {
  return apiFetch<RepoDetail>("/api/v1/repos", {
    method: "POST",
    headers: authHeader(token),
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

export function listRuns(token: string): Promise<RunOut[]> {
  return apiFetch<RunOut[]>("/api/v1/runs", {
    headers: authHeader(token),
  });
}

export function getRun(token: string, id: string): Promise<RunDetail> {
  return apiFetch<RunDetail>(`/api/v1/runs/${id}`, {
    headers: authHeader(token),
  });
}

export function createRun(
  token: string,
  body: { repo_id: string; issue_text: string },
): Promise<RunOut> {
  return apiFetch<RunOut>("/api/v1/runs", {
    method: "POST",
    headers: authHeader(token),
    body: JSON.stringify(body),
  });
}

export function approveRun(token: string, runId: string): Promise<RunOut> {
  return apiFetch<RunOut>(`/api/v1/runs/${runId}/approve`, {
    method: "POST",
    headers: authHeader(token),
  });
}

export function rejectRun(
  token: string,
  runId: string,
  reason?: string,
): Promise<RunOut> {
  return apiFetch<RunOut>(`/api/v1/runs/${runId}/reject`, {
    method: "POST",
    headers: authHeader(token),
    body: JSON.stringify({ reason }),
  });
}
