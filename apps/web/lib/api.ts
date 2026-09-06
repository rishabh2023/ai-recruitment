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

  // candidates
  listCandidates: (jobId: string) => req<JobCandidateListItem[]>(`/jobs/${jobId}/candidates`),
  importCandidate: (jobId: string, body: CandidateImport) =>
    req<JobCandidateOut>(`/jobs/${jobId}/candidates`, { method: "POST", body: JSON.stringify(body) }),
  timeline: (jcId: string) => req<Timeline>(`/job-candidates/${jcId}/timeline`),
  // Returns Hunar internals in hunar_payload; the UI intentionally ignores that (recruiters
  // see product concepts only, never telephony/agent internals).
  launch: (jcId: string) =>
    req<{ call_id: string; normalized_status: string }>(`/job-candidates/${jcId}/launch`, { method: "POST" }),
};

export type Job = { id: string; title: string; status: string; created_at: string };
export type JobVersion = { id: string; version: number; confirmed: boolean; extracted: Record<string, unknown> };
export type WorkflowVersion = { id: string; version: number; approved: boolean };
export type Stage = { id: string; stage_order: number; name: string; execution_type: string };

export type CandidateSummary = {
  id: string;
  full_name: string | null;
  phone: string | null;
  email: string | null;
  location: string | null;
};
export type JobCandidateOut = {
  id: string;
  job_id: string;
  candidate_id: string;
  current_stage_id: string | null;
  pipeline_state: string | null;
};
export type JobCandidateListItem = {
  id: string;
  candidate: CandidateSummary;
  current_stage_id: string | null;
  current_stage_name: string | null;
  pipeline_state: string | null;
};
export type CandidateImport = {
  full_name: string;
  phone?: string;
  email?: string;
  location?: string;
  source?: string;
  known_facts?: Record<string, string>;
};
export type StageRun = { id: string; stage_id: string; stage_name: string | null; status: string };
export type CallItem = { id: string; normalized_status: string; hunar_call_id: string | null };
export type Fact = { field_key: string; value: string | null; source: string | null };
export type Timeline = {
  job_candidate: JobCandidateOut;
  candidate: CandidateSummary;
  stage_runs: StageRun[];
  calls: CallItem[];
  facts: Fact[];
};
