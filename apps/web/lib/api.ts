// Minimal API client for the FastAPI backend.
// Dev auth: org/user ids from the bootstrap flow are stored in localStorage and sent as
// X-Org-Id / X-User-Id headers (placeholder until real auth — see docs/interfaces.md).

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Session = { orgId: string; userId: string };

export function getSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem("session");
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function setSession(s: Session | null) {
  if (typeof window === "undefined") return;
  if (s) localStorage.setItem("session", JSON.stringify(s));
  else localStorage.removeItem("session");
}

function headers(auth = true): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const s = getSession();
  if (auth && s) {
    h["X-Org-Id"] = s.orgId;
    h["X-User-Id"] = s.userId;
  }
  return h;
}

async function req<T>(path: string, init?: RequestInit & { auth?: boolean }): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...headers(init?.auth ?? true), ...(init?.headers ?? {}) },
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
  bootstrap: (orgName: string) =>
    req<{ org_id: string; user_id: string; role: string }>("/dev/bootstrap", {
      method: "POST",
      auth: false,
      body: JSON.stringify({ org_name: orgName }),
    }),
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
