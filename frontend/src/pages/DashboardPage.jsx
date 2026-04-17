import { Link, useNavigate } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { formatDateTime, labelize, statusTone } from "../lib/formatters";

export default function DashboardPage() {
  const navigate = useNavigate();
  const { request } = useSession();
  const { data, loading, error, refresh } = useApiResource(() => request("/dashboard"), [request]);
  const cards = data?.cards || [];
  const recentRuns = data?.recent_runs || [];

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-2">
        <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
          Dashboard
        </h1>
        <p className="text-sm text-on-surface-variant">
          Live operational overview for workspaces, runs, workers, and review backlog.
        </p>
      </header>

      <section className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        {(cards.length
          ? cards
          : [
              { label: "Queued Runs", value: "N/A" },
              { label: "Running Workers", value: "N/A" },
              { label: "Jobs Waiting Review", value: "N/A" },
              { label: "Completed Today", value: "N/A" },
            ]).map((card) => (
          <div
            key={card.label}
            className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft"
          >
            <p className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
              {card.label}
            </p>
            <p className="mt-3 font-headline text-4xl font-extrabold tracking-tight text-on-surface">
              {card.value ?? "N/A"}
            </p>
          </div>
        ))}
      </section>

      <section className="overflow-hidden rounded-xl border border-outline-variant/20 bg-surface-container-lowest">
        <div className="flex items-center justify-between border-b border-outline-variant/10 px-6 py-4">
          <div>
            <h2 className="font-headline text-xl font-bold text-on-surface">Recent Runs</h2>
            <p className="text-sm text-on-surface-variant">Latest activity across all workspaces.</p>
          </div>
          <button
            className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
            onClick={() => navigate("/runs")}
            type="button"
          >
            View All Runs
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface-container-low text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
              <tr>
                <th className="px-6 py-4">Run</th>
                <th className="px-6 py-4">Workspace</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4">Current Stage</th>
                <th className="px-6 py-4">Attempts</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <tr>
                  <td className="px-6 py-10 text-on-surface-variant" colSpan={6}>
                    Loading dashboard data...
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td className="px-6 py-10" colSpan={6}>
                    <div className="flex items-center justify-between gap-4">
                      <span className="text-error">{error}</span>
                      <button
                        className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
                        onClick={() => refresh().catch(() => undefined)}
                        type="button"
                      >
                        Retry
                      </button>
                    </div>
                  </td>
                </tr>
              ) : recentRuns.length ? (
                recentRuns.map((run) => (
                  <tr key={run.id} className="hover:bg-surface-container-low">
                    <td className="px-6 py-4 font-semibold text-on-surface">{run.id}</td>
                    <td className="px-6 py-4 text-on-surface-variant">{run.workspace_name}</td>
                    <td className="px-6 py-4">
                      <StatusBadge tone={statusTone(run.status)}>{labelize(run.status)}</StatusBadge>
                    </td>
                    <td className="px-6 py-4 text-on-surface-variant">{labelize(run.current_stage)}</td>
                    <td className="px-6 py-4 text-on-surface-variant">
                      {run.attempt_count}/{run.max_attempts} / {formatDateTime(run.updated_at)}
                    </td>
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
                    No runs exist yet. Start one from the Workspaces page.
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
