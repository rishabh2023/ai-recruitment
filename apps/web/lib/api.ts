// Minimal API client for the FastAPI backend.
// Auth: server-side session cookie. The browser stores the HttpOnly `session` cookie set by
// POST /auth/login and sends it automatically because every request uses credentials:"include".
// We never read or store the token in JS; call `api.me()` to learn the current principal.

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Principal = { org_id: string; user_id: string; role: string };

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    credentials: "include", // send/receive the session cookie
    cache: "no-store",
  });
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const msg = body?.error?.message ?? res.statusText;
    throw new Error(msg);
  }
  return body as T;
}

export const api = {
  // auth
  me: async (): Promise<Principal | null> => {
    try {
      return await req<Principal>("/auth/me");
    } catch {
      return null; // 401 → not logged in
    }
  },
  login: (email: string, password: string) =>
    req<Principal>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => req<null>("/auth/logout", { method: "POST" }),
  bootstrap: (org_name: string, user_email: string, password: string) =>
    req<{ org_id: string; user_id: string; role: string }>("/dev/bootstrap", {
      method: "POST",
      body: JSON.stringify({ org_name, user_email, password }),
    }),

  // jobs
  listJobs: () => req<Job[]>("/jobs"),
  getJob: (id: string) => req<Job>(`/jobs/${id}`),
  createJob: (title: string) =>
    req<Job>("/jobs", { method: "POST", body: JSON.stringify({ title }) }),
  addVersion: (jobId: string, jd_text: string) =>
    req<JobVersion>(`/jobs/${jobId}/versions`, { method: "POST", body: JSON.stringify({ jd_text }) }),
  confirmVersion: (jobId: string, vid: string) =>
    req<JobVersion>(`/jobs/${jobId}/versions/${vid}/confirm`, { method: "POST" }),
  draftWorkflow: (jobId: string) =>
    req<WorkflowVersion>(`/jobs/${jobId}/workflow/draft`, { method: "POST" }),
  listStages: (jobId: string, vid: string) =>
    req<Stage[]>(`/jobs/${jobId}/workflow/versions/${vid}/stages`),
  approveWorkflow: (jobId: string, vid: string) =>
    req<WorkflowVersion>(`/jobs/${jobId}/workflow/versions/${vid}/approve`, { method: "POST" }),
  activateJob: (jobId: string) => req<Job>(`/jobs/${jobId}/activate`, { method: "POST" }),
};

export type Job = { id: string; title: string; status: string; created_at: string };
export type JobVersion = { id: string; version: number; confirmed: boolean; extracted: Record<string, unknown> };
export type WorkflowVersion = { id: string; version: number; approved: boolean };
export type Stage = { id: string; stage_order: number; name: string; execution_type: string };
