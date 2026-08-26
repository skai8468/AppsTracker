"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AppStatus, EmailEvent } from "@/lib/types";

const STAGES: AppStatus[] = ["confirmed", "interviewing", "offer", "rejected"];
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
    <>
      <header className="nav">
        <div className="nav-bar">
          <div />
        </div>
        <h1 className="large-title">Inbox</h1>
        <p className="nav-sub">
          Emails from tracked companies · tap a stage to update the application
        </p>
      </header>

      <div className="content">
        {loading ? (
          <div className="loading">Loading…</div>
        ) : events.length === 0 ? (
          <div className="empty">
            <span className="big">📭</span>
            No company emails yet.
            <br />
            Connect Gmail in Settings, then this fills up as recruiters reply.
          </div>
        ) : (
          <div className="group">
            {events.map((ev) => (
              <div className={`row mail ${ev.is_read ? "" : "unread"}`} key={ev.id}>
                <div className="row-body">
                  <div className="row-title">{ev.subject || "(no subject)"}</div>
                  <div className="row-sub">
                    <span>{ev.from_addr}</span>
                  </div>
                  {ev.snippet && <div className="mail-snip">{ev.snippet}</div>}
                  {ev.classified_stage ? (
                    <div className="mail-actions">
                      <span className={`status st-${ev.classified_stage}`}>
                        {ev.classified_stage}
                      </span>
                    </div>
                  ) : (
                    <div className="mail-actions">
                      {STAGES.map((s) => (
                        <button
                          key={s}
                          className="pill"
                          onClick={() => classify(ev, s)}
                        >
                          {STAGE_LABEL[s]}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
