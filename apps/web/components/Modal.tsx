"use client";

import { useEffect, useRef, type ReactNode } from "react";

/**
 * Accessible overlay dialog: role="dialog" + aria-modal, closes on Escape and backdrop click,
 * locks body scroll, and moves focus into the panel on open. Render nothing when `open` is
 * false so it stays unmounted between uses.
 */
export default function Modal({
  open,
  onClose,
  title,
  children,
  labelledBy = "modal-title",
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  labelledBy?: string;
  size?: "sm" | "md" | "lg";
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  // Focus the panel and lock body scroll only when `open` transitions — NOT when `onClose`
  // identity changes. Callers commonly pass a fresh onClose each render; if this depended on
  // onClose it would re-focus the panel on every parent re-render (e.g. each keystroke in a
  // field inside the modal), stealing focus out of inputs.
  useEffect(() => {
    if (!open) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();
    return () => { document.body.style.overflow = prevOverflow; };
  }, [open]);

  // Escape-to-close reads the latest onClose; re-binding on identity change is harmless.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <div
        className={`modal-panel modal-${size}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? labelledBy : undefined}
        tabIndex={-1}
        ref={panelRef}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {title && <h2 id={labelledBy} className="modal-title">{title}</h2>}
        {children}
      </div>
    </div>
  );
}
