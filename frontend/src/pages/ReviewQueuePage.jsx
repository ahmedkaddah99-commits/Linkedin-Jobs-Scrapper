import { useMemo, useState } from "react";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { labelize, statusTone } from "../lib/formatters";

function buildApplicationCopyText(profile, row) {
  const candidateName = String(profile?.name || "").trim();
  const candidateEmail = String(profile?.email || "").trim();
  const summary = String(profile?.summary || "").trim();
  return [
    `Name: ${candidateName || "Not set"}`,
    `Email: ${candidateEmail || "Not set"}`,
    `Target Job: ${row.title || "Not set"}${row.company ? ` at ${row.company}` : ""}`,
    "",
    "Summary:",
    summary || "No profile summary saved yet.",
  ].join("\n");
}

function selectPrimaryReferralContact(row) {
  const contacts = Array.isArray(row?.referral_contacts) ? row.referral_contacts : [];
  return contacts.find((contact) => contact.can_refer) || contacts[0] || null;
}

export default function ReviewQueuePage() {
  const { request, user } = useSession();
  const [filters, setFilters] = useState({
    status: "",
    workspaceId: "",
    runId: "",
  });
  const [actionState, setActionState] = useState({ jobId: "", message: "", error: "" });
  const [appliedIds, setAppliedIds] = useState(new Set());
  const [draftComposer, setDraftComposer] = useState({
    open: false,
    mode: "",
    title: "",
    recipientLabel: "",
    message: "",
    metadata: null,
  });

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
  const { data: settingsData } = useApiResource(() => request("/settings"), [request]);

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

  async function markApplied(row) {
    if (!row.review_id) return;
    try {
      await request(`/tracker/${row.review_id}`, {
        method: "PUT",
        body: { tracker_status: "applied" },
      });
      setAppliedIds((prev) => new Set([...prev, row.review_id]));
    } catch {
      // silently swallow — tracker update failure shouldn't block the review queue UX
    }
  }

  async function copyApplicationData(row) {
    const payload = buildApplicationCopyText(settingsData?.profile, row);
    setActionState({ jobId: row.job_id, message: "", error: "" });
    try {
      await navigator.clipboard.writeText(payload);
      setActionState({
        jobId: row.job_id,
        message: "Copied application data.",
        error: "",
      });
    } catch (copyError) {
      setActionState({
        jobId: row.job_id,
        message: "",
        error: copyError.message || "Unable to copy application data.",
      });
    }
  }

  function applyOnCompanySite(row) {
    if (!row.apply_link) {
      setActionState({
        jobId: row.job_id,
        message: "",
        error: "No application URL is available for this job yet.",
      });
      return;
    }
    window.open(row.apply_link, "_blank", "noopener,noreferrer");
    setActionState({
      jobId: row.job_id,
      message: "Opened application link in a new tab.",
      error: "",
    });
  }

  async function generateReferralDraft(row) {
    const contact = selectPrimaryReferralContact(row);
    if (!contact) {
      setActionState({
        jobId: row.job_id,
        message: "",
        error: "No referral contact is saved for this company yet.",
      });
      return;
    }
    setActionState({ jobId: row.job_id, message: "", error: "" });
    try {
      const payload = await request("/outreach/referral-draft", {
        method: "POST",
        body: {
          run_id: row.run_id,
          job_id: row.job_id,
          contact_id: contact.contact_id,
        },
      });
      setDraftComposer({
        open: true,
        mode: "referral",
        title: `Referral outreach for ${row.title}`,
        recipientLabel: contact.name || contact.company || "Referral Contact",
        message: payload.message || "",
        metadata: payload,
      });
      setActionState({
        jobId: row.job_id,
        message: "Referral outreach draft generated.",
        error: "",
      });
    } catch (draftError) {
      setActionState({
        jobId: row.job_id,
        message: "",
        error: draftError.message || "Unable to generate referral outreach draft.",
      });
    }
  }

  async function generateHiringManagerDraft(row) {
    setActionState({ jobId: row.job_id, message: "", error: "" });
    try {
      const payload = await request("/outreach/hiring-manager-draft", {
        method: "POST",
        body: {
          run_id: row.run_id,
          job_id: row.job_id,
        },
      });
      const hiringManager = payload.hiring_manager || {};
      setDraftComposer({
        open: true,
        mode: "hiring_manager",
        title: `Hiring manager outreach for ${row.title}`,
        recipientLabel:
          hiringManager.name || hiringManager.title || row.company || "Hiring Manager",
        message: payload.message || "",
        metadata: payload,
      });
      setActionState({
        jobId: row.job_id,
        message: "Hiring-manager outreach draft generated.",
        error: "",
      });
    } catch (draftError) {
      setActionState({
        jobId: row.job_id,
        message: "",
        error: draftError.message || "Unable to generate hiring-manager outreach draft.",
      });
    }
  }

  async function copyDraftMessage() {
    try {
      await navigator.clipboard.writeText(draftComposer.message || "");
      setActionState({
        jobId: "",
        message: "Outreach message copied.",
        error: "",
      });
    } catch (copyError) {
      setActionState({
        jobId: "",
        message: "",
        error: copyError.message || "Unable to copy outreach message.",
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

      {actionState.jobId === "" && (actionState.message || actionState.error) ? (
        <div
          className={[
            "rounded-xl border px-4 py-3 text-sm",
            actionState.error
              ? "border-error/30 bg-error/10 text-error"
              : "border-primary/20 bg-primary/10 text-primary",
          ].join(" ")}
        >
          {actionState.error || actionState.message}
        </div>
      ) : null}

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
                      {row.has_referral_contact ? (
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <span className="rounded-full bg-teal-500/10 px-2.5 py-1 text-xs font-semibold text-teal-500">
                            You have a contact here
                          </span>
                          <span className="text-xs text-on-surface-variant">
                            {(row.referral_contacts || [])
                              .map((contact) => contact.name)
                              .filter(Boolean)
                              .join(", ")}
                          </span>
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
                        {(row.decision === "approved" || row.status === "approved") && row.review_id ? (
                          appliedIds.has(row.review_id) || row.tracker_status === "applied" || row.tracker_status ? (
                            <span
                              className="flex items-center gap-1 rounded-full bg-teal-500/10 px-2.5 py-1 text-xs font-semibold text-teal-600"
                              title="Already in Tracker"
                            >
                              <span className="material-symbols-outlined text-[14px]">task_alt</span>
                              In Tracker
                            </span>
                          ) : (
                            <button
                              className="flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary transition-colors hover:bg-primary/20"
                              onClick={() => markApplied(row)}
                              title="Mark as Applied and send to Tracker"
                              type="button"
                            >
                              <span className="material-symbols-outlined text-[14px]">send</span>
                              Mark Applied
                            </button>
                          )
                        ) : null}
                        {(row.decision === "approved" || row.status === "approved") ? (
                          <>
                            <button
                              className="ml-2 rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary transition-colors hover:bg-primary/20"
                              onClick={() => applyOnCompanySite(row)}
                              type="button"
                            >
                              Apply
                            </button>
                            <button
                              className="rounded-full bg-surface-container px-2.5 py-1 text-xs font-semibold text-on-surface transition-colors hover:bg-surface-container-high"
                              onClick={() => copyApplicationData(row)}
                              type="button"
                            >
                              Copy Data
                            </button>
                          </>
                        ) : null}
                        {row.has_referral_contact ? (
                          <button
                            className="rounded-full bg-teal-500/10 px-2.5 py-1 text-xs font-semibold text-teal-500 transition-colors hover:bg-teal-500/20"
                            onClick={() => generateReferralDraft(row)}
                            type="button"
                          >
                            Generate Outreach
                          </button>
                        ) : null}
                        <button
                          className="rounded-full bg-surface-container px-2.5 py-1 text-xs font-semibold text-on-surface transition-colors hover:bg-surface-container-high"
                          onClick={() => generateHiringManagerDraft(row)}
                          type="button"
                        >
                          Find Hiring Manager
                        </button>
                        <a
                          className="ml-2 text-sm font-medium text-primary transition-colors hover:text-primary-container"
                          href={row.apply_link || "#"}
                          rel="noreferrer"
                          target={row.apply_link ? "_blank" : undefined}
                        >
                          Open Job
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

      {draftComposer.open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-6 py-10 backdrop-blur-sm">
          <div className="w-full max-w-3xl rounded-2xl border border-outline-variant/20 bg-surface-container-lowest shadow-2xl">
            <div className="flex items-start justify-between gap-4 border-b border-outline-variant/10 px-6 py-5">
              <div>
                <h2 className="font-headline text-2xl font-bold tracking-tight text-on-surface">
                  {draftComposer.title}
                </h2>
                <p className="mt-1 text-sm text-on-surface-variant">
                  Draft for {draftComposer.recipientLabel}
                </p>
              </div>
              <button
                className="rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container-low hover:text-on-surface"
                onClick={() =>
                  setDraftComposer({
                    open: false,
                    mode: "",
                    title: "",
                    recipientLabel: "",
                    message: "",
                    metadata: null,
                  })
                }
                type="button"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>

            <div className="space-y-4 px-6 py-5">
              {draftComposer.mode === "hiring_manager" ? (
                <div className="rounded-xl bg-surface-container-low p-4 text-sm text-on-surface-variant">
                  <div className="font-medium text-on-surface">Hiring manager signal</div>
                  <div className="mt-1">
                    {draftComposer.metadata?.hiring_manager?.name ||
                      draftComposer.metadata?.hiring_manager?.title ||
                      "No named manager found; using a generic hiring-manager draft."}
                  </div>
                  {draftComposer.metadata?.hiring_manager?.confidence ? (
                    <div className="mt-1 text-xs uppercase tracking-wider">
                      Confidence: {draftComposer.metadata.hiring_manager.confidence}
                    </div>
                  ) : null}
                </div>
              ) : null}

              <textarea
                className="min-h-56 w-full rounded-xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm leading-7 text-on-surface"
                onChange={(event) =>
                  setDraftComposer((current) => ({ ...current, message: event.target.value }))
                }
                value={draftComposer.message}
              />
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-outline-variant/10 px-6 py-4">
              <div className="text-xs text-on-surface-variant">
                Edit the draft here, then copy and send it yourself.
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  className="rounded bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                  onClick={copyDraftMessage}
                  type="button"
                >
                  Copy Message
                </button>
                <button
                  className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90"
                  onClick={() =>
                    setDraftComposer({
                      open: false,
                      mode: "",
                      title: "",
                      recipientLabel: "",
                      message: "",
                      metadata: null,
                    })
                  }
                  type="button"
                >
                  Done
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
