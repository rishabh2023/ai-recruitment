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
import WorkflowEditor, { stagesToEdit } from "@/components/WorkflowEditor";

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
  const currentStep = job?.status === "active" ? null : workflow?.approved ? 4 : version?.confirmed ? 3 : job ? 2 : 1;

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
    <main className="container job-create">
      <div className="job-create-header">
        <div>
          <Link className="back-link" href="/">← Dashboard</Link>
          <p className="eyebrow">New hiring funnel</p>
          <h1>Create a job</h1>
          <p className="muted">Set the role, review the AI draft, then approve a funnel your team can run with.</p>
        </div>
        <ol className="wizard-progress" aria-label="Job creation progress">
          <li className={job ? "complete" : "current"} aria-current={currentStep === 1 ? "step" : undefined}>1 · Role</li>
          <li className={version?.confirmed ? "complete" : job ? "current" : ""} aria-current={currentStep === 2 ? "step" : undefined}>2 · Job details</li>
          <li className={workflow?.approved ? "complete" : version?.confirmed ? "current" : ""} aria-current={currentStep === 3 ? "step" : undefined}>3 · Funnel</li>
          <li className={job?.status === "active" ? "complete" : workflow?.approved ? "current" : ""} aria-current={currentStep === 4 ? "step" : undefined}>4 · Activate</li>
        </ol>
      </div>
      {error && <p className="error">{error}</p>}

      <div className="job-create-layout">
        <aside className="create-context">
          <p className="eyebrow">Build with confidence</p>
          <h2>{!job ? "Start with the role" : !version?.confirmed ? "Add role context" : !workflow?.approved ? "Shape the process" : "Ready to launch"}</h2>
          <p>{!job ? "A clear title anchors the job description, funnel, and candidate journey." : !version?.confirmed ? "Paste a description or upload a PDF. You will review AI extraction before it is used." : !workflow?.approved ? "Your team can customize every stage before a recruiter approves it." : "The funnel is approved. Activate the role when you are ready to accept candidates."}</p>
          <div className="create-context-steps"><span className={job ? "done" : "active"}>01 <b>Role</b></span><span className={version?.confirmed ? "done" : job ? "active" : ""}>02 <b>Job details</b></span><span className={workflow?.approved ? "done" : version?.confirmed ? "active" : ""}>03 <b>Funnel</b></span><span className={job?.status === "active" ? "done" : workflow?.approved ? "active" : ""}>04 <b>Activate</b></span></div>
        </aside>
        <div className="job-create-steps">

      {/* Step 1 — create */}
      <section className={`wizard-step ${job ? "done" : ""}`}>
        <div className="step-marker">1</div>
        <div className="step-heading"><div><p className="eyebrow">Start here</p><h2>Role details</h2><p>Give the hiring team a clear name for this position.</p></div>{job && <span className="step-status">Complete</span>}</div>
        {!job ? (
          <div className="step-card compact-card">
            <label htmlFor="job-title">Job title</label>
            <div className="form-action-row"><input id="job-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Backend Engineer" /><button disabled={busy || !title} onClick={() => run(async () => setJob(await api.createJob(title)))}>Create role</button></div>
          </div>
        ) : (
          <div className="step-card completed-card"><div><strong>{job.title}</strong><p>Role created and ready for job details.</p></div><span className={`badge ${job.status}`}>{job.status}</span></div>
        )}
      </section>

      {/* Step 2 — JD + extraction */}
      {job && (
        <section className={`wizard-step ${version?.confirmed ? "done" : ""}`}>
          <div className="step-marker">2</div>
          <div className="step-heading"><div><p className="eyebrow">Role context</p><h2>Job description</h2><p>Use text or a PDF. You will confirm the extracted details before we draft a funnel.</p></div>{version?.confirmed && <span className="step-status">Confirmed</span>}</div>
          {!version ? (
            <div className="step-card">
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
                  <label htmlFor="job-description">Paste the job description</label>
                  <textarea id="job-description" rows={8} value={jd} onChange={(e) => setJd(e.target.value)} placeholder="Paste the full job description, key responsibilities, and required skills…" />
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
            </div>
          ) : (
            <div className="step-card extraction-card">
              <div className="card-intro"><div><p className="eyebrow">AI draft</p><h3>Review extracted job details</h3></div><span className="badge">Needs confirmation</span></div>
              <pre>{JSON.stringify(version.extracted, null, 2)}</pre>
              {!version.confirmed ? (
                <button disabled={busy} onClick={() => run(async () => setVersion(await api.confirmVersion(job.id, version.id)))}>
                  Confirm details
                </button>
              ) : (
                <p className="muted">✓ Confirmed</p>
              )}
            </div>
          )}
        </section>
      )}

      {/* Step 3 — workflow */}
      {version?.confirmed && (
        <section className={`wizard-step workflow-step ${workflow?.approved ? "done" : ""}`}>
          <div className="step-marker">3</div>
          <div className="step-heading"><div><p className="eyebrow">Recruiter review</p><h2>Hiring funnel</h2><p>Customize stages and success criteria before this funnel can be used.</p></div>{workflow?.approved && <span className="step-status">Approved</span>}</div>
          {!workflow ? (
            <div className="step-card empty-workflow"><div><h3>Generate a first draft</h3><p>We will suggest stages and criteria from the confirmed job description. You remain in control before approval.</p></div><button
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const wf = await api.draftWorkflow(job!.id);
                  setWorkflow(wf);
                  setWfDetail(await api.getJobWorkflow(job!.id));
                })
              }
            >{busy ? "Drafting…" : "Draft funnel"}</button></div>
          ) : (
            <>
              {!workflow.approved ? (
                <>
                  <div className="workflow-review-note"><span>✦</span><p>Review each stage, set what it collects, and adjust the criteria that guide decisions.</p></div>
                  {wfDetail && (
                    <WorkflowEditor
                      initialStages={stagesToEdit(wfDetail.stages)}
                      saveLabel="Save funnel changes"
                      onSave={async (s) => {
                        const wf = await api.editWorkflowStages(job!.id, wfDetail.version_id, s);
                        setWfDetail(wf);
                        return stagesToEdit(wf.stages);
                      }}
                    />
                  )}
                  <div className="workflow-approval">
                    <div><strong>Ready to make this funnel live?</strong><p>After approval, stage changes require a new funnel version.</p></div>
                    <button disabled={busy} onClick={() => run(async () => setWorkflow(await api.approveWorkflow(job!.id, workflow.id)))}>
                      {busy ? "Approving…" : "Approve funnel"}
                    </button>
                  </div>
                </>
              ) : (
                <p className="muted">✓ Approved</p>
              )}
            </>
          )}
        </section>
      )}

      {/* Step 4 — activate */}
      {workflow?.approved && (
        <section className={`wizard-step ${job?.status === "active" ? "done" : ""}`}>
          <div className="step-marker">4</div>
          <div className="step-heading"><div><p className="eyebrow">Launch</p><h2>Activate job</h2><p>Make this approved funnel available to your recruiting team.</p></div>{job?.status === "active" && <span className="step-status">Active</span>}</div>
          {job?.status !== "active" ? (
            <div className="step-card activate-card"><div><h3>Everything is ready</h3><p>Candidates can be added after activation.</p></div><button disabled={busy} onClick={() => run(async () => setJob(await api.activateJob(job!.id)))}>{busy ? "Activating…" : "Activate job"}</button></div>
          ) : (
            <div className="step-card completed-card"><div><strong>Job is active</strong><p>Your team can now add candidates and begin the hiring funnel.</p></div><Link className="btn" href={`/jobs/${job.id}/candidates`}>Add candidates</Link></div>
          )}
        </section>
      )}
        </div>
      </div>
    </main>
  );
}
