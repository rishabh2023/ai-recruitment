"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type DashboardSummary, type Job } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import Icon from "@/components/Icon";

function Stat({ icon, label, value, tone }: { icon: string; label: string; value: number; tone?: "warn" | "danger" }) {
  return (
    <div className={`stat ${value > 0 && tone ? tone : ""}`}>
      <span className="stat-icon"><Icon name={icon} size={18} /></span>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

const STEPS = [
  { icon: "file", title: "Create a role & add your JD", body: "Paste or upload a job description. We read it and draft the essentials — no forms to fill." },
  { icon: "funnels", title: "Shape the hiring funnel", body: "Start from a proven template or let AI draft your stages and scoring, then tweak and approve." },
  { icon: "rocket", title: "Add candidates & hire with confidence", body: "Source or import people, run AI screening calls, and move the best forward on evidence." },
];

// In-memory cache of the last successful dashboard load, scoped to the signed-in user.
// It survives client-side navigation (Dashboard → Jobs → back) within the SPA session, so
// returning renders the last data instantly and revalidates in the background instead of
// flashing the full-page "Loading…" state on every re-entry. Scoped by user id so a different
// account (after logout/login in the same tab, no full reload) never sees stale data.
let dashboardCache: { userId: string; summary: DashboardSummary; jobs: Job[] } | null = null;

export default function Dashboard() {
  const { me } = useAuth();
  const cached = me && dashboardCache?.userId === me.user_id ? dashboardCache : null;
  const [summary, setSummary] = useState<DashboardSummary | null>(cached?.summary ?? null);
  const [jobs, setJobs] = useState<Job[]>(cached?.jobs ?? []);
  // Only block the whole page on the very first load (no cache yet). On return visits we
  // already have data to show, so revalidation happens silently.
  const [loading, setLoading] = useState(!cached);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.dashboardSummary(), api.listJobs()])
      .then(([s, j]) => {
        if (cancelled) return;
        if (me) dashboardCache = { userId: me.user_id, summary: s, jobs: j };
        setSummary(s);
        setJobs(j);
        setError(null);
      })
      .catch((e) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [me]);

  if (loading) return <main className="container">Loading…</main>;

  const firstName = me?.name ? me.name.split(" ")[0] : null;
  const isEmpty = (summary?.total_jobs ?? 0) === 0;

  return (
    <main className="container dashboard-page">
      <div className="dashboard-header">
        <div>
          <p className="eyebrow">Hiring command center</p>
          <h1 style={{ marginBottom: 4 }}>{firstName ? `Welcome, ${firstName}` : "Hiring Dashboard"}</h1>
          <p className="muted" style={{ margin: 0 }}>What&apos;s happening in hiring right now, and what needs your attention.</p>
        </div>
        <Link className="btn" href="/jobs/new">+ Create Job</Link>
      </div>

      {error && <p className="error">{error}</p>}

      {isEmpty ? (
        <>
          <section className="launchpad">
            <div className="launchpad-glow" aria-hidden="true" />
            <div className="launchpad-inner">
              <p className="eyebrow launchpad-eyebrow"><Icon name="spark" size={15} style={{ verticalAlign: "-2px", marginRight: 6 }} />Let&apos;s make your first hire</p>
              <h2>From job description to hired — in one place.</h2>
              <p>You have a clean slate. Set up your first role and the platform drafts the workflow, screens candidates, and keeps every decision on the record.</p>
              <div className="launchpad-cta">
                <Link className="btn" href="/jobs/new">Add your first job</Link>
                <Link className="linklike" href="/funnels">Or browse funnel templates →</Link>
              </div>
            </div>
          </section>

          <section className="dashboard-attention">
            <div className="dashboard-section-heading"><div><p className="eyebrow">How it works</p><h2>Three steps to hire with confidence</h2></div></div>
            <ol className="steps-grid">
              {STEPS.map((s, i) => (
                <li key={i} className="step-card">
                  <div className="step-top"><span className="step-num">{i + 1}</span><span className="step-icon"><Icon name={s.icon} size={20} /></span></div>
                  <h3>{s.title}</h3>
                  <p>{s.body}</p>
                </li>
              ))}
            </ol>
          </section>
        </>
      ) : (
        <>
          {summary && (
            <div className="stat-grid dashboard-stats">
              <Stat icon="jobs" label="Active jobs" value={summary.active_jobs} />
              <Stat icon="candidates" label="Candidates in pipeline" value={summary.candidates_in_pipeline} />
              <Stat icon="review" label="Needs review" value={summary.needs_review} tone="warn" />
              <Stat icon="clock" label="Awaiting result" value={summary.awaiting_result} tone="warn" />
              <Stat icon="phone" label="Failed calls" value={summary.failed_calls} tone="danger" />
              <Stat icon="layers" label="Total jobs" value={summary.total_jobs} />
            </div>
          )}

          <section className="dashboard-attention">
            <div className="dashboard-section-heading"><div><p className="eyebrow">Focus now</p><h2>Hiring attention</h2></div></div>
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
            <div className="dashboard-job-grid">{jobs.slice(0, 4).map((j) => <Link className="dashboard-job-card" key={j.id} href={`/jobs/${j.id}`}><span className="job-list-icon">{j.title.slice(0, 1)}</span><div><h3>{j.title}</h3><p>{j.status === "active" ? "Hiring is active" : "Draft needs review"}</p></div><span className={`badge ${j.status}`}>{j.status}</span><small>Open workspace →</small></Link>)}</div>
          </section>
        </>
      )}
    </main>
  );
}
