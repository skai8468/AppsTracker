"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Company, Sector } from "@/lib/types";
import { Monogram, Nav, SectorBadge, Sheet } from "./ui";

type Mode = "application" | "company";

const SECTORS: Sector[] = ["tech", "finance", "other"];

const EMPTY_FORM = {
  url: "",
  title: "",
  company: "",
  domains: "",
  sector: "other" as Sector,
};

export default function AddPanel({ onAdded }: { onAdded?: () => void }) {
  const [mode, setMode] = useState<Mode>("application");
  const [gmailConnected, setGmailConnected] = useState(true);

  useEffect(() => {
    api
      .gmailStatus()
      .then((s) => setGmailConnected(s.connected))
      // A failed probe shouldn't nag about setup — assume fine and stay quiet.
      .catch(() => setGmailConnected(true));
  }, []);

  return (
    <>
      <Nav
        title="Add"
        sub="Add an application or company domain"
        filters={
          <div className="segmented">
            {(["application", "company"] as Mode[]).map((m) => (
              <button
                key={m}
                className={mode === m ? "active" : ""}
                onClick={() => setMode(m)}
              >
                {m === "application" ? "Application" : "Company"}
              </button>
            ))}
          </div>
        }
      />

      <div className="content">
        {!gmailConnected && (
          <div className="notice">
            <b>Gmail isn&apos;t connected yet.</b> Until it is, applications won&apos;t
            flip to <i>Confirmed</i> on their own. Run the one-time authorization on the
            backend to enable it.
          </div>
        )}
        {mode === "application" ? (
          <AddApplication onAdded={onAdded} />
        ) : (
          <AddCompany />
        )}
      </div>
    </>
  );
}

// --- add an application by link -------------------------------------------------------

function AddApplication({ onAdded }: { onAdded?: () => void }) {
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [detecting, setDetecting] = useState(false);
  const [autofilled, setAutofilled] = useState({ title: false, company: false });
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  async function detect(url: string) {
    if (!/^https?:\/\//i.test(url.trim())) return;
    setDetecting(true);
    try {
      const p = await api.previewLink(url.trim());
      if (p.ok) {
        setForm((f) => ({
          ...f,
          title: f.title || p.title,
          company: f.company || p.company,
          sector: p.sector,
        }));
        setAutofilled({ title: !!p.title, company: !!p.company });
      }
    } catch {
      /* best-effort; leave fields for manual entry */
    } finally {
      setDetecting(false);
    }
  }

  async function pasteUrl() {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        setForm((f) => ({ ...f, url: text.trim() }));
        detect(text);
      }
    } catch {
      /* clipboard blocked; user can type */
    }
  }

  const canSave = form.url.trim() && form.title.trim() && form.company.trim();

  async function save() {
    if (!canSave || saving) return;
    setSaving(true);
    try {
      await api.addApplication({
        url: form.url.trim(),
        title: form.title.trim(),
        company: form.company.trim(),
        email_domains: form.domains.trim(),
        sector: form.sector,
        status: "interested",
      });
      setForm({ ...EMPTY_FORM });
      setAutofilled({ title: false, company: false });
      setDone(true);
      onAdded?.();
      setTimeout(() => setDone(false), 2500);
    } catch (e: any) {
      alert(
        String(e?.message || "").includes("409")
          ? "You're already tracking this link."
          : "Couldn't save — please try again."
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="group-label">Job link</div>
      <div className="field-group">
        <div className="field">
          <input
            className="accent-input"
            placeholder="https://…"
            value={form.url}
            onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
            onBlur={(e) => detect(e.target.value)}
          />
          <button className="pill" onClick={pasteUrl}>
            Paste
          </button>
        </div>
      </div>

      {detecting ? (
        <div className="detected">
          <span className="dot" style={{ background: "var(--label-tertiary)" }} />
          Detecting…
        </div>
      ) : autofilled.title || autofilled.company ? (
        <div className="detected">
          <span className="dot" />
          Detected from link · you can edit below
        </div>
      ) : null}

      <div className="group-label">Details</div>
      <div className="field-group">
        <div className="field">
          <span className="field-label">Title</span>
          <input
            placeholder="Role title"
            value={form.title}
            onChange={(e) => {
              setForm((f) => ({ ...f, title: e.target.value }));
              setAutofilled((a) => ({ ...a, title: false }));
            }}
          />
          {autofilled.title && <span className="auto-tag">✓ Auto</span>}
        </div>
        <div className="field">
          <span className="field-label">Company</span>
          <input
            placeholder="Company"
            value={form.company}
            onChange={(e) => {
              setForm((f) => ({ ...f, company: e.target.value }));
              setAutofilled((a) => ({ ...a, company: false }));
            }}
          />
          {autofilled.company && <span className="auto-tag">✓ Auto</span>}
        </div>
        <div className="field">
          <span className="field-label">Domain</span>
          <input
            placeholder="company.com (optional)"
            value={form.domains}
            onChange={(e) => setForm((f) => ({ ...f, domains: e.target.value }))}
          />
        </div>
      </div>
      <p className="sheet-sub">
        The domain is how Gmail spots the confirmation email. You can add or change it
        later from the application itself.
      </p>

      <div className="group-label">Sector</div>
      <div className="segmented segmented-inline">
        {SECTORS.map((s) => (
          <button
            key={s}
            className={form.sector === s ? "active" : ""}
            onClick={() => setForm((f) => ({ ...f, sector: s }))}
            style={{ textTransform: "capitalize" }}
          >
            {s}
          </button>
        ))}
      </div>

      <button className="btn-primary" disabled={!canSave || saving} onClick={save}>
        {saving ? "Saving…" : done ? "Saved ✓" : "Save"}
      </button>
    </>
  );
}

// --- add / edit a tracked company -----------------------------------------------------

function AddCompany() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [name, setName] = useState("");
  const [domains, setDomains] = useState("");
  const [sector, setSector] = useState<Sector>("tech");
  const [editing, setEditing] = useState<Company | null>(null);

  async function load() {
    setCompanies(await api.listCompanies());
  }
  useEffect(() => {
    load();
  }, []);

  async function add() {
    if (!name.trim()) return;
    try {
      await api.createCompany({
        name: name.trim(),
        email_domains: domains.trim(),
        sector,
      });
      setName("");
      setDomains("");
      load();
    } catch (e: any) {
      alert(
        String(e?.message || "").includes("409")
          ? "That company is already tracked — tap it below to edit its domains."
          : "Couldn't save — please try again."
      );
    }
  }

  return (
    <>
      <div className="group-label">Add company</div>
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
      <div className="segmented segmented-inline">
        {SECTORS.map((s) => (
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
        Save
      </button>

      <div className="group-label" style={{ marginTop: 26 }}>
        Tracked companies
      </div>
      {companies.length === 0 ? (
        <div className="empty">
          No companies yet. Adding a job auto-creates its company; set its email domains so
          Gmail matching works.
        </div>
      ) : (
        <div className="group">
          {companies.map((c) => (
            <button className="row row-tap" key={c.id} onClick={() => setEditing(c)}>
              <Monogram name={c.name} />
              <div className="row-body">
                <div className="row-title">{c.name}</div>
                <div className="row-sub">
                  <SectorBadge sector={c.sector} />
                  {c.email_domains ? (
                    <span>{c.email_domains}</span>
                  ) : (
                    <span className="row-warn">⚠ no domains — Gmail can&apos;t match</span>
                  )}
                </div>
              </div>
              <span className="row-chevron" aria-hidden="true">
                ›
              </span>
            </button>
          ))}
        </div>
      )}

      <EditCompany
        company={editing}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          load();
        }}
      />
    </>
  );
}

function EditCompany({
  company,
  onClose,
  onSaved,
}: {
  company: Company | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState("");
  const [domains, setDomains] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setName(company?.name || "");
    setDomains(company?.email_domains || "");
  }, [company?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!company) return null;

  const dirty =
    name.trim() !== company.name || domains.trim() !== (company.email_domains || "");

  async function save() {
    if (!company || saving || !name.trim()) return;
    setSaving(true);
    try {
      await api.updateCompany(company.id, {
        name: name.trim(),
        email_domains: domains.trim(),
      });
      onSaved();
    } catch (e: any) {
      alert(
        String(e?.message || "").includes("409")
          ? "Another tracked company already uses that name."
          : "Couldn't save — please try again."
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet open onClose={onClose} title={company.name}>
      <div className="group-label">Company</div>
      <div className="field-group">
        <div className="field">
          <span className="field-label">Name</span>
          <input
            placeholder="e.g. Goldman Sachs"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="field">
          <span className="field-label">Domains</span>
          <input
            placeholder="gs.com, oracle.com"
            value={domains}
            autoFocus
            onChange={(e) => setDomains(e.target.value)}
          />
        </div>
      </div>
      <p className="sheet-sub">
        Domains are comma-separated, and subdomains count too — <code>oracle.com</code>{" "}
        also matches mail from <code>notification.oracle.com</code>. Any email from them is
        matched to this company, and a confirmation flips the application automatically.
      </p>
      <button className="btn-primary" disabled={saving || !dirty || !name.trim()} onClick={save}>
        {saving ? "Saving…" : "Save"}
      </button>
    </Sheet>
  );
}
