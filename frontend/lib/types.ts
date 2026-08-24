export type Sector = "tech" | "finance" | "other";
export type JobType = "grad" | "internship" | "ma_program" | "other";
export type AppStatus =
  | "interested"
  | "applied"
  | "confirmed"
  | "interviewing"
  | "offer"
  | "rejected"
  | "withdrawn";

export interface Job {
  id: number;
  source: string;
  title: string;
  company_name: string;
  sector: Sector;
  category: string | null;
  job_type: JobType;
  seniority: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string;
  salary_period: string;
  location: string | null;
  apply_url: string;
  posted_at: string | null;
  closing_at: string | null;
  is_active: boolean;
  application_id: number | null;
  application_status: AppStatus | null;
}

export interface Application {
  id: number;
  job_id: number;
  status: AppStatus;
  applied_at: string | null;
  last_stage_change_at: string;
  notes: string | null;
  job: Job | null;
}

export interface EmailEvent {
  id: number;
  from_addr: string;
  subject: string;
  snippet: string;
  received_at: string | null;
  matched_company_id: number | null;
  matched_application_id: number | null;
  classified_stage: AppStatus | null;
  is_read: boolean;
}

export interface Company {
  id: number;
  name: string;
  slug: string;
  email_domains: string;
  career_page_url: string | null;
  sector: Sector;
  notes: string | null;
}
