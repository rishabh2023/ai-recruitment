"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  api,
  type ActivityItem,
  type DashboardSummary,
  type Job,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

function Stat({ label, value, tone }: { label: string; value: number; tone?: "warn" | "danger" }) {
  return (
    <div className={`stat ${value > 0 && tone ? tone : ""}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function humanize(a: ActivityItem): string {
  const map: Record<string, string> = {
    "candidate.imported": "Candidate imported",
    "candidate.started_at_later_stage": "Candidate started at a later stage",
    "job.created": "Job created",
    "job.activated": "Job activated",
    "workflow.approved": "Workflow approved",
    "stage_run.created": "Stage run created",
  };
  const base = map[a.action] ?? a.action.replace(/[._]/g, " ");
  return a.to_state ? `${base} → ${a.to_state}` : base;
}

export default function Dashboard() {
  const { me } = useAuth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.dashboardSummary(), api.listJobs(), api.dashboardActivity()])
      .then(([s, j, act]) => {
        setSummary(s);
        setJobs(j);
        setActivity(act);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <main className="container">Loading…</main>;

  return (
    <main className="container dashboard-page">
      <div className="dashboard-header">
        <div>
          <p className="eyebrow">Hiring command center</p>
          <h1 style={{ marginBottom: 4 }}>
            {me?.name ? `Welcome, ${me.name.split(" ")[0]}` : "Hiring Dashboard"}
          </h1>
          <p className="muted" style={{ margin: 0 }}>
            What&apos;s happening in hiring right now, and what needs your attention.
          </p>
        </div>
        <Link className="btn" href="/jobs/new">+ Create Job</Link>
      </div>

      {error && <p className="error">{error}</p>}

      {summary && (
        <div className="stat-grid dashboard-stats">
          <Stat label="Active jobs" value={summary.active_jobs} />
          <Stat label="Candidates in pipeline" value={summary.candidates_in_pipeline} />
          <Stat label="Needs review" value={summary.needs_review} tone="warn" />
          <Stat label="Awaiting result" value={summary.awaiting_result} tone="warn" />
          <Stat label="Failed calls" value={summary.failed_calls} tone="danger" />
          <Stat label="Total jobs" value={summary.total_jobs} />
        </div>
      )}

      <section className="dashboard-attention">
        <div className="dashboard-section-heading">
          <div><p className="eyebrow">Focus now</p><h2>Hiring attention</h2></div>
        </div>
        <div className="attention-grid">
          <div><span>Draft workflows</span><strong>{jobs.filter((job) => job.status !== "active").length}</strong><p>Roles waiting for review or activation.</p><Link href="/jobs">Review drafts →</Link></div>
          <div><span>Needs review</span><strong>{summary?.needs_review ?? 0}</strong><p>Candidate decisions waiting on your team.</p><Link href="/jobs">Open hiring workspaces →</Link></div>
          <div><span>Failed calls</span><strong>{summary?.failed_calls ?? 0}</strong><p>Calls needing a retry or manual next step.</p><Link href="/jobs">Check pipeline →</Link></div>
        </div>
      </section>

      <section className="dashboard-jobs">
        <div className="dashboard-section-heading">
          <div><p className="eyebrow">Role portfolio</p><h2>Jobs</h2></div>
          <Link href="/jobs" className="muted" style={{ fontSize: 13 }}>View all jobs →</Link>
        </div>
        {jobs.length === 0 ? (
          <div className="card muted">
            No jobs yet. <Link href="/jobs/new">Create your first job</Link> to start hiring.
          </div>
        ) : (
          <div className="dashboard-job-grid">{jobs.slice(0, 4).map((j) => <Link className="dashboard-job-card" key={j.id} href={`/jobs/${j.id}`}><span className="job-list-icon">{j.title.slice(0, 1)}</span><div><h3>{j.title}</h3><p>{j.status === "active" ? "Hiring is active" : "Draft needs review"}</p></div><span className={`badge ${j.status}`}>{j.status}</span><small>Open workspace →</small></Link>)}</div>
        )}
      </section>

      <section className="dashboard-activity">
        <div className="dashboard-section-heading"><div><p className="eyebrow">Audit trail</p><h2>Recent activity</h2></div></div>
        {activity.length === 0 ? (
          <div className="card muted">No activity yet.</div>
        ) : (
          <div className="card">
            <ul className="activity">
              {activity.map((a, i) => (
                <li key={i}>
                  <span>{humanize(a)}</span>
                  <time className="muted">{new Date(a.created_at).toLocaleString()}</time>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </main>
  );
}
