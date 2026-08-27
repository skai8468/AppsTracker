"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import AddPanel from "@/components/AddPanel";
import ApplicationsBoard from "@/components/ApplicationsBoard";
import EmailInbox from "@/components/EmailInbox";
import { Icon } from "@/components/ui";

type Tab = "applications" | "inbox" | "add";

const TABS: { key: Tab; label: string; icon: string }[] = [
  { key: "applications", label: "Applications", icon: "list" },
  { key: "inbox", label: "Inbox", icon: "mail" },
  { key: "add", label: "Add", icon: "plus" },
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

  // After adding, jump to the list so the new application is visible.
  const onAdded = useCallback(() => setTab("applications"), []);

  return (
    <div className="shell">
      <nav className="tabbar">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`tab ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            <span className="tab-ico">
              <Icon name={t.icon} />
            </span>
            <span className="tab-label">{t.label}</span>
            {t.key === "inbox" && unread > 0 && (
              <span className="tab-badge">{unread}</span>
            )}
          </button>
        ))}
      </nav>

      <main className="main">
        {tab === "applications" && <ApplicationsBoard />}
        {tab === "inbox" && <EmailInbox />}
        {tab === "add" && <AddPanel onAdded={onAdded} />}
      </main>
    </div>
  );
}
