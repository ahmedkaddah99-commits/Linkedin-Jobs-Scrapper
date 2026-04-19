import { useMemo, useState } from "react";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";

const EMPTY_FORM = {
  name: "",
  company: "",
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

export default function ReferralsPage() {
  const { request } = useSession();
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState("");
  const [actionState, setActionState] = useState({ message: "", error: "", busyId: "" });

  const { data, loading, error, refresh } = useApiResource(() => request("/referrals"), [request]);

  const contacts = data?.contacts || [];
  const stats = useMemo(() => {
    const uniqueCompanies = new Set(
      contacts.map((contact) => String(contact.company || "").trim().toLowerCase()).filter(Boolean),
    );
    return {
      total: contacts.length,
      companies: uniqueCompanies.size,
      canRefer: contacts.filter((contact) => contact.can_refer).length,
    };
  }, [contacts]);

  function updateForm(patch) {
    setForm((current) => ({ ...current, ...patch }));
  }

  function startEditing(contact) {
    setEditingId(contact.contact_id);
    setForm({
      name: contact.name || "",
      company: contact.company || "",
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
    setActionState({ message: "", error: "", busyId: editingId || "new" });
    try {
      const path = editingId ? `/referrals/${editingId}` : "/referrals";
      const method = editingId ? "PUT" : "POST";
      await request(path, { method, body: form });
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

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-headline text-[2.25rem] font-extrabold leading-tight tracking-tight text-on-surface">
          Referrals
        </h1>
        <p className="mt-1 text-sm text-on-surface-variant">
          Keep a private database of people at target companies so the review queue can surface warm paths.
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        {[
          { label: "Contacts", value: stats.total },
          { label: "Target Companies", value: stats.companies },
          { label: "Can Refer", value: stats.canRefer },
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
        <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6">
          <div className="mb-5 flex items-start justify-between gap-4">
            <div>
              <h2 className="font-headline text-xl font-bold tracking-tight text-on-surface">
                {editingId ? "Edit Contact" : "Add Contact"}
              </h2>
              <p className="mt-1 text-sm text-on-surface-variant">
                Store the contact, their company, and whether they can actively refer you.
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

            <ReferralFormField label="Company">
              <input
                className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
                onChange={(event) => updateForm({ company: event.target.value })}
                placeholder="Acme GmbH"
                value={form.company}
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
                  Use this to prioritize warm-intro outreach in the review queue.
                </div>
              </div>
            </label>
          </div>

          {(actionState.message || actionState.error) && !actionState.busyId ? (
            <div className={["mt-4 text-sm", actionState.error ? "text-error" : "text-primary"].join(" ")}>
              {actionState.error || actionState.message}
            </div>
          ) : null}

          <div className="mt-6 flex flex-wrap gap-3">
            <button
              className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={!form.name.trim() || !form.company.trim() || Boolean(actionState.busyId)}
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

        <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest">
          <div className="border-b border-outline-variant/10 px-6 py-5">
            <h2 className="font-headline text-xl font-bold tracking-tight text-on-surface">
              Saved Contacts
            </h2>
            <p className="mt-1 text-sm text-on-surface-variant">
              These are matched against job-company names in the review queue.
            </p>
          </div>

          <div className="divide-y divide-outline-variant/10">
            {loading ? (
              <div className="px-6 py-10 text-on-surface-variant">Loading contacts...</div>
            ) : error ? (
              <div className="px-6 py-10 text-error">{error}</div>
            ) : contacts.length ? (
              contacts.map((contact) => (
                <article key={contact.contact_id} className="px-6 py-5">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-lg font-semibold text-on-surface">{contact.name}</h3>
                        <span className="rounded-full bg-surface-container-low px-2.5 py-1 text-xs font-medium text-on-surface">
                          {contact.company}
                        </span>
                        {contact.can_refer ? (
                          <span className="rounded-full bg-teal-500/10 px-2.5 py-1 text-xs font-semibold text-teal-500">
                            Can Refer
                          </span>
                        ) : (
                          <span className="rounded-full bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-500">
                            Warm Contact
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
                      <p className="max-w-2xl whitespace-pre-wrap text-sm leading-6 text-on-surface-variant">
                        {contact.relationship_note || "No relationship note saved yet."}
                      </p>
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
              ))
            ) : (
              <div className="px-6 py-10 text-on-surface-variant">
                No referral contacts yet. Add people at target companies so the review queue can flag warm paths.
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
