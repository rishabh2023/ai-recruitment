"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth";
import AuthScreen from "./AuthScreen";

type NavItem = { href: string; label: string; icon: string; match: (p: string) => boolean; disabled?: boolean };

const NAV: NavItem[] = [
  { href: "/", label: "Dashboard", icon: "▤", match: (p) => p === "/" },
  { href: "/jobs", label: "Jobs", icon: "▦", match: (p) => p.startsWith("/jobs") || p.startsWith("/job-candidates") },
  { href: "/sourcing", label: "Sourcing", icon: "◎", match: (p) => p.startsWith("/sourcing") },
  { href: "/settings", label: "Settings", icon: "⚙", match: (p) => p.startsWith("/settings") },
];

export default function AppShell({ children }: { children: ReactNode }) {
  const { me, loading, logout } = useAuth();
  const pathname = usePathname() || "/";

  if (loading) {
    return <div className="shell-loading">Loading…</div>;
  }
  if (!me) {
    return <AuthScreen />;
  }

  const initials = (me.name ?? me.email ?? "?")
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase())
    .join("");

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="auth-logo">HR</div>
          <span>AI Recruitment</span>
        </div>
        <nav className="sidebar-nav">
          {NAV.map((item) =>
            item.disabled ? (
              <span key={item.label} className="nav-item disabled" title="Coming soon">
                <span className="nav-icon">{item.icon}</span>
                {item.label}
                <span className="soon">soon</span>
              </span>
            ) : (
              <Link
                key={item.label}
                href={item.href}
                className={`nav-item ${item.match(pathname) ? "active" : ""}`}
              >
                <span className="nav-icon">{item.icon}</span>
                {item.label}
              </Link>
            ),
          )}
        </nav>
        <div className="sidebar-foot">
          <div className="avatar">{initials || "?"}</div>
          <div className="who">
            <div className="who-name">{me.name ?? me.email ?? "User"}</div>
            <div className="who-role muted">{me.role}</div>
          </div>
        </div>
        <button className="secondary signout" onClick={logout}>Sign out</button>
      </aside>
      <div className="content">{children}</div>
    </div>
  );
}
