import type { Job, JobType, Sector } from "@/lib/types";

const JOB_TYPE_LABEL: Record<JobType, string> = {
  grad: "Fresh grad",
  internship: "Internship",
  ma_program: "MA / Grad prog",
  other: "Role",
};

export function SectorBadge({ sector }: { sector: Sector }) {
  return <span className={`badge ${sector}`}>{sector}</span>;
}

export function TypeBadge({ jobType }: { jobType: JobType }) {
  return <span className={`badge ${jobType}`}>{JOB_TYPE_LABEL[jobType]}</span>;
}

export function salaryText(job: Job): { text: string; na: boolean } {
  if (!job.salary_min && !job.salary_max) {
    return { text: "Salary not disclosed", na: true };
  }
  const lo = job.salary_min ? Math.round(job.salary_min).toLocaleString() : "?";
  const hi = job.salary_max ? Math.round(job.salary_max).toLocaleString() : "?";
  const per =
    job.salary_period === "year"
      ? "/yr"
      : job.salary_period === "hour"
      ? "/hr"
      : "/mo";
  return { text: `${job.salary_currency} ${lo}–${hi}${per}`, na: false };
}

export function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso).getTime();
  const days = Math.floor((Date.now() - d) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "1 day ago";
  if (days < 30) return `${days} days ago`;
  return `${Math.floor(days / 30)} mo ago`;
}
