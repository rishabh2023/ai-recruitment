"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  api,
  type ExternalCandidate,
  type Job,
  type PeopleSearchInput,
  type PeopleSearchResult,
} from "@/lib/api";

const EMPTY_QUERY: PeopleSearchInput = {
  titles: [],
  keywords: [],
  locations: [],
  skills: [],
  seniorities: [],
  page: 1,
  page_size: 25,
};

// comma-separated <-> string[] helpers for the form fields
const toText = (xs: string[]) => xs.join(", ");
const toList = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const keyOf = (c: ExternalCandidate) => `${c.source}:${c.source_id}`;

function SourcingInner() {
  const router = useRouter();
  const params = useSearchParams();
  const jobParam = params.get("job");

  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [jobId, setJobId] = useState<string | null>(jobParam);

  const [titles, setTitles] = useState("");
  const [locations, setLocations] = useState("");
  const [seniorities, setSeniorities] = useState("");
  const [keywords, setKeywords] = useState("");
  const [skills, setSkills] = useState("");

  const [result, setResult] = useState<PeopleSearchResult | null>(null);
  const [selected, setSelected] = useState<Record<string, ExternalCandidate>>({});
  const [searching, setSearching] = useState(false);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  useEffect(() => {
    api
      .listJobs()
      .then((all) => {
        setJobs(all);
        if (!jobId && all.length === 1) setJobId(all[0].id);
      })
      .catch((e) => setError(e.message))
      .finally(() => setJobsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applyQuery = useCallback((q: PeopleSearchInput) => {
    setTitles(toText(q.titles));
    setLocations(toText(q.locations));
    setSeniorities(toText(q.seniorities));
    setKeywords(toText(q.keywords));
    setSkills(toText(q.skills));
  }, []);

  // When a job is chosen, prefill the form from its JD-derived suggested query.
  useEffect(() => {
    if (!jobId) return;
    setResult(null);
    setSelected({});
    setError(null);
    api.suggestedQuery(jobId).then(applyQuery).catch(() => {});
  }, [jobId, applyQuery]);

  const selectedList = useMemo(() => Object.values(selected), [selected]);
  const activeJob = jobs.find((j) => j.id === jobId) || null;

  async function runSearch(page = 1) {
    if (!jobId) return;
    setSearching(true);
    setError(null);
    setFlash(null);
    try {
      const q: PeopleSearchInput = {
        titles: toList(titles),
        locations: toList(locations),
        seniorities: toList(seniorities),
        keywords: toList(keywords),
        skills: toList(skills),
        page,
        page_size: 25,
      };
      const res = await api.peopleSearch(jobId, q);
      setResult(res);
      setSelected({});
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSearching(false);
    }
  }

  function toggle(c: ExternalCandidate) {
    setSelected((prev) => {
      const next = { ...prev };
      const k = keyOf(c);
      if (next[k]) delete next[k];
      else next[k] = c;
      return next;
    });
  }

  function toggleAll() {
    if (!result) return;
    const all = result.candidates;
    const allSelected = all.every((c) => selected[keyOf(c)]);
    if (allSelected) setSelected({});
    else setSelected(Object.fromEntries(all.map((c) => [keyOf(c), c])));
  }

  async function addSelected() {
    if (!jobId || selectedList.length === 0) return;
    setAdding(true);
    setError(null);
    try {
      const res = await api.addSourced(jobId, selectedList);
      const parts = [`${res.added} added to the pipeline`];
      if (res.skipped) parts.push(`${res.skipped} skipped (already in pipeline)`);
      setFlash(parts.join(" · "));
      setSelected({});
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAdding(false);
    }
  }

  if (jobsLoading) return <main className="container">Loading…</main>;

  return (
    <main className="container sourcing-page">
      <header className="jobs-header">
        <div>
          <p className="eyebrow">People search &amp; outreach</p>
          <h1>Sourcing</h1>
          <p>Find candidates for a role, then add the strongest matches straight into its pipeline.</p>
        </div>
        {activeJob && (
          <Link className="btn secondary" href={`/jobs/${activeJob.id}`}>
            Open {activeJob.title} →
          </Link>
        )}
      </header>

      {error && <p className="error">{error}</p>}

      {jobs.length === 0 ? (
        <div className="workspace-empty">
          You need a job before sourcing. <Link href="/jobs/new">Create your first job</Link>, approve its
          workflow, then come back to source candidates for it.
        </div>
      ) : (
        <>
          <section className="sourcing-jobpick" aria-label="Choose a role to source for">
            <label>
              <span className="field-label">Role</span>
              <select
                value={jobId ?? ""}
                onChange={(e) => {
                  const id = e.target.value || null;
                  setJobId(id);
                  router.replace(id ? `/sourcing?job=${id}` : "/sourcing");
                }}
              >
                <option value="">Select a role…</option>
                {jobs.map((j) => (
                  <option key={j.id} value={j.id}>
                    {j.title} {j.status === "active" ? "" : "(draft)"}
                  </option>
                ))}
              </select>
            </label>
          </section>

          {jobId && (
            <>
              <section className="sourcing-form" aria-label="Search filters">
                <div className="sourcing-fields">
                  <Field label="Job titles" hint="e.g. Forward Deployed Engineer" value={titles} onChange={setTitles} />
                  <Field label="Locations" hint="e.g. Bengaluru, Remote" value={locations} onChange={setLocations} />
                  <Field label="Seniority" hint="junior · mid · senior · lead" value={seniorities} onChange={setSeniorities} />
                  <Field label="Skills" hint="e.g. Python, AWS, LLM" value={skills} onChange={setSkills} />
                  <Field label="Keywords" hint="free-text match" value={keywords} onChange={setKeywords} />
                </div>
                <div className="sourcing-actions">
                  <button className="btn" onClick={() => runSearch(1)} disabled={searching}>
                    {searching ? "Searching…" : "Search candidates"}
                  </button>
                  <span className="field-hint">Filters are comma-separated. Empty fields don&apos;t restrict.</span>
                </div>
              </section>

              {flash && <p className="sourcing-flash" role="status">{flash}</p>}

              {result && (
                <section className="sourcing-results" aria-label="Search results">
                  {result.is_sample && (
                    <div className="sourcing-notice" role="note">
                      <strong>Sample data.</strong> {result.notice}
                    </div>
                  )}

                  <div className="sourcing-results-bar">
                    <div>
                      <strong>{result.candidates.length}</strong> shown
                      {typeof result.total === "number" ? ` of ${result.total}` : ""} ·{" "}
                      <span className="muted">provider: {result.provider}</span>
                    </div>
                    {result.candidates.length > 0 && (
                      <div className="sourcing-results-actions">
                        <button className="secondary" onClick={toggleAll}>
                          {result.candidates.every((c) => selected[keyOf(c)]) ? "Clear all" : "Select all"}
                        </button>
                        <button className="btn" onClick={addSelected} disabled={adding || selectedList.length === 0}>
                          {adding ? "Adding…" : `Add ${selectedList.length || ""} to pipeline`.trim()}
                        </button>
                      </div>
                    )}
                  </div>

                  {result.candidates.length === 0 ? (
                    <div className="workspace-empty">
                      No candidates matched. Broaden the filters — try fewer titles or drop the location.
                    </div>
                  ) : (
                    <ul className="sourcing-list">
                      {result.candidates.map((c) => {
                        const k = keyOf(c);
                        const checked = !!selected[k];
                        return (
                          <li key={k} className={`sourcing-card ${checked ? "selected" : ""}`}>
                            <label className="sourcing-check">
                              <input type="checkbox" checked={checked} onChange={() => toggle(c)} />
                            </label>
                            <div className="sourcing-card-main">
                              <div className="sourcing-card-top">
                                <h3>{c.full_name ?? "Unknown"}</h3>
                                {c.linkedin_url && (
                                  <a href={c.linkedin_url} target="_blank" rel="noreferrer" className="muted">
                                    LinkedIn ↗
                                  </a>
                                )}
                              </div>
                              <p className="sourcing-card-sub">
                                {[c.title, c.company].filter(Boolean).join(" · ") || "—"}
                              </p>
                              <p className="muted">{c.location ?? "Location unknown"}</p>
                            </div>
                            <span className="badge draft">contact via enrichment</span>
                          </li>
                        );
                      })}
                    </ul>
                  )}

                  {(result.page > 1 || result.has_more) && (
                    <div className="sourcing-pager">
                      <button className="secondary" disabled={result.page <= 1 || searching} onClick={() => runSearch(result.page - 1)}>
                        ← Previous
                      </button>
                      <span className="muted">Page {result.page}</span>
                      <button className="secondary" disabled={!result.has_more || searching} onClick={() => runSearch(result.page + 1)}>
                        Next →
                      </button>
                    </div>
                  )}
                </section>
              )}
            </>
          )}
        </>
      )}
    </main>
  );
}

function Field({ label, hint, value, onChange }: { label: string; hint: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="sourcing-field">
      <span className="field-label">{label}</span>
      <input value={value} placeholder={hint} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

export default function SourcingPage() {
  return (
    <Suspense fallback={<main className="container">Loading…</main>}>
      <SourcingInner />
    </Suspense>
  );
}
