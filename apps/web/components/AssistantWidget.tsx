"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

type Link = { label: string; href: string };
type Pending = { tool: string; label: string; args: Record<string, unknown> };
type Msg = { role: "assistant" | "user"; text: string; links?: Link[]; pending?: Pending | null };

const GREETING = "Hi! I'm your hiring copilot. Tell me what to do — e.g. “create a job for a Forward Deployed Engineer” — and I'll walk you through it step by step.";

const QUICK: Array<{ label: string; href: string }> = [
  { label: "Create a job", href: "/jobs/new" },
  { label: "View candidates", href: "/candidates" },
  { label: "Browse funnels", href: "/funnels" },
];

const JOB_HREF = /^\/jobs\/([0-9a-f-]{36})$/i;

// The job the conversation is currently about — inferred from the assistant's most recent
// job link. Used to target a PDF the user attaches with 📎.
function activeJobFrom(msgs: Msg[]): { id: string; label: string } | null {
  for (let i = msgs.length - 1; i >= 0; i--) {
    for (const l of msgs[i].links ?? []) {
      const m = l.href.match(JOB_HREF);
      if (m) return { id: m[1], label: l.label.replace(/^(Open|Review workflow for)\s+/i, "").replace(/[“”"]/g, "") };
    }
  }
  return null;
}

export default function AssistantWidget() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([{ role: "assistant", text: GREETING }]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const activeJob = activeJobFrom(msgs);

  useEffect(() => { bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight }); }, [msgs, open, busy]);

  // A PDF dropped before a job exists is held here; once the assistant creates the job we
  // upload it automatically.
  const pendingPdf = useRef<File | null>(null);

  function jobIdFromLinks(links?: Link[]): string | null {
    for (const l of links ?? []) { const m = l.href.match(JOB_HREF); if (m) return m[1]; }
    return null;
  }

  async function ask(history: Msg[], approve?: { tool: string; args: Record<string, unknown> }): Promise<{ links: Link[] } | null> {
    setBusy(true);
    try {
      const payload = history.filter((m) => m.text).map((m) => ({ role: m.role, content: m.text }));
      const r = await api.assistantChat(payload, approve);
      setMsgs((m) => [...m, { role: "assistant", text: r.reply, links: r.links, pending: r.pending ?? null }]);
      // If a PDF is waiting and the assistant just created/named a job, attach it now.
      const jid = jobIdFromLinks(r.links);
      if (pendingPdf.current && jid) { const f = pendingPdf.current; pendingPdf.current = null; await uploadTo(jid, "the job", f); }
      return { links: r.links };
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", text: `Sorry — ${(e as Error).message}` }]);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function uploadTo(jobId: string, label: string, file: File) {
    setBusy(true);
    setMsgs((m) => [...m, { role: "user", text: `📎 Uploading “${file.name}”…` }]);
    try {
      const v = await api.addVersionFromPdf(jobId, file);
      const ex = (v.extracted ?? {}) as Record<string, unknown>;
      const skills = Array.isArray(ex.skills) ? (ex.skills as string[]).slice(0, 8).join(", ") : "";
      const note = `The user uploaded a PDF job description for job_id ${jobId}. Extracted — title: ${ex.title ?? "?"}; role family: ${ex.role_family ?? "?"}; location: ${ex.location ?? "?"}; skills: ${skills || "none detected"}. Summarize these details warmly and ask the user to confirm before drafting the workflow.`;
      const history = [...msgs, { role: "user" as const, text: `Uploaded a PDF job description.` }, { role: "user" as const, text: note }];
      setMsgs((m) => [...m, { role: "user", text: "📄 PDF job description uploaded." }]);
      await ask(history);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", text: `⚠️ That PDF didn't process: ${(e as Error).message}. You can paste the JD text here instead.` }]);
      setBusy(false);
    }
  }

  async function confirmPending(p: Pending) {
    // clear the pending flag so its buttons disappear, then approve the one-shot action
    setMsgs((m) => m.map((x) => (x.pending?.tool === p.tool ? { ...x, pending: null } : x)));
    const history = [...msgs.map((x) => (x.pending ? { ...x, pending: null } : x)), { role: "user" as const, text: "Yes, go ahead ✅" }];
    setMsgs((m) => [...m, { role: "user", text: "Yes, go ahead ✅" }]);
    await ask(history, { tool: p.tool, args: p.args });
  }
  function cancelPending(p: Pending) {
    setMsgs((m) => [
      ...m.map((x) => (x.pending?.tool === p.tool ? { ...x, pending: null } : x)),
      { role: "user", text: "No, hold off." },
      { role: "assistant", text: "No problem — I'll hold off. 👍 Tell me when you're ready, or what you'd like to change." },
    ]);
  }

  async function send(text: string) {
    const t = text.trim();
    if (!t || busy) return;
    setInput("");
    const history = [...msgs, { role: "user" as const, text: t }];
    setMsgs(history);
    await ask(history);
  }

  async function onPdf(file: File) {
    if (fileRef.current) fileRef.current.value = "";
    if (busy) return;
    if (file.type && file.type !== "application/pdf") {
      setMsgs((m) => [...m, { role: "assistant", text: "⚠️ That's not a PDF. Attach a PDF, or paste the JD text here." }]);
      return;
    }
    if (activeJob) { await uploadTo(activeJob.id, activeJob.label, file); return; }
    // No job yet: hold the PDF, ask for the role title, then auto-attach after the job is made.
    pendingPdf.current = file;
    setMsgs((m) => [
      ...m,
      { role: "user", text: `📎 Attached “${file.name}”` },
      { role: "assistant", text: `Got it — “${file.name}” is ready. 📄 What's the role title? I'll create the job and attach this JD automatically. 🎯` },
    ]);
  }

  return (
    <>
      <button className="assistant-fab" aria-label={open ? "Close assistant" : "Open assistant"} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {open ? "✕" : "✦"}
      </button>

      {open && (
        <section className="assistant-panel" role="dialog" aria-label="Hiring assistant">
          <header className="assistant-head">
            <div><strong>Hiring copilot</strong><span className="muted">Ask, or tell me what to do</span></div>
            <button className="assistant-close" aria-label="Close" onClick={() => setOpen(false)}>✕</button>
          </header>
          <div className="assistant-body" ref={bodyRef}>
            {msgs.map((m, i) => (
              <div key={i} className={`assistant-msg ${m.role === "user" ? "user" : "bot"}`}>
                {m.text}
                {m.links && m.links.length > 0 && (
                  <div className="assistant-links">
                    {m.links.map((l, j) => (
                      <button key={j} className="assistant-chip" onClick={() => { setOpen(false); router.push(l.href); }}>{l.label}</button>
                    ))}
                  </div>
                )}
                {m.pending && (
                  <div className="assistant-confirm">
                    <span className="assistant-confirm-label">⚠️ {m.pending.label}</span>
                    <div className="assistant-confirm-actions">
                      <button className="assistant-confirm-yes" disabled={busy} onClick={() => confirmPending(m.pending!)}>Confirm</button>
                      <button className="assistant-chip" disabled={busy} onClick={() => cancelPending(m.pending!)}>Cancel</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
            {busy && <div className="assistant-msg bot assistant-typing">Working…</div>}
            {msgs.length <= 1 && (
              <div className="assistant-quick">
                {QUICK.map((a) => <button key={a.href} className="assistant-chip" onClick={() => { setOpen(false); router.push(a.href); }}>{a.label}</button>)}
              </div>
            )}
          </div>
          <form className="assistant-input" onSubmit={(e) => { e.preventDefault(); send(input); }}>
            <input type="file" accept="application/pdf,.pdf" ref={fileRef} hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) onPdf(f); }} />
            <button type="button" className="assistant-attach" title={activeJob ? `Attach a PDF JD for ${activeJob.label}` : "Attach a PDF JD (create a job first)"} aria-label="Attach a PDF job description" disabled={busy} onClick={() => fileRef.current?.click()}>📎</button>
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Type or paste the JD…" aria-label="Message the assistant" disabled={busy} />
            <button type="submit" disabled={!input.trim() || busy}>Send</button>
          </form>
        </section>
      )}
    </>
  );
}
