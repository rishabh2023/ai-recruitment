"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  api,
  type CandidateImport,
  type Job,
  type JobCandidateListItem,
} from "@/lib/api";

type FactRow = { key: string; value: string };

export default function JobCandidatesPage() {
  const { id: jobId } = useParams<{ id: string }>();

  const [job, setJob] = useState<Job | null>(null);
  const [candidates, setCandidates] = useState<JobCandidateListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // import form
  const [showForm, setShowForm] = useState(false);
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [location, setLocation] = useState("");
  const [facts, setFacts] = useState<FactRow[]>([{ key: "", value: "" }]);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [j, list] = await Promise.all([api.getJob(jobId), api.listCandidates(jobId)]);
      setJob(j);
      setCandidates(list);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    load();
  }, [load]);

  function resetForm() {
    setFullName("");
    setPhone("");
    setEmail("");
    setLocation("");
    setFacts([{ key: "", value: "" }]);
    setFormError(null);
  }

  async function submit() {
    if (!fullName.trim()) {
      setFormError("Full name is required.");
      return;
    }
    const known_facts: Record<string, string> = {};
    for (const f of facts) {
      if (f.key.trim() && f.value.trim()) known_facts[f.key.trim()] = f.value.trim();
    }
    const payload: CandidateImport = {
      full_name: fullName.trim(),
      phone: phone.trim() || undefined,
      email: email.trim() || undefined,
      location: location.trim() || undefined,
      source: "import",
      known_facts,
    };
    setBusy(true);
    setFormError(null);
    try {
      await api.importCandidate(jobId, payload);
      resetForm();
      setShowForm(false);
      await load();
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <main className="container">Loading…</main>;

  return (
    <main className="container">
      <div className="header">
        <div>
          <Link href="/">← Dashboard</Link>
          <h1 style={{ marginTop: 8 }}>{job ? job.title : "Candidates"}</h1>
          {job && (
            <span className={`badge ${job.status}`}>{job.status}</span>
          )}
        </div>
        <button onClick={() => setShowForm((s) => !s)}>{showForm ? "Cancel" : "+ Import candidate"}</button>
      </div>

      {error && <p className="error">{error}</p>}

      {job && job.status !== "active" && (
        <div className="card muted">
          This job is <b>{job.status}</b>. You can import candidates, but AI stages can only run
          once the job is active (JD confirmed and a workflow approved).
        </div>
      )}

      {showForm && (
        <div className="card" style={{ display: "grid", gap: 8 }}>
          <h3 style={{ margin: 0 }}>Import candidate</h3>
          {formError && <p className="error">{formError}</p>}
          <label>
            Full name *
            <input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Asha Rao" />
          </label>
          <div className="row" style={{ gap: 8 }}>
            <label style={{ flex: 1 }}>
              Phone
              <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+9199…" />
            </label>
            <label style={{ flex: 1 }}>
              Email
              <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" />
            </label>
          </div>
          <label>
            Location
            <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Bengaluru" />
          </label>

          <div>
            <div className="muted" style={{ fontSize: 13, marginBottom: 4 }}>
              Known facts (optional) — carried into the AI stage as starting context.
            </div>
            {facts.map((f, i) => (
              <div className="row" key={i} style={{ gap: 8, marginBottom: 6 }}>
                <input
                  aria-label="fact key"
                  placeholder="expected_ctc"
                  value={f.key}
                  onChange={(e) =>
                    setFacts((rows) => rows.map((r, j) => (j === i ? { ...r, key: e.target.value } : r)))
                  }
                />
                <input
                  aria-label="fact value"
                  placeholder="24 LPA"
                  value={f.value}
                  onChange={(e) =>
                    setFacts((rows) => rows.map((r, j) => (j === i ? { ...r, value: e.target.value } : r)))
                  }
                />
              </div>
            ))}
            <button className="linklike" onClick={() => setFacts((r) => [...r, { key: "", value: "" }])}>
              + add fact
            </button>
          </div>

          <div>
            <button disabled={busy || !fullName.trim()} onClick={submit}>
              {busy ? "Importing…" : "Import"}
            </button>
          </div>
        </div>
      )}

      {candidates.length === 0 ? (
        <div className="card muted">
          No candidates yet. Import your first candidate to start the hiring journey.
        </div>
      ) : (
        candidates.map((c) => (
          <Link className="card cardlink" key={c.id} href={`/job-candidates/${c.id}`}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div>
                <div style={{ fontWeight: 600 }}>{c.candidate.full_name ?? "(unnamed)"}</div>
                <div className="muted" style={{ fontSize: 13 }}>
                  {c.candidate.phone ?? "no phone"}
                  {c.candidate.location ? ` · ${c.candidate.location}` : ""}
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                {c.pipeline_state && <span className="badge">{c.pipeline_state}</span>}
                <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                  {c.current_stage_name ?? "no stage"}
                </div>
              </div>
            </div>
          </Link>
        ))
      )}
    </main>
  );
}
