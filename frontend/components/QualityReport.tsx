"use client";

import { QAReport } from "@/lib/api";

interface Props {
  report: QAReport;
  scaleStatus: string | null;
}

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 80 ? "bg-green-700 text-green-100" :
    score >= 50 ? "bg-yellow-700 text-yellow-100" :
    "bg-red-700 text-red-100";
  return (
    <span className={`inline-block px-3 py-1 rounded-full text-sm font-bold ${color}`}>
      {score}/100
    </span>
  );
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    verified: "bg-green-800 text-green-200",
    assumed: "bg-yellow-800 text-yellow-200",
    unverified: "bg-red-800 text-red-200",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${map[status] ?? "bg-gray-700 text-gray-300"}`}>
      {status}
    </span>
  );
}

export default function QualityReport({ report, scaleStatus }: Props) {
  return (
    <div className="mt-4 space-y-4">
      <div className="flex items-center gap-3">
        <span className="text-gray-400 text-sm">Confidence score:</span>
        <ScoreBadge score={report.confidence_score} />
        {scaleStatus && <StatusPill status={scaleStatus} />}
      </div>

      {report.warnings.length > 0 && (
        <div className="space-y-2">
          {report.warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-2 bg-yellow-900/30 border border-yellow-700/40 rounded px-3 py-2 text-yellow-300 text-xs">
              <svg className="w-4 h-4 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
              </svg>
              {w}
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 text-xs text-gray-400">
        <div>PDF type: <span className="text-gray-200">{report.pdf_type}</span></div>
        <div>Unit: <span className="text-gray-200">{report.scale_unit}</span></div>
        <div>Circles: <span className="text-gray-200">{report.geometry_counts.circles ?? 0}</span></div>
        <div>Polylines: <span className="text-gray-200">{report.geometry_counts.polylines ?? 0}</span></div>
      </div>

      {report.scale_notes.length > 0 && (
        <div className="text-xs text-gray-500 space-y-1">
          {report.scale_notes.map((n, i) => <p key={i}>{n}</p>)}
        </div>
      )}
    </div>
  );
}
