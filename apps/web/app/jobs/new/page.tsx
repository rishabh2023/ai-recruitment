"use client";

import { useState } from "react";
import Link from "next/link";
import {
  api,
  type Job,
  type JobVersion,
  type Stage,
  type WorkflowVersion,
} from "@/lib/api";

export default function CreateJob() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [title, setTitle] = useState("");
  const [job, setJob] = useState<Job | null>(null);

  const [jd, setJd] = useState("");
  const [version, setVersion] = useState<JobVersion | null>(null);

  const [workflow, setWorkflow] = useState<WorkflowVersion | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="container">
      <div className="header">
        <h1>Create Job</h1>
        <Link href="/">← Dashboard</Link>
      </div>
      {error && <p className="error">{error}</p>}

      {/* Step 1 — create */}
      <div className={`step ${job ? "done" : ""}`}>
        <h3>1. Job</h3>
        {!job ? (
          <>
            <label>Job title</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Backend Engineer" />
            <div style={{ marginTop: 10 }}>
              <button disabled={busy || !title} onClick={() => run(async () => setJob(await api.createJob(title)))}>
                Create
              </button>
            </div>
          </>
        ) : (
          <p className="muted">Created <b>{job.title}</b> · <span className={`badge ${job.status}`}>{job.status}</span></p>
        )}
      </div>

      {/* Step 2 — JD + extraction */}
      {job && (
        <div className={`step ${version ? "done" : ""}`}>
          <h3>2. Job description</h3>
          {!version ? (
            <>
              <label>Paste the JD</label>
              <textarea rows={6} value={jd} onChange={(e) => setJd(e.target.value)} />
              <div style={{ marginTop: 10 }}>
                <button disabled={busy || !jd} onClick={() => run(async () => setVersion(await api.addVersion(job.id, jd)))}>
                  Extract details
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="muted">Extracted (confirm before continuing):</p>
              <pre>{JSON.stringify(version.extracted, null, 2)}</pre>
              {!version.confirmed ? (
                <button disabled={busy} onClick={() => run(async () => setVersion(await api.confirmVersion(job.id, version.id)))}>
                  Confirm details
                </button>
              ) : (
                <p className="muted">✓ Confirmed</p>
              )}
            </>
          )}
        </div>
      )}

      {/* Step 3 — workflow */}
      {version?.confirmed && (
        <div className={`step ${workflow?.approved ? "done" : ""}`}>
          <h3>3. Hiring workflow</h3>
          {!workflow ? (
            <button
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const wf = await api.draftWorkflow(job!.id);
                  setWorkflow(wf);
                  setStages(await api.listStages(job!.id, wf.id));
                })
              }
            >
              Draft workflow
            </button>
          ) : (
            <>
              <p className="muted">Review the drafted stages, then approve:</p>
              {stages.map((s) => (
                <div className="card" key={s.id}>
                  <b>{s.stage_order}. {s.name}</b> <span className="badge">{s.execution_type}</span>
                </div>
              ))}
              {!workflow.approved ? (
                <button disabled={busy} onClick={() => run(async () => setWorkflow(await api.approveWorkflow(job!.id, workflow.id)))}>
                  Approve workflow
                </button>
              ) : (
                <p className="muted">✓ Approved</p>
              )}
            </>
          )}
        </div>
      )}

      {/* Step 4 — activate */}
      {workflow?.approved && (
        <div className={`step ${job?.status === "active" ? "done" : ""}`}>
          <h3>4. Activate</h3>
          {job?.status !== "active" ? (
            <button disabled={busy} onClick={() => run(async () => setJob(await api.activateJob(job!.id)))}>
              Activate job
            </button>
          ) : (
            <p className="muted">✓ Job is active. Add candidates next.</p>
          )}
        </div>
      )}
    </main>
  );
}
