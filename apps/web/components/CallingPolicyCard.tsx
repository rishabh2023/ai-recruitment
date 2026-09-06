"use client";

import { useEffect, useState } from "react";
import { api, type CallingPolicyInput } from "@/lib/api";

const DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];
const RETRIES = [0, 3, 6, 9, 12, 24];
const LANGS = ["ENGLISH", "HINDI", "TAMIL", "TELUGU", "KANNADA", "MARATHI", "MALAYALAM", "GUJARATI", "BENGALI", "TURKISH", "ARABIC", "SPANISH"];

const DEFAULTS: CallingPolicyInput = {
  allowed_days: ["MON", "TUE", "WED", "THU", "FRI"],
  earliest_call_time: "09:00",
  last_call_time: "18:00",
  timezone: "Asia/Kolkata",
  max_attempts: 3,
  retry_interval_hours: 6,
  language: "ENGLISH",
};

export default function CallingPolicyCard({ jobId }: { jobId: string }) {
  const [p, setP] = useState<CallingPolicyInput>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.getCallingPolicy(jobId).then((res) => { if (res) setP(res); }).finally(() => setLoading(false));
  }, [jobId]);

  function set<K extends keyof CallingPolicyInput>(k: K, v: CallingPolicyInput[K]) {
    setP((prev) => ({ ...prev, [k]: v }));
    setSaved(false);
  }
  function toggleDay(d: string) {
    setP((prev) => ({ ...prev, allowed_days: prev.allowed_days.includes(d) ? prev.allowed_days.filter((x) => x !== d) : [...prev.allowed_days, d] }));
    setSaved(false);
  }

  async function save() {
    setBusy(true); setError(null);
    try {
      const saved = await api.setCallingPolicy(jobId, p);
      setP(saved);
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="card muted">Loading calling policy…</div>;

  return (
    <div className="card" style={{ display: "grid", gap: 10, maxWidth: 640 }}>
      {error && <p className="error" style={{ margin: 0 }}>{error}</p>}
      <div>
        <div className="muted" style={{ fontSize: 12 }}>Calling days (min 3)</div>
        <div className="chips" style={{ marginTop: 4 }}>
          {DAYS.map((d) => (
            <button key={d} className={`chip ${p.allowed_days.includes(d) ? "chip-on" : ""}`} onClick={() => toggleDay(d)} type="button">{d}</button>
          ))}
        </div>
      </div>
      <div className="row" style={{ gap: 10 }}>
        <label style={{ flex: 1, margin: 0 }}>Earliest<input type="time" value={p.earliest_call_time ?? ""} onChange={(e) => set("earliest_call_time", e.target.value || null)} /></label>
        <label style={{ flex: 1, margin: 0 }}>Latest<input type="time" value={p.last_call_time ?? ""} onChange={(e) => set("last_call_time", e.target.value || null)} /></label>
        <label style={{ flex: 1, margin: 0 }}>Timezone<input value={p.timezone ?? ""} onChange={(e) => set("timezone", e.target.value || null)} placeholder="Asia/Kolkata" /></label>
      </div>
      <div className="row" style={{ gap: 10 }}>
        <label style={{ flex: 1, margin: 0 }}>Max attempts<input type="number" min={1} max={10} value={p.max_attempts} onChange={(e) => set("max_attempts", Number(e.target.value))} /></label>
        <label style={{ flex: 1, margin: 0 }}>Retry interval (h)
          <select value={p.retry_interval_hours} onChange={(e) => set("retry_interval_hours", Number(e.target.value))}>
            {RETRIES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        <label style={{ flex: 1, margin: 0 }}>Preferred agent language
          <select value={p.language ?? "ENGLISH"} onChange={(e) => set("language", e.target.value)}>
            {LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </label>
      </div>
      <div className="row" style={{ gap: 8 }}>
        <button onClick={save} disabled={busy}>{busy ? "Saving…" : "Save calling policy"}</button>
        {saved && <span className="ok" style={{ fontSize: 13 }}>Saved ✓</span>}
      </div>
    </div>
  );
}
