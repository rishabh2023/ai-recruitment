"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Settings } from "@/lib/api";

export default function SettingsPage() {
  const [s, setS] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // local edits
  const [defaultProvider, setDefaultProvider] = useState("");
  const [liveCalls, setLiveCalls] = useState(false);
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({});

  // invite form
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [inviteRole, setInviteRole] = useState("recruiter");
  const [inviting, setInviting] = useState(false);
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.getSettings();
      setS(data);
      setDefaultProvider(data.default_provider ?? "");
      setLiveCalls(data.live_calls_enabled);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function saveKey(providerKey: string) {
    const value = keyInputs[providerKey];
    if (value === undefined) return;
    await save({ provider_keys: { [providerKey]: value } }, `${providerKey} key saved.`);
    setKeyInputs((k) => ({ ...k, [providerKey]: "" }));
  }

  async function save(patch: Parameters<typeof api.updateSettings>[0], note: string) {
    setSaving(true);
    setError(null);
    setFlash(null);
    try {
      const data = await api.updateSettings(patch);
      setS(data);
      setDefaultProvider(data.default_provider ?? "");
      setLiveCalls(data.live_calls_enabled);
      setFlash(note);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function sendInvite() {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    setError(null);
    setFlash(null);
    setInviteLink(null);
    setCopied(false);
    try {
      const inv = await api.createInvite({ email: inviteEmail.trim(), role: inviteRole, name: inviteName.trim() || undefined });
      setInviteLink(inv.accept_url);
      setFlash(`Invite created for ${inv.email}. Copy the link below and share it with them.`);
      setInviteEmail("");
      setInviteName("");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setInviting(false);
    }
  }

  async function revoke(id: string) {
    setError(null);
    try {
      await api.revokeInvite(id);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function copyLink() {
    if (!inviteLink) return;
    try {
      await navigator.clipboard.writeText(inviteLink);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  if (loading) return <main className="container">Loading…</main>;
  if (!s) return <main className="container"><p className="error">{error}</p></main>;

  const admin = s.is_admin;
  const ROLES = [
    { key: "recruiter", label: "Recruiter" },
    { key: "hiring_manager", label: "Hiring Manager" },
    { key: "admin", label: "Admin" },
  ];

  return (
    <main className="container settings-page">
      <header className="jobs-header">
        <div>
          <p className="eyebrow">Organization</p>
          <h1>Settings</h1>
          <p>{s.org_name} · configure people-search providers, outreach calling, and your team.</p>
        </div>
      </header>

      {!admin && (
        <div className="candidate-notice"><div><strong>Read-only</strong>
          <p>Only an admin can change these settings. You can review the current configuration below.</p></div></div>
      )}
      {error && <p className="error">{error}</p>}
      {flash && <p className="sourcing-flash" role="status">{flash}</p>}

      {/* People-search providers */}
      <section className="settings-card">
        <div className="settings-card-head">
          <h2>People-search providers</h2>
          <p className="muted">Add an API key to search real candidates with that provider. Keys are stored securely and never shown again.</p>
        </div>
        <div className="settings-providers">
          {s.providers.map((p) => (
            <div className="settings-provider" key={p.key}>
              <div className="settings-provider-main">
                <div className="row" style={{ gap: 8, alignItems: "center" }}>
                  <strong>{p.label}</strong>
                  <span className={`badge ${p.configured ? "active" : "draft"}`}>
                    {p.configured ? "configured" : "not configured"}
                  </span>
                </div>
              </div>
              {admin && (
                <div className="settings-provider-key">
                  <input
                    type="password"
                    placeholder={p.configured ? "Replace API key…" : "Paste API key…"}
                    value={keyInputs[p.key] ?? ""}
                    onChange={(e) => setKeyInputs((k) => ({ ...k, [p.key]: e.target.value }))}
                  />
                  <button className="secondary" disabled={saving || !(keyInputs[p.key] ?? "").trim()} onClick={() => saveKey(p.key)}>
                    Save
                  </button>
                  {p.configured && (
                    <button className="linklike" disabled={saving} onClick={() => save({ provider_keys: { [p.key]: "" } }, `${p.label} key removed.`)}>
                      Remove
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
        {admin && (
          <div className="settings-row">
            <label className="settings-inline">
              <span className="field-label">Default provider for new searches</span>
              <select value={defaultProvider} onChange={(e) => setDefaultProvider(e.target.value)}>
                {s.providers.map((p) => (
                  <option key={p.key} value={p.key} disabled={!p.configured}>
                    {p.label}{p.configured ? "" : " — not configured"}
                  </option>
                ))}
              </select>
            </label>
            <button disabled={saving || !defaultProvider} onClick={() => save({ default_provider: defaultProvider }, "Default provider updated.")}>
              Save default
            </button>
          </div>
        )}
      </section>

      {/* Outreach calling */}
      <section className="settings-card">
        <div className="settings-card-head">
          <h2>Outreach calling</h2>
          <p className="muted">When on, launching an outreach or interview stage places a real Hunar call (a Hunar API key must also be configured on the server). When off, calls are queued but not dialed.</p>
        </div>
        <label className="approval-toggle" style={{ maxWidth: 480 }}>
          <input type="checkbox" checked={liveCalls} disabled={!admin || saving} onChange={(e) => { setLiveCalls(e.target.checked); save({ live_calls_enabled: e.target.checked }, `Live calling ${e.target.checked ? "enabled" : "disabled"}.`); }} />
          <span>Enable live outbound calls<small>Real candidates will be dialed. Keep off unless you intend to place live calls.</small></span>
        </label>
      </section>

      {/* Team */}
      <section className="settings-card">
        <div className="settings-card-head">
          <h2>Team</h2>
          <p className="muted">People in {s.org_name}. Role-based access (admin can manage settings).</p>
        </div>
        <table className="facts settings-team">
          <thead><tr><th>Name</th><th>Email</th><th>Role</th></tr></thead>
          <tbody>
            {s.users.map((u) => (
              <tr key={u.id}>
                <td>{u.name ?? "—"}</td>
                <td>{u.email}</td>
                <td><span className="badge">{u.role}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        {admin && (
          <div className="settings-invite">
            <h3>Invite a teammate</h3>
            <div className="settings-invite-form">
              <label className="settings-inline" style={{ flex: 2 }}>
                <span className="field-label">Email</span>
                <input type="email" placeholder="teammate@company.com" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} />
              </label>
              <label className="settings-inline">
                <span className="field-label">Name (optional)</span>
                <input placeholder="Full name" value={inviteName} onChange={(e) => setInviteName(e.target.value)} />
              </label>
              <label className="settings-inline">
                <span className="field-label">Role</span>
                <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)}>
                  {ROLES.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
                </select>
              </label>
              <button disabled={inviting || !inviteEmail.trim()} onClick={sendInvite}>
                {inviting ? "Creating…" : "Create invite"}
              </button>
            </div>

            {inviteLink && (
              <div className="settings-invite-link">
                <span className="field-label">Share this one-time link (shown once)</span>
                <div className="row" style={{ gap: 8 }}>
                  <input readOnly value={inviteLink} onFocus={(e) => e.currentTarget.select()} />
                  <button className="secondary" onClick={copyLink}>{copied ? "Copied ✓" : "Copy"}</button>
                </div>
              </div>
            )}

            {s.invites.length > 0 && (
              <div className="settings-pending">
                <span className="field-label">Pending invites</span>
                {s.invites.map((i) => (
                  <div className="settings-pending-row" key={i.id}>
                    <div>
                      <strong>{i.email}</strong> <span className="badge">{i.role}</span>
                      <div className="muted" style={{ fontSize: 12 }}>Expires {new Date(i.expires_at).toLocaleDateString()}</div>
                    </div>
                    <button className="linklike" onClick={() => revoke(i.id)}>Revoke</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
