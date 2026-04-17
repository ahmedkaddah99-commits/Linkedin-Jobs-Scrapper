import { Link, useSearchParams } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { formatDateTime, labelize, statusTone } from "../lib/formatters";

export default function RunsPage() {
  const { request } = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const workspaceId = searchParams.get("workspace_id") || "";
  const status = searchParams.get("status") || "";

  const { data, loading, error, refresh } = useApiResource(
    () =>
      request(`/runs?limit=100&workspace_id=${encodeURIComponent(workspaceId)}&status=${encodeURIComponent(status)}`),
    [request, workspaceId, status],
  );

  const runs = data?.runs || [];

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
        <div className="grid gap-4 md:grid-cols-3">
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
        </div>
      </section>

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
                    <td className="px-6 py-4 text-on-surface-variant">{formatDateTime(run.updated_at)}</td>
                    <td className="px-6 py-4 text-right">
                      <Link
                        className="text-sm font-medium text-primary transition-colors hover:text-primary-container"
                        to={`/runs/${run.id}`}
                      >
                        Open
                      </Link>
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
