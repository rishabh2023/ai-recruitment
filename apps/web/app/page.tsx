"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Job, type Principal } from "@/lib/api";

export default function Dashboard() {
  const [me, setMe] = useState<Principal | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Login form state
  const [email, setEmail] = useState("recruiter@demo.test");
  const [password, setPassword] = useState("demo-password");

  useEffect(() => {
    api.me().then((p) => {
      setMe(p);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (!me) return;
    api.listJobs().then(setJobs).catch((e) => setError(e.message));
  }, [me]);

  async function login() {
    setError(null);
    try {
      setMe(await api.login(email, password));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function createDemoOrg() {
    setError(null);
    try {
      await api.bootstrap("Demo Org", email, password);
      setMe(await api.login(email, password));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function logout() {
    await api.logout().catch(() => {});
    setMe(null);
    setJobs([]);
  }

  if (loading) return <main className="container">Loading…</main>;

  if (!me) {
    return (
      <main className="container">
        <div className="header">
          <h1>Sign in</h1>
        </div>
        {error && <p className="error">{error}</p>}
        <div className="card" style={{ display: "grid", gap: 12, maxWidth: 380 }}>
          <label>
            Email
            <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" />
          </label>
          <label>
            Password
            <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" />
          </label>
          <button onClick={login}>Sign in</button>
          <p className="muted" style={{ fontSize: 13 }}>
            No account yet?{" "}
            <button className="linklike" onClick={createDemoOrg}>
              Create a demo org
            </button>{" "}
            (dev: calls <code>/dev/bootstrap</code>).
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="container">
      <div className="header">
        <h1>Hiring Dashboard</h1>
        <div className="row" style={{ gap: 8 }}>
          <Link className="btn" href="/jobs/new">+ Create Job</Link>
          <button onClick={logout}>Sign out</button>
        </div>
      </div>

      <p className="muted" style={{ fontSize: 13 }}>
        Signed in as <b>{me.role}</b> · org <code>{me.org_id}</code>
      </p>

      {error && <p className="error">{error}</p>}

      {jobs.length === 0 && (
        <div className="card muted">No jobs yet. Create your first job to get started.</div>
      )}

      {jobs.map((j) => (
        <Link className="card cardlink" key={j.id} href={`/jobs/${j.id}/candidates`}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <div style={{ fontWeight: 600 }}>{j.title}</div>
              <div className="muted" style={{ fontSize: 13 }}>View candidates →</div>
            </div>
            <span className={`badge ${j.status}`}>{j.status}</span>
          </div>
        </Link>
      ))}
    </main>
  );
}
