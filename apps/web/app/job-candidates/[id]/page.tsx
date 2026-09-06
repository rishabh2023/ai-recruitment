"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, type Timeline } from "@/lib/api";

// Stage-run statuses that mean "an AI stage can be launched now".
const LAUNCHABLE = new Set(["READY", "SCHEDULED"]);
// Terminal states a recruiter can retry from (e.g. candidate didn't answer).
const RETRYABLE = new Set(["FAILED", "CANCELLED"]);

export default function CandidateDetailPage() {
  const { id: jcId } = useParams<{ id: string }>();

  const [tl, setTl] = useState<Timeline | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [launchNote, setLaunchNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setTl(await api.timeline(jcId));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [jcId]);

  useEffect(() => {
    load();
  }, [load]);

  async function launch() {
    setLaunching(true);
    setLaunchError(null);
    setLaunchNote(null);
    try {
      const r = await api.launch(jcId);
      setLaunchNote(
        r.dispatched
          ? `AI call placed via Hunar — status ${r.normalized_status}.`
          : `AI stage queued — status ${r.normalized_status}. (Live calling is off; enable it to dial.)`,
      );
      await load();
    } catch (e) {
      // External/API or state failure: surface reason + next action (retryable).
      setLaunchError((e as Error).message);
    } finally {
      setLaunching(false);
    }
  }

  async function syncCall(callId: string) {
    setLaunchError(null);
    try {
      await api.syncCall(callId);
      await load();
    } catch (e) {
      setLaunchError((e as Error).message);
    }
  }

  if (loading) return <main className="container">Loading…</main>;
  if (error)
    return (
      <main className="container">
        <Link href="/">← Dashboard</Link>
        <p className="error">{error}</p>
        <button onClick={load}>Retry</button>
      </main>
    );
  if (!tl) return null;

  const c = tl.candidate;
  const latestRun = tl.stage_runs[tl.stage_runs.length - 1];
  const isRetry = !!latestRun && RETRYABLE.has(latestRun.status);
  const canLaunch = !!latestRun && (LAUNCHABLE.has(latestRun.status) || isRetry);

  return (
    <main className="container">
      <div className="header">
        <div>
          <Link href={`/jobs/${tl.job_candidate.job_id}/candidates`}>← Candidates</Link>
          <h1 style={{ marginTop: 8 }}>{c.full_name ?? "(unnamed candidate)"}</h1>
          {tl.job_candidate.pipeline_state && (
            <span className="badge">{tl.job_candidate.pipeline_state}</span>
          )}
        </div>
        <div style={{ textAlign: "right" }}>
          <button onClick={launch} disabled={launching || !canLaunch} title={canLaunch ? "" : "No stage is ready to launch"}>
            {launching ? (isRetry ? "Retrying…" : "Launching…") : isRetry ? "Retry call" : "Launch AI stage"}
          </button>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
            <button className="linklike" onClick={load}>Refresh</button>
          </div>
        </div>
      </div>

      {isRetry && !launchNote && (
        <p className="muted" style={{ fontSize: 13 }}>
          The last attempt didn&apos;t connect (candidate didn&apos;t answer). Use <b>Retry call</b> to try again.
        </p>
      )}
      {launchNote && <p className="ok">{launchNote}</p>}
      {launchError && (
        <div className="card" style={{ borderColor: "var(--danger, #b91c1c)" }}>
          <p className="error" style={{ margin: 0 }}>Could not launch: {launchError}</p>
          <p className="muted" style={{ fontSize: 13 }}>
            The candidate&apos;s state is unchanged. Fix the cause (e.g. confirm the stage is
            ready), then retry.{" "}
            <button className="linklike" onClick={launch} disabled={launching}>Retry</button>
          </p>
        </div>
      )}

      {/* Profile */}
      <section>
        <h3>Profile</h3>
        <div className="card">
          <dl className="kv">
            <dt>Phone</dt><dd>{c.phone ?? <span className="muted">— missing</span>}</dd>
            <dt>Email</dt><dd>{c.email ?? <span className="muted">— missing</span>}</dd>
            <dt>Location</dt><dd>{c.location ?? <span className="muted">— missing</span>}</dd>
          </dl>
        </div>
      </section>

      {/* Hiring Journey */}
      <section>
        <h3>Hiring Journey</h3>
        {tl.stage_runs.length === 0 ? (
          <div className="card muted">No stages yet.</div>
        ) : (
          <ol className="timeline">
            {tl.stage_runs.map((r) => (
              <li key={r.id} className="card">
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <b>{r.stage_name ?? "Stage"}</b>
                  <span className={`badge status-${r.status}`}>{r.status}</span>
                </div>
              </li>
            ))}
          </ol>
        )}

        {tl.calls.length > 0 && (
          <>
            <h4 className="muted">Call attempts</h4>
            {tl.calls.map((call) => (
              <div className="card" key={call.id}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <span className={`badge status-${call.normalized_status}`}>{call.normalized_status}</span>
                  {call.hunar_call_id && (
                    <button className="linklike" onClick={() => syncCall(call.id)}>Sync from Hunar</button>
                  )}
                </div>
              </div>
            ))}
          </>
        )}
      </section>

      {/* Evidence & Results */}
      <section>
        <h3>Evidence &amp; Results</h3>
        {tl.facts.length === 0 ? (
          <div className="card muted">No results collected yet.</div>
        ) : (
          <div className="card">
            <table className="facts">
              <thead>
                <tr><th>Field</th><th>Value</th><th>Source</th></tr>
              </thead>
              <tbody>
                {tl.facts.map((f, i) => (
                  <tr key={i}>
                    <td>{f.field_key}</td>
                    <td>{f.value ?? <span className="muted">—</span>}</td>
                    <td className="muted">{f.source ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
