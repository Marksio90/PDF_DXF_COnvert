const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Job {
  id: string;
  status: "queued" | "analyzing" | "converting" | "done" | "error";
  original_filename: string;
  pdf_type: string | null;
  page_count: number | null;
  scale_status: string | null;
  scale_factor: number | null;
  unit: string | null;
  unit_source: string | null;
  confidence_score: number | null;
  qa_report: QAReport | null;
  error_message: string | null;
  has_preview: boolean;
  has_dxf: boolean;
  created_at: string;
  completed_at: string | null;
}

export interface QAReport {
  confidence_score: number;
  pdf_type: string;
  page_count: number;
  scale_status: string;
  scale_unit: string;
  scale_notes: string[];
  geometry_counts: Record<string, number>;
  warnings: string[];
}

export async function uploadPDF(file: File, forcedUnit?: string): Promise<Job> {
  const form = new FormData();
  form.append("file", file);
  if (forcedUnit) form.append("forced_unit", forcedUnit);

  const res = await fetch(`${API_BASE}/api/jobs`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed (${res.status})`);
  }
  return res.json();
}

export async function fetchJobs(): Promise<Job[]> {
  const res = await fetch(`${API_BASE}/api/jobs`);
  if (!res.ok) throw new Error("Failed to fetch jobs");
  return res.json();
}

export async function fetchJob(id: string): Promise<Job> {
  const res = await fetch(`${API_BASE}/api/jobs/${id}`);
  if (!res.ok) throw new Error("Job not found");
  return res.json();
}

export async function deleteJob(id: string): Promise<void> {
  await fetch(`${API_BASE}/api/jobs/${id}`, { method: "DELETE" });
}

export async function reconvertJob(id: string, forcedUnit?: string): Promise<Job> {
  const url = new URL(`${API_BASE}/api/jobs/${id}/reconvert`);
  if (forcedUnit) url.searchParams.set("forced_unit", forcedUnit);
  const res = await fetch(url.toString(), { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Re-convert failed (${res.status})`);
  }
  return res.json();
}

export function previewUrl(id: string): string {
  return `${API_BASE}/api/jobs/${id}/preview`;
}

export function downloadUrl(id: string): string {
  return `${API_BASE}/api/jobs/${id}/download`;
}
