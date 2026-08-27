"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AppStatus, EmailEvent } from "@/lib/types";
import { Nav, STAGE_LABEL } from "./ui";

/** The stages worth one-tap classifying straight from an email. */
const STAGES: AppStatus[] = ["confirmed", "interviewing", "offer", "rejected"];

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
      <Nav title="Inbox" sub="Tap a stage to update the application" />

      <div className="content">
        {loading ? (
          <div className="loading">Loading…</div>
        ) : events.length === 0 ? (
          <div className="empty">
            No company emails yet.
            <br />
            This fills up as tracked companies reply.
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
                      <span className={`status status-static st-${ev.classified_stage}`}>
                        {STAGE_LABEL[ev.classified_stage]}
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
