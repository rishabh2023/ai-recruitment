"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, type Job } from "@/lib/api";
import ConfirmDialog from "@/components/ConfirmDialog";

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]); const [query, setQuery] = useState(""); const [filter, setFilter] = useState("all"); const [loading, setLoading] = useState(true); const [error, setError] = useState<string | null>(null);
  const [toArchive, setToArchive] = useState<Job | null>(null);
  const [toDelete, setToDelete] = useState<Job | null>(null);
  useEffect(() => { api.listJobs().then(setJobs).catch((e) => setError(e.message)).finally(() => setLoading(false)); }, []);
  const shown = useMemo(() => jobs.filter((job) => (filter === "all" || job.status === filter) && job.title.toLowerCase().includes(query.toLowerCase())), [jobs, query, filter]);
  async function archive(job: Job) {
    const updated = await api.archiveJob(job.id);
    setJobs((prev) => prev.map((j) => (j.id === updated.id ? updated : j)));
  }
  async function remove(job: Job) {
    await api.deleteJob(job.id);
    setJobs((prev) => prev.filter((j) => j.id !== job.id));
  }
  if (loading) return <main className="container">Loading jobs…</main>;
  const active = jobs.filter((job) => job.status === "active").length;
  return <main className="container jobs-page"><header className="jobs-header"><div><p className="eyebrow">Hiring portfolio</p><h1>Jobs</h1><p>Keep every role, workflow, and candidate pipeline moving from one place.</p></div><Link className="btn" href="/jobs/new">+ Create job</Link></header>{error && <p className="error">{error}</p>}<section className="jobs-metrics"><div><span>Total roles</span><strong>{jobs.length}</strong></div><div><span>Active roles</span><strong>{active}</strong></div><div><span>Drafts to review</span><strong>{jobs.filter((job) => job.status === "draft").length}</strong></div></section><section className="jobs-toolbar"><label><span className="sr-only">Search jobs</span><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search roles…" /></label><div className="jobs-filters" aria-label="Job status filter">{["all", "draft", "active", "archived"].map((status) => <button key={status} className={filter === status ? "active" : ""} onClick={() => setFilter(status)}>{status === "all" ? "All roles" : status === "archived" ? "Inactive" : status}</button>)}</div></section>{jobs.length === 0 ? <div className="workspace-empty">No jobs yet. <Link href="/jobs/new">Create your first job</Link> to begin.</div> : shown.length === 0 ? <div className="workspace-empty">No roles match this view. Clear the search or filter to see your jobs.</div> : <section className="job-list" aria-label="Jobs">{shown.map((job) => <div className="job-list-card" key={job.id}><Link className="job-list-link" href={`/jobs/${job.id}`}><div className="job-list-icon">{job.title.slice(0, 1).toUpperCase()}</div><div className="job-list-main"><h2>{job.title}</h2><p>{job.status === "active" ? "Active hiring workspace" : job.status === "archived" ? "Inactive — history is preserved" : "Draft workflow ready for review"} · Created {new Date(job.created_at).toLocaleDateString()}</p></div></Link><div className="job-list-action"><span className={`badge ${job.status}`}>{job.status === "archived" ? "inactive" : job.status}</span><Link href={`/jobs/${job.id}`}>{job.status === "active" ? "Open workspace →" : job.status === "archived" ? "View inactive role →" : "Review draft →"}</Link>{job.status !== "archived" && <button className="linklike text-danger" onClick={() => setToArchive(job)}>Archive</button>}{job.status !== "active" && <button className="linklike text-danger" onClick={() => setToDelete(job)}>Delete</button>}</div></div>)}</section>}
    <ConfirmDialog
      open={toArchive !== null}
      title="Archive this role?"
      message={toArchive ? <>“{toArchive.title}” becomes <strong>inactive</strong>. Its workflow and candidate history are kept, and you can reactivate it later.</> : null}
      confirmLabel="Archive role"
      busyLabel="Archiving…"
      danger
      onConfirm={() => toArchive ? archive(toArchive) : undefined}
      onClose={() => setToArchive(null)}
    />
    <ConfirmDialog
      open={toDelete !== null}
      title="Delete this role permanently?"
      message={toDelete ? <>This <strong>permanently deletes</strong> “{toDelete.title}” and all of its data — JD versions, workflow, candidate participations, and interview/call history for this role. This cannot be undone.</> : null}
      confirmLabel="Delete role"
      busyLabel="Deleting…"
      danger
      requireText={toDelete?.title}
      onConfirm={() => toDelete ? remove(toDelete) : undefined}
      onClose={() => setToDelete(null)}
    />
  </main>;
}
