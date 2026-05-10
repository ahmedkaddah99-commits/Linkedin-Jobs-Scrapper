import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { formatDateTime, labelize, statusTone } from "../lib/formatters";

const ACTIVE_RUN_STATUSES = ["planned", "queued", "running", "cancel_requested"];

function SummaryCard({ description, label, value }) {
  return (
    <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">
        {label}
      </div>
      <div className="mt-3 font-headline text-3xl font-bold text-on-surface">{value}</div>
      <div className="mt-1 text-sm text-on-surface-variant">{description}</div>
    </div>
  );
}

function ReviewSection({ children, count, defaultOpen = true, title, tone = "primary" }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest">
      <button
        className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left"
        onClick={() => setOpen((currentValue) => !currentValue)}
        type="button"
      >
        <div className="flex items-center gap-3">
          <span
            className={[
              "rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide",
              tone === "warning" ? "bg-error/10 text-error" : "bg-primary/10 text-primary",
            ].join(" ")}
          >
            {count}
          </span>
          <span className="text-sm font-semibold text-on-surface">{title}</span>
        </div>
        <span className="material-symbols-outlined text-on-surface-variant">
          {open ? "expand_less" : "expand_more"}
        </span>
      </button>
      {open ? <div className="space-y-3 border-t border-outline-variant/10 px-5 py-5">{children}</div> : null}
    </section>
  );
}

function IncludedJobRow({ job }) {
  return (
    <article className="rounded-2xl border border-outline-variant/15 bg-surface p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-headline text-lg font-bold text-on-surface">
              {job.title || "Untitled role"}
            </h3>
            {job.document_count ? (
              <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
                {job.document_count} doc{job.document_count === 1 ? "" : "s"}
              </span>
            ) : null}
            {job.tracker_status ? (
              <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
                {labelize(job.application_status || job.tracker_status)}
              </span>
            ) : null}
          </div>
          <p className="text-sm text-on-surface-variant">
            {[job.company, job.location].filter(Boolean).join(" | ") || "No company details saved yet."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-on-surface-variant">
          {job.source_label ? (
            <span className="rounded-full bg-surface-container-low px-2.5 py-1 font-semibold text-on-surface">
              {labelize(job.source_label)}
            </span>
          ) : null}
          {job.priority_rank ? (
            <span className="rounded-full bg-surface-container-low px-2.5 py-1 font-semibold text-on-surface">
              Rank {job.priority_rank}
            </span>
          ) : null}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-3">
        {job.apply_link ? (
          <a
            className="rounded-full bg-surface-container-low px-3 py-1.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            href={job.apply_link}
            rel="noreferrer"
            target="_blank"
          >
            Open Job
          </a>
        ) : null}
        {job.tracker_status ? (
          <Link
            className="rounded-full bg-primary/10 px-3 py-1.5 text-sm font-medium text-primary transition-colors hover:bg-primary/20"
            to="/tracker"
          >
            Open Tracker
          </Link>
        ) : null}
      </div>
    </article>
  );
}

function ExcludedJobRow({ job, onGenerate, pending }) {
  const hasDocumentRun = Boolean(job.create_documents_run_id);
  const childRunActive = ACTIVE_RUN_STATUSES.includes(String(job.create_documents_run_status || "").trim());

  return (
    <article className="rounded-2xl border border-outline-variant/15 bg-surface p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-headline text-lg font-bold text-on-surface">
              {job.title || "Untitled role"}
            </h3>
            <span className="rounded-full bg-error/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-error">
              {job.reason_label || "Not selected"}
            </span>
            {hasDocumentRun ? (
              <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
                {childRunActive ? "Document Run Active" : "Document Run Created"}
              </span>
            ) : null}
          </div>
          <p className="text-sm text-on-surface-variant">{job.company || "Unknown company"}</p>
          <p className="text-sm leading-7 text-on-surface-variant">
            {job.reason_summary || "This job was not selected for document generation."}
          </p>
        </div>
        <div className="text-sm text-on-surface-variant">
          {job.recorded_at ? `Updated ${formatDateTime(job.recorded_at)}` : "Reviewed in this run"}
        </div>
      </div>

      {job.details?.length ? (
        <div className="mt-4 rounded-2xl bg-surface-container-low p-4 text-sm text-on-surface-variant">
          <div className="font-semibold text-on-surface">Reason details</div>
          <div className="mt-2 space-y-1">
            {job.details.map((detail) => (
              <div key={`${job.job_id}-${detail}`}>{detail}</div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-5 flex flex-wrap gap-3">
        {job.apply_link ? (
          <a
            className="rounded-full bg-surface-container-low px-3 py-1.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            href={job.apply_link}
            rel="noreferrer"
            target="_blank"
          >
            Open Job
          </a>
        ) : null}
        {job.workspace_editor_url ? (
          <Link
            className="rounded-full bg-surface-container-low px-3 py-1.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            to={job.workspace_editor_url}
          >
            Adjust Matching
          </Link>
        ) : null}
        {hasDocumentRun ? (
          <Link
            className="rounded-full bg-primary/10 px-3 py-1.5 text-sm font-medium text-primary transition-colors hover:bg-primary/20"
            to={job.create_documents_run_url || `/runs/${job.create_documents_run_id}`}
          >
            {childRunActive ? "Open Document Run" : "View Document Run"}
          </Link>
        ) : (
          <button
            className="rounded-full bg-gradient-to-br from-primary to-primary-container px-4 py-1.5 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!job.can_generate_documents || pending}
            onClick={() => onGenerate(job)}
            type="button"
          >
            {pending ? "Creating..." : job.can_generate_documents ? "Create Documents" : "Unavailable"}
          </button>
        )}
      </div>
    </article>
  );
}

export default function RunDetailPage() {
  const { runId } = useParams();
  const { request } = useSession();
  const [actionState, setActionState] = useState({
    pendingJobId: "",
    message: "",
    error: "",
  });

  const { data, loading, error, refresh } = useApiResource(
    () => request(`/runs/${runId}/customer-view`),
    [request, runId],
  );

  const run = data?.run || null;
  const summary = data?.summary || {};
  const tracker = data?.tracker || {};
  const review = data?.review || { included_jobs: [], excluded_jobs: [] };
  const hasActiveRun = ACTIVE_RUN_STATUSES.includes(String(run?.status || "").trim());
  const hasActiveChildRuns = (review.excluded_jobs || []).some((job) =>
    ACTIVE_RUN_STATUSES.includes(String(job.create_documents_run_status || "").trim()),
  );

  useEffect(() => {
    if (!hasActiveRun && !hasActiveChildRuns) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      refresh().catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(intervalId);
  }, [hasActiveChildRuns, hasActiveRun, refresh]);

  async function createDocumentsForExcludedJob(job) {
    setActionState({ pendingJobId: job.job_id, message: "", error: "" });
    try {
      const result = await request(`/runs/${runId}/excluded-jobs/${encodeURIComponent(job.job_id)}/generate-documents`, {
        method: "POST",
        body: {
          source_stage: job.source_stage,
          reason_summary: job.reason_summary,
          execution_mode: "queued",
          notes: "Generate documents from the run review.",
        },
      });
      setActionState({
        pendingJobId: "",
        message: `Document run ${result.run?.id || ""} created for ${job.title || "the selected job"}.`,
        error: "",
      });
      refresh().catch(() => undefined);
    } catch (actionError) {
      setActionState({
        pendingJobId: "",
        message: "",
        error: actionError.message || "Unable to create documents for this excluded job.",
      });
    }
  }

  return (
    <div className="space-y-8">
      <header className="relative overflow-hidden rounded-[2rem] border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
        <div className="pointer-events-none absolute inset-y-0 right-0 w-1/2 bg-[radial-gradient(circle_at_top_right,_rgba(0,133,122,0.18),_transparent_60%)]" />
        <div className="relative z-10 flex flex-col gap-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-3">
                <StatusBadge tone={statusTone(run?.status)}>{labelize(run?.status || "pending")}</StatusBadge>
              </div>
              <div>
                <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
                  {run?.workspace_name || "Run Review"}
                </h1>
                <p className="mt-2 max-w-3xl text-sm leading-7 text-on-surface-variant">
                  Review the included and excluded jobs for this run. You can create documents for
                  excluded jobs when needed, and completed document jobs move to Tracker automatically.
                </p>
              </div>
            </div>
            <button
              className="rounded-full bg-surface px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
              onClick={() => refresh().catch(() => undefined)}
              type="button"
            >
              Refresh
            </button>
          </div>

          <div className="grid gap-3 text-sm text-on-surface-variant md:grid-cols-3">
            <div>
              <span className="font-semibold text-on-surface">Created:</span> {formatDateTime(run?.created_at)}
            </div>
            <div>
              <span className="font-semibold text-on-surface">Updated:</span> {formatDateTime(run?.updated_at)}
            </div>
            <div>
              <span className="font-semibold text-on-surface">Finished:</span>{" "}
              {run?.finished_at ? formatDateTime(run.finished_at) : "Still in progress"}
            </div>
          </div>
        </div>
      </header>

      {actionState.message || actionState.error ? (
        <section
          className={[
            "rounded-2xl border px-5 py-4 text-sm",
            actionState.error
              ? "border-error/20 bg-error/5 text-error"
              : "border-primary/20 bg-primary/5 text-primary",
          ].join(" ")}
        >
          {actionState.error || actionState.message}
        </section>
      ) : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          description="Jobs currently selected in this run."
          label="Included Jobs"
          value={summary.included_job_count ?? review.included_count ?? 0}
        />
        <SummaryCard
          description="Jobs reviewed out of the run for now."
          label="Excluded Jobs"
          value={summary.excluded_job_count ?? review.excluded_count ?? 0}
        />
        <SummaryCard
          description="Excluded jobs that can still have documents created."
          label="Ready To Create"
          value={summary.excluded_ready_for_documents_count ?? 0}
        />
        <SummaryCard
          description="Jobs from this run already active in Tracker."
          label="In Tracker"
          value={summary.tracker_job_count ?? 0}
        />
      </section>

      {loading ? (
        <section className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest px-6 py-5 text-on-surface-variant shadow-soft">
          Loading run review...
        </section>
      ) : error ? (
        <section className="rounded-[1.75rem] border border-error/20 bg-error/5 px-6 py-5 text-error shadow-soft">
          {error}
        </section>
      ) : (
        <section className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h2 className="font-headline text-2xl font-bold text-on-surface">Run Review</h2>
              <p className="mt-1 max-w-3xl text-sm leading-7 text-on-surface-variant">
                Use this view to decide which roles stay out and which excluded roles should still get
                documents. Once documents are ready, those jobs appear in Tracker.
              </p>
            </div>
            <Link
              className="rounded-full bg-primary/10 px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-primary/20"
              to={tracker.href || "/tracker"}
            >
              Open Tracker
            </Link>
          </div>

          <div className="mt-6 space-y-4">
            <ReviewSection count={review.included_jobs?.length || 0} title="Included Jobs">
              {review.included_jobs?.length ? (
                review.included_jobs.map((job) => <IncludedJobRow job={job} key={job.job_id} />)
              ) : (
                <div className="rounded-2xl border border-outline-variant/10 bg-surface p-4 text-sm text-on-surface-variant">
                  No included jobs are available in this run yet.
                </div>
              )}
            </ReviewSection>

            <ReviewSection
              count={review.excluded_jobs?.length || 0}
              defaultOpen={Boolean(review.excluded_jobs?.length)}
              title="Excluded Jobs"
              tone="warning"
            >
              {review.excluded_jobs?.length ? (
                review.excluded_jobs.map((job) => (
                  <ExcludedJobRow
                    job={job}
                    key={job.job_id}
                    onGenerate={createDocumentsForExcludedJob}
                    pending={actionState.pendingJobId === job.job_id}
                  />
                ))
              ) : (
                <div className="rounded-2xl border border-outline-variant/10 bg-surface p-4 text-sm text-on-surface-variant">
                  No excluded jobs were saved for this run.
                </div>
              )}
            </ReviewSection>
          </div>
        </section>
      )}
    </div>
  );
}
