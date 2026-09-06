"use client";

import { useState } from "react";
import { api, type Criterion, type JobWorkflow, type StageEdit } from "@/lib/api";

const EXEC = ["ai", "human", "system"] as const;

function toEdit(wf: JobWorkflow): StageEdit[] {
  return wf.stages.map((s) => ({
    name: s.name,
    purpose: s.purpose,
    execution_type: s.execution_type,
    information_requirements: [...s.information_requirements],
    requires_human_approval: s.requires_human_approval,
    criteria: s.criteria.map((c) => ({ ...c })),
  }));
}

export default function WorkflowEditor({
  jobId,
  versionId,
  initial,
  onSaved,
}: {
  jobId: string;
  versionId: string;
  initial: JobWorkflow;
  onSaved: (wf: JobWorkflow) => void;
}) {
  const [stages, setStages] = useState<StageEdit[]>(toEdit(initial));
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
      // normalize empty weights to null
      const clean = stages.map((s) => ({
        ...s,
        criteria: s.criteria.filter((c) => c.name.trim()),
      }));
      const wf = await api.editWorkflowStages(jobId, versionId, clean);
      setStages(toEdit(wf));
      setSaved(true);
      onSaved(wf);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {error && <p className="error">{error}</p>}
      {stages.map((s, i) => (
        <div className="card" key={i} style={{ display: "grid", gap: 8 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <b>Stage {i + 1}</b>
            <div className="row" style={{ gap: 6 }}>
              <button className="linklike" onClick={() => move(i, -1)} disabled={i === 0}>↑</button>
              <button className="linklike" onClick={() => move(i, 1)} disabled={i === stages.length - 1}>↓</button>
              <button className="linklike" onClick={() => removeStage(i)}>remove</button>
            </div>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <input style={{ flex: 2 }} value={s.name} onChange={(e) => update(i, { name: e.target.value })} placeholder="Stage name" />
            <select style={{ flex: 1 }} value={s.execution_type} onChange={(e) => update(i, { execution_type: e.target.value })}>
              {EXEC.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </div>
          <input value={s.purpose ?? ""} onChange={(e) => update(i, { purpose: e.target.value })} placeholder="Purpose (optional)" />
          <input
            value={s.information_requirements.join(", ")}
            onChange={(e) => update(i, { information_requirements: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })}
            placeholder="Collects (comma-separated, e.g. interest, notice_period)"
          />
          <label className="row" style={{ gap: 6, margin: 0 }}>
            <input type="checkbox" style={{ width: "auto" }} checked={s.requires_human_approval}
              onChange={(e) => update(i, { requires_human_approval: e.target.checked })} />
            Requires human approval
          </label>
          <div>
            <div className="muted" style={{ fontSize: 12 }}>Criteria</div>
            {s.criteria.map((c, ci) => (
              <div className="row" key={ci} style={{ gap: 6, marginTop: 4 }}>
                <input style={{ flex: 2 }} value={c.name} onChange={(e) => updateCriterion(i, ci, { name: e.target.value })} placeholder="Criterion" />
                <input style={{ flex: 1 }} type="number" value={c.weight ?? ""} onChange={(e) => updateCriterion(i, ci, { weight: e.target.value === "" ? null : Number(e.target.value) })} placeholder="weight %" />
              </div>
            ))}
            <button className="linklike" onClick={() => update(i, { criteria: [...s.criteria, { name: "", kind: "numeric", weight: null }] })}>+ add criterion</button>
          </div>
        </div>
      ))}
      <div className="row" style={{ gap: 8, marginTop: 8 }}>
        <button className="secondary" onClick={addStage}>+ Add stage</button>
        <button onClick={save} disabled={busy || stages.length === 0}>{busy ? "Saving…" : "Save changes"}</button>
        {saved && <span className="ok" style={{ fontSize: 13 }}>Saved ✓</span>}
      </div>
    </div>
  );
}
