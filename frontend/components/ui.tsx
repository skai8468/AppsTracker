import type { AppStatus, Sector } from "@/lib/types";

/** Pipeline stages shown as grouped-list sections, in order. "interested" = Saved. */
export const STAGES: { key: AppStatus; label: string }[] = [
  { key: "interested", label: "Saved" },
  { key: "applied", label: "Applied" },
  { key: "confirmed", label: "Confirmed" },
  { key: "interviewing", label: "Interviewing" },
  { key: "offer", label: "Offer" },
  { key: "rejected", label: "Rejected" },
];

/** All statuses a card can be moved to (adds Withdrawn, which has no section). */
export const ALL_STATUSES: { key: AppStatus; label: string }[] = [
  ...STAGES,
  { key: "withdrawn", label: "Withdrawn" },
];

export const STAGE_LABEL: Record<AppStatus, string> = {
  interested: "Saved",
  applied: "Applied",
  confirmed: "Confirmed",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export const stageClass = (s: AppStatus) => `st-${s}`;

/** Section-dot color per stage (mirrors the status-pill colors in globals.css). */
export const STAGE_COLOR: Record<AppStatus, string> = {
  interested: "var(--gray)",
  applied: "var(--blue)",
  confirmed: "var(--indigo)",
  interviewing: "var(--orange)",
  offer: "var(--green)",
  rejected: "var(--red)",
  withdrawn: "var(--gray)",
};

export function SectorBadge({ sector }: { sector: Sector }) {
  return <span className={`badge ${sector}`}>{sector}</span>;
}

const MONO_COLORS = [
  "#5856d6", "#30b0c7", "#ff9500", "#34c759",
  "#007aff", "#ff2d55", "#af52de", "#5ac8fa",
];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

export function Monogram({ name }: { name: string }) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  const color = MONO_COLORS[hash % MONO_COLORS.length];
  return (
    <div className="mono" style={{ background: color }}>
      {initials(name)}
    </div>
  );
}

export function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso).getTime();
  const days = Math.floor((Date.now() - d) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "1 day ago";
  if (days < 30) return `${days} days ago`;
  return `${Math.floor(days / 30)} mo ago`;
}
