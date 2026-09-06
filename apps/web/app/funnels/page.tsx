"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, type FunnelPreset, type FunnelSummary, type StageEdit } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import WorkflowEditor, { stagesToEdit } from "@/components/WorkflowEditor";

const SEED_STAGE: StageEdit = {
  name: "Initial screening",
  purpose: "Confirm interest and basic fit",
  execution_type: "ai",
  information_requirements: ["interest", "notice_period"],
  requires_human_approval: false,
  criteria: [],
};

export default function FunnelsPage() {
  const { me } = useAuth();
  const router = useRouter();
  const isAdmin = me?.role === "admin";
  const [funnels, setFunnels] = useState<FunnelSummary[] | null>(null);
  const [presets, setPresets] = useState<FunnelPreset[]>([]);
  const [showArchived, setShowArchived] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [usingKey, setUsingKey] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setFunnels(await api.listFunnels(showArchived)); }
    catch (e) { setError((e as Error).message); }
  }, [showArchived]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.listFunnelPresets().then(setPresets).catch(() => setPresets([])); }, []);

  async function usePreset(preset: FunnelPreset) {
    setUsingKey(preset.key); setError(null);
    try {
      const created = await api.createFunnel(preset.name, stagesToEdit(preset.stages));
      router.push(`/funnels/${created.id}`);
    } catch (e) { setError((e as Error).message); setUsingKey(null); }
  }

  return (
    <main className="container">
      <header className="page-head">
        <div>
          <p className="eyebrow">Reusable hiring funnels</p>
          <h1>Funnels</h1>
          <p className="muted">A funnel is a reusable set of stages and criteria. Apply one to any job — each job gets its own copy, so editing a funnel never disturbs jobs already using it.</p>
        </div>
        {isAdmin && !creating && <button onClick={() => { setName(""); setCreating(true); }}>New funnel</button>}
      </header>

      {error && <p className="error">{error}</p>}

      {creating && (
        <section className="card funnel-create">
          <label>Funnel name<input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Engineering — AI screen → assessment → HM review" /></label>
          <p className="muted" style={{ marginTop: 4 }}>Define the stages below, then save to create the funnel.</p>
          <WorkflowEditor
            initialStages={[SEED_STAGE]}
            saveLabel="Create funnel"
            onSave={async (stages) => {
              if (!name.trim()) { throw new Error("Give the funnel a name first."); }
              const created = await api.createFunnel(name.trim(), stages);
              router.push(`/funnels/${created.id}`);
              return stagesToEdit(created.stages);
            }}
          />
          <button className="secondary" style={{ marginTop: 8 }} onClick={() => setCreating(false)}>Cancel</button>
        </section>
      )}

      {presets.length > 0 && !creating && (
        <section style={{ marginBottom: 28 }}>
          <div className="workspace-section-heading"><div><p className="eyebrow">Start from a template</p><h2>Predefined funnels</h2><p className="muted">Proven starting points. Using one adds an editable copy to your library — tweak it or apply it to a job.</p></div></div>
          <div className="preset-grid">
            {presets.map((p) => (
              <article key={p.key} className="card preset-card">
                <strong>{p.name}</strong>
                <p className="muted">{p.description}</p>
                <div className="preset-stages">{p.stages.map((s, i) => <span key={i} className="preset-chip">{i + 1}. {s.name}</span>)}</div>
                {isAdmin && <button className="secondary" disabled={usingKey === p.key} onClick={() => usePreset(p)}>{usingKey === p.key ? "Adding…" : "Use this template"}</button>}
              </article>
            ))}
          </div>
        </section>
      )}

      <div className="workspace-section-heading" style={{ marginBottom: 8 }}><div><p className="eyebrow">Your library</p><h2>Your funnels</h2></div></div>
      <div className="row" style={{ justifyContent: "space-between", margin: "0 0 12px" }}>
        <span className="muted">{funnels ? `${funnels.length} funnel${funnels.length === 1 ? "" : "s"}` : ""}</span>
        <label className="row" style={{ gap: 6, margin: 0 }}><input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} /> Show archived</label>
      </div>

      {funnels === null ? (
        <p className="muted">Loading funnels…</p>
      ) : funnels.length === 0 ? (
        <div className="workspace-empty">No funnels yet. {isAdmin ? "Create one to reuse across jobs." : "An admin can create reusable funnels."}</div>
      ) : (
        <div className="funnel-list">
          {funnels.map((f) => (
            <Link key={f.id} href={`/funnels/${f.id}`} className="card cardlink funnel-row">
              <div>
                <strong>{f.name}</strong>
                {f.archived && <span className="badge archived" style={{ marginLeft: 8 }}>archived</span>}
                <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>{f.stage_count} stage{f.stage_count === 1 ? "" : "s"} · v{f.version}</div>
              </div>
              <span className="muted">→</span>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
