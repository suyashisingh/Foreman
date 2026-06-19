/**
 * Typed fetch wrapper for the Foreman FastAPI backend.
 *
 * Base URL is read from NEXT_PUBLIC_API_BASE_URL so that the same bundle
 * works in both local dev (http://localhost:8000) and deployed environments.
 *
 * Only the /health endpoint is wired at this stage. Additional endpoints are
 * added as the backend grows (auth — Day 2, runs — Day 3, etc.).
 */

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** Shape of the FastAPI /health response. */
export interface HealthResponse {
  status: string;
}

/** Shape of the FastAPI /ready response (includes optional errors). */
export interface ReadyResponse {
  status: string;
  errors?: string[];
}

/**
 * Internal fetch helper that attaches JSON headers and throws on non-2xx.
 */
async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${path} → ${res.status}: ${text}`);
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Health endpoints — the one real API call proven in Day 1
// ---------------------------------------------------------------------------

/** GET /health — liveness probe. Returns { status: "ok" }. */
export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

/** GET /ready — readiness probe. Returns 503 if DB or Redis is down. */
export async function getReady(): Promise<ReadyResponse> {
  return apiFetch<ReadyResponse>("/ready");
}
