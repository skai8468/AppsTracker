"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import ApplicationsBoard from "@/components/ApplicationsBoard";
import EmailInbox from "@/components/EmailInbox";
import SettingsPanel from "@/components/SettingsPanel";

type Tab = "applications" | "inbox" | "settings";

const TABS: { key: Tab; label: string; icon: string }[] = [
  { key: "applications", label: "Applications", icon: "🗂️" },
  { key: "inbox", label: "Inbox", icon: "📥" },
  { key: "settings", label: "Settings", icon: "⚙️" },
];

export default function Home() {
  const [tab, setTab] = useState<Tab>("applications");
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    api
      .listEmailEvents()
      .then((e) => setUnread(e.filter((x) => !x.is_read).length))
      .catch(() => setUnread(0));
  }, [tab]);

  return (
    <div className="shell">
      {tab === "applications" && <ApplicationsBoard />}
      {tab === "inbox" && <EmailInbox />}
      {tab === "settings" && <SettingsPanel />}

      <nav className="tabbar">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`tab ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            <span className="tab-ico">{t.icon}</span>
            <span className="tab-label">{t.label}</span>
            {t.key === "inbox" && unread > 0 && (
              <span className="tab-badge">{unread}</span>
            )}
          </button>
        ))}
      </nav>
    </div>
  );
}
