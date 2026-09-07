// Minimal API client for the FastAPI backend.
// Auth: server-side session cookie. The browser stores the HttpOnly `session` cookie set by
// POST /auth/login and sends it automatically because every request uses credentials:"include".
// We never read or store the token in JS; call `api.me()` to learn the current principal.

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Principal = {
  org_id: string;
  user_id: string;
  role: string;
  name?: string | null;
  email?: string | null;
};
export type DashboardSummary = {
  total_jobs: number;
  active_jobs: number;
  candidates_in_pipeline: number;
  needs_review: number;
  awaiting_result: number;
  failed_calls: number;
};
export type ActivityItem = {
  action: string;
  entity_type: string;
  to_state: string | null;
  reason: string | null;
  created_at: string;
};
export type AssistantReply = { reply: string; links: Array<{ label: string; href: string }>; pending?: { tool: string; label: string; args: Record<string, unknown> } | null };
export type AuditLogItem = {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  from_state: string | null;
  to_state: string | null;
  reason: string | null;
  actor_email: string | null;
  created_at: string;
};
export type AuditPageResult = { items: AuditLogItem[]; total: number; page: number; page_size: number };
export type HunarHealth = {
  status: "healthy" | "invalid" | "unconfigured" | "unreachable";
  source: "override" | "env" | null;
  checked_at: string;
};

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
  signup: (input: { name: string; email: string; password: string; org_name?: string }) =>
    req<Principal>("/auth/signup", { method: "POST", body: JSON.stringify(input) }),
  logout: () => req<null>("/auth/logout", { method: "POST" }),
  bootstrap: (org_name: string, user_email: string, password: string) =>
    req<{ org_id: string; user_id: string; role: string }>("/dev/bootstrap", {
      method: "POST",
      body: JSON.stringify({ org_name, user_email, password }),
    }),

  // dashboard
  dashboardSummary: () => req<DashboardSummary>("/dashboard/summary"),
  dashboardActivity: () => req<ActivityItem[]>("/dashboard/activity"),
  auditLog: (opts: { page?: number; page_size?: number; q?: string } = {}) => {
    const p = new URLSearchParams();
    p.set("page", String(opts.page ?? 1));
    p.set("page_size", String(opts.page_size ?? 50));
    if (opts.q) p.set("q", opts.q);
    return req<AuditPageResult>(`/dashboard/audit?${p.toString()}`);
  },
  assistantChat: (messages: Array<{ role: string; content: string }>, approve?: { tool: string; args: Record<string, unknown> }) =>
    req<AssistantReply>("/assistant/chat", { method: "POST", body: JSON.stringify({ messages, approve }) }),

  // jobs
  listJobs: () => req<Job[]>("/jobs"),
  getJob: (id: string) => req<Job>(`/jobs/${id}`),
  createJob: (title: string) =>
    req<Job>("/jobs", { method: "POST", body: JSON.stringify({ title }) }),
  addVersion: (jobId: string, jd_text: string) =>
    req<JobVersion>(`/jobs/${jobId}/versions`, { method: "POST", body: JSON.stringify({ jd_text }) }),
  tidyJobDescription: (jobId: string, text: string) =>
    req<{ text: string }>(`/jobs/${jobId}/versions/tidy`, { method: "POST", body: JSON.stringify({ text }) }),
  addVersionFromPdf: async (jobId: string, file: File): Promise<JobVersion> => {
    // multipart: let the browser set the Content-Type (with boundary), so don't use req().
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/jobs/${jobId}/versions/upload`, {
      method: "POST",
      body: form,
      credentials: "include",
      cache: "no-store",
    });
    const text = await res.text();
    const body = text ? JSON.parse(text) : null;
    if (!res.ok) throw new Error(body?.error?.message ?? res.statusText);
    return body as JobVersion;
  },
  confirmVersion: (jobId: string, vid: string) =>
    req<JobVersion>(`/jobs/${jobId}/versions/${vid}/confirm`, { method: "POST" }),
  draftWorkflow: (jobId: string) =>
    req<WorkflowVersion>(`/jobs/${jobId}/workflow/draft`, { method: "POST" }),
  listStages: (jobId: string, vid: string) =>
    req<Stage[]>(`/jobs/${jobId}/workflow/versions/${vid}/stages`),
  getJobWorkflow: (jobId: string) => req<JobWorkflow>(`/jobs/${jobId}/workflow`),
  getLatestVersion: (jobId: string) => req<JobVersion | null>(`/jobs/${jobId}/version`),
  getJobFunnel: (jobId: string) => req<Funnel>(`/jobs/${jobId}/funnel`),
  getCallingPolicy: (jobId: string) => req<CallingPolicy | null>(`/jobs/${jobId}/calling-policy`),
  setCallingPolicy: (jobId: string, policy: CallingPolicyInput) =>
    req<CallingPolicy>(`/jobs/${jobId}/calling-policy`, { method: "PUT", body: JSON.stringify(policy) }),
  editWorkflowStages: (jobId: string, versionId: string, stages: StageEdit[]) =>
    req<JobWorkflow>(`/jobs/${jobId}/workflow/versions/${versionId}/stages`, {
      method: "PUT",
      body: JSON.stringify({ stages }),
    }),
  approveWorkflow: (jobId: string, vid: string) =>
    req<WorkflowVersion>(`/jobs/${jobId}/workflow/versions/${vid}/approve`, { method: "POST" }),
  activateJob: (jobId: string) => req<Job>(`/jobs/${jobId}/activate`, { method: "POST" }),
  archiveJob: (jobId: string) => req<Job>(`/jobs/${jobId}/archive`, { method: "POST" }),
  deleteJob: (jobId: string) => req<null>(`/jobs/${jobId}`, { method: "DELETE" }),

  // funnels (org-owned reusable workflow templates)
  listFunnels: (includeArchived = false) =>
    req<FunnelSummary[]>(`/funnels${includeArchived ? "?include_archived=true" : ""}`),
  listFunnelPresets: () => req<FunnelPreset[]>("/funnels/presets"),
  createFunnel: (name: string, stages: StageEdit[]) =>
    req<FunnelDetail>("/funnels", { method: "POST", body: JSON.stringify({ name, stages }) }),
  getFunnel: (id: string) => req<FunnelDetail>(`/funnels/${id}`),
  editFunnelStages: (id: string, stages: StageEdit[]) =>
    req<FunnelDetail>(`/funnels/${id}/stages`, { method: "PUT", body: JSON.stringify({ stages }) }),
  renameFunnel: (id: string, name: string) =>
    req<FunnelDetail>(`/funnels/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  archiveFunnel: (id: string) =>
    req<FunnelSummary>(`/funnels/${id}/archive`, { method: "POST" }),
  useFunnel: (id: string, jobId: string) =>
    req<WorkflowVersion>(`/funnels/${id}/use`, { method: "POST", body: JSON.stringify({ job_id: jobId }) }),

  // candidates
  listCandidates: (jobId: string) => req<JobCandidateListItem[]>(`/jobs/${jobId}/candidates`),
  pipelinePage: (jobId: string, opts: { stage?: string; state?: string; q?: string; page?: number; page_size?: number } = {}) => {
    const p = new URLSearchParams();
    if (opts.stage) p.set("stage", opts.stage);
    if (opts.state) p.set("state", opts.state);
    if (opts.q) p.set("q", opts.q);
    p.set("page", String(opts.page ?? 1));
    p.set("page_size", String(opts.page_size ?? 25));
    return req<PipelinePage>(`/jobs/${jobId}/pipeline?${p.toString()}`);
  },
  listAllCandidates: () => req<OrgCandidateListItem[]>("/candidates"),
  deleteJobCandidate: (jcId: string) => req<null>(`/job-candidates/${jcId}`, { method: "DELETE" }),
  importCandidate: (jobId: string, body: CandidateImport) =>
    req<JobCandidateOut>(`/jobs/${jobId}/candidates`, { method: "POST", body: JSON.stringify(body) }),
  updateCandidate: (jcId: string, body: { full_name?: string; phone?: string | null; email?: string | null; location?: string | null }) =>
    req<CandidateSummary>(`/job-candidates/${jcId}`, { method: "PATCH", body: JSON.stringify(body) }),
  importCandidatesCsv: async (jobId: string, file: File): Promise<CsvImportResult> => {
    // multipart: let the browser set Content-Type (with boundary), so don't use req().
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/jobs/${jobId}/candidates/import-csv`, { method: "POST", credentials: "include", body: form });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error(data?.error?.message ?? `Upload failed (${res.status})`);
    return data as CsvImportResult;
  },
  timeline: (jcId: string) => req<Timeline>(`/job-candidates/${jcId}/timeline`),
  // Returns Hunar internals in hunar_payload; the UI intentionally ignores that (recruiters
  // see product concepts only, never telephony/agent internals).
  launch: (jcId: string) =>
    req<{ call_id: string; normalized_status: string; dispatched: boolean; hunar_call_id: string | null }>(
      `/job-candidates/${jcId}/launch`,
      { method: "POST" },
    ),
  // Launch the AI interview for every eligible candidate in a stage. Already-handled
  // candidates (call in progress/awaiting result, already reviewed/completed, or rejected)
  // are skipped server-side — nobody is re-dialed.
  launchStageAll: (jobId: string, stageId: string) =>
    req<BulkLaunchResult>(`/jobs/${jobId}/stages/${stageId}/launch-all`, { method: "POST" }),
  decide: (jcId: string, outcome: "pass" | "reject", reason?: string) =>
    req<{ outcome: string; advanced: boolean; pipeline_state: string | null; current_stage_name: string | null }>(
      `/job-candidates/${jcId}/decision`,
      { method: "POST", body: JSON.stringify({ outcome, reason }) },
    ),
  // sourcing (people search & outreach — Flow B)
  sourcingProviders: (jobId: string) =>
    req<ProvidersInfo>(`/jobs/${jobId}/sourcing/providers`),
  suggestedQuery: (jobId: string) =>
    req<PeopleSearchInput>(`/jobs/${jobId}/sourcing/suggested-query`),
  peopleSearch: (jobId: string, query: PeopleSearchInput) =>
    req<PeopleSearchResult>(`/jobs/${jobId}/sourcing/search`, {
      method: "POST",
      body: JSON.stringify(query),
    }),
  addSourced: (jobId: string, candidates: ExternalCandidate[]) =>
    req<{ added: number; skipped: number; job_candidate_ids: string[] }>(
      `/jobs/${jobId}/sourcing/add`,
      { method: "POST", body: JSON.stringify({ candidates }) },
    ),
  enrichCandidate: (jcId: string) =>
    req<EnrichResult>(`/job-candidates/${jcId}/enrich`, { method: "POST" }),

  // settings (org-scoped config)
  getSettings: () => req<Settings>("/settings"),
  updateSettings: (patch: SettingsUpdate) =>
    req<Settings>("/settings", { method: "PUT", body: JSON.stringify(patch) }),
  getHunarHealth: (refresh = false) =>
    req<HunarHealth>(`/hunar/health${refresh ? "?refresh=1" : ""}`),
  updateHunarKey: (apiKey: string) =>
    req<HunarHealth>("/hunar/key", { method: "PUT", body: JSON.stringify({ api_key: apiKey }) }),

  // team invites
  createInvite: (input: { email: string; role: string; name?: string }) =>
    req<InviteCreated>("/settings/invites", { method: "POST", body: JSON.stringify(input) }),
  revokeInvite: (id: string) => req<null>(`/settings/invites/${id}`, { method: "DELETE" }),
  previewInvite: (token: string) => req<InvitePreview>(`/auth/invite?token=${encodeURIComponent(token)}`),
  acceptInvite: (input: { token: string; password: string; name?: string }) =>
    req<Principal>("/auth/accept-invite", { method: "POST", body: JSON.stringify(input) }),

  syncCall: (callId: string) =>
    req<{ call_id: string; normalized_status: string | null; vendor_status: string | null; hunar_call_id: string | null }>(
      `/calls/${callId}/sync`,
      { method: "POST" },
    ),
};

export type Job = { id: string; title: string; status: string; created_at: string };
export type JobVersion = { id: string; version: number; confirmed: boolean; jd_text: string; extracted: Record<string, unknown> };
export type FunnelStage = {
  stage_id: string;
  stage_order: number;
  name: string;
  execution_type: string;
  reached: number;
  current: number;
  reached_pct: number;
};
export type Funnel = {
  total: number;
  in_progress: number;
  rejected: number;
  completed: number;
  completion_pct: number;
  stages: FunnelStage[];
};
export type WorkflowVersion = { id: string; version: number; approved: boolean };
export type Stage = { id: string; stage_order: number; name: string; execution_type: string };
export type Criterion = { name: string; kind: string; weight: number | null };
export type StageDetail = {
  id: string;
  stage_order: number;
  name: string;
  purpose: string | null;
  execution_type: string;
  information_requirements: string[];
  requires_human_approval: boolean;
  criteria: Criterion[];
};
export type JobWorkflow = {
  version_id: string;
  version: number;
  approved: boolean;
  stages: StageDetail[];
};
export type CallingPolicyInput = {
  allowed_days: string[];
  earliest_call_time: string | null;
  last_call_time: string | null;
  timezone: string | null;
  max_attempts: number;
  retry_interval_hours: number;
  language: string | null;
};
export type CallingPolicy = CallingPolicyInput & { id: string };
export type FunnelSummary = { id: string; name: string; version: number; stage_count: number; archived: boolean; created_at: string };
export type FunnelStageSpec = {
  stage_order: number;
  name: string;
  purpose: string | null;
  execution_type: string;
  information_requirements: string[];
  requires_human_approval: boolean;
  criteria: Criterion[];
};
export type FunnelDetail = { id: string; name: string; version: number; archived: boolean; stages: FunnelStageSpec[] };
export type FunnelPreset = { key: string; name: string; description: string; stages: FunnelStageSpec[] };

export type StageEdit = {
  name: string;
  purpose?: string | null;
  execution_type: string;
  information_requirements: string[];
  requires_human_approval: boolean;
  criteria: Criterion[];
};

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
export type OrgCandidateListItem = {
  id: string;
  candidate: CandidateSummary;
  job_id: string;
  job_title: string;
  current_stage_name: string | null;
  pipeline_state: string | null;
  created_at: string;
};
export type CandidateImport = {
  full_name: string;
  phone?: string;
  email?: string;
  location?: string;
  source?: string;
  known_facts?: Record<string, string>;
};
export type CsvImportResult = { added: number; skipped: number; errors: Array<{ row: number; reason: string }> };
export type PipelinePage = { items: JobCandidateListItem[]; total: number; page: number; page_size: number };
export type BulkLaunchResultItem = {
  job_candidate_id: string;
  name: string | null;
  outcome: "launched" | "skipped" | "failed";
  reason: string | null;
  call_id: string | null;
  dispatched: boolean;
};
export type BulkLaunchResult = {
  stage_id: string;
  launched: number;
  skipped: number;
  failed: number;
  results: BulkLaunchResultItem[];
};
export type StageRun = { id: string; stage_id: string; stage_name: string | null; status: string };
export type CallItem = { id: string; normalized_status: string; hunar_call_id: string | null };
export type Fact = { field_key: string; value: string | null; source: string | null };
export type PeopleSearchInput = {
  titles: string[];
  keywords: string[];
  locations: string[];
  skills: string[];
  seniorities: string[];
  page: number;
  page_size: number;
  provider?: string | null;
};
export type ProviderOption = { key: string; label: string; configured: boolean };
export type ProvidersInfo = { default: string | null; providers: ProviderOption[] };
export type ExternalCandidate = {
  source: string;
  source_id: string;
  full_name: string | null;
  title: string | null;
  company: string | null;
  location: string | null;
  linkedin_url: string | null;
  has_contact?: boolean;
};
export type PeopleSearchResult = {
  provider: string;
  requested_provider: string;
  is_sample: boolean;
  notice: string | null;
  total: number | null;
  page: number;
  has_more: boolean;
  suggested_query: PeopleSearchInput;
  applied_query: PeopleSearchInput;
  candidates: ExternalCandidate[];
};
export type SettingsUser = { id: string; name: string | null; email: string; role: string };
export type PendingInvite = {
  id: string;
  email: string;
  name: string | null;
  role: string;
  created_at: string;
  expires_at: string;
};
export type Settings = {
  org_name: string;
  is_admin: boolean;
  default_provider: string | null;
  providers: ProviderOption[];
  live_calls_enabled: boolean;
  users: SettingsUser[];
  invites: PendingInvite[];
};
export type InviteCreated = {
  id: string;
  email: string;
  name: string | null;
  role: string;
  expires_at: string;
  accept_url: string;
};
export type InvitePreview = { org_name: string; email: string; role: string };
export type SettingsUpdate = {
  org_name?: string;
  default_provider?: string | null;
  live_calls_enabled?: boolean;
  provider_keys?: Record<string, string>;
};
export type EnrichResult = {
  phone: string | null;
  email: string | null;
  provider: string;
  requested_provider: string;
  is_sample: boolean;
  already_had_contact: boolean;
  notice: string | null;
  pipeline_state: string | null;
};
export type Timeline = {
  job_candidate: JobCandidateOut;
  candidate: CandidateSummary;
  stage_runs: StageRun[];
  calls: CallItem[];
  facts: Fact[];
};
