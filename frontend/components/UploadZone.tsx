"use client";

import { useState, useRef, DragEvent, ChangeEvent } from "react";
import { uploadPDF, Job } from "@/lib/api";

interface Props {
  onJobCreated: (job: Job) => void;
}

const UNIT_OPTIONS = [
  { value: "",          label: "Auto (pt→mm, standard)" },
  { value: "mm_direct", label: "mm natywne — gdy DXF ~2.83× za mały" },
];

export default function UploadZone({ onJobCreated }: Props) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [forcedUnit, setForcedUnit] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are accepted.");
      return;
    }
    setError(null);
    setUploading(true);
    try {
      const job = await uploadPDF(file, forcedUnit || undefined);
      onJobCreated(job);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = "";
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-gray-300">Unit override:</label>
        <select
          value={forcedUnit}
          onChange={(e) => setForcedUnit(e.target.value)}
          className="bg-gray-800 border border-gray-600 text-gray-200 text-sm rounded px-3 py-1.5 focus:outline-none focus:border-blue-500"
        >
          {UNIT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      <div
        className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${
          dragging
            ? "border-blue-400 bg-blue-900/20"
            : "border-gray-600 hover:border-gray-400 bg-gray-900/40"
        } ${uploading ? "opacity-60 pointer-events-none" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={onChange}
        />
        <div className="flex flex-col items-center gap-3 pointer-events-none">
          <svg className="w-12 h-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
          {uploading ? (
            <p className="text-gray-300 text-sm">Uploading…</p>
          ) : (
            <>
              <p className="text-gray-200 font-medium">Drop PDF here or click to browse</p>
              <p className="text-gray-500 text-xs">Max {50} MB · Vector/CAD PDFs only</p>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-700 text-red-300 text-sm rounded px-4 py-2">
          {error}
        </div>
      )}
    </div>
  );
}
