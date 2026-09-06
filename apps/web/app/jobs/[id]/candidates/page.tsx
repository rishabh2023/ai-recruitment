"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

/**
 * Candidate operations now live in the job workspace Pipeline tab (paginated board, in-place
 * add + CSV import, search and stage filters). This standalone page is superseded, so it
 * redirects there to keep any existing links working.
 */
export default function JobCandidatesRedirect() {
  const { id: jobId } = useParams<{ id: string }>();
  const router = useRouter();
  useEffect(() => { router.replace(`/jobs/${jobId}?tab=pipeline`); }, [jobId, router]);
  return <main className="container"><p className="muted">Opening the candidate pipeline…</p></main>;
}
