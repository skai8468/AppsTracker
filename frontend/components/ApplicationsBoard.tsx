"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Application, AppStatus } from "@/lib/types";

const COLUMNS: AppStatus[] = [
  "applied",
  "confirmed",
  "interviewing",
  "offer",
  "rejected",
];
const COLUMN_LABEL: Record<string, string> = {
  applied: "Applied",
  confirmed: "Confirmed",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Rejected",
};

const NEXT_STAGES: AppStatus[] = [
  "applied",
  "confirmed",
  "interviewing",
  "offer",
  "rejected",
  "withdrawn",
];

export default function ApplicationsBoard() {
  const [apps, setApps] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);

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
    await api.updateApplication(app.id, { status });
    load();
  }

  const byCol = (status: AppStatus) => apps.filter((a) => a.status === status);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">My applications</h1>
          <p className="page-sub">
            {apps.length} tracked · confirmations flip automatically from your inbox
          </p>
        </div>
      </div>

      {loading ? (
        <div className="empty">Loading…</div>
      ) : apps.length === 0 ? (
        <div className="empty">
          Nothing tracked yet. Go to Jobs and hit “+ Track” on roles you apply to.
        </div>
      ) : (
        <div className="kanban">
          {COLUMNS.map((col) => (
            <div className="col" key={col}>
              <div className="col-head">
                <span>{COLUMN_LABEL[col]}</span>
                <span>{byCol(col).length}</span>
              </div>
              {byCol(col).map((app) => (
                <div className="mini-card" key={app.id}>
                  <div className="t">{app.job?.title || `Job #${app.job_id}`}</div>
                  <div className="c">{app.job?.company_name}</div>
                  <select
                    style={{ marginTop: 8, width: "100%", fontSize: 12 }}
                    value={app.status}
                    onChange={(e) => move(app, e.target.value as AppStatus)}
                  >
                    {NEXT_STAGES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
