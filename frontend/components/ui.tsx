"use client";

import { useEffect, useRef, type ReactNode } from "react";
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

/** The three filter tabs, and which underlying statuses each one collects.
 *
 *  All seven statuses stay in the data model — the Gmail poller sets `confirmed` on its
 *  own — these groups only decide what the list shows. */
export type Filter = "saved" | "applied" | "rejected";

export const FILTERS: { key: Filter; label: string; statuses: AppStatus[] }[] = [
  { key: "saved", label: "Saved", statuses: ["interested"] },
  {
    key: "applied",
    label: "Applied",
    statuses: ["applied", "confirmed", "interviewing", "offer"],
  },
  { key: "rejected", label: "Rejected", statuses: ["rejected", "withdrawn"] },
];

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

/** Compact page header. Every view shares this, so title sizing changes in one place.
 *
 *  `filters` (a segmented control) sits on its own row under the title on a phone and
 *  moves up beside the title on desktop, where there's width to spare. */
export function Nav({
  title,
  sub,
  filters,
  actions,
}: {
  title: string;
  sub?: string;
  filters?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="nav">
      <div className="nav-bar">
        <div className="nav-titles">
          <h1 className="large-title">{title}</h1>
          {sub && <p className="nav-sub">{sub}</p>}
        </div>
        {actions && <div className="nav-actions">{actions}</div>}
        {filters && <div className="nav-filters">{filters}</div>}
      </div>
    </header>
  );
}

/** Monochrome stroke icons. Inline SVG keeps the zero-dependency stack intact. */
const ICON_PATHS: Record<string, ReactNode> = {
  list: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <path d="M7 9h10M7 13h10M7 17h5" />
    </>
  ),
  mail: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2.5" />
      <path d="m3.5 7.5 8.5 6 8.5-6" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
};

export function Icon({ name, size = 26 }: { name: keyof typeof ICON_PATHS | string; size?: number }) {
  return (
    <svg
      className="ico"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICON_PATHS[name] ?? null}
    </svg>
  );
}

/** iOS-style bottom sheet. On wide screens CSS re-renders it as a docked side pane. */
export function Sheet({
  open,
  onClose,
  title,
  leading,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  leading?: ReactNode;
  children: ReactNode;
}) {
  const sheetRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    // Stop the page behind the scrim from scrolling under the sheet.
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  // Lift the sheet above the on-screen keyboard. iOS doesn't resize the layout viewport
  // when the keyboard opens, so a bottom-anchored sheet ends up underneath it; the
  // visual viewport is the only thing that reports the covered height.
  useEffect(() => {
    if (!open) return;
    const vv = window.visualViewport;
    const el = sheetRef.current;
    if (!vv || !el) return;

    const fit = () => {
      const covered = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      el.style.transform = covered ? `translateY(-${covered}px)` : "";
      // Shrink to match, or the top of the sheet is pushed off-screen.
      el.style.maxHeight = covered ? `calc(88vh - ${covered}px)` : "";
      if (covered) {
        document.activeElement?.scrollIntoView?.({ block: "nearest" });
      }
    };
    vv.addEventListener("resize", fit);
    vv.addEventListener("scroll", fit);
    fit();
    return () => {
      vv.removeEventListener("resize", fit);
      vv.removeEventListener("scroll", fit);
      el.style.transform = "";
      el.style.maxHeight = "";
    };
  }, [open]);

  if (!open) return null;
  return (
    <div className="scrim" onClick={onClose}>
      <div
        className="sheet"
        ref={sheetRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="grabber" />
        <div className="sheet-head">
          {leading ?? (
            <button className="btn-plain" onClick={onClose}>
              Cancel
            </button>
          )}
          <span className="sheet-title">{title}</span>
          <span style={{ width: 52 }} />
        </div>
        {children}
      </div>
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

/** ISO timestamp -> the `YYYY-MM-DD` an <input type="date"> expects (local calendar day). */
export function toDateInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** `YYYY-MM-DD` -> ISO timestamp for the API. Empty input clears the date. */
export function fromDateInput(value: string): string | null {
  if (!value) return null;
  const d = new Date(`${value}T12:00:00`); // midday avoids tz-shifting the calendar day
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

/** Long date for display, e.g. "12 Aug 2026". */
export function formatDate(iso: string | null): string {
  if (!iso) return "Not set";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Not set";
  return d.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
