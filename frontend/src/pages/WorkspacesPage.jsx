import { useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { labelize } from "../lib/formatters";

export default function WorkspacesPage() {
  const { request } = useSession();
  const [actionState, setActionState] = useState({ workspaceId: "", message: "", error: "" });
  const { data, loading, error, refresh } = useApiResource(() => request("/workspaces?limit=100"), [request]);

  async function queueRun(workspaceId) {
    setActionState({ workspaceId, message: "", error: "" });
    try {
      const run = await request("/runs", {
        method: "POST",
        body: { workspace_id: workspaceId, execution_mode: "queued", max_attempts: 1 },
      });
      setActionState({
        workspaceId,
        message: `Queued ${run.id}`,
        error: "",
      });
      refresh().catch(() => undefined);
    } catch (runError) {
      setActionState({
        workspaceId,
        message: "",
        error: runError.message || "Unable to queue run.",
      });
    }
  }

  const workspaces = data?.workspaces || [];

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-2">
        <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
          Workspaces
        </h1>
        <p className="text-sm text-on-surface-variant">
          Saved product setups that decide which backend capabilities are active for each run.
        </p>
      </header>

      <section className="grid gap-6 xl:grid-cols-3">
        {loading ? (
          <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 text-on-surface-variant shadow-soft xl:col-span-3">
            Loading workspaces...
          </div>
        ) : error ? (
          <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft xl:col-span-3">
            <p className="text-error">{error}</p>
            <button
              className="mt-4 rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
              onClick={() => refresh().catch(() => undefined)}
              type="button"
            >
              Retry
            </button>
          </div>
        ) : (
          workspaces.map((workspace) => (
            <article
              key={workspace.id}
              className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="font-headline text-xl font-bold text-on-surface">{workspace.name}</h2>
                  <p className="mt-1 text-xs uppercase tracking-wider text-primary">
                    {labelize(workspace.workspace_type)}
                  </p>
                </div>
                <button
                  className="rounded bg-surface-container-low p-2 text-on-surface-variant transition-colors hover:text-primary"
                  type="button"
                >
                  <span className="material-symbols-outlined text-[18px]">more_horiz</span>
                </button>
              </div>

              <p className="mt-4 text-sm leading-7 text-on-surface-variant">{workspace.description}</p>

              <div className="mt-5 space-y-3 text-sm text-on-surface-variant">
                <div>
                  <span className="font-semibold text-on-surface">Workflow:</span>{" "}
                  {workspace.workflow_template_id}
                </div>
                <div>
                  <span className="font-semibold text-on-surface">Sources:</span>{" "}
                  {(workspace.sources || []).map((source) => source.connector_id).join(", ") || "N/A"}
                </div>
                <div>
                  <span className="font-semibold text-on-surface">Features:</span>{" "}
                  {Object.entries(workspace.feature_flags || {})
                    .filter(([, enabled]) => enabled)
                    .map(([key]) => labelize(key.replace(/^enable_/, "")))
                    .join(", ") || "N/A"}
                </div>
              </div>

              {actionState.workspaceId === workspace.id && (actionState.message || actionState.error) ? (
                <div
                  className={[
                    "mt-4 rounded-lg px-4 py-3 text-sm",
                    actionState.error
                      ? "bg-error-container text-on-error-container"
                      : "bg-surface-container-low text-on-surface",
                  ].join(" ")}
                >
                  {actionState.error || actionState.message}
                </div>
              ) : null}

              <div className="mt-6 flex gap-3">
                <button
                  className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90"
                  onClick={() => queueRun(workspace.id)}
                  type="button"
                >
                  Queue Run
                </button>
                <Link
                  className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                  to={`/runs?workspace_id=${workspace.id}`}
                >
                  View Runs
                </Link>
              </div>
            </article>
          ))
        )}
      </section>
    </div>
  );
}
