"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Job } from "@/lib/api";

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listJobs().then(setJobs).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, []);

  if (loading) return <main className="container">Loading…</main>;

  return (
    <main className="container">
      <div className="header">
        <h1>Jobs</h1>
        <Link className="btn" href="/jobs/new">+ Create Job</Link>
      </div>

      {error && <p className="error">{error}</p>}

      {jobs.length === 0 ? (
        <div className="card muted">
          No jobs yet. <Link href="/jobs/new">Create your first job</Link>.
        </div>
      ) : (
        jobs.map((j) => (
          <Link className="card cardlink" key={j.id} href={`/jobs/${j.id}/candidates`}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div>
                <div style={{ fontWeight: 600 }}>{j.title}</div>
                <div className="muted" style={{ fontSize: 13 }}>View candidates →</div>
              </div>
              <span className={`badge ${j.status}`}>{j.status}</span>
            </div>
          </Link>
        ))
      )}
    </main>
  );
}
