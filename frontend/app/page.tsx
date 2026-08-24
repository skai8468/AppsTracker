"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import JobsBoard from "@/components/JobsBoard";
import ApplicationsBoard from "@/components/ApplicationsBoard";
import EmailInbox from "@/components/EmailInbox";
import SettingsPanel from "@/components/SettingsPanel";

type Tab = "jobs" | "applications" | "inbox" | "settings";

export default function Home() {
  const [tab, setTab] = useState<Tab>("jobs");
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    api
      .listEmailEvents()
      .then((e) => setUnread(e.filter((x) => !x.is_read).length))
      .catch(() => setUnread(0));
  }, [tab]);

  const nav = (t: Tab, label: string, icon: string, badge?: number) => (
    <button
      className={`nav-item ${tab === t ? "active" : ""}`}
      onClick={() => setTab(t)}
    >
      <span>{icon}</span>
      {label}
      {badge ? <span className="nav-badge">{badge}</span> : null}
    </button>
  );

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          Job<span>Track</span> SG
        </div>
        {nav("jobs", "Jobs", "🔍")}
        {nav("applications", "Applications", "📋")}
        {nav("inbox", "Inbox", "📩", unread)}
        {nav("settings", "Settings", "⚙️")}
      </aside>
      <main className="main">
        {tab === "jobs" && <JobsBoard />}
        {tab === "applications" && <ApplicationsBoard />}
        {tab === "inbox" && <EmailInbox />}
        {tab === "settings" && <SettingsPanel />}
      </main>
    </div>
  );
}
