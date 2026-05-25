import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { formatDateTime, labelize, statusTone } from "../lib/formatters";

const ACTIVE_RUN_STATUSES = ["planned", "queued", "running", "cancel_requested"];
const DELETABLE_RUN_STATUSES = ["planned", "queued", "completed", "failed", "cancelled"];

function formatDuration(seconds) {
  const total = Math.max(0, Number.parseInt(seconds || 0, 10) || 0);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainingSeconds = total % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${remainingSeconds}s`;
  return `${remainingSeconds}s`;
}

function progressTone(health) {
  if (health === "stale") return "warning";
  if (health === "slow") return "primary";
  return "success";
}

function RunSummaryCard({ description, label, value }) {
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

export default function RunsPage() {
  const { request } = useSession();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [actionState, setActionState] = useState({
    pendingRunId: "",
    message: String(location.state?.runActionMessage || ""),
    error: "",
  });
  const workspaceId = searchParams.get("workspace_id") || "";
  const status = searchParams.get("status") || "";

  const { data, loading, error, refresh } = useApiResource(
    () =>
      request(
        `/runs?limit=100&workspace_id=${encodeURIComponent(workspaceId)}&status=${encodeURIComponent(status)}`,
      ),
    [request, workspaceId, status],
  );

  const runs = data?.runs || [];
  const hasActiveRuns = runs.some((run) => ACTIVE_RUN_STATUSES.includes(String(run.status || "").trim()));

  useEffect(() => {
    if (!hasActiveRuns) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      refresh().catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(intervalId);
  }, [hasActiveRuns, refresh]);

  useEffect(() => {
    if (!location.state?.runActionMessage) {
      return;
    }
    navigate(location.pathname + location.search, { replace: true, state: null });
  }, [location.pathname, location.search, location.state, navigate]);

  async function deleteRun(run) {
    const runName = run.workspace_name || run.workspace_id || "this run";
    const confirmed = window.confirm(`Delete ${runName}? This removes the run review, jobs, reviews, and artifacts saved for it.`);
    if (!confirmed) {
      return;
    }
    setActionState({ pendingRunId: run.id, message: "", error: "" });
    try {
      await request(`/runs/${run.id}`, { method: "DELETE" });
      setActionState({
        pendingRunId: "",
        message: `${runName} was deleted.`,
        error: "",
      });
      refresh().catch(() => undefined);
    } catch (actionError) {
      setActionState({
        pendingRunId: "",
        message: "",
        error: actionError.message || "Unable to delete this run.",
      });
    }
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-3">
        <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">Runs</h1>
        <p className="max-w-3xl text-sm leading-7 text-on-surface-variant">
          Open a run to review included and excluded jobs, create documents for excluded jobs you want
          to keep, and follow those jobs into Tracker once documents are ready.
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        <RunSummaryCard
          description="Runs in the current filtered view."
          label="Visible Runs"
          value={runs.length}
        />
        <RunSummaryCard
          description="Runs still progressing or waiting to finish."
          label="Active Runs"
          value={runs.filter((run) => ACTIVE_RUN_STATUSES.includes(String(run.status || "").trim())).length}
        />
        <RunSummaryCard
          description="Runs that already finished successfully."
          label="Completed Runs"
          value={runs.filter((run) => String(run.status || "").trim() === "completed").length}
        />
      </section>

      <section className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
        <div className="grid gap-4 md:grid-cols-[1.2fr_1fr_auto]">
          <input
            className="rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) => {
              const next = new URLSearchParams(searchParams);
              if (event.target.value) next.set("workspace_id", event.target.value);
              else next.delete("workspace_id");
              setSearchParams(next);
            }}
            placeholder="Filter by workspace id"
            type="text"
            value={workspaceId}
          />
          <select
            className="rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) => {
              const next = new URLSearchParams(searchParams);
              if (event.target.value) next.set("status", event.target.value);
              else next.delete("status");
              setSearchParams(next);
            }}
            value={status}
          >
            <option value="">All Statuses</option>
            <option value="planned">Planned</option>
            <option value="queued">Queued</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <button
            className="rounded-2xl bg-surface px-4 py-3 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
            onClick={() => refresh().catch(() => undefined)}
            type="button"
          >
            Refresh
          </button>
        </div>
      </section>

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

      <section className="space-y-4">
        {loading ? (
          <div className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-6 text-on-surface-variant shadow-soft">
            Loading runs...
          </div>
        ) : error ? (
          <div className="rounded-[1.75rem] border border-error/20 bg-error/5 p-6 text-error shadow-soft">
            {error}
          </div>
        ) : runs.length ? (
          runs.map((run) => (
            <article
              className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft"
              key={run.id}
            >
              <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <StatusBadge tone={statusTone(run.status)}>{labelize(run.status)}</StatusBadge>
                    <span className="rounded-full bg-surface-container-low px-3 py-1 text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                      {run.workspace_name || run.workspace_id}
                    </span>
                  </div>
                  <div>
                    <h2 className="font-headline text-2xl font-bold text-on-surface">
                      {run.workspace_name || run.workspace_id || run.id}
                    </h2>
                    <p className="mt-1 text-sm text-on-surface-variant">
                      {run.progress?.message || "Review included and excluded jobs for this run."}
                    </p>
                  </div>
                  {run.progress?.stage_id ? (
                    <div className="rounded-2xl bg-surface p-4 text-sm text-on-surface-variant">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusBadge tone={progressTone(run.progress.health)}>
                          {run.progress.health_label || "Running"}
                        </StatusBadge>
                        <span className="font-semibold text-on-surface">
                          {run.progress.stage_name || labelize(run.progress.stage_id)}
                        </span>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-4">
                        <div>Elapsed: {formatDuration(run.progress.elapsed_seconds)}</div>
                        {run.progress.counters?.total_sites ? (
                          <div>
                            Sites: {run.progress.counters.processed_sites ?? 0}/{run.progress.counters.total_sites}
                          </div>
                        ) : null}
                        {run.progress.counters?.jobs_found !== undefined ? (
                          <div>Jobs: {run.progress.counters.jobs_found}</div>
                        ) : null}
                      </div>
                      {run.progress.current_item?.company_name || run.progress.current_item?.site_url ? (
                        <div className="mt-2 truncate">
                          Current: {run.progress.current_item.company_name || run.progress.current_item.site_url}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  <div className="flex flex-wrap gap-6 text-sm text-on-surface-variant">
                    <div>
                      <span className="font-semibold text-on-surface">Created:</span>{" "}
                      {formatDateTime(run.created_at)}
                    </div>
                    <div>
                      <span className="font-semibold text-on-surface">Updated:</span>{" "}
                      {formatDateTime(run.updated_at)}
                    </div>
                  </div>
                </div>
                <div className="flex flex-wrap gap-3">
                  <Link
                    className="rounded-full bg-gradient-to-br from-primary to-primary-container px-5 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90"
                    to={`/runs/${run.id}`}
                  >
                    Open Run Review
                  </Link>
                  <button
                    className="rounded-full border border-error/25 bg-error/5 px-5 py-2.5 text-sm font-medium text-error transition-colors hover:bg-error/10 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={
                      actionState.pendingRunId === run.id
                      || !DELETABLE_RUN_STATUSES.includes(String(run.status || "").trim())
                    }
                    onClick={() => deleteRun(run)}
                    title={
                      DELETABLE_RUN_STATUSES.includes(String(run.status || "").trim())
                        ? "Delete this run"
                        : "Active runs can be deleted after they finish."
                    }
                    type="button"
                  >
                    {actionState.pendingRunId === run.id ? "Deleting..." : "Delete Run"}
                  </button>
                </div>
              </div>
            </article>
          ))
        ) : (
          <div className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-6 text-on-surface-variant shadow-soft">
            No runs found for the current filters.
          </div>
        )}
      </section>
    </div>
  );
}
