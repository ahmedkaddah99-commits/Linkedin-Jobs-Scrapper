import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { logEvent } from "../lib/analytics";
import { labelize, statusTone } from "../lib/formatters";
import { buildJobWorkspaceRoute } from "../lib/peopleDiscovery";

const REFERRAL_OUTREACH_STATUSES = [
  "Not contacted",
  "Contacted",
  "Replied",
  "Referral offered",
  "No referral",
];

const EMPTY_DRAFT_COMPOSER = {
  open: false,
  mode: "",
  title: "",
  recipientLabel: "",
  message: "",
  metadata: null,
};

const EMPTY_COMPOSER_FEEDBACK = {
  message: "",
  error: "",
};

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

function referralRowKey(row) {
  return `${row.run_id}::${row.job_id}`;
}

function companyEntries(contact) {
  if (Array.isArray(contact?.companies) && contact.companies.length) {
    return contact.companies;
  }
  if (contact?.company) {
    return [{ company_name: contact.company, role_title: "" }];
  }
  return [];
}

function referralStatusTone(status) {
  switch (status) {
    case "Contacted":
      return "primary";
    case "Replied":
    case "Referral offered":
      return "success";
    case "No referral":
      return "warning";
    default:
      return "neutral";
  }
}

export default function ReviewQueuePage() {
  const { request, user } = useSession();
  const [searchParams] = useSearchParams();
  const [filters, setFilters] = useState(() => ({
    status: searchParams.get("status") || "",
    workspaceId: searchParams.get("workspace_id") || "",
    runId: searchParams.get("run_id") || "",
  }));
  const [actionState, setActionState] = useState({ scope: "", message: "", error: "" });
  const [appliedIds, setAppliedIds] = useState(new Set());
  const [draftComposer, setDraftComposer] = useState(EMPTY_DRAFT_COMPOSER);
  const [composerFeedback, setComposerFeedback] = useState(EMPTY_COMPOSER_FEEDBACK);
  const [expandedReferralRows, setExpandedReferralRows] = useState({});
  const [selectedReferralContacts, setSelectedReferralContacts] = useState({});
  const [bulkOutreachStatusByRow, setBulkOutreachStatusByRow] = useState({});
  const [pendingScopes, setPendingScopes] = useState({});

  useEffect(() => {
    const nextFilters = {
      status: searchParams.get("status") || "",
      workspaceId: searchParams.get("workspace_id") || "",
      runId: searchParams.get("run_id") || "",
    };
    setFilters((current) => {
      if (
        current.status === nextFilters.status &&
        current.workspaceId === nextFilters.workspaceId &&
        current.runId === nextFilters.runId
      ) {
        return current;
      }
      return nextFilters;
    });
  }, [searchParams]);

  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    params.set("limit", "200");
    if (filters.status) params.set("status", filters.status);
    if (filters.workspaceId) params.set("workspace_id", filters.workspaceId);
    if (filters.runId) params.set("run_id", filters.runId);
    return params.toString();
  }, [filters]);

  const { data, loading, error, refresh, setData } = useApiResource(
    () => request(`/review-queue?${queryString}`),
    [request, queryString],
  );
  const { data: settingsData } = useApiResource(() => request("/settings"), [request]);

  const rows = data?.items || [];
  const workspaceOptions = Array.from(
    new Map(rows.map((row) => [row.workspace_id, row.workspace_name])).entries(),
  );
  const runOptions = Array.from(new Set(rows.map((row) => row.run_id)));

  function setFeedback(scope, patch) {
    setActionState({
      scope,
      message: patch?.message || "",
      error: patch?.error || "",
    });
  }

  function setScopePending(scope, isPending) {
    setPendingScopes((current) => {
      if (isPending) {
        return { ...current, [scope]: true };
      }
      const next = { ...current };
      delete next[scope];
      return next;
    });
  }

  function closeDraftComposer() {
    setDraftComposer(EMPTY_DRAFT_COMPOSER);
    setComposerFeedback(EMPTY_COMPOSER_FEEDBACK);
  }

  function setReferralContactStatuses(row, contactIds, outreachStatus) {
    const targetIds = new Set(contactIds);
    setData((current) => {
      if (!current) return current;
      return {
        ...current,
        items: (current.items || []).map((item) => {
          if (item.run_id !== row.run_id || item.job_id !== row.job_id) {
            return item;
          }
          return {
            ...item,
            referral_contacts: (item.referral_contacts || []).map((contact) =>
              targetIds.has(contact.contact_id)
                ? { ...contact, outreach_status: outreachStatus }
                : contact,
            ),
          };
        }),
      };
    });
  }

  function toggleReferralPanel(row) {
    const rowKey = referralRowKey(row);
    setExpandedReferralRows((current) => ({
      ...current,
      [rowKey]: !current[rowKey],
    }));
  }

  function selectedContactIdsForRow(row) {
    return selectedReferralContacts[referralRowKey(row)] || [];
  }

  function selectedContactsForRow(row) {
    const selectedIds = new Set(selectedContactIdsForRow(row));
    return (row.referral_contacts || []).filter((contact) => selectedIds.has(contact.contact_id));
  }

  function setSelectedContacts(row, contactIds) {
    const rowKey = referralRowKey(row);
    setSelectedReferralContacts((current) => {
      if (!contactIds.length) {
        const next = { ...current };
        delete next[rowKey];
        return next;
      }
      return {
        ...current,
        [rowKey]: Array.from(new Set(contactIds)),
      };
    });
  }

  function toggleContactSelection(row, contactId) {
    const currentIds = new Set(selectedContactIdsForRow(row));
    if (currentIds.has(contactId)) {
      currentIds.delete(contactId);
    } else {
      currentIds.add(contactId);
    }
    setSelectedContacts(row, Array.from(currentIds));
  }

  function openLinkedInProfiles(row, contacts, scope = `panel:${referralRowKey(row)}`) {
    const urls = contacts
      .map((contact) => String(contact?.linkedin_url || "").trim())
      .filter(Boolean);
    if (!urls.length) {
      setFeedback(scope, {
        error:
          contacts.length > 1
            ? "No LinkedIn profile URLs are saved for the selected contacts."
            : "No LinkedIn profile URL is saved for this contact yet.",
      });
      return;
    }
    urls.forEach((url) => window.open(url, "_blank", "noopener,noreferrer"));
    setFeedback(scope, {
      message: `Opened ${urls.length} LinkedIn profile${urls.length === 1 ? "" : "s"}.`,
    });
  }

  async function persistOutreachStatus(
    row,
    contactIds,
    outreachStatus,
    { pendingKey, feedbackScope, successMessage },
  ) {
    if (!contactIds.length) {
      setFeedback(feedbackScope, { error: "Select at least one referral contact first." });
      return;
    }
    setScopePending(pendingKey, true);
    try {
      await Promise.all(
        contactIds.map((contactId) =>
          request("/referrals/outreach-status", {
            method: "POST",
            body: {
              run_id: row.run_id,
              job_id: row.job_id,
              contact_id: contactId,
              outreach_status: outreachStatus,
            },
          }),
        ),
      );
      setReferralContactStatuses(row, contactIds, outreachStatus);
      setFeedback(feedbackScope, {
        message:
          successMessage ||
          `Updated ${contactIds.length} referral outreach status${contactIds.length === 1 ? "" : "es"}.`,
      });
    } catch (statusError) {
      setFeedback(feedbackScope, {
        error: statusError.message || "Unable to update referral outreach status.",
      });
    } finally {
      setScopePending(pendingKey, false);
    }
  }

  async function submitDecision(row, decision) {
    const feedbackScope = `job:${referralRowKey(row)}`;
    setFeedback(feedbackScope, {});
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
      logEvent("review_decision_submitted", {
        decision,
        job_id: row.job_id,
      });
      setFeedback(feedbackScope, {
        message: decision === "approved" ? "Approved." : "Rejected.",
      });
      refresh().catch(() => undefined);
    } catch (reviewError) {
      setFeedback(feedbackScope, {
        error: reviewError.message || "Unable to update review.",
      });
    }
  }

  async function deleteJob(row) {
    const rowKey = referralRowKey(row);
    const feedbackScope = `job:${rowKey}`;
    const pendingKey = `delete:${rowKey}`;
    const confirmed = window.confirm(
      `Delete ${row.title || "this job"} from run ${row.run_id}? This removes the job, its review state, and linked tracker entry.`,
    );
    if (!confirmed) {
      return;
    }
    setScopePending(pendingKey, true);
    setFeedback(feedbackScope, {});
    try {
      await request(`/runs/${row.run_id}/jobs/by-id/${row.job_id}`, {
        method: "DELETE",
      });
      setData((current) => {
        if (!current) return current;
        return {
          ...current,
          items: (current.items || []).filter(
            (item) => !(item.run_id === row.run_id && item.job_id === row.job_id),
          ),
        };
      });
      setFeedback(feedbackScope, { message: "Deleted job." });
    } catch (deleteError) {
      setFeedback(feedbackScope, {
        error: deleteError.message || "Unable to delete this job.",
      });
    } finally {
      setScopePending(pendingKey, false);
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
      // Tracker update failure should not block the review queue workflow.
    }
  }

  async function copyApplicationData(row) {
    const payload = buildApplicationCopyText(settingsData?.profile, row);
    const feedbackScope = `job:${referralRowKey(row)}`;
    setFeedback(feedbackScope, {});
    try {
      await navigator.clipboard.writeText(payload);
      setFeedback(feedbackScope, { message: "Copied application data." });
    } catch (copyError) {
      setFeedback(feedbackScope, {
        error: copyError.message || "Unable to copy application data.",
      });
    }
  }

  function applyOnCompanySite(row) {
    const feedbackScope = `job:${referralRowKey(row)}`;
    if (!row.apply_link) {
      setFeedback(feedbackScope, {
        error: "No application URL is available for this job yet.",
      });
      return;
    }
    window.open(row.apply_link, "_blank", "noopener,noreferrer");
    logEvent("apply_link_opened", {
      job_id: row.job_id,
      source: row.source_type || "unknown",
      portal: row.source_label || row.source_type || "unknown",
    });
    setFeedback(feedbackScope, {
      message: "Opened application link in a new tab.",
    });
  }

  async function generateReferralDraft(row, contact) {
    const rowKey = referralRowKey(row);
    const pendingKey = `draft:${rowKey}:${contact.contact_id}`;
    const feedbackScope = `panel:${rowKey}`;
    setScopePending(pendingKey, true);
    setFeedback(feedbackScope, {});
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
      setComposerFeedback(EMPTY_COMPOSER_FEEDBACK);
      setFeedback(feedbackScope, {
        message: `Referral outreach draft generated for ${contact.name || "this contact"}.`,
      });
    } catch (draftError) {
      setFeedback(feedbackScope, {
        error: draftError.message || "Unable to generate referral outreach draft.",
      });
    } finally {
      setScopePending(pendingKey, false);
    }
  }

  async function generateSelectedReferralDraft(row) {
    const selectedContacts = selectedContactsForRow(row);
    const feedbackScope = `panel:${referralRowKey(row)}`;
    if (selectedContacts.length !== 1) {
      setFeedback(feedbackScope, {
        error: "Select exactly one referral contact to generate a draft.",
      });
      return;
    }
    await generateReferralDraft(row, selectedContacts[0]);
  }

  async function generateHiringManagerDraft(row) {
    const feedbackScope = `job:${referralRowKey(row)}`;
    setFeedback(feedbackScope, {});
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
      setComposerFeedback(EMPTY_COMPOSER_FEEDBACK);
      setFeedback(feedbackScope, {
        message: "Hiring-manager outreach draft generated.",
      });
    } catch (draftError) {
      setFeedback(feedbackScope, {
        error: draftError.message || "Unable to generate hiring-manager outreach draft.",
      });
    }
  }

  async function copyDraftMessage() {
    try {
      await navigator.clipboard.writeText(draftComposer.message || "");
      setComposerFeedback({ message: "Outreach message copied.", error: "" });
    } catch (copyError) {
      setComposerFeedback({
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
            Generated jobs land here automatically. Use this queue to update tracker status, notes, and outreach.
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

      {actionState.scope === "global" && (actionState.message || actionState.error) ? (
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
                rows.map((row) => {
                  const rowKey = referralRowKey(row);
                  const jobFeedbackScope = `job:${rowKey}`;
                  const panelFeedbackScope = `panel:${rowKey}`;
                  const deletePending = Boolean(pendingScopes[`delete:${rowKey}`]);
                  const isReferralPanelOpen = Boolean(expandedReferralRows[rowKey]);
                  const selectedContacts = selectedContactsForRow(row);
                  const selectedLinkedInCount = selectedContacts.filter((contact) => contact.linkedin_url).length;
                  const bulkStatus = bulkOutreachStatusByRow[rowKey] || "";
                  const jobWorkspaceUrl =
                    row.job_workspace_url || buildJobWorkspaceRoute({ runId: row.run_id, jobId: row.job_id });
                  const panelFeedback =
                    actionState.scope === panelFeedbackScope && (actionState.message || actionState.error)
                      ? actionState
                      : null;

                  return (
                    <Fragment key={rowKey}>
                      <tr className="group transition-colors hover:bg-surface-container-high">
                        <td className="px-6 py-4">
                          <div className="mb-1 text-base font-medium text-on-surface">{row.title}</div>
                          <div className="flex items-center gap-1.5 text-on-surface-variant">
                            <span className="material-symbols-outlined text-[1rem]">business</span>
                            {row.company || "Unknown Company"}
                          </div>
                          {row.manual_approved ? (
                            <div className="mt-2 text-xs font-medium text-primary">
                              Manual URL | Filtering bypassed
                            </div>
                          ) : null}
                          {row.has_referral_contact ? (
                            <div className="mt-2 flex flex-wrap items-center gap-2">
                              <span className="rounded-full bg-teal-500/10 px-2.5 py-1 text-xs font-semibold text-teal-500">
                                You have {row.referral_contacts?.length || 0} contact
                                {row.referral_contacts?.length === 1 ? "" : "s"} here
                              </span>
                              <span className="text-xs text-on-surface-variant">
                                {(row.referral_contacts || [])
                                  .map((contact) => contact.name)
                                  .filter(Boolean)
                                  .join(", ")}
                              </span>
                              <button
                                className="inline-flex items-center gap-1 rounded-full bg-surface-container px-2.5 py-1 text-xs font-semibold text-on-surface transition-colors hover:bg-surface-container-high"
                                onClick={() => toggleReferralPanel(row)}
                                type="button"
                              >
                                <span className="material-symbols-outlined text-[14px]">
                                  {isReferralPanelOpen ? "expand_less" : "expand_more"}
                                </span>
                                {isReferralPanelOpen ? "Hide Matches" : "Manage Matches"}
                              </button>
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
                            {row.artifact_status === "artifact_ready" ? "Documents Ready" : "No Documents"}
                          </div>
                          {actionState.scope === jobFeedbackScope && (actionState.message || actionState.error) ? (
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
                          <div className="flex flex-wrap items-center justify-end gap-2 opacity-0 transition-opacity group-hover:opacity-100">
                            <button
                              className="flex items-center gap-1 rounded-full bg-error/10 px-2.5 py-1 text-xs font-semibold text-error transition-colors hover:bg-error/20 disabled:cursor-not-allowed disabled:opacity-60"
                              disabled={deletePending}
                              onClick={() => deleteJob(row)}
                              type="button"
                            >
                              <span className="material-symbols-outlined text-[14px]">delete</span>
                              {deletePending ? "Deleting..." : "Delete"}
                            </button>
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
                                  className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary transition-colors hover:bg-primary/20"
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
                                onClick={() => toggleReferralPanel(row)}
                                type="button"
                              >
                                {isReferralPanelOpen ? "Hide Referrals" : "Review Referrals"}
                              </button>
                            ) : null}
                            <button
                              className="rounded-full bg-surface-container px-2.5 py-1 text-xs font-semibold text-on-surface transition-colors hover:bg-surface-container-high"
                              onClick={() => generateHiringManagerDraft(row)}
                              type="button"
                            >
                              Find Hiring Manager
                            </button>
                            <Link
                              className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary transition-colors hover:bg-primary/20"
                              to={jobWorkspaceUrl}
                            >
                              Relevant People
                            </Link>
                            <a
                              className="text-sm font-medium text-primary transition-colors hover:text-primary-container"
                              href={row.apply_link || "#"}
                              rel="noreferrer"
                              target={row.apply_link ? "_blank" : undefined}
                            >
                              Open Job
                            </a>
                          </div>
                        </td>
                      </tr>
                      {row.has_referral_contact && isReferralPanelOpen ? (
                        <tr>
                          <td className="bg-surface-container-low px-6 py-5" colSpan={5}>
                            <div className="space-y-5 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5">
                              <div className="flex flex-wrap items-start justify-between gap-4">
                                <div>
                                  <div className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
                                    Referral Matches
                                  </div>
                                  <h3 className="mt-1 text-lg font-semibold text-on-surface">
                                    {row.company || "This company"} referral context
                                  </h3>
                                  <p className="mt-1 text-sm text-on-surface-variant">
                                    Choose all, some, or one contact to act on. Status is stored per run, job, and contact.
                                  </p>
                                </div>
                                <div className="flex flex-wrap items-center gap-2 text-xs">
                                  <button
                                    className="rounded-full bg-surface-container px-3 py-1.5 font-semibold text-on-surface transition-colors hover:bg-surface-container-high"
                                    onClick={() =>
                                      setSelectedContacts(
                                        row,
                                        (row.referral_contacts || []).map((contact) => contact.contact_id),
                                      )
                                    }
                                    type="button"
                                  >
                                    Select All
                                  </button>
                                  <button
                                    className="rounded-full bg-surface-container px-3 py-1.5 font-semibold text-on-surface transition-colors hover:bg-surface-container-high"
                                    onClick={() =>
                                      setSelectedContacts(
                                        row,
                                        (row.referral_contacts || [])
                                          .filter((contact) => contact.can_refer)
                                          .map((contact) => contact.contact_id),
                                      )
                                    }
                                    type="button"
                                  >
                                    Select Referable
                                  </button>
                                  <button
                                    className="rounded-full bg-surface-container px-3 py-1.5 font-semibold text-on-surface transition-colors hover:bg-surface-container-high"
                                    onClick={() => setSelectedContacts(row, [])}
                                    type="button"
                                  >
                                    Clear
                                  </button>
                                </div>
                              </div>

                              <div className="grid gap-3 rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4 lg:grid-cols-[1.2fr_1fr_auto_auto]">
                                <div>
                                  <div className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
                                    Selected Contacts
                                  </div>
                                  <div className="mt-1 text-sm text-on-surface">
                                    {selectedContacts.length
                                      ? `${selectedContacts.length} selected`
                                      : "No contacts selected yet."}
                                  </div>
                                  <div className="mt-1 text-xs text-on-surface-variant">
                                    {selectedLinkedInCount
                                      ? `${selectedLinkedInCount} selected contact${selectedLinkedInCount === 1 ? " has" : "s have"} a LinkedIn URL saved.`
                                      : "Open LinkedIn is available when a selected contact has a saved profile URL."}
                                  </div>
                                </div>
                                <label className="space-y-1">
                                  <div className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
                                    Bulk Status
                                  </div>
                                  <select
                                    className="w-full rounded-lg border border-outline-variant/20 bg-surface px-3 py-2 text-sm text-on-surface"
                                    onChange={(event) =>
                                      setBulkOutreachStatusByRow((current) => ({
                                        ...current,
                                        [rowKey]: event.target.value,
                                      }))
                                    }
                                    value={bulkStatus}
                                  >
                                    <option value="">Choose status...</option>
                                    {REFERRAL_OUTREACH_STATUSES.map((statusValue) => (
                                      <option key={statusValue} value={statusValue}>
                                        {statusValue}
                                      </option>
                                    ))}
                                  </select>
                                </label>
                                <button
                                  className="rounded-lg bg-primary/10 px-4 py-2 text-sm font-semibold text-primary transition-colors hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-60"
                                  disabled={!selectedContacts.length || !selectedLinkedInCount}
                                  onClick={() => openLinkedInProfiles(row, selectedContacts)}
                                  type="button"
                                >
                                  Open Selected LinkedIn
                                </button>
                                <div className="flex flex-wrap gap-2">
                                  <button
                                    className="rounded-lg bg-surface-container px-4 py-2 text-sm font-semibold text-on-surface transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-60"
                                    disabled={
                                      selectedContacts.length !== 1 ||
                                      Boolean(pendingScopes[`bulk-draft:${rowKey}`])
                                    }
                                    onClick={() => {
                                      setScopePending(`bulk-draft:${rowKey}`, true);
                                      generateSelectedReferralDraft(row).finally(() =>
                                        setScopePending(`bulk-draft:${rowKey}`, false),
                                      );
                                    }}
                                    type="button"
                                  >
                                    Draft Selected
                                  </button>
                                  <button
                                    className="rounded-lg bg-gradient-to-br from-primary to-primary-container px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                                    disabled={
                                      !selectedContacts.length ||
                                      !bulkStatus ||
                                      Boolean(pendingScopes[`bulk-status:${rowKey}`])
                                    }
                                    onClick={() =>
                                      persistOutreachStatus(
                                        row,
                                        selectedContacts.map((contact) => contact.contact_id),
                                        bulkStatus,
                                        {
                                          pendingKey: `bulk-status:${rowKey}`,
                                          feedbackScope: panelFeedbackScope,
                                          successMessage: `Updated ${selectedContacts.length} selected contact${selectedContacts.length === 1 ? "" : "s"} to ${bulkStatus}.`,
                                        },
                                      )
                                    }
                                    type="button"
                                  >
                                    {pendingScopes[`bulk-status:${rowKey}`] ? "Saving..." : "Update Selected"}
                                  </button>
                                </div>
                              </div>

                              {panelFeedback ? (
                                <div
                                  className={[
                                    "rounded-xl border px-4 py-3 text-sm",
                                    panelFeedback.error
                                      ? "border-error/30 bg-error/10 text-error"
                                      : "border-primary/20 bg-primary/10 text-primary",
                                  ].join(" ")}
                                >
                                  {panelFeedback.error || panelFeedback.message}
                                </div>
                              ) : null}

                              <div className="grid gap-4 lg:grid-cols-2">
                                {(row.referral_contacts || []).map((contact) => {
                                  const contactSelectionScope = `status:${rowKey}:${contact.contact_id}`;
                                  const contactDraftScope = `draft:${rowKey}:${contact.contact_id}`;
                                  const isSelected = selectedContactIdsForRow(row).includes(contact.contact_id);
                                  const companies = companyEntries(contact);

                                  return (
                                    <article
                                      key={contact.contact_id}
                                      className={[
                                        "rounded-2xl border p-4 transition-colors",
                                        isSelected
                                          ? "border-teal-500/30 bg-teal-500/5"
                                          : "border-outline-variant/20 bg-surface",
                                      ].join(" ")}
                                    >
                                      <div className="flex items-start justify-between gap-3">
                                        <label className="flex items-start gap-3">
                                          <input
                                            checked={isSelected}
                                            className="mt-1 h-4 w-4 rounded border-outline-variant/30 text-primary focus:ring-primary/20"
                                            onChange={() => toggleContactSelection(row, contact.contact_id)}
                                            type="checkbox"
                                          />
                                          <div>
                                            <div className="text-base font-semibold text-on-surface">
                                              {contact.name || "Unnamed contact"}
                                            </div>
                                            <div className="mt-1 flex flex-wrap items-center gap-2">
                                              <StatusBadge tone={referralStatusTone(contact.outreach_status)}>
                                                {contact.outreach_status || "Not contacted"}
                                              </StatusBadge>
                                              <span
                                                className={[
                                                  "rounded-full px-2.5 py-1 text-xs font-semibold",
                                                  contact.can_refer
                                                    ? "bg-teal-500/10 text-teal-500"
                                                    : "bg-amber-500/10 text-amber-500",
                                                ].join(" ")}
                                              >
                                                {contact.can_refer ? "Can Refer" : "Warm Contact"}
                                              </span>
                                            </div>
                                          </div>
                                        </label>
                                      </div>

                                      <div className="mt-3 flex flex-wrap gap-2">
                                        {companies.length ? (
                                          companies.map((entry) => {
                                            const companyName = String(
                                              entry.company_name || entry.company || "",
                                            ).trim();
                                            const roleTitle = String(entry.role_title || "").trim();
                                            return (
                                              <span
                                                key={`${contact.contact_id}-${companyName}-${roleTitle || "role"}`}
                                                className="rounded-full bg-surface-container-low px-2.5 py-1 text-xs font-medium text-on-surface"
                                              >
                                                {companyName || "Company not set"}
                                                {roleTitle ? ` | ${roleTitle}` : ""}
                                              </span>
                                            );
                                          })
                                        ) : (
                                          <span className="rounded-full bg-surface-container-low px-2.5 py-1 text-xs font-medium text-on-surface-variant">
                                            No company links saved yet
                                          </span>
                                        )}
                                      </div>

                                      <p className="mt-3 min-h-12 whitespace-pre-wrap text-sm leading-6 text-on-surface-variant">
                                        {contact.relationship_note || "No relationship note saved yet."}
                                      </p>

                                      <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto_auto]">
                                        <label className="space-y-1">
                                          <div className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
                                            Outreach Status
                                          </div>
                                          <select
                                            className="w-full rounded-lg border border-outline-variant/20 bg-surface-container-lowest px-3 py-2 text-sm text-on-surface disabled:cursor-not-allowed disabled:opacity-60"
                                            disabled={Boolean(pendingScopes[contactSelectionScope])}
                                            onChange={(event) =>
                                              persistOutreachStatus(
                                                row,
                                                [contact.contact_id],
                                                event.target.value,
                                                {
                                                  pendingKey: contactSelectionScope,
                                                  feedbackScope: panelFeedbackScope,
                                                  successMessage: `${contact.name || "Contact"} marked as ${event.target.value}.`,
                                                },
                                              )
                                            }
                                            value={contact.outreach_status || "Not contacted"}
                                          >
                                            {REFERRAL_OUTREACH_STATUSES.map((statusValue) => (
                                              <option key={statusValue} value={statusValue}>
                                                {statusValue}
                                              </option>
                                            ))}
                                          </select>
                                        </label>
                                        <button
                                          className="rounded-lg bg-primary/10 px-4 py-2 text-sm font-semibold text-primary transition-colors hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-60"
                                          disabled={!contact.linkedin_url}
                                          onClick={() => openLinkedInProfiles(row, [contact])}
                                          type="button"
                                        >
                                          Open LinkedIn
                                        </button>
                                        <button
                                          className="rounded-lg bg-surface-container px-4 py-2 text-sm font-semibold text-on-surface transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-60"
                                          disabled={Boolean(pendingScopes[contactDraftScope])}
                                          onClick={() => generateReferralDraft(row, contact)}
                                          type="button"
                                        >
                                          {pendingScopes[contactDraftScope] ? "Drafting..." : "Draft Message"}
                                        </button>
                                      </div>
                                    </article>
                                  );
                                })}
                              </div>
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })
              ) : (
                <tr>
                  <td className="px-6 py-10 text-on-surface-variant" colSpan={5}>
                    No generated jobs are in the queue right now.
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
                onClick={closeDraftComposer}
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
              {composerFeedback.message || composerFeedback.error ? (
                <div
                  className={[
                    "rounded-xl border px-4 py-3 text-sm",
                    composerFeedback.error
                      ? "border-error/30 bg-error/10 text-error"
                      : "border-primary/20 bg-primary/10 text-primary",
                  ].join(" ")}
                >
                  {composerFeedback.error || composerFeedback.message}
                </div>
              ) : null}
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
                  onClick={closeDraftComposer}
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
