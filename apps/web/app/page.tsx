"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, getSession, setSession, type Job, type Session } from "@/lib/api";

export default function Dashboard() {
  const [session, setLocal] = useState<Session | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLocal(getSession());
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!session) return;
    api.listJobs().then(setJobs).catch((e) => setError(e.message));
  }, [session]);

  async function connect() {
    setError(null);
    try {
      const b = await api.bootstrap("Demo Org");
      const s = { orgId: b.org_id, userId: b.user_id };
      setSession(s);
      setLocal(s);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (loading) return <main className="container">Loading…</main>;

  return (
    <main className="container">
      <div className="header">
        <h1>Hiring Dashboard</h1>
        {session ? (
          <Link className="btn" href="/jobs/new">+ Create Job</Link>
        ) : (
          <button onClick={connect}>Connect (dev session)</button>
        )}
      </div>

      {error && <p className="error">{error}</p>}

      {!session && (
        <div className="card">
          <p className="muted">
            No session yet. Click <b>Connect</b> to create a dev org + recruiter
            (calls <code>/dev/bootstrap</code>) so the console can talk to the API.
          </p>
        </div>
      )}

      {session && jobs.length === 0 && (
        <div className="card muted">No jobs yet. Create your first job to get started.</div>
      )}

      {jobs.map((j) => (
        <div className="card" key={j.id}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <div style={{ fontWeight: 600 }}>{j.title}</div>
              <div className="muted" style={{ fontSize: 13 }}>{j.id}</div>
            </div>
            <span className={`badge ${j.status}`}>{j.status}</span>
          </div>
        </div>
      ))}
    </main>
  );
}
