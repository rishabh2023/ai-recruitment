"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, type OrgCandidateListItem } from "@/lib/api";
import ConfirmDialog from "@/components/ConfirmDialog";

function stateLabel(s: string | null): string {
  if (!s) return "—";
  return s.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
}

export default function CandidatesPage() {
  const [rows, setRows] = useState<OrgCandidateListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [state, setState] = useState("all");
  const [toDelete, setToDelete] = useState<OrgCandidateListItem | null>(null);

  useEffect(() => { api.listAllCandidates().then(setRows).catch((e) => setError((e as Error).message)); }, []);

  async function remove(row: OrgCandidateListItem) {
    await api.deleteJobCandidate(row.id);
    setRows((prev) => (prev ?? []).filter((r) => r.id !== row.id));
  }

  const states = useMemo(() => {
    const set = new Set<string>();
    (rows ?? []).forEach((r) => { if (r.pipeline_state) set.add(r.pipeline_state); });
    return ["all", ...Array.from(set)];
  }, [rows]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (rows ?? []).filter((r) => {
      if (state !== "all" && r.pipeline_state !== state) return false;
      if (!q) return true;
      return [r.candidate.full_name, r.candidate.email, r.candidate.phone, r.job_title]
        .some((v) => (v ?? "").toLowerCase().includes(q));
    });
  }, [rows, query, state]);

  return (
    <main className="container">
      <header className="page-head">
        <div>
          <p className="eyebrow">Talent directory</p>
          <h1>Candidates</h1>
          <p className="muted">Everyone across every job. A person applying to more than one role appears once per role.</p>
        </div>
      </header>

      {error && <p className="error">{error}</p>}

      <section className="jobs-toolbar">
        <label><span className="sr-only">Search candidates</span><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by name, email, phone, or job…" /></label>
        <div className="jobs-filters" aria-label="Pipeline state filter">
          {states.map((s) => <button key={s} className={state === s ? "active" : ""} onClick={() => setState(s)}>{s === "all" ? "All" : stateLabel(s)}</button>)}
        </div>
      </section>

      {rows === null ? (
        <p className="muted">Loading candidates…</p>
      ) : rows.length === 0 ? (
        <div className="workspace-empty">No candidates yet. Add or import candidates from a job to see them here.</div>
      ) : shown.length === 0 ? (
        <div className="workspace-empty">No candidates match this view.</div>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr><th>Candidate</th><th>Job</th><th>Stage</th><th>State</th><th>Added</th><th aria-label="Actions" /></tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link href={`/job-candidates/${r.id}`} className="cell-strong candidate-name">{r.candidate.full_name ?? "(unnamed)"}</Link>
                    <div className="muted cell-sub">{r.candidate.email ?? r.candidate.phone ?? "No contact on file"}</div>
                  </td>
                  <td><Link href={`/jobs/${r.job_id}`}>{r.job_title}</Link></td>
                  <td>{r.current_stage_name ?? <span className="muted">—</span>}</td>
                  <td><span className="badge">{stateLabel(r.pipeline_state)}</span></td>
                  <td className="muted">{new Date(r.created_at).toLocaleDateString()}</td>
                  <td className="cell-action"><Link href={`/job-candidates/${r.id}`}>Open →</Link> <button className="linklike text-danger" style={{ marginLeft: 12 }} onClick={() => setToDelete(r)}>Delete</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows && rows.length > 0 && <p className="muted" style={{ marginTop: 12 }}>{shown.length} of {rows.length}</p>}

      <ConfirmDialog
        open={toDelete !== null}
        title="Remove this candidate from the job?"
        message={toDelete ? <>This removes <strong>{toDelete.candidate.full_name ?? "this candidate"}</strong> from “{toDelete.job_title}”, including their stage runs and call history for this role. The candidate&apos;s other jobs are unaffected. This cannot be undone.</> : null}
        confirmLabel="Remove candidate"
        busyLabel="Removing…"
        danger
        onConfirm={() => toDelete ? remove(toDelete) : undefined}
        onClose={() => setToDelete(null)}
      />
    </main>
  );
}
