import type { CSSProperties } from "react";

// Minimal inline line-icon set (24×24, currentColor stroke). Kept as path data so icons stay
// crisp, themeable, and dependency-free.
const PATHS: Record<string, string> = {
  dashboard: "M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z",
  jobs: "M4 7h16v13H4zM9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M4 12h16",
  candidates: "M16 19v-2a3 3 0 0 0-3-3H6a3 3 0 0 0-3 3v2M9.5 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6M21 19v-2a3 3 0 0 0-2.3-2.9M15.5 4.1a3 3 0 0 1 0 5.8",
  funnels: "M3 4h18l-7 8v6l-4 2v-8z",
  sourcing: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-4.3-4.3",
  audit: "M9 4h6a1 1 0 0 1 1 1v0h2v15H6V5h2v0a1 1 0 0 1 1-1zM8 5h8M9 11h6M9 15h4",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 0 1-4 0v-.1A1.6 1.6 0 0 0 6.6 19l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3 12.6H3a2 2 0 0 1 0-4h.1A1.6 1.6 0 0 0 4.6 6l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V2a2 2 0 0 1 4 0v.1A1.6 1.6 0 0 0 18 3.6l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V8a1.6 1.6 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z",
  review: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
  phone: "M5 3h4l2 5-2.5 1.5a12 12 0 0 0 5 5L20 14l1 4a2 2 0 0 1-2 2A16 16 0 0 1 3 5a2 2 0 0 1 2-2z",
  layers: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 17l9 5 9-5",
  file: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h6",
  rocket: "M5 15c-1.5 1.5-2 5-2 5s3.5-.5 5-2a2.8 2.8 0 0 0-3-3zM12 15l-3-3a10 10 0 0 1 8-8 10 10 0 0 1-5 11zM15 9a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
  spark: "M12 3l1.8 4.8L18 9.6l-4.2 1.8L12 16l-1.8-4.6L6 9.6l4.2-1.8z",
};

export default function Icon({ name, size = 20, style, className }: { name: keyof typeof PATHS | string; size?: number; style?: CSSProperties; className?: string }) {
  const d = PATHS[name] ?? PATHS.spark;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
      style={style} className={className}>
      {d.split("M").filter(Boolean).map((seg, i) => <path key={i} d={"M" + seg} />)}
    </svg>
  );
}
