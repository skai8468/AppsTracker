"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AppStatus, EmailEvent } from "@/lib/types";
import { Icon, Nav, STAGE_LABEL } from "./ui";

/** The stages worth one-tap classifying straight from an email. */
const STAGES: AppStatus[] = ["confirmed", "interviewing", "offer", "rejected"];

/** Read but unclassified = seen and judged not to be about an application. */
const isUnrelated = (ev: EmailEvent) => ev.is_read && ev.classified_stage === null;

export default function EmailInbox() {
  const [events, setEvents] = useState<EmailEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [showUnrelated, setShowUnrelated] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanMsg, setScanMsg] = useState<string | null>(null);

  async function load() {
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

  async function dismiss(ev: EmailEvent) {
    setEvents((prev) =>
      prev.map((e) => (e.id === ev.id ? { ...e, is_read: true, classified_stage: null } : e))
    );
    await api.dismissEmail(ev.id);
    load();
  }

  async function restore(ev: EmailEvent) {
    await api.restoreEmail(ev.id);
    load();
  }

  /** Re-read recent mail — for after adding or correcting a company's domain, when an
   *  email that arrived un-matchable can finally be matched. */
  async function rescan() {
    if (scanning) return;
    setScanning(true);
    setScanMsg(null);
    try {
      const r = await api.scanInbox(30);
      if (r.status !== "ok") {
        setScanMsg("Gmail isn't connected.");
      } else if (r.tracked) {
        setScanMsg(`Found ${r.tracked} new — check Applications.`);
      } else {
        setScanMsg(`Checked ${r.scanned ?? 0} recent emails · nothing new matched.`);
      }
      await load();
    } catch {
      setScanMsg("Couldn't rescan — please try again.");
    } finally {
      setScanning(false);
    }
  }

  const unrelated = events.filter(isUnrelated);
  const active = events.filter((e) => !isUnrelated(e));
  const visible = showUnrelated ? unrelated : active;

  return (
    <>
      <Nav
        title="Inbox"
        sub={
          scanMsg ??
          (unrelated.length
            ? `${active.length} to review · ${unrelated.length} unrelated`
            : "Tap a stage to update the application")
        }
        actions={
          <button
            className={`icon-btn ${scanning ? "spinning" : ""}`}
            onClick={rescan}
            disabled={scanning}
            aria-label="Rescan recent email"
            title="Re-read the last 30 days — use after adding a company domain"
          >
            <Icon name="refresh" size={20} />
          </button>
        }
        filters={
          unrelated.length > 0 ? (
            <div className="segmented">
              <button
                className={!showUnrelated ? "active" : ""}
                onClick={() => setShowUnrelated(false)}
              >
                Inbox {active.length}
              </button>
              <button
                className={showUnrelated ? "active" : ""}
                onClick={() => setShowUnrelated(true)}
              >
                Unrelated {unrelated.length}
              </button>
            </div>
          ) : null
        }
      />

      <div className="content">
        {loading ? (
          <div className="loading">Loading…</div>
        ) : visible.length === 0 ? (
          <div className="empty">
            {showUnrelated
              ? "Nothing filed as unrelated."
              : "No company emails to review."}
            {!showUnrelated && (
              <>
                <br />
                This fills up as tracked companies reply.
              </>
            )}
          </div>
        ) : (
          <div className="group">
            {visible.map((ev) => (
              <div className={`row mail ${ev.is_read ? "" : "unread"}`} key={ev.id}>
                <div className="row-body">
                  <div className="row-title">{ev.subject || "(no subject)"}</div>
                  <div className="row-sub">
                    <span>{ev.from_addr}</span>
                  </div>
                  {ev.snippet && <div className="mail-snip">{ev.snippet}</div>}

                  {isUnrelated(ev) ? (
                    <div className="mail-actions">
                      <span className="status status-static st-withdrawn">Unrelated</span>
                      <button className="pill" onClick={() => restore(ev)}>
                        Move back
                      </button>
                    </div>
                  ) : ev.classified_stage ? (
                    <div className="mail-actions">
                      <span className={`status status-static st-${ev.classified_stage}`}>
                        {STAGE_LABEL[ev.classified_stage]}
                      </span>
                    </div>
                  ) : (
                    <div className="mail-actions">
                      {STAGES.map((s) => (
                        <button key={s} className="pill" onClick={() => classify(ev, s)}>
                          {STAGE_LABEL[s]}
                        </button>
                      ))}
                      <button className="pill muted" onClick={() => dismiss(ev)}>
                        Not related
                      </button>
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
