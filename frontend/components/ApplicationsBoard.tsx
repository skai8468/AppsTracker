"use client";

import { useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { Application, AppStatus, Sector } from "@/lib/types";
import {
  ALL_STATUSES,
  Monogram,
  SectorBadge,
  STAGES,
  STAGE_COLOR,
  STAGE_LABEL,
  stageClass,
  timeAgo,
} from "./ui";

type Filter = "all" | "active" | "closed";
const CLOSED: AppStatus[] = ["rejected", "withdrawn"];

const EMPTY_FORM = {
  url: "",
  title: "",
  company: "",
  domains: "",
  sector: "other" as Sector,
};

export default function ApplicationsBoard() {
  const [apps, setApps] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>("all");

  const [sheet, setSheet] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [detecting, setDetecting] = useState(false);
  const [autofilled, setAutofilled] = useState({ title: false, company: false });
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setApps(await api.listApplications());
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function move(app: Application, status: AppStatus) {
    setApps((prev) => prev.map((a) => (a.id === app.id ? { ...a, status } : a)));
    await api.updateApplication(app.id, { status });
    load();
  }

  async function remove(app: Application) {
    if (!confirm(`Remove "${app.job?.title || "this application"}"?`)) return;
    setApps((prev) => prev.filter((a) => a.id !== app.id));
    await api.deleteApplication(app.id);
    load();
  }

  function openSheet() {
    setForm({ ...EMPTY_FORM });
    setAutofilled({ title: false, company: false });
    setDetecting(false);
    setSheet(true);
  }

  async function detect(url: string) {
    if (!/^https?:\/\//i.test(url.trim())) return;
    setDetecting(true);
    try {
      const p = await api.previewLink(url.trim());
      if (p.ok) {
        setForm((f) => ({
          ...f,
          title: f.title || p.title,
          company: f.company || p.company,
          sector: p.sector,
        }));
        setAutofilled({ title: !!p.title, company: !!p.company });
      }
    } catch {
      /* best-effort; leave fields for manual entry */
    } finally {
      setDetecting(false);
    }
  }

  async function pasteUrl() {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        setForm((f) => ({ ...f, url: text.trim() }));
        detect(text);
      }
    } catch {
      /* clipboard blocked; user can type */
    }
  }

  const canSave = form.url.trim() && form.title.trim() && form.company.trim();

  async function save() {
    if (!canSave || saving) return;
    setSaving(true);
    try {
      await api.addApplication({
        url: form.url.trim(),
        title: form.title.trim(),
        company: form.company.trim(),
        email_domains: form.domains.trim(),
        sector: form.sector,
        status: "interested",
      });
      setSheet(false);
      load();
    } catch (e: any) {
      alert(
        String(e?.message || "").includes("409")
          ? "You're already tracking this link."
          : "Couldn't save — please try again."
      );
    } finally {
      setSaving(false);
    }
  }

  const visibleStages = STAGES.filter((s) => {
    if (filter === "active") return !CLOSED.includes(s.key);
    if (filter === "closed") return CLOSED.includes(s.key);
    return true;
  });
  // Withdrawn has no dedicated section; surface it under the "closed" and "all" views.
  const showWithdrawn = filter !== "active";
  const byStatus = (s: AppStatus) => apps.filter((a) => a.status === s);
  const withdrawn = byStatus("withdrawn");

  return (
    <>
      <header className="nav">
        <div className="nav-bar">
          <div />
          <div className="nav-actions">
            <button className="icon-btn" onClick={openSheet} aria-label="Add by link">
              ＋
            </button>
          </div>
        </div>
        <h1 className="large-title">Applications</h1>
        <p className="nav-sub">
          {apps.length
            ? `${apps.length} tracked · confirmations flip automatically from your inbox`
            : "Paste a job link to start tracking"}
        </p>
      </header>

      {apps.length > 0 && (
        <div className="segmented">
          {(["all", "active", "closed"] as Filter[]).map((f) => (
            <button
              key={f}
              className={filter === f ? "active" : ""}
              onClick={() => setFilter(f)}
            >
              {f === "all" ? "All" : f === "active" ? "Active" : "Closed"}
            </button>
          ))}
        </div>
      )}

      <div className="content">
        {loading ? (
          <div className="loading">Loading…</div>
        ) : apps.length === 0 ? (
          <div className="empty">
            <span className="big">🗂️</span>
            No applications yet.
            <br />
            Tap ＋ to paste a job link — we'll fill in the role and company for you.
          </div>
        ) : (
          <>
            {visibleStages.map((stage) => {
              const rows = byStatus(stage.key);
              if (rows.length === 0) return null;
              return (
                <Section key={stage.key} status={stage.key} count={rows.length}>
                  {rows.map((app) => (
                    <Row key={app.id} app={app} onMove={move} onRemove={remove} />
                  ))}
                </Section>
              );
            })}
            {showWithdrawn && withdrawn.length > 0 && (
              <Section status="withdrawn" count={withdrawn.length}>
                {withdrawn.map((app) => (
                  <Row key={app.id} app={app} onMove={move} onRemove={remove} />
                ))}
              </Section>
            )}
          </>
        )}
      </div>

      {sheet && (
        <div className="scrim" onClick={() => setSheet(false)}>
          <div className="sheet" onClick={(e) => e.stopPropagation()}>
            <div className="grabber" />
            <div className="sheet-head">
              <button className="btn-plain" onClick={() => setSheet(false)}>
                Cancel
              </button>
              <span className="sheet-title">Add by Link</span>
              <span style={{ width: 52 }} />
            </div>
            <p className="sheet-sub">
              Paste a job link — we'll try to fill in the role and company. You can edit
              anything before saving.
            </p>

            <div className="field-group">
              <div className="field">
                <input
                  className="accent-input"
                  placeholder="https://…"
                  value={form.url}
                  autoFocus
                  onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
                  onBlur={(e) => detect(e.target.value)}
                />
                <button className="pill" onClick={pasteUrl}>
                  Paste
                </button>
              </div>
            </div>

            {detecting ? (
              <div className="detected">
                <span className="dot" style={{ background: "var(--label-tertiary)" }} />
                Detecting…
              </div>
            ) : (autofilled.title || autofilled.company) ? (
              <div className="detected">
                <span className="dot" />
                Detected from link · you can edit below
              </div>
            ) : null}

            <div className="field-group">
              <div className="field">
                <span className="field-label">Title</span>
                <input
                  placeholder="Role title"
                  value={form.title}
                  onChange={(e) => {
                    setForm((f) => ({ ...f, title: e.target.value }));
                    setAutofilled((a) => ({ ...a, title: false }));
                  }}
                />
                {autofilled.title && <span className="auto-tag">✓ Auto</span>}
              </div>
              <div className="field">
                <span className="field-label">Company</span>
                <input
                  placeholder="Company"
                  value={form.company}
                  onChange={(e) => {
                    setForm((f) => ({ ...f, company: e.target.value }));
                    setAutofilled((a) => ({ ...a, company: false }));
                  }}
                />
                {autofilled.company && <span className="auto-tag">✓ Auto</span>}
              </div>
            </div>

            <div className="field-group">
              <div className="field">
                <span className="field-label">Domain</span>
                <input
                  placeholder="company.com (optional)"
                  value={form.domains}
                  onChange={(e) => setForm((f) => ({ ...f, domains: e.target.value }))}
                />
              </div>
            </div>
            <p className="sheet-sub" style={{ marginTop: -10 }}>
              So Gmail can auto-detect the confirmation email. You can add or edit this
              later in Settings.
            </p>

            <div className="group-label">Sector</div>
            <div className="segmented" style={{ margin: "0 0 20px" }}>
              {(["tech", "finance", "other"] as Sector[]).map((s) => (
                <button
                  key={s}
                  className={form.sector === s ? "active" : ""}
                  onClick={() => setForm((f) => ({ ...f, sector: s }))}
                  style={{ textTransform: "capitalize" }}
                >
                  {s}
                </button>
              ))}
            </div>

            <button className="btn-primary" disabled={!canSave || saving} onClick={save}>
              {saving ? "Saving…" : "Save to Saved"}
            </button>
          </div>
        </div>
      )}
    </>
  );
}

function Section({
  status,
  count,
  children,
}: {
  status: AppStatus;
  count: number;
  children: ReactNode;
}) {
  return (
    <div className="section">
      <div className="section-head">
        <span className="section-dot" style={{ background: STAGE_COLOR[status] }} />
        <span className="section-title">{STAGE_LABEL[status]}</span>
        <span className="section-count">{count}</span>
      </div>
      <div className="group">{children}</div>
    </div>
  );
}

function Row({
  app,
  onMove,
  onRemove,
}: {
  app: Application;
  onMove: (a: Application, s: AppStatus) => void;
  onRemove: (a: Application) => void;
}) {
  const title = app.job?.title || `Job #${app.job_id}`;
  const company = app.job?.company_name || "";
  const applied = app.applied_at ? `Applied ${timeAgo(app.applied_at)}` : null;
  return (
    <div className="row">
      <Monogram name={company || title} />
      <div className="row-body">
        <div className="row-title">{title}</div>
        <div className="row-sub">
          {company && <span>{company}</span>}
          {app.job && <SectorBadge sector={app.job.sector} />}
        </div>
        {applied && <div className="row-meta">↑ {applied}</div>}
      </div>
      <div className="row-actions">
        {app.job?.apply_url && (
          <a
            className="pill"
            href={app.job.apply_url}
            target="_blank"
            rel="noreferrer"
          >
            Apply ↗
          </a>
        )}
        <select
          className={`status ${stageClass(app.status)}`}
          value={app.status}
          onChange={(e) => onMove(app, e.target.value as AppStatus)}
        >
          {ALL_STATUSES.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </select>
        <button
          className="pill danger"
          onClick={() => onRemove(app)}
          aria-label="Remove"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
