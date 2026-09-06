"use client";

import { useState } from "react";
import Link from "next/link";
import {
  api,
  type Job,
  type JobVersion,
  type JobWorkflow,
  type WorkflowVersion,
} from "@/lib/api";
import WorkflowEditor from "@/components/WorkflowEditor";

export default function CreateJob() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [title, setTitle] = useState("");
  const [job, setJob] = useState<Job | null>(null);

  const [jd, setJd] = useState("");
  const [version, setVersion] = useState<JobVersion | null>(null);
  const [jdMode, setJdMode] = useState<"paste" | "upload">("paste");
  const [pdfName, setPdfName] = useState<string | null>(null);

  const [workflow, setWorkflow] = useState<WorkflowVersion | null>(null);
  const [wfDetail, setWfDetail] = useState<JobWorkflow | null>(null);

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
              <div className="tabs" style={{ maxWidth: 280, marginBottom: 12 }} role="tablist">
                <button
                  role="tab"
                  aria-selected={jdMode === "paste"}
                  className={`tab ${jdMode === "paste" ? "active" : ""}`}
                  onClick={() => setJdMode("paste")}
                >
                  Paste text
                </button>
                <button
                  role="tab"
                  aria-selected={jdMode === "upload"}
                  className={`tab ${jdMode === "upload" ? "active" : ""}`}
                  onClick={() => setJdMode("upload")}
                >
                  Upload PDF
                </button>
              </div>

              {jdMode === "paste" ? (
                <>
                  <label>Paste the JD</label>
                  <textarea rows={6} value={jd} onChange={(e) => setJd(e.target.value)} placeholder="Paste the full job description…" />
                  <div style={{ marginTop: 10 }}>
                    <button disabled={busy || !jd.trim()} onClick={() => run(async () => setVersion(await api.addVersion(job.id, jd)))}>
                      {busy ? "Extracting…" : "Extract details"}
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <label htmlFor="jd-pdf">Upload a JD (PDF, max 10 MB)</label>
                  <label className="filedrop" htmlFor="jd-pdf">
                    <input
                      id="jd-pdf"
                      type="file"
                      accept="application/pdf,.pdf"
                      style={{ display: "none" }}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (!f) return;
                        setPdfName(f.name);
                        run(async () => setVersion(await api.addVersionFromPdf(job.id, f)));
                      }}
                    />
                    <span className="fileicon">⬆</span>
                    <span>{busy ? "Extracting from PDF…" : pdfName ? pdfName : "Click to choose a PDF, or drop it here"}</span>
                  </label>
                  <p className="muted" style={{ fontSize: 13 }}>
                    We extract the text and pull out role details. Scanned/image-only PDFs won&apos;t
                    work — paste the text instead.
                  </p>
                </>
              )}
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
                  setWfDetail(await api.getJobWorkflow(job!.id));
                })
              }
            >
              Draft workflow
            </button>
          ) : (
            <>
              {!workflow.approved ? (
                <>
                  <p className="muted">Review and customize the drafted stages, then approve:</p>
                  {wfDetail && (
                    <WorkflowEditor
                      jobId={job!.id}
                      versionId={wfDetail.version_id}
                      initial={wfDetail}
                      onSaved={setWfDetail}
                    />
                  )}
                  <div style={{ marginTop: 12 }}>
                    <button disabled={busy} onClick={() => run(async () => setWorkflow(await api.approveWorkflow(job!.id, workflow.id)))}>
                      Approve workflow
                    </button>
                  </div>
                </>
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
