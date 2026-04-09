"use client";

import { useState } from "react";
import { Job, deleteJob, reconvertJob, downloadUrl, previewUrl } from "@/lib/api";
import QualityReport from "./QualityReport";

interface Props {
  job: Job;
  onDelete: (id: string) => void;
  onUpdate: (job: Job) => void;
}

const UNIT_OPTIONS = [
  { value: "",          label: "Auto" },
  { value: "mm",        label: "mm (pt→mm)" },
  { value: "mm_direct", label: "mm natywne" },
  { value: "inch",      label: "inch" },
  { value: "cm",        label: "cm" },
];

const STATUS_COLORS: Record<string, string> = {
  queued: "text-gray-400",
  analyzing: "text-blue-400",
  converting: "text-blue-400",
  done: "text-green-400",
  error: "text-red-400",
};

const STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  analyzing: "Analyzing…",
  converting: "Converting…",
  done: "Done",
  error: "Error",
};

export default function JobCard({ job, onDelete, onUpdate }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [reconverting, setReconverting] = useState(false);
  const [forcedUnit, setForcedUnit] = useState("");
  const [deleting, setDeleting] = useState(false);

  const isProcessing = job.status === "queued" || job.status === "analyzing" || job.status === "converting";

  const handleDelete = async () => {
    setDeleting(true);
    await deleteJob(job.id);
    onDelete(job.id);
  };

  const handleReconvert = async () => {
    setReconverting(true);
    try {
      const updated = await reconvertJob(job.id, forcedUnit || undefined);
      onUpdate(updated);
    } finally {
      setReconverting(false);
    }
  };

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-100 truncate">{job.original_filename}</p>
          <p className="text-xs text-gray-500">{new Date(job.created_at).toLocaleString()}</p>
        </div>

        <span className={`text-xs font-semibold ${STATUS_COLORS[job.status] ?? "text-gray-300"}`}>
          {isProcessing && (
            <svg className="inline w-3 h-3 mr-1 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
          )}
          {STATUS_LABELS[job.status]}
        </span>

        {job.confidence_score !== null && (
          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
            job.confidence_score >= 80 ? "bg-green-800 text-green-200" :
            job.confidence_score >= 50 ? "bg-yellow-800 text-yellow-200" :
            "bg-red-800 text-red-200"
          }`}>
            {job.confidence_score}%
          </span>
        )}

        <button
          onClick={() => setExpanded(!expanded)}
          className="text-gray-400 hover:text-gray-200 transition-colors"
          title="Toggle details"
        >
          <svg className={`w-4 h-4 transition-transform ${expanded ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      {/* Actions bar */}
      <div className="flex items-center gap-2 px-4 pb-3">
        {job.status === "done" && job.has_dxf && (
          <a
            href={downloadUrl(job.id)}
            className="text-xs bg-blue-700 hover:bg-blue-600 text-white px-3 py-1.5 rounded font-medium transition-colors"
          >
            Download DXF
          </a>
        )}

        {(job.status === "done" || job.status === "error") && (
          <div className="flex items-center gap-1">
            <select
              value={forcedUnit}
              onChange={(e) => setForcedUnit(e.target.value)}
              className="bg-gray-700 border border-gray-600 text-gray-200 text-xs rounded px-2 py-1 focus:outline-none"
            >
              {UNIT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <button
              onClick={handleReconvert}
              disabled={reconverting}
              className="text-xs bg-gray-700 hover:bg-gray-600 text-gray-200 px-3 py-1 rounded transition-colors disabled:opacity-50"
            >
              {reconverting ? "…" : "Re-convert"}
            </button>
          </div>
        )}

        <button
          onClick={handleDelete}
          disabled={deleting}
          className="ml-auto text-xs text-red-400 hover:text-red-300 transition-colors disabled:opacity-50"
        >
          Delete
        </button>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="border-t border-gray-700 px-4 py-4 space-y-4">
          {/* Preview */}
          {job.has_preview && (
            <div className="relative bg-gray-900 rounded overflow-hidden max-h-64 flex items-center justify-center">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={previewUrl(job.id)}
                alt="PDF preview"
                className="max-h-64 object-contain"
              />
            </div>
          )}

          {/* Metadata */}
          <div className="grid grid-cols-2 gap-2 text-xs text-gray-400">
            {job.pdf_type && <div>PDF type: <span className="text-gray-200">{job.pdf_type}</span></div>}
            {job.page_count && <div>Pages: <span className="text-gray-200">{job.page_count}</span></div>}
            {job.unit && <div>Unit: <span className="text-gray-200">{job.unit}</span></div>}
            {job.scale_status && <div>Scale: <span className="text-gray-200">{job.scale_status}</span></div>}
          </div>

          {/* Error */}
          {job.status === "error" && job.error_message && (
            <div className="bg-red-900/30 border border-red-700/40 rounded px-3 py-2 text-red-300 text-xs font-mono whitespace-pre-wrap">
              {job.error_message}
            </div>
          )}

          {/* QA report */}
          {job.qa_report && (
            <QualityReport
              report={job.qa_report}
              scaleStatus={job.scale_status}
              scaleFactor={job.scale_factor}
              scaleSource={job.unit_source}
            />
          )}
        </div>
      )}
    </div>
  );
}
