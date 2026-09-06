"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth";
import AuthScreen from "./AuthScreen";
import AssistantWidget from "./AssistantWidget";
import Icon from "./Icon";

type NavItem = { href: string; label: string; icon: string; match: (p: string) => boolean; disabled?: boolean };

const NAV: NavItem[] = [
  { href: "/", label: "Dashboard", icon: "dashboard", match: (p) => p === "/" },
  { href: "/jobs", label: "Jobs", icon: "jobs", match: (p) => p.startsWith("/jobs") },
  { href: "/candidates", label: "Candidates", icon: "candidates", match: (p) => p.startsWith("/candidates") || p.startsWith("/job-candidates") },
  { href: "/funnels", label: "Funnels", icon: "funnels", match: (p) => p.startsWith("/funnels") },
  { href: "/sourcing", label: "Sourcing", icon: "sourcing", match: (p) => p.startsWith("/sourcing") },
  { href: "/audit", label: "Audit logs", icon: "audit", match: (p) => p.startsWith("/audit") },
  { href: "/settings", label: "Settings", icon: "settings", match: (p) => p.startsWith("/settings") },
];

export default function AppShell({ children }: { children: ReactNode }) {
  const { me, loading, logout } = useAuth();
  const pathname = usePathname() || "/";

  // Public routes render outside the authenticated shell (e.g. accepting an invite while
  // logged out). Everything else requires a session.
  const isPublic = pathname.startsWith("/accept-invite");

  if (loading) {
    return <div className="shell-loading">Loading…</div>;
  }
  if (isPublic) {
    return <>{children}</>;
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
                <span className="nav-icon"><Icon name={item.icon} size={18} /></span>
                {item.label}
                <span className="soon">soon</span>
              </span>
            ) : (
              <Link
                key={item.label}
                href={item.href}
                className={`nav-item ${item.match(pathname) ? "active" : ""}`}
              >
                <span className="nav-icon"><Icon name={item.icon} size={18} /></span>
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
      <AssistantWidget />
    </div>
  );
}
