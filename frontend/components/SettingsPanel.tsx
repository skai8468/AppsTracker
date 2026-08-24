"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Company } from "@/lib/types";
import { SectorBadge } from "./ui";

export default function SettingsPanel() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [name, setName] = useState("");
  const [domains, setDomains] = useState("");
  const [sector, setSector] = useState("tech");

  async function load() {
    setCompanies(await api.listCompanies());
  }
  useEffect(() => {
    load();
  }, []);

  async function add() {
    if (!name.trim()) return;
    await api.createCompany({
      name: name.trim(),
      email_domains: domains.trim(),
      sector: sector as Company["sector"],
    });
    setName("");
    setDomains("");
    load();
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-sub">Connect integrations and manage tracked companies</p>
        </div>
      </div>

      <div className="notice">
        <b>Gmail</b> — run <code>python -m app.gmail.oauth</code> once on the backend to
        grant read-only access. The poller then watches for confirmation emails and
        replies from the companies below.
      </div>
      <div className="notice">
        <b>Telegram</b> — message your bot <code>/start</code> to link it. You&apos;ll get
        a ping when an application is confirmed and whenever a tracked company emails you.
      </div>

      <h3 style={{ marginTop: 24 }}>Tracked companies</h3>
      <p className="page-sub" style={{ marginBottom: 12 }}>
        Email domains here drive Gmail matching (e.g. <code>dbs.com,dbs.com.sg</code>).
      </p>

      <div className="toolbar">
        <input
          placeholder="Company name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          placeholder="email domains, comma-separated"
          value={domains}
          onChange={(e) => setDomains(e.target.value)}
          style={{ minWidth: 240 }}
        />
        <select value={sector} onChange={(e) => setSector(e.target.value)}>
          <option value="tech">Tech</option>
          <option value="finance">Finance</option>
          <option value="other">Other</option>
        </select>
        <button className="btn" onClick={add}>
          Add
        </button>
      </div>

      {companies.length === 0 ? (
        <div className="empty">
          No companies yet. Tracking a job auto-creates its company; add email domains
          here so Gmail matching works.
        </div>
      ) : (
        companies.map((c) => (
          <div className="list-row" key={c.id}>
            <div className="card-row">
              <span className="subj">{c.name}</span>
              <SectorBadge sector={c.sector} />
            </div>
            <div className="from">
              {c.email_domains
                ? `domains: ${c.email_domains}`
                : "⚠ no email domains set — Gmail can't match this company"}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
