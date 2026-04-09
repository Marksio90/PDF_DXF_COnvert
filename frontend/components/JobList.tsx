"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { fetchJobs, fetchJob, Job } from "@/lib/api";
import JobCard from "./JobCard";

interface Props {
  newJob: Job | null;
}

const IN_PROGRESS = new Set(["queued", "analyzing", "converting"]);

export default function JobList({ newJob }: Props) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  // Ref zawsze aktualny — rozwiązuje stale closure w setInterval
  const jobsRef = useRef<Job[]>([]);

  const loadJobs = useCallback(async () => {
    try {
      const data = await fetchJobs();
      setJobs(data);
      jobsRef.current = data;
    } catch {
      // ignorujemy błędy przy pollingowych odczytach
    } finally {
      setLoading(false);
    }
  }, []);

  // Dodaj nowy job optimistycznie
  useEffect(() => {
    if (newJob) {
      setJobs((prev) => {
        const updated = [newJob, ...prev.filter((j) => j.id !== newJob.id)];
        jobsRef.current = updated;
        return updated;
      });
    }
  }, [newJob]);

  // Inicjalne załadowanie + stały polling co 2 s
  useEffect(() => {
    loadJobs();
    const interval = setInterval(async () => {
      const processing = jobsRef.current.filter((j) => IN_PROGRESS.has(j.status));
      if (processing.length === 0) return;

      const updates = await Promise.allSettled(processing.map((j) => fetchJob(j.id)));
      setJobs((prev) => {
        const map = new Map(prev.map((j) => [j.id, j]));
        updates.forEach((r) => {
          if (r.status === "fulfilled") map.set(r.value.id, r.value);
        });
        const sorted = Array.from(map.values()).sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        jobsRef.current = sorted;
        return sorted;
      });
    }, 2000);
    return () => clearInterval(interval);
  }, [loadJobs]);

  const handleDelete = (id: string) =>
    setJobs((prev) => {
      const updated = prev.filter((j) => j.id !== id);
      jobsRef.current = updated;
      return updated;
    });

  const handleUpdate = (job: Job) =>
    setJobs((prev) => {
      const updated = prev.map((j) => (j.id === job.id ? job : j));
      jobsRef.current = updated;
      return updated;
    });

  if (loading) {
    return <p className="text-gray-500 text-sm text-center py-8">Ładowanie zadań…</p>;
  }

  if (jobs.length === 0) {
    return (
      <p className="text-gray-600 text-sm text-center py-8">
        Brak zadań. Wgraj plik PDF powyżej.
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
