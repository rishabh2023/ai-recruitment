"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Settings } from "@/lib/api";

type SettingsTab = "organization" | "providers" | "outreach" | "team";

export default function SettingsPage() {
  const [s, setS] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<SettingsTab>("organization");

  // local edits
  const [orgName, setOrgName] = useState("");
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
      setOrgName(data.org_name);
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
      setOrgName(data.org_name);
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
  const tabs: { key: SettingsTab; label: string; detail: string }[] = [
    { key: "organization", label: "Organization", detail: "Profile" },
    { key: "providers", label: "Providers", detail: "Candidate discovery" },
    { key: "outreach", label: "Outreach", detail: "Calling controls" },
    { key: "team", label: "Team", detail: "Access management" },
  ];

  return (
    <main className="container settings-page">
      <header className="jobs-header">
        <div>
          <p className="eyebrow">Organization</p>
          <h1>Settings</h1>
          <p>{s.org_name} · configure people-search providers, outreach calling, and your team.</p>
        </div>
        <div className="settings-org-mark" aria-label={`${s.org_name} organization`}>
          <span>{s.org_name.slice(0, 1).toUpperCase()}</span>
          <small>Workspace</small>
        </div>
      </header>

      {!admin && (
        <div className="candidate-notice"><div><strong>Read-only</strong>
          <p>Only an admin can change these settings. You can review the current configuration below.</p></div></div>
      )}
      {error && <p className="error">{error}</p>}
      {flash && <p className="sourcing-flash" role="status">{flash}</p>}

      <div className="settings-tabs" role="tablist" aria-label="Settings sections">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.key}
            className={activeTab === tab.key ? "active" : ""}
            onClick={() => setActiveTab(tab.key)}
          >
            <span>{tab.label}</span>
            <small>{tab.detail}</small>
          </button>
        ))}
      </div>

      {activeTab === "organization" && <section className="settings-card settings-profile-card" role="tabpanel">
        <div className="settings-card-head">
          <p className="settings-section-kicker">Organization profile</p>
          <h2>Organization name</h2>
          <p className="muted">This name is shown throughout your recruitment workspace.</p>
        </div>
        {admin ? (
          <div className="settings-profile-form">
            <label className="settings-inline">
              <span className="field-label">Organization name</span>
              <input
                value={orgName}
                maxLength={120}
                onChange={(e) => setOrgName(e.target.value)}
                placeholder="Your organization"
              />
            </label>
            <button
              disabled={saving || !orgName.trim() || orgName.trim() === s.org_name}
              onClick={() => save({ org_name: orgName.trim() }, "Organization name updated.")}
            >
              Save name
            </button>
          </div>
        ) : (
          <p className="settings-readonly-value">{s.org_name}</p>
        )}
      </section>}

      {/* People-search providers */}
      {activeTab === "providers" && <>
      <section className="settings-card" role="tabpanel">
        <div className="settings-card-head">
          <p className="settings-section-kicker">Candidate discovery</p>
          <h2>People-search providers</h2>
          <p className="muted">Add an API key to search real candidates with that provider. Keys are stored securely and never shown again.</p>
        </div>
        <div className="settings-providers">
          {s.providers.map((p) => (
            <div className="settings-provider" key={p.key}>
              <div className="settings-provider-identity">
                <div className="settings-provider-icon" aria-hidden="true">{p.label.slice(0, 1)}</div>
                <div className="settings-provider-main">
                  <div className="row" style={{ gap: 8, alignItems: "center" }}>
                    <strong>{p.label}</strong>
                    <span className={`badge ${p.configured ? "active" : "draft"}`}>
                      {p.configured ? "connected" : "not connected"}
                    </span>
                  </div>
                  <span className="settings-provider-status">
                    {p.configured ? "Ready for candidate searches" : "Add a key to enable searches"}
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
      </section>

      <section className="settings-card settings-defaults-card">
        <div className="settings-card-head">
          <p className="settings-section-kicker">Search defaults</p>
          <h2>Preferred provider</h2>
          <p className="muted">This provider is selected automatically when a recruiter starts a new search.</p>
        </div>
        {admin ? (
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
        ) : (
          <p className="settings-readonly-value">{s.providers.find((p) => p.key === defaultProvider)?.label ?? "No provider selected"}</p>
        )}
      </section>
      </>}

      {/* Outreach calling */}
      {activeTab === "outreach" && <section className="settings-card" role="tabpanel">
        <div className="settings-card-head">
          <p className="settings-section-kicker">Calling controls</p>
          <h2>Outreach calling</h2>
          <p className="muted">When on, launching an outreach or interview stage places a real Hunar call (a Hunar API key must also be configured on the server). When off, calls are queued but not dialed.</p>
        </div>
        <label className="approval-toggle settings-call-control">
          <input type="checkbox" checked={liveCalls} disabled={!admin || saving} onChange={(e) => { setLiveCalls(e.target.checked); save({ live_calls_enabled: e.target.checked }, `Live calling ${e.target.checked ? "enabled" : "disabled"}.`); }} />
          <span><strong>Enable live outbound calls</strong><small>Real candidates will be dialed. Keep off unless you intend to place live calls.</small></span>
          <span className={`settings-call-status ${liveCalls ? "on" : "off"}`}>{liveCalls ? "Live" : "Paused"}</span>
        </label>
      </section>}

      {/* Team */}
      {activeTab === "team" && <section className="settings-card" role="tabpanel">
        <div className="settings-card-head">
          <p className="settings-section-kicker">Access management</p>
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
      </section>}
    </main>
  );
}
