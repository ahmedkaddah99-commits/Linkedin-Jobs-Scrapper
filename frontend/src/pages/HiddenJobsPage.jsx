import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { formatJobDate, toPersonalizedJobView } from "../lib/personalizedJobsApi";

function Icon({ children, className = "" }) {
  return <span className={["material-symbols-outlined", className].join(" ")}>{children}</span>;
}

function HiddenJobRow({ job, onReport, onRestore, restoring }) {
  return <article className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-4 shadow-soft"><div className="flex items-start gap-3"><div className="rounded-lg bg-primary px-3 py-2 text-sm font-bold text-white">{job.company.slice(0, 1)}</div><div className="min-w-0 flex-1"><Link className="font-semibold text-on-surface hover:text-primary" to={`/jobs/${encodeURIComponent(job.id)}`}>{job.title}</Link><p className="mt-1 text-sm text-on-surface-variant">{job.company} · {job.location} · {formatJobDate(job.postedAt)}</p><p className="mt-2 text-xs text-on-surface-variant">Hidden because a saved filter could not verify a required field or because you hid this job.</p></div></div><div className="mt-4 flex flex-wrap gap-2"><button className="rounded-full bg-surface-container px-3 py-1.5 text-xs font-semibold text-on-surface-variant hover:bg-surface-container-high" onClick={() => onReport(job)} type="button">Report incorrect</button><button className="rounded-full bg-primary/10 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/20" disabled={restoring === job.id} onClick={() => onRestore(job)} type="button">{restoring === job.id ? "Restoring…" : "Restore to jobs"}</button></div></article>;
}

export default function HiddenJobsPage() {
  const { isConnected, request } = useSession();
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [restoring, setRestoring] = useState("");

  function loadHiddenJobs() {
    setLoading(true);
    setError("");
    return request("/personalized-jobs/hidden?limit=100")
      .then((nextPayload) => setPayload(nextPayload || { jobs: [], total: 0 }))
      .catch((requestError) => setError(requestError?.message || "Unable to load hidden jobs."))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (isConnected) void loadHiddenJobs();
  }, [isConnected]);

  async function restoreJob(job) {
    setRestoring(job.id);
    try {
      await request(`/personalized-jobs/${encodeURIComponent(job.id)}/restore`, { method: "POST", body: {} });
      setFeedback(`${job.title} is back in your jobs.`);
      await loadHiddenJobs();
    } catch (requestError) {
      setFeedback(requestError?.message || "Unable to restore this job.");
    } finally {
      setRestoring("");
    }
  }

  async function reportJob(job) {
    try {
      await request(`/personalized-jobs/${encodeURIComponent(job.id)}/report`, { method: "POST", body: { reason_code: "incorrect_filtering" } });
      setFeedback(`Your report about ${job.title} was recorded.`);
    } catch (requestError) {
      setFeedback(requestError?.message || "Unable to send this report.");
    }
  }

  const jobs = Array.isArray(payload?.jobs) ? payload.jobs.map(toPersonalizedJobView) : [];
  return <div className="mx-auto w-full max-w-5xl px-4 py-8 md:px-8"><header className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">Eligibility review</p><h1 className="mt-2 font-headline text-3xl font-bold tracking-tight text-on-surface">Hidden jobs</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-on-surface-variant">Review jobs removed from your feed. Runr keeps their source-backed details and lets you restore or report them.</p></div><Link className="inline-flex items-center gap-2 rounded-full border border-outline-variant/20 bg-surface-container-lowest px-4 py-2 text-sm font-semibold text-on-surface hover:bg-surface-container" to="/jobs"><Icon className="text-[17px]">arrow_back</Icon>Back to jobs</Link></header>
    <section className="mt-8 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft"><div className="flex items-center gap-3"><span className="rounded-full bg-primary/10 p-3 text-primary"><Icon>visibility_off</Icon></span><div><p className="text-xs font-semibold uppercase tracking-[0.15em] text-on-surface-variant">Shared catalog</p><h2 className="mt-1 text-lg font-semibold text-on-surface">{loading ? "Loading hidden jobs" : `${payload?.total ?? jobs.length} hidden jobs`}</h2></div></div></section>
    {feedback ? <div className="mt-4 rounded-xl bg-primary/10 px-4 py-3 text-sm text-primary" role="status">{feedback}</div> : null}
    {error ? <div className="mt-4 rounded-xl bg-error/10 px-4 py-3 text-sm text-error" role="alert">{error}</div> : null}
    <section className="mt-6 space-y-3">{loading ? <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-8 text-center text-sm text-on-surface-variant"><Icon className="animate-spin">progress_activity</Icon><p className="mt-2">Loading hidden jobs…</p></div> : jobs.length ? jobs.map((job) => <HiddenJobRow job={job} key={job.id} onReport={reportJob} onRestore={restoreJob} restoring={restoring} />) : <div className="rounded-2xl border border-dashed border-outline-variant/30 bg-surface-container-lowest p-10 text-center"><Icon className="text-3xl text-primary">check_circle</Icon><h2 className="mt-3 font-semibold text-on-surface">Nothing is hidden</h2><p className="mt-1 text-sm text-on-surface-variant">Jobs you hide later will appear here.</p></div>}</section>
  </div>;
}
