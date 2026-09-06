"use client";

import { useState, type ReactNode } from "react";
import Modal from "./Modal";

/**
 * Themed confirmation dialog (replaces window.confirm). `onConfirm` may be async — the confirm
 * button shows a busy state and any thrown error is surfaced inline; the dialog closes only on
 * success. `danger` styles the confirm button for destructive/irreversible actions.
 */
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  busyLabel,
  requireText,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  busyLabel?: string;
  /** When set, the confirm button stays disabled until the user types this exact text. */
  requireText?: string;
  onConfirm: () => void | Promise<void>;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typed, setTyped] = useState("");

  function close() { if (!busy) { setError(null); setTyped(""); onClose(); } }
  const textOk = !requireText || typed.trim() === requireText.trim();
  async function confirm() {
    if (!textOk) return;
    setBusy(true); setError(null);
    try { await onConfirm(); setBusy(false); setTyped(""); onClose(); }
    catch (e) { setError((e as Error).message); setBusy(false); }
  }

  return (
    <Modal open={open} onClose={close} title={title} size="sm">
      <div className="modal-body">{message}</div>
      {requireText && (
        <label style={{ marginTop: 12 }}>Type <strong>{requireText}</strong> to confirm
          <input autoFocus value={typed} disabled={busy} onChange={(e) => setTyped(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && textOk) confirm(); }} placeholder={requireText} />
        </label>
      )}
      {error && <p className="error" style={{ marginTop: 10 }}>{error}</p>}
      <div className="modal-actions">
        <button className="secondary" onClick={close} disabled={busy}>{cancelLabel}</button>
        <button className={danger ? "danger" : ""} onClick={confirm} disabled={busy || !textOk}>{busy ? (busyLabel ?? "Working…") : confirmLabel}</button>
      </div>
    </Modal>
  );
}
