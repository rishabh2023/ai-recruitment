"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { api, stageAgentStatus, type BulkLaunchResult, type CandidateImport, type CsvImportResult, type Funnel, type Job, type JobCandidateListItem, type JobVersion, type JobWorkflow, type PipelinePage, type StageAgent, type StageDetail } from "@/lib/api";
import CallingPolicyCard from "@/components/CallingPolicyCard";
import ConfirmDialog from "@/components/ConfirmDialog";
import Modal from "@/components/Modal";
import WorkflowEditor, { stagesToEdit } from "@/components/WorkflowEditor";

const EXEC: Record<string, string> = { ai: "AI call", human: "Human review", system: "System" };
type Tab = "overview" | "workflow" | "pipeline" | "policy";

/** Human label for an information-requirement key (e.g. "current_ctc" → "Current CTC"). */
function fieldLabel(key: string): string {
  const map: Record<string, string> = {
    interest: "Interest in the role", current_ctc: "Current CTC", expected_ctc: "Expected CTC",
    notice_period: "Notice period", location: "Location", years_experience: "Years of experience",
    salary_expectation: "Salary expectation", availability: "Availability", skills: "Relevant skills",
  };
  return map[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

function StageCard({ stage }: { stage: StageDetail }) {
  const isAi = stage.execution_type === "ai";
  return <article className="workspace-stage-card"><div className="workspace-stage-topline"><span className="stage-number">{String(stage.stage_order).padStart(2, "0")}</span><span className={`badge exec-${stage.execution_type}`}>{EXEC[stage.execution_type] ?? stage.execution_type}</span></div><h3>{stage.name}</h3><p>{stage.purpose || "No purpose has been described for this stage."}</p>
    {isAi && <div className="stage-criteria">
      <p className="stage-criteria-label">What the AI asks</p>
      {stage.information_requirements.length > 0
        ? <div className="chip-row">{stage.information_requirements.map((k, i) => <span className="chip" key={i}>{fieldLabel(k)}</span>)}</div>
        : <p className="muted stage-criteria-empty">Interest only — edit in the Voice agents panel.</p>}
    </div>}
    <div className="stage-criteria">
      <p className="stage-criteria-label">Success criteria</p>
      {stage.criteria.length > 0
        ? <ul className="criteria-list">{stage.criteria.map((c, i) => <li key={i}><span>{c.name}</span>{c.weight != null && <span className="criteria-weight">{c.weight}</span>}</li>)}</ul>
        : <p className="muted stage-criteria-empty">None defined for this stage.</p>}
    </div>
    <div className="workspace-stage-foot"><span>{stage.criteria.length} criteria</span>{stage.requires_human_approval && <span>Human checkpoint</span>}</div></article>;
}

/**
 * F-009: recruiter-safe readiness of each AI stage's voice agent. Shows whether a stage has its
 * own on-intent agent, is falling back to the default, or has none yet — never the underlying
 * Hunar agent id (telephony internals stay server-side). Recruiters can re-provision to bind
 * correct per-stage agents when calling is configured.
 */
function StageVoiceAgents({ jobId, versionId }: { jobId: string; versionId: string }) {
  const [rows, setRows] = useState<StageAgent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => { api.listStageAgents(jobId, versionId).then(setRows).catch((e) => setError((e as Error).message)); }, [jobId, versionId]);
  const provision = async () => {
    setBusy(true); setError(null); setNote(null);
    try { setRows(await api.provisionStageAgents(jobId, versionId)); setNote("Voice agents provisioned for this funnel."); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const onSaved = (updated: StageAgent) => setRows((prev) => prev ? prev.map((r) => r.stage_id === updated.stage_id ? updated : r) : prev);
  if (error && !rows) return null; // agents are advisory; don't block the funnel view on a fetch error
  if (!rows) return null;
  if (rows.length === 0) return null; // no AI stages
  return <section className="workspace-section"><div className="workspace-section-heading"><div><p className="eyebrow">AI calling</p><h2>Voice agents</h2><p>Each AI stage is handled by a voice agent matched to this role and the stage&apos;s purpose. Review what each one does — and edit it if needed.</p></div><button className="secondary" disabled={busy} onClick={provision}>{busy ? "Provisioning…" : "Provision agents"}</button></div>
    {error && <p className="error">{error}</p>}
    {note && <p className="ok" style={{ fontSize: 13 }}>{note}</p>}
    <div className="voice-agent-list">{rows.map((a) => <VoiceAgentCard key={a.stage_id} jobId={jobId} agent={a} onSaved={onSaved} />)}</div>
    <p className="muted" style={{ fontSize: 12 }}>&ldquo;Using default&rdquo; means calls fall back to a shared agent until per-stage provisioning runs. Provisioning needs voice calling enabled in Settings.</p>
  </section>;
}

const PURPOSE_LABEL: Record<string, string> = { screening: "Screening", technical: "Technical interview", sales: "Sales", manager: "Hiring manager", compensation: "Compensation" };

/** One AI stage's voice-agent card: shows what it does (objective + what it asks) and, when the
 *  stage has its own agent, lets the recruiter edit the objective and the fields it collects. */
function VoiceAgentCard({ jobId, agent, onSaved }: { jobId: string; agent: StageAgent; onSaved: (a: StageAgent) => void }) {
  const s = stageAgentStatus(agent);
  const [editing, setEditing] = useState(false);
  const [objective, setObjective] = useState(agent.objective);
  const [collects, setCollects] = useState(agent.collect_keys.join(", "));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const start = () => { setObjective(agent.objective); setCollects(agent.collect_keys.join(", ")); setError(null); setEditing(true); };
  const save = async () => {
    setBusy(true); setError(null);
    try {
      const keys = collects.split(",").map((x) => x.trim()).filter(Boolean);
      const updated = await api.editStageAgentSpec(jobId, agent.stage_id, objective.trim(), keys);
      onSaved(updated); setEditing(false);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return <article className="voice-agent-card">
    <div className="voice-agent-head"><div><h4>{agent.stage_name}</h4><span className="muted" style={{ fontSize: 12 }}>{PURPOSE_LABEL[agent.purpose_family] ?? agent.purpose_family}</span></div><span className={`badge ${s.ready ? (s.warn ? "draft" : "active") : "archived"}`}>{s.label}</span></div>
    {!editing ? <>
      <p className="voice-agent-objective">{agent.objective}</p>
      <div className="voice-agent-collects"><span className="muted" style={{ fontSize: 12 }}>Asks about</span><div className="chip-row">{agent.collects.length ? agent.collects.map((c, i) => <span className="chip" key={i}>{c}</span>) : <span className="muted">interest only</span>}</div></div>
      {agent.editable && <button className="linklike" onClick={start}>Edit what this agent does</button>}
    </> : <div className="voice-agent-edit">
      {error && <p className="error">{error}</p>}
      <label>Objective<textarea rows={3} value={objective} onChange={(e) => setObjective(e.target.value)} placeholder="What should this agent accomplish on the call?" /></label>
      <label>Fields to collect<span className="field-hint">Separate with commas</span><input value={collects} onChange={(e) => setCollects(e.target.value)} placeholder="e.g. interest, expected_ctc, notice_period" /></label>
      <div className="row"><button disabled={busy || !objective.trim()} onClick={save}>{busy ? "Saving…" : "Save agent"}</button><button className="secondary" disabled={busy} onClick={() => setEditing(false)}>Cancel</button></div>
    </div>}
  </article>;
}

function JobDescriptionCard({ jobId, version, onChanged }: { jobId: string; version: JobVersion | null; onChanged: () => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const startEdit = () => { setDraft(version?.jd_text ?? ""); setError(null); setNote(null); setEditing(true); };
  async function act(fn: () => Promise<void>) { setBusy(true); setError(null); setNote(null); try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }
  const save = () => act(async () => {
    if (!draft.trim()) { setError("The job description cannot be empty."); return; }
    await api.addVersion(jobId, draft.trim());
    await onChanged();
    setEditing(false);
  });
  const confirm = () => act(async () => { if (version) { await api.confirmVersion(jobId, version.id); await onChanged(); } });
  const tidy = () => act(async () => {
    if (!draft.trim()) return;
    const { text } = await api.tidyJobDescription(jobId, draft);
    if (text === draft.trim()) { setNote("Formatting already looks clean — no changes needed."); return; }
    setDraft(text);
    setNote("Formatting cleaned up. Review it, then save a new version.");
  });
  return <section id="jd-card" className="workspace-section jd-card">
    <div className="workspace-section-heading">
      <div><p className="eyebrow">Role definition</p><h2>Job description</h2>
        <p>{editing ? "Saving creates a new version. Extraction re-runs, and the new version stays a draft until you confirm it." : version ? "The description candidates are assessed against. Editing creates a new version." : "No job description has been added for this role yet."}</p>
      </div>
      {!editing && <div className="jd-card-actions">{version && <span className={`badge ${version.confirmed ? "active" : "draft"}`}>v{version.version} · {version.confirmed ? "confirmed" : "draft"}</span>}<button className="secondary" disabled={busy} onClick={startEdit}>{version ? "Edit" : "Add description"}</button></div>}
    </div>
    {error && <p className="error">{error}</p>}
    {note && <p className="jd-note">{note}</p>}
    {editing
      ? <><textarea className="jd-textarea" value={draft} disabled={busy} onChange={(e) => { setDraft(e.target.value); if (note) setNote(null); }} rows={14} placeholder="Paste the full job description…" /><div className="jd-edit-bar"><button disabled={busy} onClick={save}>{busy ? "Saving…" : "Save new version"}</button><button className="secondary" disabled={busy || !draft.trim()} onClick={tidy} title="Reflow messy formatting (e.g. a PDF copy-paste broken across lines) into clean text">{busy ? "Working…" : "Clean up formatting"}</button><button className="secondary" disabled={busy} onClick={() => setEditing(false)}>Cancel</button></div></>
      : version
        ? <><pre className="jd-text">{version.jd_text}</pre>{!version.confirmed && <div className="jd-confirm-bar"><span>This version is a draft. Confirm it so it becomes authoritative for this role.</span><button disabled={busy} onClick={confirm}>{busy ? "Confirming…" : "Confirm this version"}</button></div>}</>
        : <div className="workspace-empty">Add a job description to define what candidates are assessed against.</div>}
  </section>;
}

function FunnelSection({ funnel }: { funnel: Funnel | null }) {
  if (!funnel) return null;
  const { total, in_progress, rejected, completed, completion_pct, stages } = funnel;
  const tiles: Array<[string, number | string]> = [["Total candidates", total], ["In progress", in_progress], ["Rejected", rejected], ["Completed", completed], ["Completion", `${completion_pct}%`]];
  return <section className="workspace-section funnel-section">
    <div className="workspace-section-heading"><div><p className="eyebrow">Pipeline health</p><h2>Hiring funnel</h2><p>How many candidates reached each stage (cumulative), the drop-off between stages, and overall completion.</p></div></div>
    <div className="funnel-tiles">{tiles.map(([label, value]) => <div key={label} className="funnel-tile"><span>{label}</span><strong>{value}</strong></div>)}</div>
    {total === 0
      ? <div className="workspace-empty">No candidates yet — the funnel fills in as candidates enter the pipeline.</div>
      : stages.length === 0
        ? <div className="workspace-empty">No workflow stages to chart yet.</div>
        : <ol className="funnel-bars">{stages.map((s, i) => {
            const prev = i === 0 ? null : stages[i - 1].reached;
            const step = prev && prev > 0 ? Math.round((s.reached / prev) * 100) : null;
            return <li key={s.stage_id} className="funnel-bar-row">
              <div className="funnel-bar-head"><span className="funnel-bar-name"><em>{String(s.stage_order).padStart(2, "0")}</em> {s.name}</span><span className="funnel-bar-count">{s.reached}<span className="muted"> reached · {s.reached_pct}%</span></span></div>
              <div className="funnel-bar-track"><div className="funnel-bar-fill" style={{ width: `${s.reached_pct}%` }} /></div>
              <div className="funnel-bar-foot"><span className="muted">{s.current} here now</span>{step !== null && <span className={`funnel-step${step < 100 ? " drop" : ""}`}>{step}% from previous</span>}</div>
            </li>;
          })}</ol>}
  </section>;
}

type FactRow = { key: string; value: string };

// National number + dial code → E.164 (or null when there's no number). A number already
// carrying a '+' is respected as-is.
function toE164(dial: string, phone: string): string | null {
  const raw = phone.trim();
  if (!raw) return null;
  if (raw.startsWith("+")) return "+" + raw.replace(/\D/g, "");
  const national = raw.replace(/\D/g, "");
  return national ? `${dial}${national}` : null;
}

// Split a stored phone back into a dial code + national number for editing.
function splitPhone(full: string | null, codes: string[]): { dial: string; national: string } {
  const raw = (full || "").trim();
  if (raw.startsWith("+")) {
    const digits = "+" + raw.replace(/\D/g, "");
    const match = codes.filter((c) => digits.startsWith(c)).sort((a, b) => b.length - a.length)[0];
    if (match) return { dial: match, national: digits.slice(match.length) };
    return { dial: "+91", national: digits.replace(/^\+/, "") };
  }
  return { dial: "+91", national: raw.replace(/\D/g, "") };
}

// Common dialing codes for the required country-code selector (India first — primary market).
const DIAL_CODES: Array<{ code: string; label: string }> = [
  { code: "+91", label: "🇮🇳 +91" },
  { code: "+1", label: "🇺🇸 +1" },
  { code: "+44", label: "🇬🇧 +44" },
  { code: "+971", label: "🇦🇪 +971" },
  { code: "+65", label: "🇸🇬 +65" },
  { code: "+61", label: "🇦🇺 +61" },
  { code: "+49", label: "🇩🇪 +49" },
  { code: "+33", label: "🇫🇷 +33" },
  { code: "+880", label: "🇧🇩 +880" },
  { code: "+92", label: "🇵🇰 +92" },
];

function AddCandidateModal({ jobId, open, onClose, onAdded }: { jobId: string; open: boolean; onClose: () => void; onAdded: () => Promise<void> }) {
  const [mode, setMode] = useState<"manual" | "csv">("manual");
  const [fullName, setFullName] = useState("");
  const [dialCode, setDialCode] = useState("+91");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [location, setLocation] = useState("");
  const [facts, setFacts] = useState<FactRow[]>([{ key: "", value: "" }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [csvResult, setCsvResult] = useState<CsvImportResult | null>(null);

  function reset() { setFullName(""); setDialCode("+91"); setPhone(""); setEmail(""); setLocation(""); setFacts([{ key: "", value: "" }]); setError(null); setCsvResult(null); setMode("manual"); }
  function close() { if (!busy) { reset(); onClose(); } }

  async function uploadCsv(file: File) {
    setBusy(true); setError(null); setCsvResult(null);
    try {
      const result = await api.importCandidatesCsv(jobId, file);
      setCsvResult(result);
      if (result.added > 0) await onAdded();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function submit() {
    if (!fullName.trim()) { setError("Full name is required."); return; }
    const known_facts: Record<string, string> = {};
    for (const f of facts) if (f.key.trim() && f.value.trim()) known_facts[f.key.trim()] = f.value.trim();
    const payload: CandidateImport = { full_name: fullName.trim(), phone: toE164(dialCode, phone) ?? undefined, email: email.trim() || undefined, location: location.trim() || undefined, source: "import", known_facts };
    setBusy(true); setError(null);
    try { await api.importCandidate(jobId, payload); reset(); await onAdded(); onClose(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <Modal open={open} onClose={close} title="Add candidates" size="md">
      <div className="tabs" role="tablist" style={{ maxWidth: 320 }}>
        <button role="tab" aria-selected={mode === "manual"} className={`tab ${mode === "manual" ? "active" : ""}`} onClick={() => { setMode("manual"); setError(null); }}>Enter details</button>
        <button role="tab" aria-selected={mode === "csv"} className={`tab ${mode === "csv" ? "active" : ""}`} onClick={() => { setMode("csv"); setError(null); }}>Upload CSV</button>
      </div>
      {error && <p className="error">{error}</p>}

      {mode === "csv" ? (
        csvResult ? (
          <div>
            <p className="csv-result-summary"><strong>{csvResult.added}</strong> added{csvResult.skipped > 0 && <> · <strong>{csvResult.skipped}</strong> skipped</>}.</p>
            {csvResult.errors.length > 0 && (
              <ul className="csv-errors">{csvResult.errors.map((er, i) => <li key={i}>Row {er.row}: {er.reason}</li>)}</ul>
            )}
            <div className="modal-actions">
              <button className="secondary" onClick={() => setCsvResult(null)}>Upload another</button>
              <button onClick={close}>Done</button>
            </div>
          </div>
        ) : (
          <div>
            <p className="muted modal-sub">Upload a CSV with one candidate per row. A <strong>name</strong> and <strong>mobile</strong> column are required. Numbers need a country code — either include it in the number (e.g. <code>+9198…</code>) or add a <strong>country_code</strong> column. <strong>email</strong> and <strong>location</strong> are optional.</p>
            <label className="filedrop" htmlFor="csv-file" style={{ cursor: busy ? "default" : "pointer" }}>
              <input id="csv-file" type="file" accept=".csv,text/csv" style={{ display: "none" }} disabled={busy} onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadCsv(f); e.target.value = ""; }} />
              <span className="fileicon">⬆</span>
              <span>{busy ? "Importing…" : "Click to choose a CSV, or drop it here"}</span>
            </label>
            <p className="muted csv-hint">Header row example: <code>name,mobile,country_code,email,location</code></p>
            <div className="modal-actions"><button className="secondary" disabled={busy} onClick={close}>Cancel</button></div>
          </div>
        )
      ) : (
      <>
      <p className="muted modal-sub">Enter the details you already have. Known facts are carried into the AI stage as starting context.</p>
      <label>Full name *<input value={fullName} disabled={busy} onChange={(e) => setFullName(e.target.value)} placeholder="Asha Rao" autoFocus /></label>
      <div className="row" style={{ gap: 8 }}>
        <label style={{ flex: 1 }}>Phone
          <div className="phone-row">
            <select className="dial-code" value={dialCode} disabled={busy} onChange={(e) => setDialCode(e.target.value)} aria-label="Country code">
              {DIAL_CODES.map((d) => <option key={d.code} value={d.code}>{d.label}</option>)}
            </select>
            <input value={phone} disabled={busy} onChange={(e) => setPhone(e.target.value)} placeholder="98765 43210" inputMode="tel" />
          </div>
        </label>
        <label style={{ flex: 1 }}>Email<input value={email} disabled={busy} type="email" onChange={(e) => setEmail(e.target.value)} placeholder="asha@example.com" /></label>
      </div>
      <p className="muted" style={{ fontSize: 12, margin: "6px 0 0" }}>The country code is required to place calls — pick it, then enter the number without it.</p>
      <label>Location<input value={location} disabled={busy} onChange={(e) => setLocation(e.target.value)} placeholder="Bengaluru" /></label>
      <div style={{ marginTop: 12 }}>
        <div className="muted" style={{ fontSize: 13, marginBottom: 6 }}>Known facts (optional)</div>
        {facts.map((f, i) => (
          <div className="row" key={i} style={{ gap: 8, marginBottom: 6 }}>
            <input aria-label="fact key" placeholder="expected_ctc" value={f.key} disabled={busy} onChange={(e) => setFacts((rows) => rows.map((r, j) => (j === i ? { ...r, key: e.target.value } : r)))} />
            <input aria-label="fact value" placeholder="24 LPA" value={f.value} disabled={busy} onChange={(e) => setFacts((rows) => rows.map((r, j) => (j === i ? { ...r, value: e.target.value } : r)))} />
          </div>
        ))}
        <button className="linklike" disabled={busy} onClick={() => setFacts((r) => [...r, { key: "", value: "" }])}>+ add fact</button>
      </div>
      <div className="modal-actions">
        <button className="secondary" disabled={busy} onClick={close}>Cancel</button>
        <button disabled={busy || !fullName.trim()} onClick={submit}>{busy ? "Adding…" : "Add candidate"}</button>
      </div>
      </>
      )}
    </Modal>
  );
}

function EditCandidateModal({ jc, open, onClose, onSaved }: { jc: JobCandidateListItem | null; open: boolean; onClose: () => void; onSaved: () => Promise<void> }) {
  const [fullName, setFullName] = useState("");
  const [dialCode, setDialCode] = useState("+91");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const codes = DIAL_CODES.map((d) => d.code);

  // Reload fields whenever the modal opens for a (different) candidate.
  useEffect(() => {
    if (!jc) return;
    const s = splitPhone(jc.candidate.phone, codes);
    setFullName(jc.candidate.full_name ?? ""); setDialCode(s.dial); setPhone(s.national);
    setEmail(jc.candidate.email ?? ""); setLocation(jc.candidate.location ?? ""); setError(null);
  }, [jc]); // eslint-disable-line react-hooks/exhaustive-deps

  async function save() {
    if (!jc) return;
    if (!fullName.trim()) { setError("Full name is required."); return; }
    setBusy(true); setError(null);
    try {
      await api.updateCandidate(jc.id, { full_name: fullName.trim(), phone: toE164(dialCode, phone), email: email.trim() || null, location: location.trim() || null });
      await onSaved(); onClose();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <Modal open={open} onClose={() => { if (!busy) onClose(); }} title="Edit candidate" size="md">
      <p className="muted modal-sub">Update the profile. A country code on the phone is required to place calls.</p>
      {error && <p className="error">{error}</p>}
      <label>Full name *<input value={fullName} disabled={busy} onChange={(e) => setFullName(e.target.value)} autoFocus /></label>
      <div className="row" style={{ gap: 8 }}>
        <label style={{ flex: 1 }}>Phone
          <div className="phone-row">
            <select className="dial-code" value={dialCode} disabled={busy} onChange={(e) => setDialCode(e.target.value)} aria-label="Country code">
              {DIAL_CODES.map((d) => <option key={d.code} value={d.code}>{d.label}</option>)}
            </select>
            <input value={phone} disabled={busy} onChange={(e) => setPhone(e.target.value)} placeholder="98765 43210" inputMode="tel" />
          </div>
        </label>
        <label style={{ flex: 1 }}>Email<input value={email} disabled={busy} type="email" onChange={(e) => setEmail(e.target.value)} /></label>
      </div>
      <label>Location<input value={location} disabled={busy} onChange={(e) => setLocation(e.target.value)} /></label>
      <div className="modal-actions">
        <button className="secondary" disabled={busy} onClick={() => { if (!busy) onClose(); }}>Cancel</button>
        <button disabled={busy || !fullName.trim()} onClick={save}>{busy ? "Saving…" : "Save changes"}</button>
      </div>
    </Modal>
  );
}

const PAGE_SIZE = 25;

function StateBadge({ state }: { state: string | null }) {
  if (!state) return <span className="muted" style={{ fontSize: 12 }}>—</span>;
  return <span className={`badge state-${state.toLowerCase()}`}>{state.toLowerCase().replace(/_/g, " ")}</span>;
}

function PipelineTab({ jobId, funnel, stages, onChanged, addSignal }: { jobId: string; funnel: Funnel | null; stages: StageDetail[]; onChanged: () => Promise<void>; addSignal: number }) {
  const [showAdd, setShowAdd] = useState(false);
  const [editRow, setEditRow] = useState<JobCandidateListItem | null>(null);
  // Opened from elsewhere (e.g. the Overview "Add candidates" CTA), which bumps addSignal.
  useEffect(() => { if (addSignal > 0) setShowAdd(true); }, [addSignal]);
  const [stage, setStage] = useState<string>("all");
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<PipelinePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  // "Execute" — launch this AI stage for every eligible candidate at once.
  const [confirmExec, setConfirmExec] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [execResult, setExecResult] = useState<BulkLaunchResult | null>(null);
  const [execError, setExecError] = useState<string | null>(null);
  const sourceHref = `/sourcing?job=${jobId}`;
  const total = funnel?.total ?? 0;
  // The Execute action is stage-scoped: only when a single AI stage is selected.
  const selectedStage = stage !== "all" ? stages.find((s) => s.id === stage) ?? null : null;
  const canExecuteStage = selectedStage?.execution_type === "ai";

  // Debounce the search box; committing a new term resets to the first page.
  useEffect(() => { const t = setTimeout(() => { setQ(qInput.trim()); setPage(1); }, 300); return () => clearTimeout(t); }, [qInput]);

  const fetchPage = useCallback(async () => {
    setLoading(true);
    try { setData(await api.pipelinePage(jobId, { stage: stage === "all" ? undefined : stage, q: q || undefined, page, page_size: PAGE_SIZE })); setErr(null); }
    catch (e) { setErr((e as Error).message); }
    finally { setLoading(false); }
  }, [jobId, stage, q, page]);
  useEffect(() => { fetchPage(); }, [fetchPage]);

  async function refresh() { await Promise.all([onChanged(), fetchPage()]); }

  async function executeStage() {
    if (!selectedStage) return;
    setExecuting(true);
    setExecError(null);
    try {
      const res = await api.launchStageAll(jobId, selectedStage.id);
      setExecResult(res);
      setConfirmExec(false);
      await refresh();
    } catch (e) {
      setExecError((e as Error).message);
    } finally {
      setExecuting(false);
    }
  }

  // Filter chips from the funnel: All + each stage (with its live count) + New (no stage yet).
  const stageCount = (id: string) => funnel?.stages.find((s) => s.stage_id === id)?.current ?? 0;
  const chips: Array<{ key: string; label: string; count: number | null }> = [
    { key: "all", label: "All", count: total },
    ...stages.map((s) => ({ key: s.id, label: s.name, count: stageCount(s.id) })),
  ];

  const rows = data?.items ?? [];
  const pageTotal = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(pageTotal / PAGE_SIZE));
  const from = pageTotal === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, pageTotal);

  return (
    <section className="workspace-section">
      <div className="workspace-section-heading">
        <div><p className="eyebrow">Candidate operations</p><h2>Pipeline</h2><p>Candidates enter the funnel two ways — you add them, or you source them. Their stage reflects persisted funnel state.</p></div>
        {total > 0 && <div className="pipeline-actions"><button className="secondary" onClick={() => setShowAdd(true)}>+ Add candidate</button><Link className="btn" href={sourceHref}>Source candidates</Link></div>}
      </div>

      {total === 0 && !loading ? (
        <div className="pipeline-paths">
          <div className="path-card">
            <span className="path-num">1</span>
            <h3>Add a candidate yourself</h3>
            <p>You already have someone — a resume, a referral, an inbound application. Enter their details and they join the pipeline.</p>
            <button onClick={() => setShowAdd(true)}>Add candidate</button>
          </div>
          <div className="path-card">
            <span className="path-num">2</span>
            <h3>Source from the market</h3>
            <p>Search by title, skills and location, then add the profiles you like. Sourced candidates land in this same pipeline.</p>
            <Link className="btn secondary" href={sourceHref}>Source candidates</Link>
          </div>
        </div>
      ) : (
        <>
          <div className="pipeline-toolbar">
            <div className="stage-chips" role="tablist" aria-label="Filter by stage">
              {chips.map((c) => (
                <button key={c.key} role="tab" aria-selected={stage === c.key} className={`stage-chip ${stage === c.key ? "active" : ""}`} onClick={() => { setStage(c.key); setPage(1); }}>
                  {c.label}{c.count !== null && <span className="chip-count">{c.count}</span>}
                </button>
              ))}
            </div>
            <input className="pipeline-search" type="search" value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder="Search name, phone, email…" aria-label="Search candidates" />
            {canExecuteStage && (
              <button
                className="btn pipeline-execute"
                onClick={() => { setExecResult(null); setExecError(null); setConfirmExec(true); }}
                title={`Launch “${selectedStage!.name}” for all eligible candidates`}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
                Execute
              </button>
            )}
          </div>

          {execResult && (
            <p className="sourcing-flash" role="status">
              Launched {execResult.launched} · skipped {execResult.skipped} already handled
              {execResult.failed ? ` · ${execResult.failed} failed` : ""} in “{selectedStage?.name ?? "this stage"}”.
              <button className="linklike" style={{ marginLeft: 8 }} onClick={() => setExecResult(null)}>Dismiss</button>
            </p>
          )}
          {err && <p className="error">{err}</p>}

          <div className="pipeline-table-wrap">
            <table className="pipeline-table">
              <thead><tr><th>Candidate</th><th>Contact</th><th>Location</th><th>Stage</th><th>Status</th><th aria-label="Actions"></th></tr></thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id} className="pipeline-row" onClick={() => { window.location.href = `/job-candidates/${c.id}`; }} tabIndex={0}
                      onKeyDown={(e) => { if (e.key === "Enter") window.location.href = `/job-candidates/${c.id}`; }}>
                    <td><Link href={`/job-candidates/${c.id}`} onClick={(e) => e.stopPropagation()}>{c.candidate.full_name ?? "(unnamed)"}</Link></td>
                    <td className="muted">{c.candidate.phone ?? c.candidate.email ?? "—"}</td>
                    <td className="muted">{c.candidate.location ?? "—"}</td>
                    <td>{c.current_stage_name ?? <span className="muted">New</span>}</td>
                    <td><StateBadge state={c.pipeline_state} /></td>
                    <td className="pipeline-row-actions"><button className="linklike" onClick={(e) => { e.stopPropagation(); setEditRow(c); }}>Edit</button></td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={6} className="pipeline-empty-cell">{loading ? "Loading…" : q || stage !== "all" ? "No candidates match this filter." : "No candidates yet."}</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="pipeline-footer">
            <span className="muted">{pageTotal === 0 ? "No results" : `${from}–${to} of ${pageTotal}`}</span>
            <div className="pipeline-pager">
              <button className="secondary" disabled={page <= 1 || loading} onClick={() => setPage((p) => Math.max(1, p - 1))}>← Prev</button>
              <span className="muted">Page {page} of {pageCount}</span>
              <button className="secondary" disabled={page >= pageCount || loading} onClick={() => setPage((p) => Math.min(pageCount, p + 1))}>Next →</button>
            </div>
          </div>
        </>
      )}
      {confirmExec && selectedStage && (
        <div className="hunar-modal-backdrop" role="dialog" aria-modal="true" aria-label={`Launch ${selectedStage.name} for all candidates`}>
          <div className="hunar-modal">
            <h3>Launch “{selectedStage.name}” for all candidates?</h3>
            <p className="muted">
              This places a real AI screening call to every candidate in this stage who hasn’t been
              handled yet. Candidates already called, awaiting your review, completed, or rejected
              are skipped automatically — nobody is re-dialed.
            </p>
            {execError && <p className="error">{execError}</p>}
            <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
              <button className="secondary" onClick={() => setConfirmExec(false)} disabled={executing}>Cancel</button>
              <button onClick={executeStage} disabled={executing}>{executing ? "Launching…" : "Execute calls"}</button>
            </div>
          </div>
        </div>
      )}
      <AddCandidateModal jobId={jobId} open={showAdd} onClose={() => setShowAdd(false)} onAdded={refresh} />
      <EditCandidateModal jc={editRow} open={editRow !== null} onClose={() => setEditRow(null)} onSaved={refresh} />
    </section>
  );
}

export default function JobDetailPage() {
  const { id: jobId } = useParams<{ id: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [workflow, setWorkflow] = useState<JobWorkflow | null>(null);
  const [jdVersion, setJdVersion] = useState<JobVersion | null>(null);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const searchParams = useSearchParams();
  const urlTab = searchParams.get("tab");
  const [tab, setTab] = useState<Tab>(urlTab === "workflow" || urlTab === "pipeline" || urlTab === "policy" ? urlTab : "overview");
  const [addSignal, setAddSignal] = useState(0);
  const openAddCandidate = () => { setTab("pipeline"); setAddSignal((s) => s + 1); };
  const [editing, setEditing] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => { try { const [j, jd, fn] = await Promise.all([api.getJob(jobId), api.getLatestVersion(jobId).catch(() => null), api.getJobFunnel(jobId).catch(() => null)]); setJob(j); setJdVersion(jd); setFunnel(fn); try { setWorkflow(await api.getJobWorkflow(jobId)); } catch { setWorkflow(null); } } catch (e) { setError((e as Error).message); } finally { setLoading(false); } }, [jobId]);
  useEffect(() => { load(); }, [load]);
  async function run(action: () => Promise<void>) { setBusy(true); setError(null); try { await action(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }
  if (loading) return <main className="container">Loading job workspace…</main>;
  if (!job) return <main className="container"><Link href="/jobs">← Jobs</Link><p className="error">{error ?? "Job not found."}</p></main>;
  const stages = workflow?.stages ?? [];
  const tabs: Array<[Tab, string, number?]> = [["overview", "Overview"], ["workflow", "Funnel", stages.length], ["pipeline", "Pipeline", funnel?.total ?? 0], ["policy", "Calling policy"]];
  const isInactive = job.status === "archived";
  const jdConfirmed = !!jdVersion?.confirmed;
  const nextLabel = isInactive ? "Role is inactive" : !jdConfirmed ? (jdVersion ? "Confirm the job description" : "Add a job description") : !workflow ? "Draft your hiring workflow" : !workflow.approved ? "Review and approve the draft" : job.status !== "active" ? "Activate this approved job" : "Your job is ready to hire";
  const openDraft = () => { setTab("workflow"); setEditing(true); };
  const draftWorkflow = () => run(async () => { await api.draftWorkflow(jobId); setWorkflow(await api.getJobWorkflow(jobId)); setTab("workflow"); setEditing(true); });
  return <main className="container job-workspace">
    <header className="job-workspace-header"><div><Link className="back-link" href="/jobs">← Jobs</Link><p className="eyebrow">Hiring workspace</p><h1>{job.title}</h1><div className="workspace-statuses"><span className={`badge ${job.status}`}>{isInactive ? "inactive" : job.status}</span><span className={`badge ${workflow?.approved ? "active" : "draft"}`}>{workflow ? `Funnel v${workflow.version} · ${workflow.approved ? "approved" : "draft"}` : "Funnel not drafted"}</span></div></div><div className="workspace-header-actions">{workflow && !workflow.approved && <button className="secondary" onClick={openDraft}>Edit draft</button>}{workflow?.approved && job.status !== "active" && <button disabled={busy} onClick={() => run(async () => setJob(await api.activateJob(jobId)))}>{busy ? "Reactivating…" : isInactive ? "Reactivate role" : "Activate job"}</button>}{job.status !== "archived" && <button className="secondary" disabled={busy} onClick={() => setConfirmArchive(true)}>Mark inactive</button>}<button onClick={() => setTab("pipeline")}>Manage candidates</button></div></header>
    {error && <p className="error workspace-error">{error}</p>}
    <nav className="workspace-tabs" aria-label="Job workspace">{tabs.map(([id, label, count]) => <button key={id} className={tab === id ? "active" : ""} aria-current={tab === id ? "page" : undefined} onClick={() => setTab(id)}>{label}{count ? <span>{count}</span> : null}</button>)}</nav>
    {tab === "overview" && <div className="workspace-overview"><section className="workspace-hero-card"><div><p className="eyebrow">Next action</p><h2>{nextLabel}</h2><p>{!jdConfirmed ? (jdVersion ? "Confirm the extracted job description below — the funnel is drafted from it." : "Add a job description below. The hiring funnel is drafted from it.") : !workflow ? "Draft the hiring funnel — its stages and criteria — before candidates can enter the process." : !workflow.approved ? "Open the draft to adjust stages and criteria, then approve it when your team is aligned." : job.status !== "active" ? "The funnel is approved. Activate this role before adding candidates." : "Manage candidates, review activity, and keep the pipeline moving from one place."}</p></div>{!jdConfirmed ? <button className="secondary" onClick={() => { document.getElementById("jd-card")?.scrollIntoView({ behavior: "smooth" }); }}>{jdVersion ? "Review description" : "Add description"}</button> : !workflow ? <button disabled={busy} onClick={draftWorkflow}>{busy ? "Drafting…" : "Draft funnel"}</button> : !workflow.approved ? <button onClick={openDraft}>Review draft</button> : job.status !== "active" ? <button disabled={busy} onClick={() => run(async () => setJob(await api.activateJob(jobId)))}>Activate job</button> : <button onClick={openAddCandidate}>Add candidates</button>}</section><section className="workspace-summary-grid"><div><span>Funnel</span><strong>{!workflow ? "Not drafted" : workflow.approved ? "Approved" : "Draft"}</strong><button className="linklike" onClick={() => setTab("workflow")}>View funnel</button></div><div><span>Candidates</span><strong>{funnel?.total ?? 0}</strong><button className="linklike" onClick={() => setTab("pipeline")}>Open pipeline</button></div><div><span>AI stages</span><strong>{stages.filter((stage) => stage.execution_type === "ai").length}</strong><button className="linklike" onClick={() => setTab("policy")}>Review policy</button></div></section><JobDescriptionCard jobId={jobId} version={jdVersion} onChanged={load} /><FunnelSection funnel={funnel} /><section className="workspace-section"><div className="workspace-section-heading"><div><p className="eyebrow">At a glance</p><h2>Funnel stages</h2></div>{stages.length > 0 && <button className="linklike" onClick={() => setTab("workflow")}>Open funnel →</button>}</div>{stages.length ? <div className="workspace-stage-grid">{stages.map((stage) => <StageCard key={stage.id} stage={stage} />)}</div> : <div className="workspace-empty">{jdConfirmed ? <>No funnel drafted yet. <button className="linklike" disabled={busy} onClick={draftWorkflow}>Draft the funnel</button> to suggest stages from the job description.</> : "Confirm a job description first — the funnel is drafted from it."}</div>}</section></div>}
    {tab === "workflow" && <section className="workspace-section"><div className="workspace-section-heading"><div><p className="eyebrow">Funnel configuration</p><h2>{editing ? "Edit funnel draft" : "Hiring funnel"}</h2><p>{workflow?.approved ? "This approved version is read-only to protect active candidate journeys." : editing ? "Save your changes before approving this version." : !workflow ? "Draft a funnel of stages and criteria from the confirmed job description." : "Review the stages, criteria, and approval checkpoints for this role."}</p></div>{workflow && !workflow.approved && !editing && <button onClick={() => setEditing(true)}>Edit draft</button>}</div>{!workflow ? (jdConfirmed ? <div className="step-card empty-workflow"><div><h3>Generate a first draft</h3><p>We&apos;ll suggest stages and criteria from the confirmed job description. You stay in control before approval.</p></div><button disabled={busy} onClick={draftWorkflow}>{busy ? "Drafting…" : "Draft funnel"}</button></div> : <div className="workspace-empty">Confirm a job description first. <button className="linklike" onClick={() => setTab("overview")}>Go to the description</button> — the funnel is drafted from it.</div>) : editing && !workflow.approved ? <><WorkflowEditor initialStages={stagesToEdit(workflow.stages)} saveLabel="Save funnel changes" onSave={async (s) => { const wf = await api.editWorkflowStages(jobId, workflow.version_id, s); setWorkflow(wf); return stagesToEdit(wf.stages); }} /><div className="workspace-approval-bar"><div><strong>Ready to lock this funnel?</strong><p>Once approved, this version cannot be edited. Create a new version for future changes.</p></div><button disabled={busy} onClick={() => run(async () => { await api.approveWorkflow(jobId, workflow.version_id); setWorkflow(await api.getJobWorkflow(jobId)); setEditing(false); })}>{busy ? "Approving…" : "Approve funnel"}</button></div></> : <><div className="workspace-stage-grid">{stages.map((stage) => <StageCard key={stage.id} stage={stage} />)}</div>{workflow.approved && <StageVoiceAgents jobId={jobId} versionId={workflow.version_id} />}{!workflow.approved && <button className="secondary workspace-edit-cta" onClick={() => setEditing(true)}>Edit this draft</button>}</>}</section>}
    {tab === "pipeline" && <PipelineTab jobId={jobId} funnel={funnel} stages={stages} onChanged={load} addSignal={addSignal} />}
    {tab === "policy" && <section className="workspace-section policy-workspace"><div className="workspace-section-heading"><div><p className="eyebrow">Candidate contact controls</p><h2>Calling policy</h2><p>Set when AI calls may run and how unanswered calls are retried. Preferred language is a future agent preference; it does not change an existing call.</p></div></div><CallingPolicyCard jobId={jobId} /></section>}
    <ConfirmDialog
      open={confirmArchive}
      title="Mark this role inactive?"
      message={<>“{job.title}” becomes <strong>inactive</strong>. Its workflow and candidate history are kept, and you can reactivate it later.</>}
      confirmLabel="Mark inactive"
      busyLabel="Updating…"
      danger
      onConfirm={async () => { setJob(await api.archiveJob(jobId)); }}
      onClose={() => setConfirmArchive(false)}
    />
  </main>;
}
