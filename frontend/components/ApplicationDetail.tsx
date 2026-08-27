"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Application, AppStatus } from "@/lib/types";
import {
  ALL_STATUSES,
  SectorBadge,
  Sheet,
  formatDate,
  fromDateInput,
  stageClass,
  toDateInput,
} from "./ui";

/** Everything the sheet can edit, held locally until Save. */
interface Draft {
  status: AppStatus;
  appliedAt: string; // YYYY-MM-DD for <input type="date">
  title: string;
  company: string;
  applyUrl: string;
  domains: string;
  notes: string;
}

function draftFrom(app: Application): Draft {
  return {
    status: app.status,
    appliedAt: toDateInput(app.applied_at),
    title: app.job?.title || "",
    company: app.job?.company_name || "",
    applyUrl: app.job?.apply_url || "",
    domains: app.job?.company_email_domains || "",
    notes: app.notes || "",
  };
}

export default function ApplicationDetail({
  app,
  onClose,
  onSaved,
  onRemoved,
}: {
  app: Application | null;
  onClose: () => void;
  onSaved: () => void;
  onRemoved: (id: number) => void;
}) {
  const [draft, setDraft] = useState<Draft | null>(app ? draftFrom(app) : null);
  const [saving, setSaving] = useState(false);

  // Re-seed whenever a different application is opened.
  useEffect(() => {
    setDraft(app ? draftFrom(app) : null);
  }, [app?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!app || !draft) return null;

  const title = app.job?.title || `Job #${app.job_id}`;
  const company = app.job?.company_name || "";
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) =>
    setDraft((d) => (d ? { ...d, [k]: v } : d));

  const dirty =
    draft.status !== app.status ||
    draft.appliedAt !== toDateInput(app.applied_at) ||
    draft.title !== (app.job?.title || "") ||
    draft.company !== (app.job?.company_name || "") ||
    draft.applyUrl !== (app.job?.apply_url || "") ||
    draft.domains !== (app.job?.company_email_domains || "") ||
    draft.notes !== (app.notes || "");

  async function save() {
    if (!app || !draft || saving) return;
    setSaving(true);
    try {
      await api.updateApplication(app.id, {
        status: draft.status,
        applied_at: fromDateInput(draft.appliedAt),
        title: draft.title.trim() || undefined,
        company: draft.company.trim() || undefined,
        apply_url: draft.applyUrl.trim() || undefined,
        email_domains: draft.domains.trim(),
        notes: draft.notes,
      });
      onSaved();
      onClose();
    } catch {
      alert("Couldn't save — please try again.");
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!app) return;
    if (!confirm(`Remove "${title}"?`)) return;
    try {
      await api.deleteApplication(app.id);
      onRemoved(app.id);
      onClose();
    } catch {
      alert("Couldn't remove — please try again.");
    }
  }

  return (
    <Sheet
      open
      onClose={onClose}
      title="Application"
      leading={
        <button className="btn-plain" onClick={onClose}>
          Close
        </button>
      }
    >
      <div className="detail-head">
        <div className="detail-title">{title}</div>
        <div className="row-sub">
          {company && <span>{company}</span>}
          {app.job && <SectorBadge sector={app.job.sector} />}
        </div>
      </div>

      <div className="group-label">Stage</div>
      <div className="field-group">
        <div className="field">
          <span className="field-label">Status</span>
          <select
            className={`status ${stageClass(draft.status)}`}
            value={draft.status}
            onChange={(e) => set("status", e.target.value as AppStatus)}
          >
            {ALL_STATUSES.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <span className="field-label">Applied</span>
          <input
            type="date"
            value={draft.appliedAt}
            onChange={(e) => set("appliedAt", e.target.value)}
          />
        </div>
      </div>

      {app.status === "confirmed" && (
        <p className="detail-note">
          Confirmed automatically — a matching email arrived from{" "}
          {app.job?.company_email_domains || company}.
        </p>
      )}

      <div className="group-label">Details</div>
      <div className="field-group">
        <div className="field">
          <span className="field-label">Title</span>
          <input
            placeholder="Role title"
            value={draft.title}
            onChange={(e) => set("title", e.target.value)}
          />
        </div>
        <div className="field">
          <span className="field-label">Company</span>
          <input
            placeholder="Company"
            value={draft.company}
            onChange={(e) => set("company", e.target.value)}
          />
        </div>
        <div className="field">
          <span className="field-label">Posting</span>
          <input
            className="accent-input"
            placeholder="https://…"
            value={draft.applyUrl}
            onChange={(e) => set("applyUrl", e.target.value)}
          />
        </div>
        <div className="field">
          <span className="field-label">Domain</span>
          <input
            placeholder="company.com"
            value={draft.domains}
            onChange={(e) => set("domains", e.target.value)}
          />
        </div>
        <div className="field">
          <span className="field-label">Notes</span>
          <input
            placeholder="Optional"
            value={draft.notes}
            onChange={(e) => set("notes", e.target.value)}
          />
        </div>
      </div>
      <p className="sheet-sub">
        The domain is how Gmail matches confirmation emails to this application. Last
        updated {formatDate(app.last_stage_change_at)}.
      </p>

      <button className="btn-primary" disabled={!dirty || saving} onClick={save}>
        {saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
      </button>

      {draft.applyUrl.trim() && (
        <a
          className="btn-secondary"
          href={draft.applyUrl}
          target="_blank"
          rel="noreferrer"
        >
          Open job posting ↗
        </a>
      )}

      <button className="btn-danger" onClick={remove}>
        Remove application
      </button>
    </Sheet>
  );
}
