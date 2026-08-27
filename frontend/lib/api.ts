import type {
  Application,
  AppStatus,
  Company,
  EmailEvent,
  LinkPreview,
  Sector,
} from "./types";

// Undefined (dev, no env set) -> localhost backend. Explicitly empty (production build,
// see .env.production) -> "" so requests are same-origin relative, since the backend
// serves this bundle. A real URL is used verbatim.
const RAW = process.env.NEXT_PUBLIC_API_BASE;
const BASE = (RAW === undefined ? "http://localhost:8100" : RAW).replace(/\/$/, "");

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
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export interface NewApplication {
  url: string;
  title: string;
  company: string;
  email_domains?: string;
  sector?: Sector;
  status?: AppStatus;
  notes?: string;
}

/** Partial update — omitted fields are left untouched server-side. Covers the joined
 *  Job/Company fields the detail sheet edits, so one save is one request. */
export interface ApplicationPatch {
  status?: AppStatus;
  notes?: string;
  applied_at?: string | null;
  title?: string;
  company?: string;
  apply_url?: string;
  sector?: Sector;
  email_domains?: string;
}

export const api = {
  // Best-effort auto-detect of role/company from a pasted link.
  previewLink(url: string): Promise<LinkPreview> {
    return req<LinkPreview>("/applications/preview", {
      method: "POST",
      body: JSON.stringify({ url }),
    });
  },

  addApplication(body: NewApplication): Promise<Application> {
    return req<Application>("/applications", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  deleteApplication(id: number): Promise<void> {
    return req<void>(`/applications/${id}`, { method: "DELETE" });
  },

  listApplications(): Promise<Application[]> {
    return req<Application[]>("/applications");
  },

  updateApplication(id: number, patch: ApplicationPatch): Promise<Application> {
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

  // Partial patch: only the keys sent are changed.
  updateCompany(id: number, patch: Partial<Company>): Promise<Company> {
    return req<Company>(`/companies/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },

  // 409 if applications still reference the company.
  deleteCompany(id: number): Promise<void> {
    return req<void>(`/companies/${id}`, { method: "DELETE" });
  },

  gmailStatus(): Promise<{ connected: boolean }> {
    return req<{ connected: boolean }>("/gmail/status");
  },
};
