import { useMemo, useState } from "react";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { labelize, statusTone } from "../lib/formatters";

export default function ReviewQueuePage() {
  const { request, user } = useSession();
  const [filters, setFilters] = useState({
    status: "",
    workspaceId: "",
    runId: "",
  });
  const [actionState, setActionState] = useState({ jobId: "", message: "", error: "" });

  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    params.set("limit", "200");
    if (filters.status) params.set("status", filters.status);
    if (filters.workspaceId) params.set("workspace_id", filters.workspaceId);
    if (filters.runId) params.set("run_id", filters.runId);
    return params.toString();
  }, [filters]);

  const { data, loading, error, refresh } = useApiResource(
    () => request(`/review-queue?${queryString}`),
    [request, queryString],
  );

  const rows = data?.items || [];
  const workspaceOptions = Array.from(
    new Map(rows.map((row) => [row.workspace_id, row.workspace_name])).entries(),
  );
  const runOptions = Array.from(new Set(rows.map((row) => row.run_id)));

  async function submitDecision(row, decision) {
    setActionState({ jobId: row.job_id, message: "", error: "" });
    const payload = {
      job_id: row.job_id,
      status: decision === "approved" ? "approved" : "rejected",
      decision,
      reviewer: user?.display_name || user?.email || "frontend_user",
      notes: row.notes || "",
      job_set_key: row.job_set_key,
    };
    try {
      if (row.review_id) {
        await request(`/runs/${row.run_id}/reviews/${row.review_id}`, {
          method: "PUT",
          body: payload,
        });
      } else {
        await request(`/runs/${row.run_id}/reviews`, {
          method: "POST",
          body: payload,
        });
      }
      setActionState({
        jobId: row.job_id,
        message: decision === "approved" ? "Approved." : "Rejected.",
        error: "",
      });
      refresh().catch(() => undefined);
    } catch (reviewError) {
      setActionState({
        jobId: row.job_id,
        message: "",
        error: reviewError.message || "Unable to update review.",
      });
    }
  }

  return (
    <div className="space-y-8">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="font-headline text-[2.25rem] font-extrabold leading-tight tracking-tight text-on-surface">
            Review Queue
          </h1>
          <p className="mt-1 text-sm text-on-surface-variant">
            Verify and approve extracted job artifacts.
          </p>
        </div>
        <button
          className="flex items-center gap-2 rounded bg-surface-container-high px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-surface-container-low active:scale-[0.98]"
          onClick={() => refresh().catch(() => undefined)}
          type="button"
        >
          <span className="material-symbols-outlined text-sm">refresh</span>
          Refresh
        </button>
      </header>

      <section className="rounded-xl bg-surface-container-low p-4">
        <div className="flex flex-wrap items-center gap-4">
          {[
            {
              label: "Status",
              control: (
                <select
                  className="w-full appearance-none rounded border border-outline-variant/20 bg-surface-container-lowest p-2.5 pr-8 text-sm text-on-surface focus:border-primary-container focus:ring-2 focus:ring-primary-container/30"
                  onChange={(event) =>
                    setFilters((current) => ({ ...current, status: event.target.value }))
                  }
                  value={filters.status}
                >
                  <option value="">All Statuses</option>
                  <option value="waiting_review">Waiting Review</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                </select>
              ),
            },
            {
              label: "Workspace",
              control: (
                <select
                  className="w-full appearance-none rounded border border-outline-variant/20 bg-surface-container-lowest p-2.5 pr-8 text-sm text-on-surface focus:border-primary-container focus:ring-2 focus:ring-primary-container/30"
                  onChange={(event) =>
                    setFilters((current) => ({ ...current, workspaceId: event.target.value }))
                  }
                  value={filters.workspaceId}
                >
                  <option value="">All Workspaces</option>
                  {workspaceOptions.map(([id, name]) => (
                    <option key={id} value={id}>
                      {name}
                    </option>
                  ))}
                </select>
              ),
            },
            {
              label: "Run",
              control: (
                <select
                  className="w-full appearance-none rounded border border-outline-variant/20 bg-surface-container-lowest p-2.5 pr-8 text-sm text-on-surface focus:border-primary-container focus:ring-2 focus:ring-primary-container/30"
                  onChange={(event) =>
                    setFilters((current) => ({ ...current, runId: event.target.value }))
                  }
                  value={filters.runId}
                >
                  <option value="">All Runs</option>
                  {runOptions.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              ),
            },
            {
              label: "Date Range",
              control: (
                <div className="relative">
                  <input
                    className="w-full rounded border border-outline-variant/20 bg-surface-container-lowest p-2.5 pl-10 text-sm text-on-surface focus:border-primary-container focus:ring-2 focus:ring-primary-container/30"
                    placeholder="Last 7 days"
                    type="text"
                  />
                  <span className="material-symbols-outlined absolute left-2.5 top-2.5 text-slate-400">
                    calendar_today
                  </span>
                </div>
              ),
            },
          ].map((field) => (
            <div key={field.label} className="min-w-[200px] flex-1">
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
                {field.label}
              </label>
              <div className="relative">
                {field.control}
                {field.label !== "Date Range" ? (
                  <span className="material-symbols-outlined pointer-events-none absolute right-2.5 top-2.5 text-slate-400">
                    expand_more
                  </span>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="overflow-hidden rounded-xl border border-outline-variant/20 bg-surface-container-lowest">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-surface-container bg-surface-container-low text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
              <tr>
                <th className="px-6 py-4">Job Details</th>
                <th className="px-6 py-4">Context</th>
                <th className="px-6 py-4">Source</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-container">
              {loading ? (
                <tr>
                  <td className="px-6 py-10 text-on-surface-variant" colSpan={5}>
                    Loading review queue...
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td className="px-6 py-10 text-error" colSpan={5}>
                    {error}
                  </td>
                </tr>
              ) : rows.length ? (
                rows.map((row) => (
                  <tr key={`${row.run_id}-${row.job_id}`} className="group transition-colors hover:bg-surface-container-high">
                    <td className="px-6 py-4">
                      <div className="mb-1 text-base font-medium text-on-surface">{row.title}</div>
                      <div className="flex items-center gap-1.5 text-on-surface-variant">
                        <span className="material-symbols-outlined text-[1rem]">business</span>
                        {row.company || "Unknown Company"}
                      </div>
                      {row.manual_approved ? (
                        <div className="mt-2 text-xs font-medium text-primary">
                          Manual URL • Filtering bypassed
                        </div>
                      ) : null}
                    </td>
                    <td className="px-6 py-4">
                      <div className="mb-1 text-on-surface">{row.workspace_name}</div>
                      <div className="inline-block rounded bg-surface px-1.5 py-0.5 font-mono text-xs text-on-surface-variant">
                        {row.run_id}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="mt-2 flex items-center gap-2 text-on-surface-variant">
                        <span className="material-symbols-outlined text-slate-400">
                          {row.source_type === "manual_url" ? "language" : "link"}
                        </span>
                        {labelize(row.source_label)}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge tone={statusTone(row.status)}>{labelize(row.status)}</StatusBadge>
                      <div className="mt-1.5 flex items-center gap-1 text-xs text-on-surface-variant">
                        <span className="material-symbols-outlined text-[12px]">description</span>
                        {row.artifact_status === "artifact_ready" ? "Artifact Ready" : "No Artifacts"}
                      </div>
                      {actionState.jobId === row.job_id && (actionState.message || actionState.error) ? (
                        <div
                          className={[
                            "mt-2 text-xs",
                            actionState.error ? "text-error" : "text-primary",
                          ].join(" ")}
                        >
                          {actionState.error || actionState.message}
                        </div>
                      ) : null}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2 opacity-0 transition-opacity group-hover:opacity-100">
                        <button
                          className="flex h-8 w-8 items-center justify-center rounded-full bg-surface-container text-on-surface-variant transition-colors hover:bg-error-container hover:text-on-error-container"
                          onClick={() => submitDecision(row, "rejected")}
                          title="Reject"
                          type="button"
                        >
                          <span className="material-symbols-outlined text-[1.2rem]">close</span>
                        </button>
                        <button
                          className="flex h-8 w-8 items-center justify-center rounded-full bg-surface-container text-on-surface-variant transition-colors hover:bg-primary-fixed-dim/30 hover:text-primary"
                          onClick={() => submitDecision(row, "approved")}
                          title="Approve"
                          type="button"
                        >
                          <span className="material-symbols-outlined text-[1.2rem]">check</span>
                        </button>
                        <a
                          className="ml-2 text-sm font-medium text-primary transition-colors hover:text-primary-container"
                          href={row.apply_link || "#"}
                          rel="noreferrer"
                          target={row.apply_link ? "_blank" : undefined}
                        >
                          Review
                        </a>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-6 py-10 text-on-surface-variant" colSpan={5}>
                    No jobs are waiting in the review queue.
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
