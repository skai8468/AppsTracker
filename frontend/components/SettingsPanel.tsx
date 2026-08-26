"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Company, Sector } from "@/lib/types";
import { Monogram, SectorBadge } from "./ui";

export default function SettingsPanel() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [name, setName] = useState("");
  const [domains, setDomains] = useState("");
  const [sector, setSector] = useState<Sector>("tech");

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
      sector,
    });
    setName("");
    setDomains("");
    load();
  }

  return (
    <>
      <header className="nav">
        <div className="nav-bar">
          <div />
        </div>
        <h1 className="large-title">Settings</h1>
        <p className="nav-sub">Integrations and tracked companies</p>
      </header>

      <div className="content">
        <div className="notice">
          <b>Gmail</b> — run <code>python -m app.gmail.oauth</code> once on the backend to
          grant read-only access. The poller then watches for confirmation emails and
          replies from the companies below.
        </div>
        <div className="notice">
          <b>Telegram</b> — message your bot <code>/start</code> to link it. You&apos;ll get
          a ping when an application is confirmed and whenever a tracked company emails you.
        </div>

        <div className="group-label" style={{ marginTop: 22 }}>
          Add company
        </div>
        <div className="field-group">
          <div className="field">
            <span className="field-label">Name</span>
            <input
              placeholder="e.g. DBS Bank"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="field">
            <span className="field-label">Domains</span>
            <input
              placeholder="dbs.com, dbs.com.sg"
              value={domains}
              onChange={(e) => setDomains(e.target.value)}
            />
          </div>
        </div>
        <div className="segmented" style={{ margin: "0 0 16px" }}>
          {(["tech", "finance", "other"] as Sector[]).map((s) => (
            <button
              key={s}
              className={sector === s ? "active" : ""}
              onClick={() => setSector(s)}
              style={{ textTransform: "capitalize" }}
            >
              {s}
            </button>
          ))}
        </div>
        <button className="btn-primary" disabled={!name.trim()} onClick={add}>
          Add company
        </button>

        <div className="group-label" style={{ marginTop: 26 }}>
          Tracked companies
        </div>
        {companies.length === 0 ? (
          <div className="empty">
            No companies yet. Adding a job auto-creates its company; set email domains here
            so Gmail matching works.
          </div>
        ) : (
          <div className="group">
            {companies.map((c) => (
              <div className="row" key={c.id}>
                <Monogram name={c.name} />
                <div className="row-body">
                  <div className="row-title">{c.name}</div>
                  <div className="row-sub">
                    <SectorBadge sector={c.sector} />
                  </div>
                  {c.email_domains ? (
                    <div className="row-meta">{c.email_domains}</div>
                  ) : (
                    <div className="row-warn">⚠ no email domains — Gmail can't match</div>
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
