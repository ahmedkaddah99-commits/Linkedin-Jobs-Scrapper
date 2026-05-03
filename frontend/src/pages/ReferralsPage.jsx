import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";

const EMPTY_FORM = {
  name: "",
  companies_text: "",
  linkedin_url: "",
  relationship_note: "",
  can_refer: false,
};

function ReferralFormField({ label, children, hint = "" }) {
  return (
    <label className="space-y-1.5">
      <div className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">{label}</div>
      {children}
      {hint ? <div className="text-xs text-on-surface-variant">{hint}</div> : null}
    </label>
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
  const [contactsPayload, outreachPayload] = await Promise.all([
    loadAllReferralContacts(request),
    loadAllReferralOutreachItems(request),
  ]);
  return {
    contacts: contactsPayload.contacts,
    outreachItems: outreachPayload.items,
    meta: {
      contacts: contactsPayload.meta,
      outreach: outreachPayload.meta,
    },
  };
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
  const [actionState, setActionState] = useState({ message: "", error: "", busyId: "" });
  const [importState, setImportState] = useState({
    csvText: "",
    fileName: "",
    busy: false,
    message: "",
    error: "",
    summary: null,
  });

  const { data, loading, error, refresh } = useApiResource(() => loadReferralWorkspace(request), [request]);

  const contacts = data?.contacts || [];
  const outreachItems = data?.outreachItems || [];
  const stats = useMemo(() => {
    const uniqueCompanies = new Set(
      contacts
        .flatMap((contact) => companyEntries(contact))
        .map((entry) => String(entry.company_name || entry.company || "").trim().toLowerCase())
        .filter(Boolean),
    );
    return {
      total: contacts.length,
      companies: uniqueCompanies.size,
      canRefer: contacts.filter((contact) => Boolean(contact.can_refer)).length,
      outreachTracked: outreachItems.length,
    };
  }, [contacts, outreachItems]);
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

  function updateForm(patch) {
    setForm((current) => ({ ...current, ...patch }));
  }

  function startEditing(contact) {
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
      await request(path, {
        method,
        body: {
          name: form.name,
          company: companies[0]?.company_name || "",
          companies,
          linkedin_url: form.linkedin_url,
          relationship_note: form.relationship_note,
          can_refer: form.can_refer,
        },
      });
      resetForm();
      setActionState({
        message: editingId ? "Referral contact updated." : "Referral contact added.",
        error: "",
        busyId: "",
      });
      await refresh();
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
      await refresh();
    } catch (deleteError) {
      setActionState({
        message: "",
        error: deleteError.message || "Unable to delete referral contact.",
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
      setImportState((current) => ({
        ...current,
        busy: false,
        message: "LinkedIn connections imported successfully.",
        summary,
        error: "",
      }));
      await refresh();
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

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-headline text-[2.25rem] font-extrabold leading-tight tracking-tight text-on-surface">
          Referrals
        </h1>
        <p className="mt-1 text-sm text-on-surface-variant">
          Keep a low-friction database of warm contacts, import LinkedIn exports, and link one person to multiple companies when needed.
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Contacts", value: stats.total },
          { label: "Target Companies", value: stats.companies },
          { label: "Can Refer", value: stats.canRefer },
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

      <section className="grid gap-8 xl:grid-cols-[1.05fr_1.4fr]">
        <div className="space-y-6">
          <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <h2 className="font-headline text-xl font-bold tracking-tight text-on-surface">
                  {editingId ? "Edit Contact" : "Add Contact"}
                </h2>
                <p className="mt-1 text-sm text-on-surface-variant">
                  Add a person once, then link them to as many relevant companies as needed.
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

              <ReferralFormField label="LinkedIn URL" hint="Used for quick open/copy from the app later.">
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
                {editingId ? "Save Contact" : "Add Contact"}
              </button>
              <button
                className="rounded bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                onClick={() => refresh().catch(() => undefined)}
                type="button"
              >
                Refresh
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6">
            <div className="mb-5">
              <h2 className="font-headline text-xl font-bold tracking-tight text-on-surface">
                Import LinkedIn Connections
              </h2>
              <p className="mt-1 text-sm text-on-surface-variant">
                Upload the LinkedIn connections CSV exactly as LinkedIn gives it to you. Notes before the table are ignored automatically, and the newest upload becomes the current source of truth.
              </p>
              <Link
                className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary hover:text-primary-container"
                to="/referrals/linkedin-csv-guide"
              >
                <span className="material-symbols-outlined text-[16px]">help</span>
                How to export your LinkedIn connections
              </Link>
            </div>

            <div className="space-y-4">
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
                  onChange={(event) => setImportState((current) => ({
                    ...current,
                    csvText: event.target.value,
                    message: "",
                    error: "",
                    summary: null,
                  }))}
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
              <div className="mt-3 grid gap-2 text-xs text-on-surface-variant sm:grid-cols-3">
                <div className="rounded-lg bg-surface-container-low px-3 py-2">
                  Parsed rows: <span className="font-semibold text-on-surface">{importState.summary.parsed || 0}</span>
                </div>
                <div className="rounded-lg bg-surface-container-low px-3 py-2">
                  Added: <span className="font-semibold text-on-surface">{importState.summary.created || 0}</span>
                </div>
                <div className="rounded-lg bg-surface-container-low px-3 py-2">
                  Total saved: <span className="font-semibold text-on-surface">{importState.summary.total_contacts || 0}</span>
                </div>
              </div>
            ) : null}

            <div className="mt-6 flex flex-wrap gap-3">
              <button
                className="rounded bg-primary px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={!String(importState.csvText || "").trim() || importState.busy}
                onClick={handleImport}
                type="button"
              >
                {importState.busy ? "Importing..." : "Import CSV"}
              </button>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest">
          <div className="border-b border-outline-variant/10 px-6 py-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="font-headline text-xl font-bold tracking-tight text-on-surface">
                  Saved Contacts
                </h2>
                <p className="mt-1 text-sm text-on-surface-variant">
                  These contacts are matched against company names in the review queue. Outreach status is edited there and summarized here per contact.
                </p>
              </div>
              <Link
                className="inline-flex items-center gap-1 rounded-lg bg-surface-container-low px-3 py-2 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
                to="/review-queue"
              >
                <span className="material-symbols-outlined text-[16px]">fact_check</span>
                Open Review Queue
              </Link>
            </div>
          </div>

          <div className="divide-y divide-outline-variant/10">
            {loading ? (
              <div className="px-6 py-10 text-on-surface-variant">Loading contacts...</div>
            ) : error ? (
              <div className="px-6 py-10 text-error">{error}</div>
            ) : contacts.length ? (
              contacts.map((contact) => {
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

                        <div className="rounded-xl border border-outline-variant/20 bg-surface-container-low p-4">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <h4 className="text-sm font-semibold text-on-surface">Outreach Activity</h4>
                              <p className="mt-1 text-xs text-on-surface-variant">
                                Stored per run, job, and contact. Update these statuses from the Review Queue.
                              </p>
                            </div>
                            <Link
                              className="inline-flex items-center gap-1 text-sm font-medium text-primary transition-colors hover:text-primary-container"
                              to="/review-queue"
                            >
                              <span className="material-symbols-outlined text-[15px]">fact_check</span>
                              Manage statuses
                            </Link>
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
                                    <div className="flex flex-wrap gap-2">
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
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="mt-4 text-sm text-on-surface-variant">
                              No outreach tracked yet. Once you mark a status in Review Queue, it will appear here for this contact.
                            </div>
                          )}
                        </div>
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
              })
            ) : (
              <div className="px-6 py-10 text-on-surface-variant">
                No referral contacts yet. Add a person manually or import your LinkedIn connections to start surfacing warm paths.
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
