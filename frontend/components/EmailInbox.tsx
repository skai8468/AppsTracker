"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AppStatus, EmailEvent } from "@/lib/types";

const STAGES: AppStatus[] = [
  "confirmed",
  "interviewing",
  "offer",
  "rejected",
];
const STAGE_LABEL: Record<string, string> = {
  confirmed: "Confirmed",
  interviewing: "Interview",
  offer: "Offer",
  rejected: "Rejected",
};

export default function EmailInbox() {
  const [events, setEvents] = useState<EmailEvent[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      setEvents(await api.listEmailEvents());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function classify(ev: EmailEvent, stage: AppStatus) {
    await api.classifyEmail(ev.id, stage);
    load();
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Inbox</h1>
          <p className="page-sub">
            Emails from tracked companies. Tap a stage to update the application.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="empty">Loading…</div>
      ) : events.length === 0 ? (
        <div className="empty">
          No company emails detected yet. Connect Gmail in Settings, then this fills
          up as recruiters reply.
        </div>
      ) : (
        events.map((ev) => (
          <div className={`list-row ${ev.is_read ? "" : "unread"}`} key={ev.id}>
            <div className="subj">{ev.subject || "(no subject)"}</div>
            <div className="from">{ev.from_addr}</div>
            {ev.snippet && <div className="snip">{ev.snippet}</div>}
            {ev.classified_stage ? (
              <div className="classify-row">
                <span className="badge status">
                  Classified: {ev.classified_stage}
                </span>
              </div>
            ) : (
              <div className="classify-row">
                {STAGES.map((s) => (
                  <button
                    key={s}
                    className="btn sm ghost"
                    onClick={() => classify(ev, s)}
                  >
                    {STAGE_LABEL[s]}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
}
