"use client";

import { useEffect, useState } from "react";
import { api, type JobFilters } from "@/lib/api";
import type { Job } from "@/lib/types";
import { SectorBadge, TypeBadge, salaryText, timeAgo } from "./ui";

export default function JobsBoard() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [scraping, setScraping] = useState(false);
  const [filters, setFilters] = useState<JobFilters>({});
  const [q, setQ] = useState("");

  async function load(f: JobFilters) {
    setLoading(true);
    try {
      setJobs(await api.listJobs(f));
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(filters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

  async function track(job: Job) {
    try {
      await api.trackJob(job.id, "applied");
      load(filters);
    } catch (e) {
      alert("Could not track: " + (e as Error).message);
    }
  }

  async function scrape() {
    setScraping(true);
    try {
      await api.triggerScrape();
      await load(filters);
    } finally {
      setScraping(false);
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Jobs</h1>
          <p className="page-sub">
            Fresh-grad roles, internships & MA programmes in SG tech & finance
          </p>
        </div>
        <button className="btn ghost" onClick={scrape} disabled={scraping}>
          {scraping ? "Scraping…" : "↻ Refresh sources"}
        </button>
      </div>

      <div className="toolbar">
        <input
          placeholder="Search title or company…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) =>
            e.key === "Enter" && setFilters({ ...filters, q: q || undefined })
          }
          style={{ minWidth: 240 }}
        />
        <select
          value={filters.sector || ""}
          onChange={(e) =>
            setFilters({ ...filters, sector: e.target.value || undefined })
          }
        >
          <option value="">All sectors</option>
          <option value="tech">Tech</option>
          <option value="finance">Finance</option>
        </select>
        <select
          value={filters.job_type || ""}
          onChange={(e) =>
            setFilters({ ...filters, job_type: e.target.value || undefined })
          }
        >
          <option value="">All types</option>
          <option value="grad">Fresh grad</option>
          <option value="internship">Internship</option>
          <option value="ma_program">MA / Grad programme</option>
        </select>
        <select
          value={filters.min_salary || ""}
          onChange={(e) =>
            setFilters({
              ...filters,
              min_salary: e.target.value ? Number(e.target.value) : undefined,
            })
          }
        >
          <option value="">Any salary</option>
          <option value="3000">≥ S$3k/mo</option>
          <option value="4000">≥ S$4k/mo</option>
          <option value="5000">≥ S$5k/mo</option>
        </select>
        <span className="count">{jobs.length} roles</span>
      </div>

      {loading ? (
        <div className="empty">Loading…</div>
      ) : jobs.length === 0 ? (
        <div className="empty">
          No jobs yet. Hit “Refresh sources” to pull the latest from MyCareersFuture
          and company boards.
        </div>
      ) : (
        <div className="grid">
          {jobs.map((job) => {
            const sal = salaryText(job);
            return (
              <div className="card" key={job.id}>
                <div className="card-row">
                  <SectorBadge sector={job.sector} />
                  <TypeBadge jobType={job.job_type} />
                </div>
                <div className="card-title">{job.title}</div>
                <div className="card-company">{job.company_name}</div>
                <div className={`salary ${sal.na ? "na" : ""}`}>{sal.text}</div>
                <div className="meta">
                  {job.location ? `${job.location} · ` : ""}
                  {job.posted_at ? timeAgo(job.posted_at) : ""}
                  {job.source.startsWith("company:") ? " · company site" : ""}
                </div>
                <div className="card-foot">
                  <a
                    className="btn sm"
                    href={job.apply_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Apply ↗
                  </a>
                  {job.application_id ? (
                    <span className="badge status">
                      Tracking: {job.application_status}
                    </span>
                  ) : (
                    <button className="btn sm ghost" onClick={() => track(job)}>
                      + Track
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
