"use client";

import { useState } from "react";
import { Job } from "@/lib/api";
import UploadZone from "@/components/UploadZone";
import JobList from "@/components/JobList";

export default function Home() {
  const [newJob, setNewJob] = useState<Job | null>(null);

  return (
    <main className="min-h-screen bg-gray-950 text-gray-100">
      <div className="max-w-3xl mx-auto px-4 py-10 space-y-10">
        {/* Header */}
        <header className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight">
            PDF <span className="text-blue-400">→</span> DXF Converter
          </h1>
          <p className="text-gray-500 text-sm">
            V001 · Local · No AI · CNC-ready output with native circles
          </p>
        </header>

        {/* Upload */}
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-3">
            New Conversion
          </h2>
          <UploadZone onJobCreated={(job) => setNewJob(job)} />
        </section>

        {/* Job list */}
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-3">
            Conversion Queue
          </h2>
          <JobList newJob={newJob} />
        </section>
      </div>
    </main>
  );
}
