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
    <main className="container">
      <div className="header">
        <div>
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
        <div className="stat-grid">
          <Stat label="Active jobs" value={summary.active_jobs} />
          <Stat label="Candidates in pipeline" value={summary.candidates_in_pipeline} />
          <Stat label="Needs review" value={summary.needs_review} tone="warn" />
          <Stat label="Awaiting result" value={summary.awaiting_result} tone="warn" />
          <Stat label="Failed calls" value={summary.failed_calls} tone="danger" />
          <Stat label="Total jobs" value={summary.total_jobs} />
        </div>
      )}

      <section>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h3>Active jobs</h3>
          <Link href="/jobs" className="muted" style={{ fontSize: 13 }}>View all jobs →</Link>
        </div>
        {jobs.length === 0 ? (
          <div className="card muted">
            No jobs yet. <Link href="/jobs/new">Create your first job</Link> to start hiring.
          </div>
        ) : (
          jobs.slice(0, 5).map((j) => (
            <Link className="card cardlink" key={j.id} href={`/jobs/${j.id}/candidates`}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span style={{ fontWeight: 600 }}>{j.title}</span>
                <span className={`badge ${j.status}`}>{j.status}</span>
              </div>
            </Link>
          ))
        )}
      </section>

      <section>
        <h3>Recent activity</h3>
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
