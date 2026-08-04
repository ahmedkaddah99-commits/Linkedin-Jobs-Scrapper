import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { buildJobWorkspaceRoute } from "../lib/peopleDiscovery";
import {
  getLinkedInConnectionsStatus,
  LINKEDIN_CONNECTIONS_URL,
  openLinkedInConnections,
  syncLinkedInConnections,
} from "../lib/linkedinSync";

const EMPTY_FORM = {
  name: "",
  companies_text: "",
  linkedin_url: "",
  relationship_note: "",
  can_refer: false,
};
const REFERRAL_OUTREACH_STATUSES = [
  "Not contacted",
  "Contacted",
  "Replied",
  "Referral offered",
  "No referral",
];
const LINKEDIN_SOURCE_KINDS = new Set(["linkedin_csv", "linkedin_csv_import", "linkedin_extension"]);
const REFERRAL_SECTION_OPTIONS = [
  {
    id: "people",
    label: "Relevant People Finder",
    description: "Find likely hiring managers, team members, and senior leaders.",
    icon: "person_search",
  },
  {
    id: "manual",
    label: "Personal Contacts",
    description: "People you add or maintain yourself.",
    icon: "person_add",
  },
  {
    id: "linkedin",
    label: "LinkedIn Connections",
    description: "Imported from your LinkedIn connections export.",
    icon: "group",
  },
];
const CONTACT_RENDER_BATCH_SIZE = 50;
let referralWorkspaceCache = null;
let referralWorkspaceCacheRequest = null;

function cacheReferralWorkspace(data, request = referralWorkspaceCacheRequest) {
  referralWorkspaceCache = data;
  referralWorkspaceCacheRequest = request;
  return data;
}

function emptyReferralWorkspace() {
  return {
    contacts: [],
    outreachItems: [],
    trackerItems: [],
    meta: {
      contacts: { total: 0, returned: 0 },
      outreach: { total: 0, returned: 0 },
      detailsLoaded: false,
    },
  };
}

function ReferralFormField({ label, children, hint = "" }) {
  return (
    <label className="space-y-1.5">
      <div className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">{label}</div>
      {children}
      {hint ? <div className="text-xs text-on-surface-variant">{hint}</div> : null}
    </label>
  );
}

function LinkedInSyncPanel({ request, refresh, connectionCount }) {
  const [status, setStatus] = useState(null);
  const [extensionStatus, setExtensionStatus] = useState({ state: "checking" });
  const [busy, setBusy] = useState("");
  const [feedback, setFeedback] = useState({ message: "", error: "" });

  async function loadStatus() {
    try {
      const payload = await request("/referrals/import/status");
      setStatus(payload || {});
    } catch (statusError) {
      setFeedback({ message: "", error: statusError.message || "Unable to load LinkedIn sync status." });
    }
  }

  async function loadExtensionStatus() {
    try {
      const response = await getLinkedInConnectionsStatus();
      setExtensionStatus({ state: "ready", ...(response?.sync || {}) });
    } catch {
      setExtensionStatus({ state: "missing" });
    }
  }

  useEffect(() => {
    loadStatus().catch(() => undefined);
    loadExtensionStatus().catch(() => undefined);
  }, [request]);

  async function handleSync() {
    setBusy("sync");
    setFeedback({ message: "", error: "" });
    try {
      const extensionResponse = await syncLinkedInConnections();
      const summary = extensionResponse?.sync?.summary || extensionResponse?.summary || {};
      await refresh({ showLoading: false });
      setStatus(extensionResponse?.sync?.sync_status || extensionResponse?.sync_status || null);
      await loadExtensionStatus();
      setFeedback({
        message: `LinkedIn network synced. ${summary.parsed || 0} connections processed.`,
        error: "",
      });
    } catch (syncError) {
      setFeedback({ message: "", error: syncError.message || "Unable to sync LinkedIn connections." });
      await loadStatus().catch(() => undefined);
    } finally {
      setBusy("");
    }
  }

  function handleOpenLinkedIn() {
    const opened = openLinkedInConnections();
    setFeedback({
      message: opened
        ? "LinkedIn opened in a new tab. Leave that tab open, then return here and sync your network."
        : "Allow pop-ups for Runr so LinkedIn can open in a new tab.",
      error: opened ? "" : "Unable to open LinkedIn.",
    });
  }

  const canSync = status?.can_sync !== false && !busy;
  const extensionConnected = extensionStatus.state === "ready" && extensionStatus.extension_connected === true;
  return (
    <div className="rounded-xl border border-primary/20 bg-primary/5 p-6" data-testid="linkedin-network-sync">
      <div className="mb-5">
        <div className="text-xs font-semibold uppercase tracking-wider text-primary">Recommended</div>
        <h2 className="mt-1 font-headline text-xl font-bold tracking-tight text-on-surface">
          Sync your LinkedIn network
        </h2>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-on-surface-variant">
          Keep LinkedIn open in this browser and Runr will securely read your connections through the browser extension. No Connections.csv download is required.
        </p>
      </div>

      <div className="space-y-3">
        <div className="flex flex-col gap-3 rounded-lg border border-outline-variant/20 bg-surface-container-lowest p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <span className="material-symbols-outlined mt-0.5 rounded-lg bg-primary/10 p-2 text-primary">extension</span>
            <div>
              <div className="text-sm font-semibold text-on-surface">
                {extensionStatus.state === "checking"
                  ? "Checking Runr extension"
                  : extensionConnected ? "Runr extension connected" : "Install the Runr extension"}
              </div>
              <div className="mt-1 text-sm text-on-surface-variant">
                {extensionStatus.state === "checking"
                  ? "Checking this browser automatically…"
                  : extensionConnected
                    ? "Ready to read your LinkedIn tab when you start a sync."
                    : "It securely reads the LinkedIn tab only when you start a sync."}
              </div>
            </div>
          </div>
          {extensionConnected ? (
            <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-primary/10 px-3 py-2 text-sm font-medium text-primary">
              <span className="material-symbols-outlined text-[16px]">check_circle</span>
              Connected
            </span>
          ) : (
            <a
              className="inline-flex shrink-0 items-center justify-center rounded bg-primary px-3 py-2 text-sm font-medium text-white hover:opacity-90"
              href="https://chromewebstore.google.com/detail/runr-assisted-apply/najcdfohhfgbjpbokhmmekkahghfhegp"
              rel="noreferrer"
              target="_blank"
            >
              Install extension
            </a>
          )}
        </div>

        <div className="flex flex-col gap-3 rounded-lg border border-outline-variant/20 bg-surface-container-lowest p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <span className="material-symbols-outlined mt-0.5 rounded-lg bg-primary/10 p-2 text-primary">linkedin</span>
            <div>
              <div className="text-sm font-semibold text-on-surface">Authorize LinkedIn access</div>
              <div className="mt-1 text-sm text-on-surface-variant">Sign in to LinkedIn in this browser and open your connections page.</div>
            </div>
          </div>
          <button
            className="inline-flex shrink-0 items-center justify-center rounded bg-primary px-3 py-2 text-sm font-medium text-white hover:opacity-90"
            onClick={handleOpenLinkedIn}
            type="button"
          >
            Open LinkedIn
            <span className="material-symbols-outlined ml-1 text-[16px]">open_in_new</span>
          </button>
        </div>

        <div className="flex flex-col gap-3 rounded-lg border border-outline-variant/20 bg-surface-container-lowest p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <span className="material-symbols-outlined mt-0.5 rounded-lg bg-primary/10 p-2 text-primary">sync</span>
            <div>
              <div className="text-sm font-semibold text-on-surface">Sync your connections</div>
              <div className="mt-1 text-sm text-on-surface-variant">
                {status?.last_sync_at
                  ? `Last synced ${formatUpdatedAt(status.last_sync_at)}.`
                  : `No network sync yet. ${connectionCount || 0} saved connections currently available.`}
              </div>
            </div>
          </div>
          <button
            className="inline-flex shrink-0 items-center justify-center rounded bg-primary px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!canSync}
            onClick={handleSync}
            type="button"
          >
            {busy === "sync" ? "Syncing..." : status?.can_sync === false ? "Try again tomorrow" : "Sync network"}
          </button>
        </div>
      </div>

      {busy === "sync" ? (
        <div className="mt-4 flex items-center gap-2 text-sm text-primary" role="status">
          <span className="material-symbols-outlined animate-spin text-[18px]">progress_activity</span>
          Reading LinkedIn connections in the background. Runr will stay open while this finishes…
        </div>
      ) : null}
      {(feedback.message || feedback.error) ? (
        <div className={["mt-4 text-sm", feedback.error ? "text-error" : "text-primary"].join(" ")} role={feedback.error ? "alert" : undefined}>
          {feedback.error || feedback.message}
        </div>
      ) : null}
      {status?.next_sync_at && status?.can_sync === false ? (
        <div className="mt-3 text-xs text-on-surface-variant">Next available sync: {formatUpdatedAt(status.next_sync_at)}.</div>
      ) : null}
      <a className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-primary hover:text-primary-container" href={LINKEDIN_CONNECTIONS_URL} rel="noreferrer" target="_blank">
        Open LinkedIn connections directly
        <span className="material-symbols-outlined text-[14px]">open_in_new</span>
      </a>
    </div>
  );
}

function parseCompaniesText(value, canRefer) {
  return String(value || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [companyNameRaw, roleTitleRaw = ""] = line.split("|");
      const companyName = String(companyNameRaw || "").trim();
      const roleTitle = String(roleTitleRaw || "").trim();
      if (!companyName) return null;
      return {
        company_name: companyName,
        role_title: roleTitle,
        can_refer: Boolean(canRefer),
      };
    })
    .filter(Boolean);
}

function formatCompaniesForTextarea(contact) {
  const companies = Array.isArray(contact?.companies) && contact.companies.length
    ? contact.companies
    : contact?.company
      ? [{ company_name: contact.company, role_title: "" }]
      : [];
  return companies
    .map((entry) => {
      const companyName = String(entry.company_name || entry.company || "").trim();
      const roleTitle = String(entry.role_title || "").trim();
      return roleTitle ? `${companyName} | ${roleTitle}` : companyName;
    })
    .filter(Boolean)
    .join("\n");
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

function importedConnectedDate(contact) {
  const row = contact?.metadata?.import_source_row || {};
  return row["connected on"] || row.connected_on || row["connected date"] || "";
}

function isLinkedInImportedContact(contact) {
  return LINKEDIN_SOURCE_KINDS.has(String(contact?.source_kind || "").trim());
}

async function loadAllReferralContacts(request) {
  const limit = 1000;
  let offset = 0;
  const contacts = [];

  while (true) {
    const payload = await request(`/referrals?limit=${limit}&offset=${offset}`);
    const page = Array.isArray(payload?.contacts) ? payload.contacts : [];
    const returned = Number(payload?.meta?.returned ?? page.length);

    contacts.push(...page);

    if (!page.length || returned < limit) {
      break;
    }
    offset += returned;
  }

  return {
    contacts,
    meta: {
      total: contacts.length,
      returned: contacts.length,
    },
  };
}

async function loadAllReferralOutreachItems(request) {
  const limit = 1000;
  let offset = 0;
  const items = [];

  while (true) {
    const payload = await request(`/referrals/outreach-statuses?limit=${limit}&offset=${offset}`);
    const page = Array.isArray(payload?.items) ? payload.items : [];
    const returned = Number(payload?.meta?.returned ?? page.length);

    items.push(...page);

    if (!page.length || returned < limit) {
      break;
    }
    offset += returned;
  }

  return {
    items,
    meta: {
      total: items.length,
      returned: items.length,
    },
  };
}

async function loadReferralWorkspace(request) {
  if (referralWorkspaceCache && referralWorkspaceCacheRequest === request) {
    return referralWorkspaceCache;
  }
  const contactsPayload = await loadAllReferralContacts(request);
  return cacheReferralWorkspace({
    contacts: contactsPayload.contacts,
    outreachItems: [],
    trackerItems: [],
    meta: {
      contacts: contactsPayload.meta,
      outreach: { total: 0, returned: 0 },
      detailsLoaded: false,
    },
  }, request);
}

async function loadReferralDetails(request, currentData) {
  if (currentData?.meta?.detailsLoaded) {
    return currentData;
  }
  const [outreachPayload, trackerPayload] = await Promise.all([
    loadAllReferralOutreachItems(request),
    request("/tracker").catch(() => ({ items: [] })),
  ]);
  return cacheReferralWorkspace({
    ...(currentData || emptyReferralWorkspace()),
    outreachItems: outreachPayload.items,
    trackerItems: Array.isArray(trackerPayload?.items) ? trackerPayload.items : [],
    meta: {
      ...(currentData?.meta || {}),
      outreach: outreachPayload.meta,
      detailsLoaded: true,
    },
  }, request);
}

function buildPeopleFinderTargetKey(runId, jobId) {
  return `${String(runId || "").trim()}::${String(jobId || "").trim()}`;
}

function outreachStatusTone(status) {
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

function formatUpdatedAt(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) {
    return text;
  }
  return parsed.toLocaleString();
}

export default function ReferralsPage() {
  const { request } = useSession();
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState("");
  const [activeSection, setActiveSection] = useState("manual");
  const [visibleContactLimit, setVisibleContactLimit] = useState(CONTACT_RENDER_BATCH_SIZE);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [actionState, setActionState] = useState({ message: "", error: "", busyId: "" });
  const [importState, setImportState] = useState({
    csvText: "",
    fileName: "",
    busy: false,
    clearing: false,
    message: "",
    error: "",
    summary: null,
  });

  const { data, loading, error, refresh, setData } = useApiResource(() => loadReferralWorkspace(request), [request]);

  const contacts = data?.contacts || [];
  const outreachItems = data?.outreachItems || [];
  const trackerItems = data?.trackerItems || [];
  const editingContact = useMemo(
    () => contacts.find((contact) => contact.contact_id === editingId) || null,
    [contacts, editingId],
  );
  const manualContacts = useMemo(
    () => contacts.filter((contact) => !isLinkedInImportedContact(contact)),
    [contacts],
  );
  const linkedinContacts = useMemo(
    () => contacts.filter((contact) => isLinkedInImportedContact(contact)),
    [contacts],
  );
  const visibleContacts = activeSection === "linkedin" ? linkedinContacts : manualContacts;
  const renderedContacts = visibleContacts.slice(0, visibleContactLimit);
  const hiddenContactCount = Math.max(0, visibleContacts.length - renderedContacts.length);
  const detailsLoaded = Boolean(data?.meta?.detailsLoaded);
  const editingLinkedInContact = isLinkedInImportedContact(editingContact);
  const stats = useMemo(() => {
    const uniqueCompanies = new Set(
      contacts
        .flatMap((contact) => companyEntries(contact))
        .map((entry) => String(entry.company_name || entry.company || "").trim().toLowerCase())
        .filter(Boolean),
    );
    return {
      total: contacts.length,
      manual: manualContacts.length,
      linkedin: linkedinContacts.length,
      companies: uniqueCompanies.size,
      canRefer: contacts.filter((contact) => Boolean(contact.can_refer)).length,
      outreachTracked: outreachItems.length,
    };
  }, [contacts, linkedinContacts.length, manualContacts.length, outreachItems]);
  const outreachByContact = useMemo(() => {
    const groups = new Map();
    outreachItems.forEach((item) => {
      const contactId = String(item.contact_id || "").trim();
      if (!contactId) return;
      const currentItems = groups.get(contactId) || [];
      currentItems.push(item);
      groups.set(contactId, currentItems);
    });
    return groups;
  }, [outreachItems]);
  const peopleFinderTargets = useMemo(() => {
    const entries = new Map();

    trackerItems.forEach((item) => {
      const runId = String(item.run_id || "").trim();
      const jobId = String(item.job_id || "").trim();
      if (!runId || !jobId) {
        return;
      }
      const key = buildPeopleFinderTargetKey(runId, jobId);
      entries.set(key, {
        key,
        runId,
        jobId,
        title: item.title || "Untitled job",
        company: item.company || "",
        location: item.location || "",
        workspaceName: item.workspace_name || "",
        applyLink: item.apply_link || "",
        trackerStatus: item.tracker_status || "",
        sourceLabel: "Tracker",
        jobWorkspaceUrl:
          item.job_workspace_url || buildJobWorkspaceRoute({ runId, jobId }),
        updatedAt: item.updated_at || item.run_finished_at || "",
      });
    });

    outreachItems.forEach((item) => {
      const runId = String(item.run_id || "").trim();
      const jobId = String(item.job_id || "").trim();
      if (!runId || !jobId) {
        return;
      }
      const key = buildPeopleFinderTargetKey(runId, jobId);
      if (entries.has(key)) {
        return;
      }
      entries.set(key, {
        key,
        runId,
        jobId,
        title: item.job_title || "Untitled job",
        company: item.company || "",
        location: "",
        workspaceName: item.workspace_name || "",
        applyLink: item.apply_link || "",
        trackerStatus: "",
        sourceLabel: "Outreach history",
        jobWorkspaceUrl: buildJobWorkspaceRoute({ runId, jobId }),
        updatedAt: item.updated_at || "",
      });
    });

    return Array.from(entries.values()).sort((left, right) =>
      String(right.updatedAt || "").localeCompare(String(left.updatedAt || "")),
    );
  }, [outreachItems, trackerItems]);

  useEffect(() => {
    setVisibleContactLimit(CONTACT_RENDER_BATCH_SIZE);
  }, [activeSection]);

  useEffect(() => {
    if (activeSection !== "people" || !data || detailsLoaded || detailsLoading) {
      return;
    }
    let cancelled = false;
    setDetailsLoading(true);
    loadReferralDetails(request, data)
      .then((payload) => {
        if (!cancelled) {
          setData(payload);
        }
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) {
          setDetailsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeSection, data, detailsLoaded, detailsLoading, request, setData]);

  function updateReferralData(updater) {
    setData((current) => cacheReferralWorkspace(updater(current || referralWorkspaceCache || emptyReferralWorkspace())));
  }

  function refreshContactsFromServer() {
    referralWorkspaceCache = null;
    referralWorkspaceCacheRequest = null;
    return refresh({ showLoading: false });
  }

  function updateForm(patch) {
    setForm((current) => ({ ...current, ...patch }));
  }

  function startEditing(contact) {
    setActiveSection(isLinkedInImportedContact(contact) ? "linkedin" : "manual");
    setEditingId(contact.contact_id);
    setForm({
      name: contact.name || "",
      companies_text: formatCompaniesForTextarea(contact),
      linkedin_url: contact.linkedin_url || "",
      relationship_note: contact.relationship_note || "",
      can_refer: Boolean(contact.can_refer),
    });
    setActionState({ message: "", error: "", busyId: "" });
  }

  function resetForm() {
    setEditingId("");
    setForm(EMPTY_FORM);
  }

  async function saveContact() {
    const companies = parseCompaniesText(form.companies_text, form.can_refer);
    setActionState({ message: "", error: "", busyId: editingId || "new" });
    try {
      const path = editingId ? `/referrals/${editingId}` : "/referrals";
      const method = editingId ? "PUT" : "POST";
      const sourcePayload = editingContact
        ? {
            source_kind: editingContact.source_kind || "manual",
            import_batch_id: editingContact.import_batch_id || "",
            import_ref: editingContact.import_ref || "",
            is_active: editingContact.is_active !== false,
            inactive_at: editingContact.inactive_at || "",
            inactive_reason: editingContact.inactive_reason || "",
            metadata: editingContact.metadata || {},
          }
        : {
            source_kind: "manual",
          };
      const savedContact = await request(path, {
        method,
        body: {
          name: form.name,
          company: companies[0]?.company_name || "",
          companies,
          linkedin_url: form.linkedin_url,
          relationship_note: form.relationship_note,
          can_refer: form.can_refer,
          ...sourcePayload,
        },
      });
      resetForm();
      setActionState({
        message: editingId ? "Referral contact updated." : "Referral contact added.",
        error: "",
        busyId: "",
      });
      updateReferralData((current) => {
        const contacts = Array.isArray(current.contacts) ? current.contacts : [];
        const existingIndex = contacts.findIndex((contact) => contact.contact_id === savedContact.contact_id);
        const nextContacts = existingIndex >= 0
          ? contacts.map((contact, index) => (index === existingIndex ? savedContact : contact))
          : [...contacts, savedContact];
        return {
          ...current,
          contacts: nextContacts,
          meta: {
            ...(current.meta || {}),
            contacts: {
              ...((current.meta || {}).contacts || {}),
              total: nextContacts.length,
              returned: nextContacts.length,
            },
          },
        };
      });
    } catch (saveError) {
      setActionState({
        message: "",
        error: saveError.message || "Unable to save referral contact.",
        busyId: "",
      });
    }
  }

  async function deleteContact(contactId) {
    setActionState({ message: "", error: "", busyId: contactId });
    try {
      await request(`/referrals/${contactId}`, { method: "DELETE" });
      if (editingId === contactId) {
        resetForm();
      }
      setActionState({ message: "Referral contact deleted.", error: "", busyId: "" });
      updateReferralData((current) => {
        const nextContacts = (Array.isArray(current.contacts) ? current.contacts : []).filter(
          (contact) => contact.contact_id !== contactId,
        );
        return {
          ...current,
          contacts: nextContacts,
          meta: {
            ...(current.meta || {}),
            contacts: {
              ...((current.meta || {}).contacts || {}),
              total: nextContacts.length,
              returned: nextContacts.length,
            },
          },
        };
      });
    } catch (deleteError) {
      setActionState({
        message: "",
        error: deleteError.message || "Unable to delete referral contact.",
        busyId: "",
      });
    }
  }

  async function updateOutreachStatus(item, outreachStatus) {
    const busyId = `outreach:${item.run_id}:${item.job_id}:${item.contact_id}`;
    setActionState({ message: "", error: "", busyId });
    try {
      await request("/referrals/outreach-status", {
        method: "POST",
        body: {
          run_id: item.run_id,
          job_id: item.job_id,
          contact_id: item.contact_id,
          outreach_status: outreachStatus,
        },
      });
      setActionState({ message: "Outreach status updated.", error: "", busyId: "" });
      updateReferralData((current) => ({
        ...current,
        meta: {
          ...(current.meta || {}),
          detailsLoaded: false,
        },
      }));
    } catch (updateError) {
      setActionState({
        message: "",
        error: updateError.message || "Unable to update outreach status.",
        busyId: "",
      });
    }
  }

  async function handleImport() {
    setImportState((current) => ({ ...current, busy: true, message: "", error: "" }));
    try {
      const payload = await request("/referrals/import", {
        method: "POST",
        body: {
          csv_text: importState.csvText,
          source_kind: "linkedin_csv",
        },
      });
      const summary = payload?.summary || {};
      const refreshedContacts = Array.isArray(payload?.contacts) ? payload.contacts : null;
      setImportState((current) => ({
        ...current,
        busy: false,
        message: "LinkedIn connections imported successfully.",
        summary,
        error: "",
      }));
      if (refreshedContacts) {
        updateReferralData((current) => ({
          ...current,
          contacts: refreshedContacts,
          meta: {
            ...(current.meta || {}),
            contacts: {
              ...((current.meta || {}).contacts || {}),
              total: refreshedContacts.length,
              returned: refreshedContacts.length,
            },
          },
        }));
      } else {
        await refresh({ showLoading: false });
      }
    } catch (importError) {
      setImportState((current) => ({
        ...current,
        busy: false,
        message: "",
        error: importError.message || "Unable to import referral contacts.",
        summary: null,
      }));
    }
  }

  async function clearLinkedInConnections() {
    if (!linkedinContacts.length) {
      return;
    }
    const confirmed = window.confirm(
      "Delete all imported LinkedIn connections? Personal contacts will stay saved.",
    );
    if (!confirmed) {
      return;
    }
    setImportState((current) => ({ ...current, clearing: true, message: "", error: "", summary: null }));
    try {
      const payload = await request("/referrals/import", { method: "DELETE" });
      const refreshedContacts = Array.isArray(payload?.contacts) ? payload.contacts : [];
      updateReferralData((current) => ({
        ...current,
        contacts: refreshedContacts,
        outreachItems: [],
        trackerItems: current.trackerItems || [],
        meta: {
          ...(current.meta || {}),
          contacts: {
            ...((current.meta || {}).contacts || {}),
            total: refreshedContacts.length,
            returned: refreshedContacts.length,
          },
          outreach: { total: 0, returned: 0 },
          detailsLoaded: false,
        },
      }));
      setImportState((current) => ({
        ...current,
        clearing: false,
        message: `Deleted ${payload?.deleted || 0} imported LinkedIn connection${Number(payload?.deleted || 0) === 1 ? "" : "s"}.`,
        error: "",
      }));
    } catch (clearError) {
      setImportState((current) => ({
        ...current,
        clearing: false,
        message: "",
        error: clearError.message || "Unable to delete imported LinkedIn connections.",
      }));
    }
  }

  async function handleCsvFileChange(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const csvText = await file.text();
    setImportState((current) => ({
      ...current,
      csvText,
      fileName: file.name,
      message: "",
      error: "",
      summary: null,
    }));
  }

  const manualCompanies = parseCompaniesText(form.companies_text, form.can_refer);
  const showingLinkedInImportPanel = activeSection === "linkedin" && !editingLinkedInContact;
  const visibleSectionEmptyCopy =
    activeSection === "linkedin"
      ? "No LinkedIn connections imported yet. Upload your CSV here to turn your export into searchable referral matches."
      : "No personal contacts saved yet. Add people you already know outside LinkedIn or contacts you want to track more deliberately.";

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-headline text-[2.25rem] font-extrabold leading-tight tracking-tight text-on-surface">
          Referrals
        </h1>
        <p className="mt-1 text-sm text-on-surface-variant">
          Keep manual warm contacts separate from imported LinkedIn connections, and use both when deciding who to approach for a referral.
        </p>
      </header>

      <section className="grid gap-3 lg:grid-cols-3">
        {REFERRAL_SECTION_OPTIONS.map((section) => {
          const isActive = activeSection === section.id;
          const count =
            section.id === "people"
              ? peopleFinderTargets.length
              : section.id === "linkedin"
                ? stats.linkedin
                : stats.manual;
          return (
            <button
              key={section.id}
              className={[
                "rounded-2xl border p-5 text-left transition-all",
                isActive
                  ? "border-primary/30 bg-primary/10 shadow-sm"
                  : "border-outline-variant/20 bg-surface-container-lowest hover:border-primary/20 hover:bg-surface-container-low",
              ].join(" ")}
              onClick={() => {
                setActiveSection(section.id);
                if (editingId && section.id !== (editingLinkedInContact ? "linkedin" : "manual")) {
                  resetForm();
                }
              }}
              type="button"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-[20px] text-primary">{section.icon}</span>
                    <div className="text-base font-semibold text-on-surface">{section.label}</div>
                  </div>
                  <div className="mt-2 text-sm text-on-surface-variant">{section.description}</div>
                </div>
                <span className="rounded-full bg-surface px-3 py-1 text-xs font-semibold text-on-surface-variant">
                  {count}
                </span>
              </div>
            </button>
          );
        })}
      </section>

      {activeSection === "people" ? (
        <section className="rounded-2xl border border-primary/15 bg-[radial-gradient(circle_at_top_left,rgba(58,130,246,0.12),transparent_45%),linear-gradient(135deg,rgba(15,23,42,0.02),rgba(58,130,246,0.02))] p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-primary">
              Relevant People Finder
            </div>
            <div className="mt-1 text-xl font-semibold text-on-surface">
              Find likely hiring managers, team members, and senior leaders from here
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-7 text-on-surface-variant">
              Use this before writing networking messages or asking for a referral. Runr looks for likely relevant people only, and confidence is based on public profile signals rather than certainty.
            </p>
          </div>
          <Link
            className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90"
            to="/tracker"
          >
            <span className="material-symbols-outlined text-[18px]">work</span>
            Open all applications
          </Link>
        </div>

        {peopleFinderTargets.length ? (
          <div className="mt-5 grid gap-4 xl:grid-cols-3">
            {peopleFinderTargets.slice(0, 6).map((target) => (
              <article
                key={target.key}
                className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-base font-semibold text-on-surface">
                      {target.title}
                    </div>
                    <div className="mt-1 text-sm text-on-surface-variant">
                      {[target.company, target.location].filter(Boolean).join(" | ") || "Saved application context"}
                    </div>
                  </div>
                  <span className="rounded-full bg-surface px-2.5 py-1 text-xs font-semibold text-on-surface-variant">
                    {target.sourceLabel}
                  </span>
                </div>

                <div className="mt-3 flex flex-wrap gap-2">
                  {target.workspaceName ? (
                    <span className="rounded-full bg-surface-container-low px-2.5 py-1 text-xs font-medium text-on-surface">
                      {target.workspaceName}
                    </span>
                  ) : null}
                  {target.trackerStatus ? (
                    <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
                      {target.trackerStatus.replace(/_/g, " ")}
                    </span>
                  ) : null}
                </div>

                <p className="mt-3 text-sm leading-6 text-on-surface-variant">
                  Likely relevant only. Use this to review potential matches before outreach, referrals, or tailoring.
                </p>

                <div className="mt-4 flex flex-wrap gap-2">
                  <Link
                    className="rounded-full bg-primary px-3 py-1.5 text-sm font-semibold text-white transition-opacity hover:opacity-90"
                    to={target.jobWorkspaceUrl}
                  >
                    Find relevant people
                  </Link>
                  {target.applyLink ? (
                    <a
                      className="rounded-full bg-surface-container-low px-3 py-1.5 text-sm font-semibold text-on-surface transition-colors hover:bg-surface-container-high"
                      href={target.applyLink}
                      rel="noreferrer"
                      target="_blank"
                    >
                      Open Job
                    </a>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="mt-5 rounded-2xl border border-dashed border-outline-variant/30 bg-surface-container-lowest p-5 text-sm text-on-surface-variant">
            No application context is available here yet. Once a job reaches Tracker or has saved outreach history, the Relevant People Finder entry point appears in this section.
          </div>
        )}
        </section>
      ) : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Personal Contacts", value: stats.manual },
          { label: "LinkedIn Connections", value: stats.linkedin },
          { label: "Target Companies", value: stats.companies },
          { label: "Tracked Outreach", value: stats.outreachTracked },
        ].map((card) => (
          <div
            key={card.label}
            className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-5"
          >
            <div className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
              {card.label}
            </div>
            <div className="mt-3 text-4xl font-extrabold tracking-tight text-on-surface">{card.value}</div>
          </div>
        ))}
      </section>

      {activeSection !== "people" ? (
        <section className="grid gap-8 xl:grid-cols-[1.05fr_1.4fr]">
        <div className="space-y-6">
          {!showingLinkedInImportPanel ? (
            <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6">
              <div className="mb-5 flex items-start justify-between gap-4">
                <div>
                  <h2 className="font-headline text-xl font-bold tracking-tight text-on-surface">
                    {editingLinkedInContact
                      ? "Edit LinkedIn Connection"
                      : editingId
                        ? "Edit Personal Contact"
                        : "Add Personal Contact"}
                  </h2>
                  <p className="mt-1 text-sm text-on-surface-variant">
                    {editingLinkedInContact
                      ? "Keep the LinkedIn import source, but adjust notes, company mapping, or referability."
                      : "Add a person once, then link them to as many relevant companies as needed."}
                  </p>
                </div>
                {editingId ? (
                  <button
                    className="rounded bg-surface-container-low px-3 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                    onClick={resetForm}
                    type="button"
                  >
                    Cancel Edit
                  </button>
                ) : null}
              </div>

              <div className="space-y-4">
                <ReferralFormField label="Contact Name">
                  <input
                    className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
                    onChange={(event) => updateForm({ name: event.target.value })}
                    placeholder="Jane Doe"
                    value={form.name}
                  />
                </ReferralFormField>

                <ReferralFormField
                  label="Companies"
                  hint="Use one company per line. Optional role format: Company Name | Role Title"
                >
                  <textarea
                    className="min-h-28 w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
                    onChange={(event) => updateForm({ companies_text: event.target.value })}
                    placeholder={"Acme GmbH | Engineering Manager\nContoso SE | Former Team Lead"}
                    value={form.companies_text}
                  />
                </ReferralFormField>

                <ReferralFormField label="LinkedIn URL" hint="Used for quick open or copy later.">
                  <input
                    className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
                    onChange={(event) => updateForm({ linkedin_url: event.target.value })}
                    placeholder="https://www.linkedin.com/in/jane-doe/"
                    value={form.linkedin_url}
                  />
                </ReferralFormField>

                <ReferralFormField label="Relationship Note" hint="How you know them or what context to mention.">
                  <textarea
                    className="min-h-28 w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
                    onChange={(event) => updateForm({ relationship_note: event.target.value })}
                    placeholder="Worked together on the Berlin product launch."
                    value={form.relationship_note}
                  />
                </ReferralFormField>

                <label className="flex items-center gap-3 rounded-lg border border-outline-variant/20 bg-surface px-4 py-3">
                  <input
                    checked={Boolean(form.can_refer)}
                    className="h-4 w-4 rounded border-outline-variant/30 text-primary focus:ring-primary/20"
                    onChange={(event) => updateForm({ can_refer: event.target.checked })}
                    type="checkbox"
                  />
                  <div>
                    <div className="text-sm font-medium text-on-surface">Can refer me</div>
                    <div className="text-xs text-on-surface-variant">
                      Applies to the listed companies unless you change it later.
                    </div>
                  </div>
                </label>
              </div>

              {manualCompanies.length ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  {manualCompanies.map((company) => (
                    <span
                      key={`${company.company_name}-${company.role_title || "role"}`}
                      className="rounded-full bg-surface-container-low px-2.5 py-1 text-xs font-medium text-on-surface"
                    >
                      {company.company_name}
                      {company.role_title ? ` | ${company.role_title}` : ""}
                    </span>
                  ))}
                </div>
              ) : null}

              {(actionState.message || actionState.error) && !actionState.busyId ? (
                <div className={["mt-4 text-sm", actionState.error ? "text-error" : "text-primary"].join(" ")}>
                  {actionState.error || actionState.message}
                </div>
              ) : null}

              <div className="mt-6 flex flex-wrap gap-3">
                <button
                  className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={!form.name.trim() || !manualCompanies.length || Boolean(actionState.busyId)}
                  onClick={saveContact}
                  type="button"
                >
                  {editingLinkedInContact
                    ? "Save Connection"
                    : editingId
                      ? "Save Contact"
                      : "Add Personal Contact"}
                </button>
                <button
                  className="rounded bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                  onClick={() => refreshContactsFromServer().catch(() => undefined)}
                  type="button"
                >
                  Refresh
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              <LinkedInSyncPanel request={request} refresh={refresh} connectionCount={linkedinContacts.length} />
              <details className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6">
                <summary className="cursor-pointer text-sm font-semibold text-on-surface">Use a Connections.csv export instead</summary>
                <div className="mt-5">
                  <p className="mt-1 text-sm text-on-surface-variant">
                    Keep the manual CSV import as a fallback if the browser extension is unavailable. The newest upload remains the current source of truth.
                  </p>
                  <Link
                    className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary hover:text-primary-container"
                    to="/referrals/linkedin-csv-guide"
                  >
                    <span className="material-symbols-outlined text-[16px]">help</span>
                    How to export your LinkedIn connections
                  </Link>
                </div>

                <div className="mt-5 space-y-4">
                <label className="inline-flex cursor-pointer items-center gap-3 rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-low">
                  <span className="material-symbols-outlined text-[18px]">upload_file</span>
                  {importState.fileName ? `Loaded ${importState.fileName}` : "Choose CSV File"}
                  <input
                    accept=".csv,text/csv"
                    className="hidden"
                    onChange={(event) => {
                      handleCsvFileChange(event).catch((fileError) => {
                        setImportState((current) => ({
                          ...current,
                          error: fileError.message || "Unable to read the CSV file.",
                        }));
                      });
                    }}
                    type="file"
                  />
                </label>

                <ReferralFormField
                  label="CSV Content"
                  hint="Runr looks for this LinkedIn header row: First Name, Last Name, URL, Email Address, Company, Position, Connected On. Rows keep the same order as the uploaded file."
                >
                  <textarea
                    className="min-h-40 w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
                    onChange={(event) =>
                      setImportState((current) => ({
                        ...current,
                        csvText: event.target.value,
                        message: "",
                        error: "",
                        summary: null,
                      }))
                    }
                    placeholder="Paste your LinkedIn connections CSV here if you do not want to upload a file."
                    value={importState.csvText}
                  />
                </ReferralFormField>
              </div>

                {(importState.message || importState.error) ? (
                <div className={["mt-4 text-sm", importState.error ? "text-error" : "text-primary"].join(" ")}>
                  {importState.error || importState.message}
                </div>
              ) : null}
                {importState.summary && !importState.error ? (
                <div className="mt-3 grid gap-2 text-xs text-on-surface-variant sm:grid-cols-4">
                  <div className="rounded-lg bg-surface-container-low px-3 py-2">
                    Parsed rows: <span className="font-semibold text-on-surface">{importState.summary.parsed || 0}</span>
                  </div>
                  <div className="rounded-lg bg-surface-container-low px-3 py-2">
                    Added: <span className="font-semibold text-on-surface">{importState.summary.created || 0}</span>
                  </div>
                  <div className="rounded-lg bg-surface-container-low px-3 py-2">
                    Updated: <span className="font-semibold text-on-surface">{importState.summary.updated || 0}</span>
                  </div>
                  <div className="rounded-lg bg-surface-container-low px-3 py-2">
                    Total saved: <span className="font-semibold text-on-surface">{importState.summary.total_contacts || 0}</span>
                  </div>
                </div>
              ) : null}

                <div className="mt-6 flex flex-wrap gap-3">
                <button
                  className="rounded bg-primary px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={!String(importState.csvText || "").trim() || importState.busy || importState.clearing}
                  onClick={handleImport}
                  type="button"
                >
                  {importState.busy ? "Importing..." : linkedinContacts.length ? "Update CSV" : "Import CSV"}
                </button>
                <button
                  className="rounded bg-error/10 px-4 py-2.5 text-sm font-medium text-error transition-colors hover:bg-error/20 disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={!linkedinContacts.length || importState.busy || importState.clearing}
                  onClick={clearLinkedInConnections}
                  type="button"
                >
                  {importState.clearing ? "Deleting..." : "Delete Imported List"}
                </button>
                </div>
              </details>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest">
          <div className="border-b border-outline-variant/10 px-6 py-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="font-headline text-xl font-bold tracking-tight text-on-surface">
                  {activeSection === "linkedin" ? "Imported LinkedIn Connections" : "Personal Contacts"}
                </h2>
                <p className="mt-1 text-sm text-on-surface-variant">
                  {activeSection === "linkedin"
                    ? "Imported connections stay grouped here so you can separate export-based matches from the contacts you maintain yourself."
                    : "These contacts are matched against generated jobs and keep their outreach history in one place."}
                </p>
              </div>
            </div>
          </div>

          <div className="divide-y divide-outline-variant/10">
            {loading ? (
              <div className="px-6 py-10 text-on-surface-variant">Loading contacts...</div>
            ) : error ? (
              <div className="px-6 py-10 text-error">{error}</div>
            ) : visibleContacts.length ? (
              <>
              {renderedContacts.map((contact) => {
                const contactOutreach = outreachByContact.get(contact.contact_id) || [];

                return (
                  <article key={contact.contact_id} className="px-6 py-5">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="space-y-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="text-lg font-semibold text-on-surface">{contact.name}</h3>
                          {contact.can_refer ? (
                            <span className="rounded-full bg-teal-500/10 px-2.5 py-1 text-xs font-semibold text-teal-500">
                              Can Refer
                            </span>
                          ) : (
                            <span className="rounded-full bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-500">
                              Warm Contact
                            </span>
                          )}
                          {contact.is_active === false ? (
                            <span className="rounded-full bg-error/10 px-2.5 py-1 text-xs font-semibold text-error">
                              Removed from latest upload
                            </span>
                          ) : null}
                          <span className="rounded-full bg-surface-container-low px-2.5 py-1 text-xs font-semibold text-on-surface-variant">
                            {isLinkedInImportedContact(contact) ? "LinkedIn Import" : "Personal Contact"}
                          </span>
                        </div>

                        <div className="flex flex-wrap gap-2">
                          {companyEntries(contact).length ? (
                            companyEntries(contact).map((entry) => (
                              <span
                                key={`${contact.contact_id}-${entry.company_name || entry.company}`}
                                className="rounded-full bg-surface-container-low px-2.5 py-1 text-xs font-medium text-on-surface"
                              >
                                {entry.company_name || entry.company}
                                {entry.role_title ? ` | ${entry.role_title}` : ""}
                              </span>
                            ))
                          ) : (
                            <span className="rounded-full bg-surface-container-low px-2.5 py-1 text-xs font-medium text-on-surface-variant">
                              No company linked yet
                            </span>
                          )}
                        </div>

                        {contact.linkedin_url ? (
                          <a
                            className="inline-flex items-center gap-1 text-sm text-primary transition-colors hover:text-primary-container"
                            href={contact.linkedin_url}
                            rel="noreferrer"
                            target="_blank"
                          >
                            <span className="material-symbols-outlined text-[15px]">open_in_new</span>
                            LinkedIn profile
                          </a>
                        ) : null}

                        {importedConnectedDate(contact) ? (
                          <div className="text-xs text-on-surface-variant">
                            Connected on LinkedIn: {importedConnectedDate(contact)}
                          </div>
                        ) : null}

                        <p className="max-w-2xl whitespace-pre-wrap text-sm leading-6 text-on-surface-variant">
                          {contact.relationship_note || "No relationship note saved yet."}
                        </p>

                        {detailsLoaded ? (
                        <div className="rounded-xl border border-outline-variant/20 bg-surface-container-low p-4">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <h4 className="text-sm font-semibold text-on-surface">Outreach Activity</h4>
                              <p className="mt-1 text-xs text-on-surface-variant">
                                Stored per run, job, and contact. Update these statuses directly here.
                              </p>
                            </div>
                          </div>
                          {contactOutreach.length ? (
                            <div className="mt-4 space-y-3">
                              {contactOutreach.map((item) => (
                                <div
                                  key={`${item.run_id}-${item.job_id}-${item.contact_id}`}
                                  className="rounded-xl border border-outline-variant/15 bg-surface-container-lowest p-4"
                                >
                                  <div className="flex flex-wrap items-start justify-between gap-3">
                                    <div className="space-y-2">
                                      <div className="flex flex-wrap items-center gap-2">
                                        <StatusBadge tone={outreachStatusTone(item.outreach_status)}>
                                          {item.outreach_status}
                                        </StatusBadge>
                                        <span className="text-xs text-on-surface-variant">
                                          {formatUpdatedAt(item.updated_at)}
                                        </span>
                                      </div>
                                      <div className="text-sm font-semibold text-on-surface">
                                        {item.job_title || "Untitled job"}
                                        {item.company ? ` at ${item.company}` : ""}
                                      </div>
                                      <div className="flex flex-wrap items-center gap-2 text-xs text-on-surface-variant">
                                        <span>{item.workspace_name || "Workspace not set"}</span>
                                        {item.run_id ? (
                                          <span className="rounded bg-surface px-1.5 py-0.5 font-mono text-[11px] text-on-surface-variant">
                                            {item.run_id}
                                          </span>
                                        ) : null}
                                        {item.source_label ? <span>{item.source_label}</span> : null}
                                      </div>
                                    </div>
                                    <div className="flex flex-wrap items-center gap-2">
                                      <select
                                        className="rounded border border-outline-variant/20 bg-surface-container-low px-3 py-2 text-sm text-on-surface"
                                        disabled={
                                          actionState.busyId ===
                                          `outreach:${item.run_id}:${item.job_id}:${item.contact_id}`
                                        }
                                        onChange={(event) =>
                                          updateOutreachStatus(item, event.target.value)
                                        }
                                        value={item.outreach_status || "Not contacted"}
                                      >
                                        {REFERRAL_OUTREACH_STATUSES.map((status) => (
                                          <option key={`${item.contact_id}-${status}`} value={status}>
                                            {status}
                                          </option>
                                        ))}
                                      </select>
                                      {item.contact_linkedin_url ? (
                                        <a
                                          className="rounded bg-primary/10 px-3 py-2 text-sm font-medium text-primary transition-colors hover:bg-primary/20"
                                          href={item.contact_linkedin_url}
                                          rel="noreferrer"
                                          target="_blank"
                                        >
                                          Open LinkedIn
                                        </a>
                                      ) : null}
                                      {item.apply_link ? (
                                        <a
                                          className="rounded bg-surface-container-low px-3 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface"
                                          href={item.apply_link}
                                          rel="noreferrer"
                                          target="_blank"
                                        >
                                          Open Job
                                        </a>
                                      ) : null}
                                      {item.run_id && item.job_id ? (
                                        <Link
                                          className="rounded bg-primary/10 px-3 py-2 text-sm font-medium text-primary transition-colors hover:bg-primary/20"
                                          to={buildJobWorkspaceRoute({
                                            runId: item.run_id,
                                            jobId: item.job_id,
                                          })}
                                        >
                                          Relevant People
                                        </Link>
                                      ) : null}
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="mt-4 text-sm text-on-surface-variant">
                              No outreach tracked yet. Saved outreach statuses will appear here for this contact.
                            </div>
                          )}
                        </div>
                        ) : null}
                      </div>

                      <div className="flex flex-wrap gap-2">
                        <button
                          className="rounded bg-surface-container-low px-3 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                          onClick={() => startEditing(contact)}
                          type="button"
                        >
                          Edit
                        </button>
                        <button
                          className="rounded bg-error/10 px-3 py-2 text-sm font-medium text-error transition-colors hover:bg-error/20 disabled:cursor-not-allowed disabled:opacity-60"
                          disabled={actionState.busyId === contact.contact_id}
                          onClick={() => deleteContact(contact.contact_id)}
                          type="button"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  </article>
                );
              })}
              {hiddenContactCount ? (
                <div className="px-6 py-5">
                  <button
                    className="w-full rounded bg-surface-container-low px-4 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                    onClick={() =>
                      setVisibleContactLimit((current) => current + CONTACT_RENDER_BATCH_SIZE)
                    }
                    type="button"
                  >
                    Show {Math.min(CONTACT_RENDER_BATCH_SIZE, hiddenContactCount)} more of {hiddenContactCount}
                  </button>
                </div>
              ) : null}
              </>
            ) : (
              <div className="px-6 py-10 text-on-surface-variant">
                {visibleSectionEmptyCopy}
              </div>
            )}
          </div>
        </div>
        </section>
      ) : null}
    </div>
  );
}
