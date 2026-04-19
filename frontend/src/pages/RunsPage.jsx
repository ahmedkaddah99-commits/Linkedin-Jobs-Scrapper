import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { formatDateTime, labelize, statusTone } from "../lib/formatters";

function canDeleteRun(status) {
  return ["planned", "queued", "failed", "cancelled"].includes(String(status || "").trim());
}

function canStopRun(status) {
  return ["queued", "running", "cancel_requested", "planned"].includes(String(status || "").trim());
}

export default function RunsPage() {
  const { request } = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const [actionState, setActionState] = useState({
    runId: "",
    action: "",
    busy: false,
    message: "",
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
  const queuedRuns = runs.filter((run) => String(run.status || "").trim() === "queued");

  async function deleteRun(runId) {
    const confirmed = window.confirm(
      "Delete this run and its stored test data? This is meant for queued or failed test runs.",
    );
    if (!confirmed) {
      return;
    }
    setActionState({ runId, action: "delete", busy: true, message: "", error: "" });
    try {
      await request(`/runs/${runId}`, { method: "DELETE" });
      setActionState({
        runId,
        action: "delete",
        busy: false,
        message: `Deleted ${runId}`,
        error: "",
      });
      refresh().catch(() => undefined);
    } catch (deleteError) {
      setActionState({
        runId,
        action: "delete",
        busy: false,
        message: "",
        error: deleteError.message || "Unable to delete run.",
      });
    }
  }

  async function cancelRun(runId) {
    const confirmed = window.confirm(
      "Stop this run? If it is already running, the backend will stop it at the next safe cancellation point.",
    );
    if (!confirmed) {
      return;
    }
    setActionState({ runId, action: "cancel", busy: true, message: "", error: "" });
    try {
      await request(`/runs/${runId}/cancel`, { method: "POST", body: {} });
      setActionState({
        runId,
        action: "cancel",
        busy: false,
        message: `Stop requested for ${runId}`,
        error: "",
      });
      refresh().catch(() => undefined);
    } catch (cancelError) {
      setActionState({
        runId,
        action: "cancel",
        busy: false,
        message: "",
        error: cancelError.message || "Unable to stop run.",
      });
    }
  }

  async function deleteAllQueuedRuns() {
    if (!queuedRuns.length) {
      return;
    }
    const confirmed = window.confirm(
      `Delete all queued runs in this view? This will remove ${queuedRuns.length} queued run(s).`,
    );
    if (!confirmed) {
      return;
    }
    setActionState({ runId: "bulk", action: "bulk_delete", busy: true, message: "", error: "" });
    try {
      await Promise.all(
        queuedRuns.map((run) => request(`/runs/${run.id}`, { method: "DELETE" })),
      );
      setActionState({
        runId: "bulk",
        action: "bulk_delete",
        busy: false,
        message: `Deleted ${queuedRuns.length} queued run(s).`,
        error: "",
      });
      refresh().catch(() => undefined);
    } catch (bulkDeleteError) {
      setActionState({
        runId: "bulk",
        action: "bulk_delete",
        busy: false,
        message: "",
        error: bulkDeleteError.message || "Unable to delete all queued runs.",
      });
    }
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-2">
        <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
          Runs
        </h1>
        <p className="text-sm text-on-surface-variant">
          Queue history and live execution status across your connected workspaces.
        </p>
      </header>

      <section className="rounded-xl bg-surface-container-low p-4">
        <div className="grid gap-4 md:grid-cols-4">
          <input
            className="rounded border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm"
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
            className="rounded border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm"
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
            className="rounded bg-surface-container-lowest px-4 py-2.5 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
            onClick={() => refresh().catch(() => undefined)}
            type="button"
          >
            Refresh
          </button>
          <button
            className="rounded bg-surface-container-lowest px-4 py-2.5 text-sm font-medium text-error transition-colors hover:bg-error-container hover:text-on-error-container disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!queuedRuns.length || actionState.busy}
            onClick={deleteAllQueuedRuns}
            type="button"
          >
            {actionState.busy && actionState.action === "bulk_delete"
              ? "Deleting queued..."
              : "Delete All Queued"}
          </button>
        </div>
      </section>

      {actionState.message || actionState.error ? (
        <section
          className={[
            "rounded-xl px-4 py-3 text-sm",
            actionState.error
              ? "bg-error-container text-on-error-container"
              : "bg-surface-container-low text-on-surface",
          ].join(" ")}
        >
          {actionState.error || actionState.message}
        </section>
      ) : null}

      <section className="overflow-hidden rounded-xl border border-outline-variant/20 bg-surface-container-lowest">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface-container-low text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
              <tr>
                <th className="px-6 py-4">Run</th>
                <th className="px-6 py-4">Workspace</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4">Current Stage</th>
                <th className="px-6 py-4">Updated</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <tr>
                  <td className="px-6 py-10 text-on-surface-variant" colSpan={6}>
                    Loading runs...
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td className="px-6 py-10 text-error" colSpan={6}>
                    {error}
                  </td>
                </tr>
              ) : runs.length ? (
                runs.map((run) => (
                  <tr key={run.id} className="hover:bg-surface-container-low">
                    <td className="px-6 py-4 font-semibold text-on-surface">{run.id}</td>
                    <td className="px-6 py-4 text-on-surface-variant">{run.workspace_id}</td>
                    <td className="px-6 py-4">
                      <StatusBadge tone={statusTone(run.status)}>{labelize(run.status)}</StatusBadge>
                    </td>
                    <td className="px-6 py-4 text-on-surface-variant">
                      {labelize(run.current_stage_id || "not_started")}
                    </td>
                    <td className="px-6 py-4 text-on-surface-variant">
                      {formatDateTime(run.updated_at)}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex justify-end gap-3">
                        <Link
                          className="text-sm font-medium text-primary transition-colors hover:text-primary-container"
                          to={`/runs/${run.id}`}
                        >
                          Open
                        </Link>
                        {canDeleteRun(run.status) ? (
                          <button
                            className="text-sm font-medium text-error transition-colors hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-60"
                            disabled={actionState.busy && actionState.runId === run.id}
                            onClick={() => deleteRun(run.id)}
                            type="button"
                          >
                            {actionState.busy &&
                            actionState.runId === run.id &&
                            actionState.action === "delete"
                              ? "Deleting..."
                              : "Delete"}
                          </button>
                        ) : null}
                        {canStopRun(run.status) ? (
                          <button
                            className="text-sm font-medium text-primary transition-colors hover:text-primary-container disabled:cursor-not-allowed disabled:opacity-60"
                            disabled={actionState.busy && actionState.runId === run.id}
                            onClick={() => cancelRun(run.id)}
                            type="button"
                          >
                            {actionState.busy &&
                            actionState.runId === run.id &&
                            actionState.action === "cancel"
                              ? "Stopping..."
                              : "Stop"}
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-6 py-10 text-on-surface-variant" colSpan={6}>
                    No runs found for the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
