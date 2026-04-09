"use client";

import { useEffect, useState, useCallback } from "react";
import { fetchJobs, fetchJob, Job } from "@/lib/api";
import JobCard from "./JobCard";

interface Props {
  newJob: Job | null;
}

export default function JobList({ newJob }: Props) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  const loadJobs = useCallback(async () => {
    try {
      const data = await fetchJobs();
      setJobs(data);
    } catch {
      // silently fail on poll
    } finally {
      setLoading(false);
    }
  }, []);

  // Add new job optimistically
  useEffect(() => {
    if (newJob) {
      setJobs((prev) => [newJob, ...prev.filter((j) => j.id !== newJob.id)]);
    }
  }, [newJob]);

  // Poll for status updates of in-progress jobs
  useEffect(() => {
    loadJobs();
    const interval = setInterval(async () => {
      const processing = jobs.filter(
        (j) => j.status === "queued" || j.status === "analyzing" || j.status === "converting"
      );
      if (processing.length === 0) return;

      const updates = await Promise.allSettled(processing.map((j) => fetchJob(j.id)));
      setJobs((prev) => {
        const map = new Map(prev.map((j) => [j.id, j]));
        updates.forEach((r) => {
          if (r.status === "fulfilled") map.set(r.value.id, r.value);
        });
        return Array.from(map.values()).sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
      });
    }, 2000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobs.length]);

  const handleDelete = (id: string) => setJobs((prev) => prev.filter((j) => j.id !== id));
  const handleUpdate = (job: Job) =>
    setJobs((prev) => prev.map((j) => (j.id === job.id ? job : j)));

  if (loading) {
    return <p className="text-gray-500 text-sm text-center py-8">Loading jobs…</p>;
  }

  if (jobs.length === 0) {
    return (
      <p className="text-gray-600 text-sm text-center py-8">
        No conversion jobs yet. Upload a PDF above.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {jobs.map((job) => (
        <JobCard
          key={job.id}
          job={job}
          onDelete={handleDelete}
          onUpdate={handleUpdate}
        />
      ))}
    </div>
  );
}
