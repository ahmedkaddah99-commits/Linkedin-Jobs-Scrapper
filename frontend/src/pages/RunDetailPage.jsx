import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { formatDateTime, labelize, statusTone } from "../lib/formatters";
import { buildJobWorkspaceRoute } from "../lib/peopleDiscovery";
import {
  claimRunProgressFocus,
  runProgressScrollBehavior,
} from "../lib/runProgressFocus";

const ACTIVE_RUN_STATUSES = ["planned", "queued", "running", "cancel_requested"];
const DELETABLE_RUN_STATUSES = ["planned", "queued", "completed", "failed", "cancelled"];
const CHECKLIST_STAGE_LABELS = {
  source_search: "Searching jobs",
  source_linkedin_search: "Searching job listings",
  source_company_career_sites: "Searching company career sites",
  source_academic_career_sites: "Searching academic career sites",
  source_job_boards: "Searching job boards",
  source_curated_urls: "Reading saved job postings",
  source_exact_job_links: "Reading job postings",
  merge_jobs: "Removing duplicate jobs",
  merge_source_jobs: "Removing duplicate jobs",
  merge_exact_job_links: "Removing duplicate links",
  screen_jobs: "Filtering jobs",
  prioritize_jobs: "Ranking matches",
  generate_documents: "Generating documents",
  generate_application_documents: "Generating documents",
  generate_quick_apply_documents: "Generating documents",
  classify_roles: "Grouping matching roles",
  build_reusable_profiles: "Preparing role-based documents",
  package_applications: "Saving application packages",
};
const CHECKLIST_STAGE_TYPE_LABELS = {
  "jobs.acquire.search_listings": "Searching jobs",
  "jobs.acquire.company_sites": "Searching company career sites",
  "jobs.acquire.job_boards": "Searching job boards",
  "jobs.ingest.curated_urls": "Reading job postings",
  "jobs.merge.dedupe": "Removing duplicates",
  "jobs.screen.filter": "Filtering jobs",
  "jobs.prioritize.rank": "Ranking matches",
  "jobs.classify.roles": "Grouping matching roles",
  "profiles.generate.reusable": "Preparing role-based documents",
  "applications.generate.documents": "Generating documents",
  "applications.package.export": "Saving application packages",
};
const CHECKLIST_STATUS_PRESENTATION = {
  pending: {
    icon: "check_box_outline_blank",
    label: "Pending",
    iconClassName: "text-on-surface-variant",
    rowClassName: "text-on-surface-variant",
  },
  running: {
    icon: "progress_activity",
    label: "Running",
    iconClassName: "text-primary motion-safe:animate-spin",
    rowClassName: "bg-surface-container-low text-on-surface",
  },
  done: {
    icon: "check_circle",
    label: "Done",
    iconClassName: "text-primary",
    rowClassName: "text-on-surface",
  },
  failed: {
    icon: "error",
    label: "Failed",
    iconClassName: "text-error",
    rowClassName: "bg-error/5 text-error",
  },
  stopped: {
    icon: "cancel",
    label: "Stopped",
    iconClassName: "text-error",
    rowClassName: "bg-error/5 text-error",
  },
};

function checklistStageLabel(stage) {
  return (
    CHECKLIST_STAGE_LABELS[String(stage.stage_id || "")]
    || CHECKLIST_STAGE_TYPE_LABELS[String(stage.stage_type || "")]
    || "Processing jobs"
  );
}

function checklistStageStatus(stage) {
  const recordedStatus = String(stage.status || "").trim().toLowerCase();
  if (recordedStatus === "completed") {
    return "done";
  }
  if (recordedStatus === "failed") {
    return "failed";
  }
  if (recordedStatus === "cancelled") {
    return "stopped";
  }
  if (stage.is_current) {
    return "running";
  }
  return "pending";
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

function ApplicationWarnings({ warnings = [] }) {
  const visibleWarnings = (warnings || []).filter((warning) => warning?.message || warning?.title);
  if (!visibleWarnings.length) return null;
  return (
    <div className="mt-3 space-y-2">
      {visibleWarnings.slice(0, 3).map((warning, index) => {
        const blocking = String(warning.severity || "") === "blocking";
        return (
          <div
            className={[
              "rounded-xl border px-3 py-2 text-xs leading-5",
              blocking
                ? "border-error/25 bg-error/5 text-error"
                : "border-amber-500/25 bg-amber-500/5 text-amber-700",
            ].join(" ")}
            key={`${warning.code || "warning"}-${index}`}
          >
            <div className="flex items-start gap-2">
              <span className="material-symbols-outlined mt-0.5 text-[15px]">
                {blocking ? "priority_high" : "info"}
              </span>
              <div>
                <div className="font-semibold">{warning.title || "Application requirement"}</div>
                <div>{warning.message}</div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function IncludedJobRow({ job, runId }) {
  const jobWorkspaceUrl =
    job.job_workspace_url || buildJobWorkspaceRoute({ runId, jobId: job.job_id });

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
          <ApplicationWarnings warnings={job.application_warnings} />
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
        {job.job_id ? (
          <Link
            className="rounded-full bg-surface-container-low px-3 py-1.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            to={jobWorkspaceUrl}
          >
            Relevant People
          </Link>
        ) : null}
      </div>
    </article>
  );
}

function ExcludedJobRow({ job, runId }) {
  const hasDocumentRun = Boolean(job.create_documents_run_id);
  const childRunActive = ACTIVE_RUN_STATUSES.includes(String(job.create_documents_run_status || "").trim());
  const jobWorkspaceUrl =
    job.job_workspace_url
    || buildJobWorkspaceRoute({
      runId,
      jobId: job.job_id,
      mode: "pre_generation",
      sourceStage: job.source_stage || "",
      reasonSummary: job.reason_summary || "",
    });

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
        ) : job.can_generate_documents ? (
          <Link
            className="rounded-full bg-gradient-to-br from-primary to-primary-container px-4 py-1.5 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90"
            to={jobWorkspaceUrl}
          >
            Customize &amp; Generate
          </Link>
        ) : (
          <button
            className="rounded-full bg-gradient-to-br from-primary to-primary-container px-4 py-1.5 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            disabled
            type="button"
          >
            Unavailable
          </button>
        )}
      </div>
    </article>
  );
}

function RunChecklist({ stages }) {
  const checklistStages = (stages || []).filter(
    (stage) => stage.stage_type !== "synthetic_review_stage" && stage.status !== "skipped",
  );
  if (!checklistStages.length) {
    return null;
  }

  return (
    <div>
      <ol aria-label="Run progress" className="space-y-2">
        {checklistStages.map((stage) => {
          const status = checklistStageStatus(stage);
          const presentation = CHECKLIST_STATUS_PRESENTATION[status];
          return (
            <li
              aria-current={status === "running" ? "step" : undefined}
              className={[
                "flex items-center gap-3 rounded-xl px-3 py-2.5",
                presentation.rowClassName,
              ].join(" ")}
              key={stage.stage_id}
            >
              <span
                aria-hidden="true"
                className={[
                  "material-symbols-outlined shrink-0 text-[22px]",
                  presentation.iconClassName,
                ].join(" ")}
              >
                {presentation.icon}
              </span>
              <span className="text-sm font-medium">
                <span className="sr-only">{presentation.label}: </span>
                {checklistStageLabel(stage)}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function etaLabel(eta) {
  if (!eta || eta.state !== "estimated") return "";
  const lowMinutes = Math.max(1, Math.floor(Number(eta.remaining_seconds_low || 0) / 60));
  const highMinutes = Math.max(lowMinutes, Math.ceil(Number(eta.remaining_seconds_high || 0) / 60));
  return lowMinutes === highMinutes
    ? `Estimated ${highMinutes} minute${highMinutes === 1 ? "" : "s"} remaining.`
    : `Estimated ${lowMinutes}-${highMinutes} minutes remaining.`;
}

function SourceCoverageNotice({ run, stages = [] }) {
  const stageMetrics = (stages || [])
    .filter((stage) => String(stage.stage_type || "") === "jobs.acquire.company_sites")
    .reduce(
      (accumulator, stage) => ({
        link_cap_hits: accumulator.link_cap_hits + Number(stage.metrics?.link_cap_hits || 0),
      }),
      { link_cap_hits: 0 },
    );
  const counters = run?.progress?.counters || {};
  const cappedSites = run?.capped_sites || [];
  const linkCapHits = Number(counters.link_cap_hits || stageMetrics.link_cap_hits || cappedSites.length || 0);
  if (!linkCapHits) return null;

  const cappedLabels = cappedSites
    .map((site) => String(site.url || "").trim())
    .filter(Boolean)
    .slice(0, 3);

  return (
    <section className="rounded-2xl border border-primary/15 bg-primary/5 px-5 py-4 text-sm text-on-surface">
      <div className="flex items-start gap-3">
        <span className="material-symbols-outlined mt-0.5 text-[20px] text-primary">travel_explore</span>
        <div>
          <div className="font-semibold text-on-surface">Company-site coverage</div>
          <div className="mt-1 leading-6 text-on-surface-variant">
            {`${linkCapHits} career site${linkCapHits === 1 ? "" : "s"} hit the configured job-link cap.`}
          </div>
          {cappedLabels.length ? (
            <div className="mt-2 text-xs text-on-surface-variant">
              Capped: {cappedLabels.join(" | ")}
              {cappedSites.length > cappedLabels.length ? ` +${cappedSites.length - cappedLabels.length} more` : ""}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

export default function RunDetailPage() {
  const { runId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { request } = useSession();
  const progressRef = useRef(null);
  const progressHeadingRef = useRef(null);
  const focusedRunIdsRef = useRef(new Set());
  const [actionState, setActionState] = useState({
    deletingRun: false,
    message: String(location.state?.runStartedMessage || ""),
    error: "",
  });

  const {
    data: runStatusData,
    loading: runStatusLoading,
    error: runStatusError,
    refresh: refreshRunStatus,
  } = useApiResource(
    () => request(`/runs/${runId}`, { timeoutMs: 8000 }),
    [request, runId],
    {
      cacheKey: `run-status:${runId}`,
      staleMs: 2000,
      backgroundRefresh: true,
    },
  );

  const {
    data,
    loading: reviewLoading,
    error: reviewError,
    refresh,
  } = useApiResource(
    () => request(`/runs/${runId}/customer-view`, { timeoutMs: 20000 }),
    [request, runId],
    {
      cacheKey: `run-customer-view:${runId}`,
      staleMs: 2000,
      backgroundRefresh: true,
    },
  );

  const customerRun = data?.run || null;
  const runStatus = runStatusData?.id ? runStatusData : null;
  const run = customerRun && runStatus ? {
    ...customerRun,
    status: runStatus.status || customerRun.status,
    updated_at: runStatus.updated_at || customerRun.updated_at,
    finished_at: runStatus.finished_at || customerRun.finished_at,
    current_stage_id: runStatus.current_stage_id || customerRun.current_stage_id,
    last_error: runStatus.last_error || customerRun.last_error,
    attempt_count: runStatus.attempt_count ?? customerRun.attempt_count,
    max_attempts: runStatus.max_attempts ?? customerRun.max_attempts,
  } : (customerRun || runStatus);
  const tracker = data?.tracker || {};
  const review = data?.review || { included_jobs: [], excluded_jobs: [] };
  const stages = data?.stages || [];
  const hasActiveRun = ACTIVE_RUN_STATUSES.includes(String(run?.status || "").trim());
  const hasActiveChildRuns = (review.excluded_jobs || []).some((job) =>
    ACTIVE_RUN_STATUSES.includes(String(job.create_documents_run_status || "").trim()),
  );
  const shouldPollRunStatus = !runStatus || hasActiveRun;
  const shouldPollReview = Boolean(run) && (hasActiveRun || hasActiveChildRuns);
  const detailLoading = reviewLoading && !data;
  const pageLoading = !run && (runStatusLoading || reviewLoading);
  const pageError = !run ? (runStatusError || reviewError) : "";

  const refreshRunResources = useCallback((options = {}) => {
    return Promise.allSettled([
      refreshRunStatus({ showLoading: false }),
      refresh(options),
    ]);
  }, [refresh, refreshRunStatus]);

  useEffect(() => {
    if (!shouldPollRunStatus) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      refreshRunStatus({ showLoading: false }).catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(intervalId);
  }, [refreshRunStatus, shouldPollRunStatus]);

  useEffect(() => {
    if (!shouldPollReview || reviewLoading) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      refresh({ showLoading: false }).catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(intervalId);
  }, [refresh, reviewLoading, shouldPollReview]);

  useEffect(() => {
    function refreshVisibleRun() {
      if (document.visibilityState === "visible") {
        refreshRunResources({ showLoading: false }).catch(() => undefined);
      }
    }
    window.addEventListener("focus", refreshVisibleRun);
    document.addEventListener("visibilitychange", refreshVisibleRun);
    return () => {
      window.removeEventListener("focus", refreshVisibleRun);
      document.removeEventListener("visibilitychange", refreshVisibleRun);
    };
  }, [refreshRunResources]);

  useEffect(() => {
    const resolvedRunId = String(run?.id || runId || "");
    if (
      !progressRef.current
      || !claimRunProgressFocus(focusedRunIdsRef.current, {
        hash: location.hash,
        runId: resolvedRunId,
        runStatus: run?.status,
      })
    ) {
      return;
    }
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    progressHeadingRef.current?.focus({ preventScroll: true });
    progressRef.current.scrollIntoView({
      behavior: runProgressScrollBehavior(Boolean(reducedMotion)),
      block: "start",
    });
  }, [location.hash, run?.id, run?.status, runId]);

  async function deleteRun() {
    if (!run) {
      return;
    }
    const runName = run.workspace_name || "this run";
    const confirmed = window.confirm(`Delete ${runName}? This removes the run review, jobs, reviews, and artifacts saved for it.`);
    if (!confirmed) {
      return;
    }
    setActionState((currentValue) => ({
      ...currentValue,
      deletingRun: true,
      message: "",
      error: "",
    }));
    try {
      await request(`/runs/${runId}`, { method: "DELETE" });
      navigate("/runs", {
        replace: true,
        state: {
          runActionMessage: `${runName} was deleted.`,
        },
      });
    } catch (actionError) {
      setActionState((currentValue) => ({
        ...currentValue,
        deletingRun: false,
        message: "",
        error: actionError.message || "Unable to delete this run.",
      }));
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
                {run?.is_test_run ? (
                  <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-primary">
                    Test Run
                  </span>
                ) : null}
              </div>
              <div>
                <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
                  {run?.workspace_name || "Run Review"}
                </h1>
                <p className="mt-2 max-w-3xl text-sm leading-7 text-on-surface-variant">
                  {run?.is_test_run
                    ? "Review the single selected job and every document produced by this workspace. The selected job is added to Tracker automatically."
                    : "Review the included and excluded jobs for this run. You can create documents for excluded jobs when needed, and completed document jobs move to Tracker automatically."}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-3">
              <button
                className="rounded-full bg-surface px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                onClick={() => refreshRunResources().catch(() => undefined)}
                type="button"
              >
                Refresh
              </button>
              <button
                className="rounded-full border border-error/25 bg-error/5 px-4 py-2.5 text-sm font-medium text-error transition-colors hover:bg-error/10 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={
                  actionState.deletingRun
                  || !DELETABLE_RUN_STATUSES.includes(String(run?.status || "").trim())
                }
                onClick={deleteRun}
                title={
                  DELETABLE_RUN_STATUSES.includes(String(run?.status || "").trim())
                    ? "Delete this run"
                    : "Active runs can be deleted after they finish."
                }
                type="button"
              >
                {actionState.deletingRun ? "Deleting..." : "Delete Run"}
              </button>
            </div>
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

      <section
        aria-labelledby="run-progress-heading"
        className="scroll-mt-20 rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft"
        id="run-progress"
        ref={progressRef}
        tabIndex={-1}
      >
        <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2
              className="font-headline text-2xl font-bold text-on-surface outline-none"
              id="run-progress-heading"
              ref={progressHeadingRef}
              tabIndex={-1}
            >
              Run progress
            </h2>
            <p className="mt-1 text-sm text-on-surface-variant">
              You can leave this page and return later; progress is saved.
            </p>
          </div>
          {run?.eta?.state === "estimated" ? (
            <div className="rounded-full bg-primary/10 px-3 py-1.5 text-sm font-semibold text-primary">
              {etaLabel(run.eta)}
            </div>
          ) : hasActiveRun ? (
            <div className="rounded-full bg-surface-container-low px-3 py-1.5 text-sm font-medium text-on-surface-variant">
              Estimating remaining time...
            </div>
          ) : null}
        </div>
        <RunChecklist stages={stages} />
      </section>
      <SourceCoverageNotice run={run} stages={stages} />

      {run?.last_error ? (
        <section className="rounded-[1.75rem] border border-error/20 bg-error/5 px-6 py-5 text-sm text-error shadow-soft">
          {run.last_error}
        </section>
      ) : null}

      {pageLoading ? (
        <section className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest px-6 py-5 text-on-surface-variant shadow-soft">
          Loading run review...
        </section>
      ) : pageError ? (
        <section className="rounded-[1.75rem] border border-error/20 bg-error/5 px-6 py-5 text-error shadow-soft">
          {pageError}
        </section>
      ) : detailLoading ? (
        <section className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest px-6 py-5 text-on-surface-variant shadow-soft">
          Loading detailed review...
        </section>
      ) : reviewError && !data ? (
        <section className="rounded-[1.75rem] border border-error/20 bg-error/5 px-6 py-5 text-error shadow-soft">
          {reviewError}
        </section>
      ) : (
        <section className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h2 className="font-headline text-2xl font-bold text-on-surface">Run Review</h2>
              <p className="mt-1 max-w-3xl text-sm leading-7 text-on-surface-variant">
                {run?.is_test_run
                  ? "This test run keeps one job that reached document generation so you can inspect the workspace output. The selected job and its documents are available in Tracker."
                  : "Use this view to decide which roles stay out and which excluded roles should still get documents. Once documents are ready, those jobs appear in Tracker."}
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
                review.included_jobs.map((job) => (
                  <IncludedJobRow job={job} key={job.job_id} runId={runId} />
                ))
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
                    runId={runId}
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
