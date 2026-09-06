"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Tab = "signin" | "signup";

const DEMO = { email: "recruiter@demo.test", password: "demo-password" };

export default function AuthScreen() {
  const { setMe } = useAuth();
  const [tab, setTab] = useState<Tab>("signin");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // sign in
  const [email, setEmail] = useState(DEMO.email);
  const [password, setPassword] = useState(DEMO.password);

  // sign up
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [suEmail, setSuEmail] = useState("");
  const [suPassword, setSuPassword] = useState("");

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const signIn = () => run(async () => setMe(await api.login(email, password)));
  const signUp = () =>
    run(async () => {
      if (!name.trim() || !suEmail.trim() || suPassword.length < 6) {
        throw new Error("Enter your name, a valid email, and a password of at least 6 characters.");
      }
      setMe(
        await api.signup({
          name: name.trim(),
          email: suEmail.trim(),
          password: suPassword,
          org_name: company.trim() || undefined,
        }),
      );
    });

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <div className="auth-brand">
          <div className="auth-logo">HR</div>
          <div>
            <div className="auth-title">AI Recruitment</div>
            <div className="muted" style={{ fontSize: 13 }}>Hiring operations console</div>
          </div>
        </div>

        <div className="tabs" role="tablist">
          <button
            role="tab"
            aria-selected={tab === "signin"}
            className={`tab ${tab === "signin" ? "active" : ""}`}
            onClick={() => { setTab("signin"); setError(null); }}
          >
            Sign in
          </button>
          <button
            role="tab"
            aria-selected={tab === "signup"}
            className={`tab ${tab === "signup" ? "active" : ""}`}
            onClick={() => { setTab("signup"); setError(null); }}
          >
            Create account
          </button>
        </div>

        {error && <p className="error">{error}</p>}

        {tab === "signin" ? (
          <form onSubmit={(e) => { e.preventDefault(); signIn(); }} style={{ display: "grid", gap: 10 }}>
            <label>
              Email
              <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoComplete="email" />
            </label>
            <label>
              Password
              <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="current-password" />
            </label>
            <button disabled={busy} type="submit">{busy ? "Signing in…" : "Sign in"}</button>
            <p className="muted" style={{ fontSize: 13, margin: 0 }}>
              Demo credentials are pre-filled. New here?{" "}
              <button type="button" className="linklike" onClick={() => setTab("signup")}>Create an account</button>.
            </p>
          </form>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); signUp(); }} style={{ display: "grid", gap: 10 }}>
            <label>
              Full name *
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Priya Sharma" autoComplete="name" />
            </label>
            <label>
              Work email *
              <input value={suEmail} onChange={(e) => setSuEmail(e.target.value)} type="email" placeholder="you@company.com" autoComplete="email" />
            </label>
            <label>
              Company / workspace (optional)
              <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Acme Inc." autoComplete="organization" />
            </label>
            <label>
              Password *
              <input value={suPassword} onChange={(e) => setSuPassword(e.target.value)} type="password" placeholder="At least 6 characters" autoComplete="new-password" />
            </label>
            <button disabled={busy} type="submit">{busy ? "Creating…" : "Create account"}</button>
            <p className="muted" style={{ fontSize: 13, margin: 0 }}>
              You&apos;ll be the admin of a new workspace. Already have an account?{" "}
              <button type="button" className="linklike" onClick={() => setTab("signin")}>Sign in</button>.
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
