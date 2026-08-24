import type {
  Application,
  AppStatus,
  Company,
  EmailEvent,
  Job,
} from "./types";

const BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8100";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export interface JobFilters {
  sector?: string;
  job_type?: string;
  q?: string;
  min_salary?: number;
}

export const api = {
  listJobs(f: JobFilters = {}): Promise<Job[]> {
    const p = new URLSearchParams();
    if (f.sector) p.set("sector", f.sector);
    if (f.job_type) p.set("job_type", f.job_type);
    if (f.q) p.set("q", f.q);
    if (f.min_salary) p.set("min_salary", String(f.min_salary));
    p.set("limit", "500");
    return req<Job[]>(`/jobs?${p.toString()}`);
  },

  trackJob(job_id: number, status: AppStatus = "applied"): Promise<Application> {
    return req<Application>("/applications", {
      method: "POST",
      body: JSON.stringify({ job_id, status }),
    });
  },

  listApplications(): Promise<Application[]> {
    return req<Application[]>("/applications");
  },

  updateApplication(
    id: number,
    patch: { status?: AppStatus; notes?: string }
  ): Promise<Application> {
    return req<Application>(`/applications/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },

  listEmailEvents(): Promise<EmailEvent[]> {
    return req<EmailEvent[]>("/email-events");
  },

  classifyEmail(id: number, stage: AppStatus): Promise<EmailEvent> {
    return req<EmailEvent>(`/email-events/${id}/classify`, {
      method: "POST",
      body: JSON.stringify({ stage }),
    });
  },

  listCompanies(): Promise<Company[]> {
    return req<Company[]>("/companies");
  },

  createCompany(body: Partial<Company>): Promise<Company> {
    return req<Company>("/companies", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  triggerScrape(): Promise<Record<string, number>> {
    return req("/admin/scrape", { method: "POST" });
  },
};
