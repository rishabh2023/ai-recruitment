"use client";

import { useState } from "react";
import { type Criterion, type StageEdit } from "@/lib/api";

const EXEC = ["ai", "human", "system"] as const;

/** The fields both job-workflow stages and funnel stages share (ignores id/stage_order). */
type StageLike = {
  name: string;
  purpose: string | null;
  execution_type: string;
  information_requirements: string[];
  requires_human_approval: boolean;
  criteria: Criterion[];
};

/** Convert persisted stage detail (job workflow or funnel) into editable stages. */
export function stagesToEdit(stages: StageLike[]): StageEdit[] {
  return stages.map((s) => ({
    name: s.name,
    purpose: s.purpose,
    execution_type: s.execution_type,
    information_requirements: [...s.information_requirements],
    requires_human_approval: s.requires_human_approval,
    criteria: s.criteria.map((c) => ({ ...c })),
  }));
}

/**
 * Stage/criteria editor shared by job workflows and funnel templates. It owns the in-memory
 * stage list and delegates persistence to `onSave`, which returns the normalized stages to
 * reset the editor to (so the caller controls the API call and any surrounding state).
 */
export default function WorkflowEditor({
  initialStages,
  onSave,
  saveLabel = "Save changes",
}: {
  initialStages: StageEdit[];
  onSave: (stages: StageEdit[]) => Promise<StageEdit[]>;
  saveLabel?: string;
}) {
  const [stages, setStages] = useState<StageEdit[]>(initialStages);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  function update(i: number, patch: Partial<StageEdit>) {
    setStages((prev) => prev.map((s, j) => (j === i ? { ...s, ...patch } : s)));
    setSaved(false);
  }
  function move(i: number, dir: -1 | 1) {
    setStages((prev) => {
      const next = [...prev];
      const j = i + dir;
      if (j < 0 || j >= next.length) return prev;
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
    setSaved(false);
  }
  function removeStage(i: number) {
    setStages((prev) => prev.filter((_, j) => j !== i));
    setSaved(false);
  }
  function addStage() {
    setStages((prev) => [
      ...prev,
      { name: "New stage", execution_type: "ai", information_requirements: [], requires_human_approval: false, criteria: [] },
    ]);
    setSaved(false);
  }
  function updateCriterion(si: number, ci: number, patch: Partial<Criterion>) {
    setStages((prev) =>
      prev.map((s, j) =>
        j === si ? { ...s, criteria: s.criteria.map((c, k) => (k === ci ? { ...c, ...patch } : c)) } : s,
      ),
    );
    setSaved(false);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      // drop criteria rows with no name before persisting
      const clean = stages.map((s) => ({
        ...s,
        criteria: s.criteria.filter((c) => c.name.trim()),
      }));
      const normalized = await onSave(clean);
      setStages(normalized);
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="workflow-editor">
      {error && <p className="error">{error}</p>}
      {stages.map((s, i) => (
        <article className="workflow-stage" key={i}>
          <div className="stage-toolbar">
            <div className="stage-number">{String(i + 1).padStart(2, "0")}</div><div><p className="eyebrow">Workflow stage</p><h3>{s.name || "Untitled stage"}</h3></div>
            <div className="stage-actions">
              <button aria-label={`Move ${s.name || "stage"} up`} className="icon-button" onClick={() => move(i, -1)} disabled={i === 0}>↑</button>
              <button aria-label={`Move ${s.name || "stage"} down`} className="icon-button" onClick={() => move(i, 1)} disabled={i === stages.length - 1}>↓</button>
              <button className="text-danger" onClick={() => removeStage(i)}>Remove</button>
            </div>
          </div>
          <div className="stage-main-fields">
            <label>Stage name<input value={s.name} onChange={(e) => update(i, { name: e.target.value })} placeholder="Stage name" /></label>
            <label>Execution type<select value={s.execution_type} onChange={(e) => update(i, { execution_type: e.target.value })}>
              {EXEC.map((x) => <option key={x} value={x}>{x}</option>)}
            </select></label>
          </div>
          <label>Purpose<input value={s.purpose ?? ""} onChange={(e) => update(i, { purpose: e.target.value })} placeholder="What should this stage establish?" /></label>
          <label>Information to collect<span className="field-hint">Separate fields with commas</span><input value={s.information_requirements.join(", ")} onChange={(e) => update(i, { information_requirements: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} placeholder="e.g. interest, notice period, location" /></label>
          <label className="approval-toggle">
            <input type="checkbox" checked={s.requires_human_approval}
              onChange={(e) => update(i, { requires_human_approval: e.target.checked })} />
            <span><strong>Requires human approval</strong><small>Stop automatic progression until a recruiter reviews the result.</small></span>
          </label>
          <div className="criteria-section">
            <div className="criteria-heading"><div><h4>Success criteria</h4><p>Use weighted criteria to make evaluations consistent.</p></div><button className="secondary compact-button" onClick={() => update(i, { criteria: [...s.criteria, { name: "", kind: "numeric", weight: null }] })}>+ Add criterion</button></div>
            {s.criteria.map((c, ci) => (
              <div className="criterion-row" key={ci}>
                <input aria-label={`Criterion ${ci + 1} name`} value={c.name} onChange={(e) => updateCriterion(i, ci, { name: e.target.value })} placeholder="Criterion name" />
                <label className="weight-field"><span>Weight</span><input type="number" min="0" max="100" value={c.weight ?? ""} onChange={(e) => updateCriterion(i, ci, { weight: e.target.value === "" ? null : Number(e.target.value) })} placeholder="%" /></label>
              </div>
            ))}
          </div>
        </article>
      ))}
      <div className="workflow-editor-actions">
        <button className="secondary" onClick={addStage}>+ Add stage</button><div className="row"><span className="muted">{stages.length} stage{stages.length === 1 ? "" : "s"}</span><button onClick={save} disabled={busy || stages.length === 0}>{busy ? "Saving…" : saveLabel}</button></div>
        {saved && <span className="ok" style={{ fontSize: 13 }}>Saved ✓</span>}
      </div>
    </div>
  );
}
