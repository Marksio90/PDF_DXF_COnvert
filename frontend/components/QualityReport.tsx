"use client";

import { QAReport } from "@/lib/api";

interface Props {
  report: QAReport;
  scaleStatus: string | null;
  scaleFactor: number | null;
  scaleSource: string | null;
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

const STATUS_LABELS: Record<string, string> = {
  verified:   "skala OK",
  assumed:    "skala z tekstu PDF",
  unverified: "skala nieznana",
};

const STATUS_COLORS: Record<string, string> = {
  verified:   "bg-green-800 text-green-200",
  assumed:    "bg-yellow-800 text-yellow-200",
  unverified: "bg-red-800 text-red-200",
};

const SOURCE_LABELS: Record<string, string> = {
  forced:    "wymuszona",
  dimension: "z wymiarów",
  text:      "z tekstu",
  userunit:  "z metadanych PDF",
  default:   "domyślna",
};

export default function QualityReport({ report, scaleStatus, scaleFactor, scaleSource }: Props) {
  return (
    <div className="mt-4 space-y-4">
      {/* Score + scale status */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-gray-400 text-sm">Pewność:</span>
        <ScoreBadge score={report.confidence_score} />
        {scaleStatus && (
          <span className={`text-xs px-2 py-0.5 rounded ${STATUS_COLORS[scaleStatus] ?? "bg-gray-700 text-gray-300"}`}>
            {STATUS_LABELS[scaleStatus] ?? scaleStatus}
          </span>
        )}
      </div>

      {/* Scale factor info */}
      {scaleFactor !== null && (
        <div className="bg-gray-900 rounded px-3 py-2 text-xs font-mono space-y-0.5">
          <div className="text-gray-400">
            scale_factor = <span className="text-blue-300">{scaleFactor.toFixed(6)}</span>
            {Math.abs(scaleFactor - 25.4 / 72) < 0.0001 && (
              <span className="text-gray-500 ml-2">(= pt→mm)</span>
            )}
            {Math.abs(scaleFactor - 1.0) < 0.001 && (
              <span className="text-gray-500 ml-2">(= 1:1 mm natywne)</span>
            )}
          </div>
          {scaleSource && (
            <div className="text-gray-500">
              źródło: <span className="text-gray-300">{SOURCE_LABELS[scaleSource] ?? scaleSource}</span>
            </div>
          )}
          {scaleStatus !== "verified" && (
            <div className="text-gray-500 text-[10px] pt-1">
              Jeśli wymiary w DXF są ~2.83× za małe → spróbuj <strong>Re-convert</strong> z opcją <em>mm natywne</em>.
            </div>
          )}
        </div>
      )}

      {/* Warnings */}
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

      {/* Geometry counts */}
      <div className="grid grid-cols-2 gap-2 text-xs text-gray-400">
        <div>Typ PDF: <span className="text-gray-200">{report.pdf_type}</span></div>
        <div>Jednostka: <span className="text-gray-200">{report.scale_unit}</span></div>
        <div>Okręgi: <span className="text-gray-200">{report.geometry_counts.circles ?? 0}</span></div>
        <div>Polilinie: <span className="text-gray-200">{report.geometry_counts.polylines ?? 0}</span></div>
      </div>

      {/* Scale detection notes */}
      {report.scale_notes.length > 0 && (
        <div className="text-xs text-gray-500 space-y-1 border-t border-gray-700 pt-2">
          {report.scale_notes.map((n, i) => <p key={i}>{n}</p>)}
        </div>
      )}
    </div>
  );
}
