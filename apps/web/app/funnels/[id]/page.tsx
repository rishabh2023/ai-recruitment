"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, type FunnelDetail, type FunnelStageSpec, type Job } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import ConfirmDialog from "@/components/ConfirmDialog";
import WorkflowEditor, { stagesToEdit } from "@/components/WorkflowEditor";

const EXEC: Record<string, string> = { ai: "AI call", human: "Human review", system: "System" };

function StageView({ stage }: { stage: FunnelStageSpec }) {
  return (
    <article className="workspace-stage-card">
      <div className="workspace-stage-topline">
        <span className="stage-number">{String(stage.stage_order).padStart(2, "0")}</span>
        <span className={`badge exec-${stage.execution_type}`}>{EXEC[stage.execution_type] ?? stage.execution_type}</span>
      </div>
      <h3>{stage.name}</h3>
      <p>{stage.purpose || "No purpose described."}</p>
      <div className="workspace-stage-foot"><span>{stage.criteria.length} criteria</span>{stage.requires_human_approval && <span>Human checkpoint</span>}</div>
    </article>
  );
}

export default function FunnelDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { me } = useAuth();
  const isAdmin = me?.role === "admin";
  const [funnel, setFunnel] = useState<FunnelDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [busy, setBusy] = useState(false);
  // "use in a job"
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [usePanel, setUsePanel] = useState(false);
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [selectedJob, setSelectedJob] = useState("");
  const [applied, setApplied] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setFunnel(await api.getFunnel(id)); }
    catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  async function run(fn: () => Promise<void>) { setBusy(true); setError(null); try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }

  async function openUsePanel() {
    setUsePanel(true); setApplied(null);
    if (jobs === null) { try { setJobs(await api.listJobs()); } catch (e) { setError((e as Error).message); } }
  }

  if (loading) return <main className="container">Loading funnel…</main>;
  if (!funnel) return <main className="container"><Link href="/funnels">← Funnels</Link><p className="error">{error ?? "Funnel not found."}</p></main>;

  return (
    <main className="container">
      <header className="page-head">
        <div>
          <Link className="back-link" href="/funnels">← Funnels</Link>
          <p className="eyebrow">Reusable funnel</p>
          {renaming ? (
            <div className="row" style={{ gap: 8 }}>
              <input value={nameDraft} onChange={(e) => setNameDraft(e.target.value)} />
              <button disabled={busy} onClick={() => run(async () => { const f = await api.renameFunnel(id, nameDraft.trim()); setFunnel(f); setRenaming(false); })}>Save</button>
              <button className="secondary" onClick={() => setRenaming(false)}>Cancel</button>
            </div>
          ) : (
            <h1>{funnel.name}{funnel.archived && <span className="badge archived" style={{ marginLeft: 10, fontSize: 13 }}>archived</span>}</h1>
          )}
          <p className="muted">Version {funnel.version} · {funnel.stages.length} stage{funnel.stages.length === 1 ? "" : "s"}. Editing creates a new version; jobs already using this funnel keep their own copy.</p>
        </div>
        {isAdmin && !editing && !renaming && (
          <div className="row" style={{ gap: 8 }}>
            <button onClick={openUsePanel}>Use in a job</button>
            <button className="secondary" onClick={() => setEditing(true)}>Edit stages</button>
            <button className="secondary" onClick={() => { setNameDraft(funnel.name); setRenaming(true); }}>Rename</button>
            {!funnel.archived && <button className="secondary text-danger" onClick={() => setConfirmArchive(true)}>Archive</button>}
          </div>
        )}
      </header>

      {error && <p className="error">{error}</p>}
      {!isAdmin && <p className="muted">You have view-only access. An admin can edit or apply this funnel.</p>}

      {usePanel && isAdmin && (
        <section className="card funnel-use">
          <h3>Apply this funnel to a job</h3>
          <p className="muted">This copies the funnel's stages into the job as an unapproved workflow draft for review.</p>
          {applied ? (
            <p className="ok">Applied ✓ <Link href={`/jobs/${applied}`}>Open the job&apos;s workflow →</Link></p>
          ) : (
            <div className="row" style={{ gap: 8, marginTop: 8 }}>
              <select value={selectedJob} onChange={(e) => setSelectedJob(e.target.value)}>
                <option value="">Select a job…</option>
                {(jobs ?? []).map((j) => <option key={j.id} value={j.id}>{j.title} ({j.status})</option>)}
              </select>
              <button disabled={busy || !selectedJob} onClick={() => run(async () => { await api.useFunnel(id, selectedJob); setApplied(selectedJob); })}>{busy ? "Applying…" : "Apply funnel"}</button>
              <button className="secondary" onClick={() => setUsePanel(false)}>Close</button>
            </div>
          )}
        </section>
      )}

      {editing && isAdmin ? (
        <section className="workspace-section">
          <div className="workspace-section-heading"><div><p className="eyebrow">Editing</p><h2>Funnel stages</h2><p>Saving publishes a new version of this funnel.</p></div></div>
          <WorkflowEditor
            initialStages={stagesToEdit(funnel.stages)}
            saveLabel="Save as new version"
            onSave={async (stages) => { const f = await api.editFunnelStages(id, stages); setFunnel(f); setEditing(false); return stagesToEdit(f.stages); }}
          />
          <button className="secondary" style={{ marginTop: 8 }} onClick={() => setEditing(false)}>Cancel</button>
        </section>
      ) : (
        <section className="workspace-section">
          {funnel.stages.length === 0
            ? <div className="workspace-empty">This funnel has no stages yet.</div>
            : <div className="workspace-stage-grid">{funnel.stages.map((s) => <StageView key={s.stage_order} stage={s} />)}</div>}
        </section>
      )}

      <ConfirmDialog
        open={confirmArchive}
        title="Archive this funnel?"
        message={<>“{funnel.name}” will be hidden from the funnel library. Jobs that already use it keep their own copy. You can still find it with “Show archived”.</>}
        confirmLabel="Archive funnel"
        busyLabel="Archiving…"
        danger
        onConfirm={async () => { await api.archiveFunnel(id); await load(); }}
        onClose={() => setConfirmArchive(false)}
      />
    </main>
  );
}
