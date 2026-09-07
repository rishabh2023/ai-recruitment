"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type HunarHealth } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const LABEL: Record<HunarHealth["status"], string> = {
  healthy: "Voice AI connected",
  invalid: "Voice AI key expired",
  unconfigured: "Voice AI not configured",
  unreachable: "Voice AI unreachable",
};

export default function HunarHealthBadge() {
  const { me } = useAuth();
  const [health, setHealth] = useState<HunarHealth | null>(null);
  const [open, setOpen] = useState(false);
  const [keyInput, setKeyInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    try {
      setHealth(await api.getHunarHealth(refresh));
    } catch {
      /* leave prior state; badge shows "checking" until first success */
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(() => load(), 60_000);
    return () => clearInterval(t);
  }, [load]);

  const isAdmin = me?.role === "admin";
  const needsFix = health?.status === "invalid" || health?.status === "unconfigured";
  const tone = !health
    ? "checking"
    : health.status === "healthy"
      ? "ok"
      : health.status === "unreachable"
        ? "warn"
        : "bad";
  const label = health ? LABEL[health.status] : "Checking voice AI…";

  async function submit() {
    if (!keyInput.trim()) return;
    setSaving(true);
    setErr(null);
    try {
      const updated = await api.updateHunarKey(keyInput.trim());
      setHealth(updated);
      setOpen(false);
      setKeyInput("");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="hunar-badge">
      <button
        type="button"
        className={`hunar-badge-pill ${tone}`}
        onClick={() => isAdmin && needsFix && setOpen(true)}
        aria-label={`Voice AI status: ${label}`}
        disabled={!(isAdmin && needsFix)}
      >
        <span className="hunar-dot" aria-hidden="true" />
        <span>{label}</span>
      </button>
      {needsFix && !isAdmin && (
        <small className="hunar-badge-hint">Ask an admin to update the voice-AI key.</small>
      )}
      {needsFix && isAdmin && !open && (
        <button type="button" className="linklike" onClick={() => setOpen(true)}>
          Update key
        </button>
      )}

      {open && (
        <div className="hunar-modal-backdrop" role="dialog" aria-modal="true" aria-label="Update voice AI key">
          <div className="hunar-modal">
            <h3>Update voice-AI key</h3>
            <p className="muted">Paste a new live key from the voice-AI provider. It is verified before it is saved.</p>
            <input
              type="password"
              autoFocus
              placeholder="Paste new live key…"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
            />
            {err && <p className="error">{err}</p>}
            <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
              <button className="secondary" onClick={() => { setOpen(false); setErr(null); }} disabled={saving}>
                Cancel
              </button>
              <button onClick={submit} disabled={saving || !keyInput.trim()}>
                {saving ? "Verifying…" : "Save key"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
