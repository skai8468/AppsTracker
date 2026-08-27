"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Application } from "@/lib/types";
import ApplicationDetail from "./ApplicationDetail";
import {
  FILTERS,
  Monogram,
  Nav,
  SectorBadge,
  STAGE_LABEL,
  type Filter,
  stageClass,
} from "./ui";

export default function ApplicationsBoard() {
  const [apps, setApps] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  // null = no filter, show everything. Tapping the active tab clears back to this.
  const [filter, setFilter] = useState<Filter | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);

  async function load() {
    try {
      setApps(await api.listApplications());
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);

  const countFor = (f: Filter) => {
    const statuses = FILTERS.find((x) => x.key === f)!.statuses;
    return apps.filter((a) => statuses.includes(a.status)).length;
  };

  const visible = filter
    ? apps.filter((a) =>
        FILTERS.find((x) => x.key === filter)!.statuses.includes(a.status)
      )
    : apps;

  // Keep the open sheet bound to fresh data after a save.
  const openApp = apps.find((a) => a.id === openId) ?? null;

  return (
    <>
      <Nav
        title="Applications"
        sub={
          !apps.length
            ? "Add a job link to start tracking"
            : filter
              ? `${visible.length} of ${apps.length} · tap the tab again to clear`
              : `${apps.length} tracked`
        }
        filters={
          apps.length > 0 ? (
            <div className="segmented">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  className={filter === f.key ? "active" : ""}
                  aria-pressed={filter === f.key}
                  // Tapping the active tab clears the filter rather than doing nothing,
                  // so there's always a way back to the full list.
                  onClick={() => setFilter((cur) => (cur === f.key ? null : f.key))}
                >
                  {f.label} {countFor(f.key)}
                </button>
              ))}
            </div>
          ) : null
        }
      />

      <div className="content">
        {loading ? (
          <div className="loading">Loading…</div>
        ) : apps.length === 0 ? (
          <div className="empty">
            No applications yet.
            <br />
            Open <b>Add</b> and paste a job link — we&apos;ll fill in the role and company
            for you.
          </div>
        ) : visible.length === 0 ? (
          <div className="empty">
            Nothing in {STAGE_LABEL_FOR(filter!)}.
            <br />
            Tap it again to see all {apps.length}.
          </div>
        ) : (
          <div className="group">
            {visible.map((app) => (
              <Row key={app.id} app={app} onOpen={() => setOpenId(app.id)} />
            ))}
          </div>
        )}
      </div>

      <ApplicationDetail
        app={openApp}
        onClose={() => setOpenId(null)}
        onSaved={load}
        onRemoved={(id) => setApps((prev) => prev.filter((a) => a.id !== id))}
      />
    </>
  );
}

function STAGE_LABEL_FOR(f: Filter) {
  return FILTERS.find((x) => x.key === f)!.label;
}

function Row({ app, onOpen }: { app: Application; onOpen: () => void }) {
  const title = app.job?.title || `Job #${app.job_id}`;
  const company = app.job?.company_name || "";
  return (
    <button className="row row-tap" onClick={onOpen}>
      <Monogram name={company || title} />
      <div className="row-body">
        <div className="row-title">{title}</div>
        <div className="row-sub">
          {company && <span>{company}</span>}
          {app.job && <SectorBadge sector={app.job.sector} />}
          <span className={`status status-static ${stageClass(app.status)}`}>
            {STAGE_LABEL[app.status]}
          </span>
        </div>
      </div>
      <span className="row-chevron" aria-hidden="true">
        ›
      </span>
    </button>
  );
}
