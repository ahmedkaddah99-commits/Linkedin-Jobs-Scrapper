import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { getApiErrorMessage } from "../lib/api";
import {
  PEOPLE_CATEGORY_CONFIG,
  PEOPLE_DISCOVERY_STEPS,
  confirmRelevantPerson,
  countSelectedPeople,
  fetchJobWorkspace,
  getPeopleDiscoveryResults,
  getPeopleDiscoveryStatus,
  normalizePeopleDiscoveryRun,
  rejectRelevantPerson,
  savePersonForOutreach,
  startPeopleDiscovery,
} from "../lib/peopleDiscovery";

const DISCOVERY_STATUS_NOT_STARTED = "not_started";
const DISCOVERY_STATUS_RUNNING = "running";
const DISCOVERY_STATUS_COMPLETED = "completed";
const DISCOVERY_STATUS_FAILED = "failed";
const DISCOVERY_STATUS_NOT_CONFIGURED = "not_configured";
const DISCOVERY_STATUS_POLL_INTERVAL_MS = 2000;
const DISCOVERY_TERMINAL_STATUSES = new Set([
  DISCOVERY_STATUS_COMPLETED,
  DISCOVERY_STATUS_FAILED,
  DISCOVERY_STATUS_NOT_CONFIGURED,
]);

function StepProgress({ activeIndex, completed, running }) {
  return (
    <div className="people-step-progress rounded-2xl border border-outline-variant/20 bg-surface p-5">
      <div className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
        Two-Pass Discovery
      </div>
      <div className="mt-4 space-y-3">
        {PEOPLE_DISCOVERY_STEPS.map((step, index) => {
          const state = completed
            ? "done"
            : running
              ? index < activeIndex
                ? "done"
                : index === activeIndex
                  ? "active"
                  : "pending"
              : "pending";
          return (
            <div
              className="flex items-center gap-3 rounded-2xl border border-outline-variant/15 bg-surface-container-low px-4 py-3"
              key={step}
            >
              <div
                className={[
                  "flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold",
                  state === "done"
                    ? "bg-primary text-white"
                    : state === "active"
                      ? "bg-primary/10 text-primary"
                      : "bg-surface text-on-surface-variant",
                ].join(" ")}
              >
                {state === "done" ? (
                  <span className="material-symbols-outlined text-[16px]">check</span>
                ) : state === "active" ? (
                  <span className="material-symbols-outlined animate-spin text-[16px]">
                    progress_activity
                  </span>
                ) : (
                  index + 1
                )}
              </div>
              <div className="text-sm text-on-surface">{step}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ContextChip({ label, value, tone = "default" }) {
  if (!value) return null;
  return (
    <div
      className={[
        "context-chip rounded-2xl border px-4 py-3",
        tone === "primary"
          ? "border-primary/20 bg-primary/5"
          : "border-outline-variant/15 bg-surface-container-low",
      ].join(" ")}
    >
      <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-on-surface-variant">
        {label}
      </div>
      <div className="mt-1 text-sm font-medium text-on-surface">{value}</div>
    </div>
  );
}

function PersonActionButton({ active, busy, label, onClick, tone = "default" }) {
  return (
    <button
      className={[
        "rounded-full px-3 py-1.5 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60",
        tone === "primary"
          ? active
            ? "bg-primary text-white"
            : "bg-primary/10 text-primary hover:bg-primary/20"
          : tone === "danger"
            ? active
              ? "bg-error text-white"
              : "bg-error/10 text-error hover:bg-error/20"
            : active
              ? "bg-teal-600 text-white"
              : "bg-teal-500/10 text-teal-700 hover:bg-teal-500/20",
      ].join(" ")}
      disabled={busy}
      onClick={onClick}
      type="button"
    >
      {busy ? "Saving..." : label}
    </button>
  );
}

function RelevantPersonCard({ person, busy, onConfirm, onReject, onSave }) {
  const status = String(person.status || "unreviewed");

  return (
    <article className="relevant-person-card rounded-3xl border border-outline-variant/20 bg-surface p-5 shadow-soft">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold text-on-surface">{person.name}</h3>
            <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
              {person.confidence}% {person.confidenceLabel}
            </span>
          </div>
          <div className="mt-2 text-sm font-medium text-on-surface">
            {person.title || "Title not available"}
          </div>
          <div className="mt-1 text-sm text-on-surface-variant">
            {[person.company, person.location].filter(Boolean).join(" | ") || "No company or location saved"}
          </div>
        </div>
        <div className="rounded-2xl bg-surface-container-low px-3 py-2 text-right">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-on-surface-variant">
            Status
          </div>
          <div className="mt-1 text-sm font-semibold text-on-surface">
            {status.replace(/_/g, " ")}
          </div>
        </div>
      </div>

      <p className="mt-4 text-sm leading-6 text-on-surface-variant">{person.reasoningNote}</p>

      {person.caveats?.length ? (
        <div className="mt-4 rounded-2xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm text-amber-800">
          {person.caveats.join(" ")}
        </div>
      ) : null}

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <ContextChip label="Category" value={(person.category || "").replace(/_/g, " ")} />
        <ContextChip label="Source" value={person.source || "public_profile_search"} />
        <ContextChip
          label="Discovered Search Query"
          value={person.discoveredSearchQuery || person.searchQueries?.[0] || "Not saved"}
        />
        <ContextChip label="Region / Scope Caveat" value={person.regionScopeCaveat || "None"} />
      </div>

      {person.evidenceSnippets?.length ? (
        <div className="mt-4">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-on-surface-variant">
            Evidence Snippets
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {person.evidenceSnippets.map((snippet) => (
              <span
                className="rounded-full bg-surface-container-low px-3 py-1 text-xs text-on-surface"
                key={`${person.id}-${snippet}`}
              >
                {snippet}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-5 flex flex-wrap gap-2">
        <PersonActionButton
          active={status === "confirmed"}
          busy={busy}
          label="Confirm"
          onClick={onConfirm}
          tone="primary"
        />
        <PersonActionButton
          active={status === "rejected"}
          busy={busy}
          label="Reject"
          onClick={onReject}
          tone="danger"
        />
        <PersonActionButton
          active={status === "saved_for_outreach"}
          busy={busy}
          label="Save for outreach"
          onClick={onSave}
          tone="success"
        />
        {person.profileUrl ? (
          <a
            className="rounded-full bg-surface-container-low px-3 py-1.5 text-xs font-semibold text-on-surface transition-colors hover:bg-surface-container-high"
            href={person.profileUrl}
            rel="noreferrer"
            target="_blank"
          >
            View source
          </a>
        ) : null}
      </div>
    </article>
  );
}

function EmptyCategoryState({ message, noMatches }) {
  return (
    <div className="relevant-empty rounded-3xl border border-dashed border-outline-variant/30 bg-surface p-6 text-sm text-on-surface-variant">
      {noMatches
        ? "No strong matches found yet. Try broadening the location, checking the company name, or continuing without people context."
        : message}
    </div>
  );
}

function buildGenerationNote(discoveryRun) {
  const selectedPeople = (discoveryRun?.selectedPeople || []).filter(
    (person) => person?.status === "confirmed" || person?.status === "saved_for_outreach",
  );
  if (!selectedPeople.length) {
    return "Triggered from the job workspace without saved people context.";
  }
  const contextLines = selectedPeople.map((person) =>
    [person.name, person.title, person.category].filter(Boolean).join(" | "),
  );
  return `Triggered from the job workspace. Saved relevant people context: ${contextLines.join(" ; ")}`;
}

function countDiscoveredPeople(discoveryRun) {
  return PEOPLE_CATEGORY_CONFIG.reduce(
    (count, category) => count + (discoveryRun?.categories?.[category.id]?.length || 0),
    0,
  );
}

function discoveryNotConfiguredMessage(discoveryRun) {
  return (
    discoveryRun?.error
    || "Live relevant people discovery is not configured. Set RUNR_ENABLE_LIVE_NETWORKING_DISCOVERY=1 and restart the backend before running this search."
  );
}

export default function JobWorkspacePage() {
  const { runId, jobId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { request } = useSession();
  const [actionState, setActionState] = useState({
    discoveryRunning: false,
    generationRunning: false,
    message: "",
    error: "",
    personActionId: "",
    generationRunId: "",
  });
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const [skipped, setSkipped] = useState(false);

  const mode = String(searchParams.get("mode") || "context_only");
  const sourceStage = String(searchParams.get("source_stage") || "");
  const reasonSummary = String(searchParams.get("reason_summary") || "");
  const isPreGeneration = mode === "pre_generation";

  const { data, loading, error, refresh, setData } = useApiResource(
    () => fetchJobWorkspace(request, { runId, jobId }),
    [request, runId, jobId],
  );

  const workspacePayload = data || {};
  const job = workspacePayload.job || {};
  const discoveryRun = normalizePeopleDiscoveryRun(
    workspacePayload.relevant_people_discovery,
    job,
  );
  const discoveryStatus = String(
    discoveryRun.peopleDiscoveryStatus || DISCOVERY_STATUS_NOT_STARTED,
  );
  const showDiscoveryProgress =
    actionState.discoveryRunning || discoveryStatus === DISCOVERY_STATUS_RUNNING;
  const selectedCount = useMemo(() => countSelectedPeople(discoveryRun), [discoveryRun]);
  const totalPeopleCount = useMemo(() => countDiscoveredPeople(discoveryRun), [discoveryRun]);

  useEffect(() => {
    if (!showDiscoveryProgress) {
      return undefined;
    }
    setActiveStepIndex(0);
    const intervalId = window.setInterval(() => {
      setActiveStepIndex((currentValue) =>
        Math.min(currentValue + 1, PEOPLE_DISCOVERY_STEPS.length - 1),
      );
    }, 850);
    return () => window.clearInterval(intervalId);
  }, [showDiscoveryProgress]);

  useEffect(() => {
    if (actionState.discoveryRunning || discoveryStatus !== DISCOVERY_STATUS_RUNNING) {
      return undefined;
    }
    let cancelled = false;
    const intervalId = window.setInterval(() => {
      getPeopleDiscoveryStatus(request, { runId, jobId })
        .then((statusPayload) => {
          if (cancelled) {
            return;
          }
          const nextStatus = String(
            statusPayload?.peopleDiscoveryStatus || DISCOVERY_STATUS_NOT_STARTED,
          );
          if (!DISCOVERY_TERMINAL_STATUSES.has(nextStatus)) {
            return;
          }
          return getPeopleDiscoveryResults(request, { runId, jobId, job }).then((payload) => {
            if (cancelled) {
              return;
            }
            setData((currentValue) => ({
              ...(currentValue || {}),
              relevant_people_discovery: payload,
            }));
          });
        })
        .catch(() => undefined);
    }, DISCOVERY_STATUS_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [actionState.discoveryRunning, discoveryStatus, job, jobId, request, runId, setData]);

  async function runPeopleDiscovery() {
    setSkipped(false);
    setActionState((currentValue) => ({
      ...currentValue,
      discoveryRunning: true,
      message: "",
      error: "",
      personActionId: "",
    }));
    try {
      const payload = await startPeopleDiscovery(request, { runId, jobId, job });
      setData((currentValue) => ({
        ...(currentValue || {}),
        relevant_people_discovery: payload,
      }));
      if (payload.peopleDiscoveryStatus === DISCOVERY_STATUS_COMPLETED) {
        const discoveredCount = countDiscoveredPeople(payload);
        setActiveStepIndex(PEOPLE_DISCOVERY_STEPS.length - 1);
        setActionState((currentValue) => ({
          ...currentValue,
          discoveryRunning: false,
          message: discoveredCount
            ? "Relevant people discovery completed. Review the likely matches below."
            : "Relevant people discovery completed, but no strong matches were found.",
          error: "",
        }));
        return;
      }
      if (payload.peopleDiscoveryStatus === DISCOVERY_STATUS_NOT_CONFIGURED) {
        setActionState((currentValue) => ({
          ...currentValue,
          discoveryRunning: false,
          message: "",
          error: discoveryNotConfiguredMessage(payload),
        }));
        return;
      }
      if (payload.peopleDiscoveryStatus === DISCOVERY_STATUS_FAILED) {
        setActionState((currentValue) => ({
          ...currentValue,
          discoveryRunning: false,
          message: "",
          error:
            payload.error
            || "Relevant people discovery could not finish. Try running it again.",
        }));
        return;
      }
      setActionState((currentValue) => ({
        ...currentValue,
        discoveryRunning: false,
        message:
          "Relevant people discovery started. This page will update when the ranked matches are ready.",
        error: "",
      }));
    } catch (startError) {
      setActionState((currentValue) => ({
        ...currentValue,
        discoveryRunning: false,
        message: "",
        error: getApiErrorMessage(startError, "Unable to run relevant people discovery right now."),
      }));
    }
  }

  async function updatePersonStatus(action, personId) {
    const actionMap = {
      confirm: confirmRelevantPerson,
      reject: rejectRelevantPerson,
      save: savePersonForOutreach,
    };
    const actionLabel = {
      confirm: "Person confirmed.",
      reject: "Person rejected.",
      save: "Saved for outreach.",
    };
    const requestFn = actionMap[action];
    if (!requestFn) return;
    setActionState((currentValue) => ({
      ...currentValue,
      personActionId: personId,
      message: "",
      error: "",
    }));
    try {
      const payload = await requestFn(request, { runId, jobId, personId, job });
      setData((currentValue) => ({
        ...(currentValue || {}),
        relevant_people_discovery: payload,
      }));
      setActionState((currentValue) => ({
        ...currentValue,
        personActionId: "",
        message: actionLabel[action],
        error: "",
      }));
    } catch (statusError) {
      setActionState((currentValue) => ({
        ...currentValue,
        personActionId: "",
        message: "",
        error: getApiErrorMessage(statusError, "Unable to update this person right now."),
      }));
    }
  }

  async function startCvGeneration() {
    setActionState((currentValue) => ({
      ...currentValue,
      generationRunning: true,
      message: "",
      error: "",
    }));
    try {
      const payload = await request(
        `/runs/${encodeURIComponent(runId)}/excluded-jobs/${encodeURIComponent(jobId)}/generate-documents`,
        {
          method: "POST",
          body: {
            source_stage: sourceStage || "rejected_review",
            reason_summary:
              reasonSummary || "Selected from the job workspace for customization.",
            execution_mode: "queued",
            notes: buildGenerationNote(discoveryRun),
          },
        },
      );
      setActionState((currentValue) => ({
        ...currentValue,
        generationRunning: false,
        generationRunId: String(payload.run?.id || ""),
        message: `CV generation run ${payload.run?.id || ""} was queued from this job workspace.`,
        error: "",
      }));
    } catch (generationError) {
      setActionState((currentValue) => ({
        ...currentValue,
        generationRunning: false,
        generationRunId: "",
        message: "",
        error: getApiErrorMessage(generationError, "Unable to start CV generation from this job workspace."),
      }));
    }
  }

  if (loading && !data) {
    return (
      <div className="people-workspace-page rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-8 text-on-surface-variant shadow-soft">
        Loading selected job workspace...
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="people-workspace-page space-y-4 rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
        <div className="text-error">{error}</div>
        <div className="flex flex-wrap gap-3">
          <button
            className="rounded-full bg-primary/10 px-4 py-2 text-sm font-semibold text-primary transition-colors hover:bg-primary/20"
            onClick={() => refresh().catch(() => undefined)}
            type="button"
          >
            Retry
          </button>
          <button
            className="rounded-full bg-surface-container-low px-4 py-2 text-sm font-semibold text-on-surface transition-colors hover:bg-surface-container-high"
            onClick={() => navigate(-1)}
            type="button"
          >
            Back
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="people-workspace-page space-y-8">
      <header className="people-workspace__header rounded-[2rem] border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-3">
            <button
              className="inline-flex items-center gap-2 rounded-full bg-surface-container-low px-4 py-2 text-sm font-semibold text-on-surface transition-colors hover:bg-surface-container-high"
              onClick={() => navigate(-1)}
              type="button"
            >
              <span className="material-symbols-outlined text-[16px]">arrow_back</span>
              Back
            </button>
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                Relevant People Finder
              </div>
              <h1 className="mt-1 font-headline text-4xl font-extrabold tracking-tight text-on-surface">
                {job.title || "Selected job"}
              </h1>
              <p className="mt-2 text-sm leading-7 text-on-surface-variant">
                {[job.company, job.location || job.location_raw].filter(Boolean).join(" | ") ||
                  "Selected role context"}
              </p>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <ContextChip
              label="Confirmed People"
              value={`${selectedCount} saved for application context`}
              tone="primary"
            />
            <ContextChip
              label="Discovery Status"
              value={discoveryStatus.replace(/_/g, " ")}
            />
          </div>
        </div>

        <div className="mt-6 grid gap-3 lg:grid-cols-4">
          <ContextChip label="Department" value={discoveryRun.contextExtraction?.department || "Hiring Team"} />
          <ContextChip label="Seniority" value={discoveryRun.contextExtraction?.seniority || "Not inferred"} />
          <ContextChip label="Business Unit" value={discoveryRun.contextExtraction?.businessUnit || "Not available"} />
          <ContextChip
            label="Keywords"
            value={(discoveryRun.contextExtraction?.keywords || []).slice(0, 4).join(", ") || "No keywords extracted"}
          />
        </div>
      </header>

      {actionState.message || actionState.error ? (
        <section
          className={[
            "rounded-3xl border px-5 py-4 text-sm shadow-soft",
            actionState.error
              ? "border-error/20 bg-error/5 text-error"
              : "border-primary/20 bg-primary/5 text-primary",
          ].join(" ")}
        >
          {actionState.error || actionState.message}
          {actionState.generationRunId ? (
            <div className="mt-3">
              <Link
                className="inline-flex rounded-full bg-surface px-4 py-2 text-sm font-semibold text-on-surface transition-colors hover:bg-surface-container-high"
                to={`/runs/${actionState.generationRunId}`}
              >
                Open Generated Run
              </Link>
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="people-workspace__finder rounded-[2rem] border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h2 className="font-headline text-2xl font-bold text-on-surface">
              Relevant People Finder
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-7 text-on-surface-variant">
              Runr can look for likely hiring managers, team members, and senior leaders connected
              to this role before tailoring your application.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              className="rounded-full bg-gradient-to-br from-primary to-primary-container px-5 py-3 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={actionState.discoveryRunning}
              onClick={runPeopleDiscovery}
              type="button"
            >
              {actionState.discoveryRunning
                ? "Finding relevant people..."
                : (
                    discoveryStatus === DISCOVERY_STATUS_NOT_CONFIGURED
                    || discoveryStatus === DISCOVERY_STATUS_FAILED
                  )
                  ? "Try again"
                  : totalPeopleCount
                    ? "Run broader search"
                    : "Find relevant people"}
            </button>
            <button
              className="rounded-full bg-surface-container-low px-5 py-3 text-sm font-semibold text-on-surface transition-colors hover:bg-surface-container-high"
              onClick={() => setSkipped(true)}
              type="button"
            >
              Skip for now
            </button>
          </div>
        </div>

        <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="space-y-6">
            {skipped && discoveryRun.peopleDiscoveryStatus === "not_started" ? (
              <div className="rounded-3xl border border-outline-variant/20 bg-surface p-6 text-sm text-on-surface-variant">
                You can continue without people context. Confirmed or saved people can always be
                added later before networking, referral, or interview-prep work.
              </div>
            ) : null}

            {showDiscoveryProgress ? (
              <div className="rounded-3xl border border-outline-variant/20 bg-surface p-6">
                <StepProgress activeIndex={activeStepIndex} completed={false} running />
              </div>
            ) : null}

            {!showDiscoveryProgress && discoveryStatus === DISCOVERY_STATUS_FAILED ? (
              <div className="rounded-3xl border border-error/20 bg-error/5 p-6 text-sm text-error">
                {discoveryRun.error || "People discovery failed. Try running it again."}
              </div>
            ) : null}

            {!showDiscoveryProgress &&
            discoveryStatus === DISCOVERY_STATUS_NOT_CONFIGURED &&
            !actionState.error ? (
              <div className="rounded-3xl border border-amber-500/20 bg-amber-500/5 p-6 text-sm text-amber-800">
                {discoveryNotConfiguredMessage(discoveryRun)}
              </div>
            ) : null}

            {!showDiscoveryProgress &&
            discoveryStatus === DISCOVERY_STATUS_COMPLETED &&
            !totalPeopleCount ? (
              <EmptyCategoryState noMatches />
            ) : null}

            {!showDiscoveryProgress &&
            discoveryStatus === DISCOVERY_STATUS_COMPLETED &&
            totalPeopleCount ? (
              <div className="grid gap-5 xl:grid-cols-3">
                {PEOPLE_CATEGORY_CONFIG.map((category) => {
                  const people = discoveryRun.categories?.[category.id] || [];
                  return (
                    <section
                      className="rounded-3xl border border-outline-variant/20 bg-surface-container-low p-4"
                      key={category.id}
                    >
                      <div className="mb-4">
                        <h3 className="text-lg font-semibold text-on-surface">{category.title}</h3>
                        <p className="mt-1 text-xs leading-6 text-on-surface-variant">
                          Likely relevant only. Confidence is based on public profile signals.
                        </p>
                      </div>
                      <div className="space-y-4">
                        {people.length > 0 && people.length < 2 ? (
                          <div className="rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface-variant">
                            {category.emptyState}
                          </div>
                        ) : null}
                        {people.length ? (
                          people.map((person) => (
                            <RelevantPersonCard
                              busy={actionState.personActionId === person.id}
                              key={person.id}
                              onConfirm={() => updatePersonStatus("confirm", person.id)}
                              onReject={() => updatePersonStatus("reject", person.id)}
                              onSave={() => updatePersonStatus("save", person.id)}
                              person={person}
                            />
                          ))
                        ) : (
                          <EmptyCategoryState message={category.emptyState} />
                        )}
                      </div>
                    </section>
                  );
                })}
              </div>
            ) : null}
          </div>

          <aside className="space-y-5">
            <StepProgress
              activeIndex={showDiscoveryProgress ? activeStepIndex : PEOPLE_DISCOVERY_STEPS.length - 1}
              completed={!showDiscoveryProgress && discoveryStatus === DISCOVERY_STATUS_COMPLETED}
              running={showDiscoveryProgress}
            />

            <div className="rounded-2xl border border-outline-variant/20 bg-surface p-5">
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                Saved Context
              </div>
              <div className="mt-3 text-3xl font-bold text-on-surface">{selectedCount}</div>
              <p className="mt-2 text-sm leading-6 text-on-surface-variant">
                Confirmed or saved people can later inform CV tone, motivation letters, networking
                messages, referral strategy, company research, and interview prep.
              </p>
            </div>

            {discoveryRun.warnings?.length ? (
              <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-5 text-sm text-amber-800">
                {discoveryRun.warnings.join(" | ")}
              </div>
            ) : null}

            {job.apply_link ? (
              <a
                className="inline-flex w-full items-center justify-center rounded-full bg-surface-container-low px-4 py-3 text-sm font-semibold text-on-surface transition-colors hover:bg-surface-container-high"
                href={job.apply_link}
                rel="noreferrer"
                target="_blank"
              >
                View source job posting
              </a>
            ) : null}
          </aside>
        </div>
      </section>

      {isPreGeneration ? (
        <section className="people-workspace__continue rounded-[2rem] border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="font-headline text-2xl font-bold text-on-surface">
                Continue To CV Generation
              </h2>
              <p className="mt-2 max-w-3xl text-sm leading-7 text-on-surface-variant">
                You can continue with no saved people, or use the confirmed context above to keep
                later application work more grounded.
              </p>
            </div>
            <button
              className="rounded-full bg-gradient-to-br from-primary to-primary-container px-5 py-3 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={actionState.generationRunning}
              onClick={startCvGeneration}
              type="button"
            >
              {actionState.generationRunning ? "Starting..." : "Start CV generation"}
            </button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
