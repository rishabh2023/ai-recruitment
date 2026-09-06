"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type AuditPageResult } from "@/lib/api";

const PAGE_SIZE = 50;

function actionLabel(a: string): string {
  return a.replace(/[._]/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export default function AuditPage() {
  const [data, setData] = useState<AuditPageResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);

  // Debounce the search box; a new term resets to the first page.
  useEffect(() => { const t = setTimeout(() => { setQ(qInput.trim()); setPage(1); }, 300); return () => clearTimeout(t); }, [qInput]);

  const fetchPage = useCallback(async () => {
    setLoading(true);
    try { setData(await api.auditLog({ page, page_size: PAGE_SIZE, q: q || undefined })); setError(null); }
    catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }, [page, q]);
  useEffect(() => { fetchPage(); }, [fetchPage]);

  const rows = data?.items ?? [];
  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, total);

  return (
    <main className="container">
      <header className="page-head">
        <div>
          <p className="eyebrow">Compliance</p>
          <h1>Audit logs</h1>
          <p className="muted">An immutable record of consequential actions across your organization — who did what, and when.</p>
        </div>
      </header>

      {error && <p className="error">{error}</p>}

      <section className="jobs-toolbar" style={{ marginBottom: 14 }}>
        <label><span className="sr-only">Search audit log</span><input type="search" value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder="Search by action, entity, state, actor…" /></label>
      </section>

      {data === null && loading ? (
        <p className="muted">Loading audit log…</p>
      ) : total === 0 ? (
        <div className="workspace-empty">{q ? "No events match this search." : "No audit events yet. Actions like creating jobs, editing workflows, and candidate decisions will appear here."}</div>
      ) : (
        <>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr><th>Action</th><th>Entity</th><th>Change</th><th>Actor</th><th>When</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td><span className="cell-strong">{actionLabel(r.action)}</span>{r.reason && <div className="muted cell-sub">{r.reason}</div>}</td>
                    <td className="muted">{r.entity_type}</td>
                    <td className="muted">{r.from_state || r.to_state ? <>{r.from_state ?? "—"} → {r.to_state ?? "—"}</> : "—"}</td>
                    <td className="muted">{r.actor_email ?? <span title="No user attributed (system or automated action)">system</span>}</td>
                    <td className="muted" style={{ whiteSpace: "nowrap" }}>{new Date(r.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pipeline-footer">
            <span className="muted">{from}–{to} of {total} event{total === 1 ? "" : "s"}</span>
            <div className="pipeline-pager">
              <button className="secondary" disabled={page <= 1 || loading} onClick={() => setPage((p) => Math.max(1, p - 1))}>← Prev</button>
              <span className="muted">Page {page} of {pageCount}</span>
              <button className="secondary" disabled={page >= pageCount || loading} onClick={() => setPage((p) => Math.min(pageCount, p + 1))}>Next →</button>
            </div>
          </div>
        </>
      )}
    </main>
  );
}
