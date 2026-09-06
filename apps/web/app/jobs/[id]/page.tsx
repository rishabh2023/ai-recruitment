"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  api,
  type Job,
  type JobCandidateListItem,
  type JobWorkflow,
  type StageDetail,
} from "@/lib/api";

const EXEC_LABEL: Record<string, string> = { ai: "AI call", human: "Human", system: "System" };

function StageCard({ stage }: { stage: StageDetail }) {
  return (
    <div className="stage-card">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ fontWeight: 600 }}>
          {stage.stage_order}. {stage.name}
        </div>
        <span className={`badge exec-${stage.execution_type}`}>{EXEC_LABEL[stage.execution_type] ?? stage.execution_type}</span>
      </div>
      {stage.purpose && <p className="muted" style={{ fontSize: 13, margin: "6px 0" }}>{stage.purpose}</p>}
      {stage.information_requirements.length > 0 && (
        <div style={{ margin: "8px 0" }}>
          <div className="muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".04em" }}>Collects</div>
          <div className="chips">
            {stage.information_requirements.map((r) => (
              <span className="chip" key={r}>{r}</span>
            ))}
          </div>
        </div>
      )}
      {stage.criteria.length > 0 && (
        <div style={{ margin: "8px 0" }}>
          <div className="muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".04em" }}>Criteria</div>
          {stage.criteria.map((c) => (
            <div className="row" key={c.name} style={{ justifyContent: "space-between", fontSize: 13 }}>
              <span>{c.name}</span>
              <span className="muted">{c.weight != null ? `${c.weight}%` : c.kind}</span>
            </div>
          ))}
        </div>
      )}
      {stage.requires_human_approval && (
        <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>⚑ Requires human approval</div>
      )}
    </div>
  );
}

export default function JobDetailPage() {
  const { id: jobId } = useParams<{ id: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [workflow, setWorkflow] = useState<JobWorkflow | null>(null);
  const [candidates, setCandidates] = useState<JobCandidateListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [j, cs] = await Promise.all([api.getJob(jobId), api.listCandidates(jobId)]);
      setJob(j);
      setCandidates(cs);
      // Workflow may not exist yet (draft not created) — treat 404 as "none".
      try {
        setWorkflow(await api.getJobWorkflow(jobId));
      } catch {
        setWorkflow(null);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <main className="container">Loading…</main>;
  if (error)
    return (
      <main className="container">
        <Link href="/jobs">← Jobs</Link>
        <p className="error">{error}</p>
      </main>
    );
  if (!job) return null;

  const stages = workflow?.stages ?? [];
  const byStage = (stageId: string) => candidates.filter((c) => c.current_stage_id === stageId);
  const unassigned = candidates.filter((c) => !c.current_stage_id || !stages.some((s) => s.id === c.current_stage_id));

  return (
    <main className="container">
      <div className="header">
        <div>
          <Link href="/jobs">← Jobs</Link>
          <h1 style={{ marginTop: 8, marginBottom: 6 }}>{job.title}</h1>
          <span className={`badge ${job.status}`}>{job.status}</span>
          {workflow && (
            <span className="badge" style={{ marginLeft: 8 }}>
              workflow v{workflow.version} {workflow.approved ? "· approved" : "· draft"}
            </span>
          )}
        </div>
        <Link className="btn" href={`/jobs/${jobId}/candidates`}>Manage candidates</Link>
      </div>

      {/* Workflow */}
      <section>
        <h3>Hiring workflow</h3>
        {stages.length === 0 ? (
          <div className="card muted">
            No workflow yet. <Link href="/jobs/new">Create the job flow</Link> to draft and approve stages.
          </div>
        ) : (
          <div className="stage-flow">
            {stages.map((s, i) => (
              <div className="stage-flow-item" key={s.id}>
                <StageCard stage={s} />
                {i < stages.length - 1 && <div className="stage-arrow">→</div>}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Pipeline */}
      <section>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h3>Pipeline</h3>
          <Link href={`/jobs/${jobId}/candidates`} className="muted" style={{ fontSize: 13 }}>
            {candidates.length} candidate{candidates.length === 1 ? "" : "s"} →
          </Link>
        </div>
        {candidates.length === 0 ? (
          <div className="card muted">
            No candidates yet. <Link href={`/jobs/${jobId}/candidates`}>Import a candidate</Link> to start the pipeline.
          </div>
        ) : (
          <div className="board">
            {stages.map((s) => {
              const col = byStage(s.id);
              return (
                <div className="board-col" key={s.id}>
                  <div className="board-col-head">
                    <span>{s.name}</span>
                    <span className="count">{col.length}</span>
                  </div>
                  {col.map((c) => (
                    <Link className="pcard" key={c.id} href={`/job-candidates/${c.id}`}>
                      <div style={{ fontWeight: 600, fontSize: 14 }}>{c.candidate.full_name ?? "(unnamed)"}</div>
                      {c.pipeline_state && <span className="badge" style={{ fontSize: 11 }}>{c.pipeline_state}</span>}
                    </Link>
                  ))}
                  {col.length === 0 && <div className="muted" style={{ fontSize: 12, padding: "4px 2px" }}>—</div>}
                </div>
              );
            })}
            {unassigned.length > 0 && (
              <div className="board-col" key="unassigned">
                <div className="board-col-head"><span>Other</span><span className="count">{unassigned.length}</span></div>
                {unassigned.map((c) => (
                  <Link className="pcard" key={c.id} href={`/job-candidates/${c.id}`}>
                    <div style={{ fontWeight: 600, fontSize: 14 }}>{c.candidate.full_name ?? "(unnamed)"}</div>
                    {c.pipeline_state && <span className="badge" style={{ fontSize: 11 }}>{c.pipeline_state}</span>}
                  </Link>
                ))}
              </div>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
