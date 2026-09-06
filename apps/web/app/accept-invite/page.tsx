"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, type InvitePreview } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function AcceptInner() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token") ?? "";
  const { refresh } = useAuth();

  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token) {
      setError("This invite link is missing its token.");
      setLoading(false);
      return;
    }
    api
      .previewInvite(token)
      .then(setPreview)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [token]);

  async function accept() {
    setSubmitting(true);
    setError(null);
    try {
      await api.acceptInvite({ token, password, name: name.trim() || undefined });
      await refresh?.();
      router.push("/");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <div className="auth-brand">
          <div className="auth-logo">HR</div>
          <div>
            <div className="auth-title">Join the team</div>
            <div className="muted" style={{ fontSize: 13 }}>Set a password to accept your invitation.</div>
          </div>
        </div>

        {loading ? (
          <p className="muted">Checking your invite…</p>
        ) : error && !preview ? (
          <>
            <p className="error">{error}</p>
            <p className="muted" style={{ fontSize: 13 }}>Ask an admin to send a new invite link.</p>
          </>
        ) : preview ? (
          <>
            <div className="invite-summary">
              You&apos;ve been invited to <strong>{preview.org_name}</strong> as{" "}
              <span className="badge">{preview.role}</span>
              <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>{preview.email}</div>
            </div>
            {error && <p className="error">{error}</p>}
            <label>
              Your name (optional)
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name" />
            </label>
            <label>
              Choose a password
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 6 characters" />
            </label>
            <button disabled={submitting || password.length < 6} onClick={accept}>
              {submitting ? "Joining…" : "Accept & join"}
            </button>
          </>
        ) : null}
      </div>
    </div>
  );
}

export default function AcceptInvitePage() {
  return (
    <Suspense fallback={<div className="auth-wrap"><div className="auth-card">Loading…</div></div>}>
      <AcceptInner />
    </Suspense>
  );
}
