import { useEffect, useMemo, useState } from "react";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";

const settingsTabs = [
  "Profile",
  "Defaults",
  "Documents",
  "Review Preferences",
  "Account",
];

function SectionField({ label, children, hint = "" }) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-semibold text-on-surface">{label}</span>
      {children}
      {hint ? <span className="mt-2 block text-xs text-on-surface-variant">{hint}</span> : null}
    </label>
  );
}

function TextInput(props) {
  return (
    <input
      {...props}
      className={[
        "w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface",
        props.className || "",
      ].join(" ")}
    />
  );
}

function TextArea(props) {
  return (
    <textarea
      {...props}
      className={[
        "min-h-28 w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface",
        props.className || "",
      ].join(" ")}
    />
  );
}

function ToggleRow({ label, description, checked, onChange }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border border-outline-variant/10 bg-surface p-4">
      <div>
        <p className="text-sm font-semibold text-on-surface">{label}</p>
        <p className="mt-1 text-xs leading-6 text-on-surface-variant">{description}</p>
      </div>
      <button
        className={[
          "relative mt-1 h-7 w-12 rounded-full transition-colors",
          checked ? "bg-primary" : "bg-outline-variant/50",
        ].join(" ")}
        onClick={() => onChange(!checked)}
        type="button"
      >
        <span
          className={[
            "absolute top-1 h-5 w-5 rounded-full bg-white shadow-sm transition-all",
            checked ? "left-6" : "left-1",
          ].join(" ")}
        />
      </button>
    </div>
  );
}

function ExperienceEditor({ items, onChange }) {
  function updateItem(index, field, value) {
    const nextItems = items.map((item, itemIndex) =>
      itemIndex === index ? { ...item, [field]: value } : item,
    );
    onChange(nextItems);
  }

  function addItem() {
    onChange([...(items || []), { title: "", company: "", period: "" }]);
  }

  function removeItem(index) {
    onChange(items.filter((_, itemIndex) => itemIndex !== index));
  }

  return (
    <div className="space-y-4">
      {(items || []).map((item, index) => (
        <div key={`${item.title}-${index}`} className="rounded-lg border border-outline-variant/10 bg-surface p-4">
          <div className="grid gap-4 md:grid-cols-3">
            <TextInput
              onChange={(event) => updateItem(index, "title", event.target.value)}
              placeholder="Role title"
              value={item.title || ""}
            />
            <TextInput
              onChange={(event) => updateItem(index, "company", event.target.value)}
              placeholder="Company"
              value={item.company || ""}
            />
            <div className="flex gap-3">
              <TextInput
                className="flex-1"
                onChange={(event) => updateItem(index, "period", event.target.value)}
                placeholder="2022 - Present"
                value={item.period || ""}
              />
              <button
                className="rounded-lg border border-outline-variant/20 px-4 py-3 text-sm font-medium text-on-surface-variant transition-colors hover:bg-surface-container-low"
                onClick={() => removeItem(index)}
                type="button"
              >
                Remove
              </button>
            </div>
          </div>
        </div>
      ))}
      <button
        className="rounded-lg bg-surface-container-low px-4 py-2.5 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
        onClick={addItem}
        type="button"
      >
        Add Experience
      </button>
    </div>
  );
}

function ProfileTab({ draft, updateSection }) {
  const profile = draft.profile;
  const competenciesText = (profile.competencies || []).join("\n");

  return (
    <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8">
      <div className="space-y-6">
        <div className="grid gap-6 md:grid-cols-2">
          <SectionField label="Full Name">
            <TextInput
              onChange={(event) => updateSection("profile", { name: event.target.value })}
              value={profile.name || ""}
            />
          </SectionField>
          <SectionField label="Role Title">
            <TextInput
              onChange={(event) => updateSection("profile", { role_title: event.target.value })}
              value={profile.role_title || ""}
            />
          </SectionField>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          <SectionField label="Email">
            <TextInput
              onChange={(event) => updateSection("profile", { email: event.target.value })}
              value={profile.email || ""}
            />
          </SectionField>
          <SectionField label="Location">
            <TextInput
              onChange={(event) => updateSection("profile", { location: event.target.value })}
              value={profile.location || ""}
            />
          </SectionField>
          <SectionField label="Website / Portfolio">
            <TextInput
              onChange={(event) => updateSection("profile", { website: event.target.value })}
              value={profile.website || ""}
            />
          </SectionField>
        </div>

        <SectionField label="Avatar URL" hint="Used by the frontend card view.">
          <TextInput
            onChange={(event) => updateSection("profile", { avatar_url: event.target.value })}
            value={profile.avatar_url || ""}
          />
        </SectionField>

        <SectionField label="Professional Summary">
          <TextArea
            onChange={(event) => updateSection("profile", { summary: event.target.value })}
            value={profile.summary || ""}
          />
        </SectionField>

        <SectionField
          label="Core Competencies"
          hint="One competency per line. They will render as badges in the profile summary."
        >
          <TextArea
            onChange={(event) =>
              updateSection("profile", {
                competencies: event.target.value
                  .split("\n")
                  .map((item) => item.trim())
                  .filter(Boolean),
              })
            }
            value={competenciesText}
          />
        </SectionField>

        <div>
          <div className="mb-2 text-sm font-semibold text-on-surface">Recent Experience</div>
          <ExperienceEditor
            items={profile.recent_experience || []}
            onChange={(value) => updateSection("profile", { recent_experience: value })}
          />
        </div>
      </div>
    </section>
  );
}

function DefaultsTab({ draft, updateSection }) {
  const defaults = draft.defaults;
  const options = draft.options;
  return (
    <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8">
      <div className="grid gap-6 md:grid-cols-2">
        <SectionField label="Default Workspace">
          <select
            className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateSection("defaults", { default_workspace_id: event.target.value })}
            value={defaults.default_workspace_id || ""}
          >
            <option value="">Select workspace</option>
            {(options.workspaces || []).map((workspace) => (
              <option key={workspace.id} value={workspace.id}>
                {workspace.name}
              </option>
            ))}
          </select>
        </SectionField>

        <SectionField label="Default Execution Mode">
          <select
            className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) =>
              updateSection("defaults", { default_execution_mode: event.target.value })
            }
            value={defaults.default_execution_mode || ""}
          >
            {(options.execution_modes || []).map((mode) => (
              <option key={mode.id} value={mode.id}>
                {mode.label}
              </option>
            ))}
          </select>
        </SectionField>

        <SectionField label="Default Profile">
          <select
            className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateSection("defaults", { default_profile_id: event.target.value })}
            value={defaults.default_profile_id || ""}
          >
            <option value="">Select profile</option>
            {(options.profiles || []).map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.label}
              </option>
            ))}
          </select>
        </SectionField>

        <SectionField label="Default Prompt Set">
          <select
            className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) =>
              updateSection("defaults", { default_prompt_set_id: event.target.value })
            }
            value={defaults.default_prompt_set_id || ""}
          >
            <option value="">Select prompt set</option>
            {(options.prompt_sets || []).map((promptSet) => (
              <option key={promptSet.id} value={promptSet.id}>
                {promptSet.id}
              </option>
            ))}
          </select>
        </SectionField>
      </div>

      <div className="mt-6 max-w-xs">
        <SectionField label="Max Jobs Per Run">
          <TextInput
            min="1"
            onChange={(event) =>
              updateSection("defaults", { max_jobs_per_run: Number(event.target.value || 1) })
            }
            type="number"
            value={defaults.max_jobs_per_run ?? 25}
          />
        </SectionField>
      </div>
    </section>
  );
}

function DocumentsTab({ draft, updateSection }) {
  const documents = draft.documents;
  const options = draft.options;
  return (
    <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8">
      <div className="space-y-4">
        <ToggleRow
          checked={Boolean(documents.generate_docx)}
          description="Generate Microsoft Word application files for each produced artifact."
          label="Generate DOCX"
          onChange={(value) => updateSection("documents", { generate_docx: value })}
        />
        <ToggleRow
          checked={Boolean(documents.generate_pdf)}
          description="Generate PDF output alongside DOCX when the renderer supports it."
          label="Generate PDF"
          onChange={(value) => updateSection("documents", { generate_pdf: value })}
        />
        <ToggleRow
          checked={Boolean(documents.export_tracker)}
          description="Write tracker exports such as Excel reports and summary files."
          label="Export Tracker"
          onChange={(value) => updateSection("documents", { export_tracker: value })}
        />
        <ToggleRow
          checked={Boolean(documents.export_package)}
          description="Keep packaging artifacts such as JSON bundles and email drafts."
          label="Export Package"
          onChange={(value) => updateSection("documents", { export_package: value })}
        />
      </div>

      <div className="mt-6 max-w-md">
        <SectionField label="File Naming Strategy">
          <select
            className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateSection("documents", { file_naming: event.target.value })}
            value={documents.file_naming || ""}
          >
            {(options.document_naming_modes || []).map((mode) => (
              <option key={mode.id} value={mode.id}>
                {mode.label}
              </option>
            ))}
          </select>
        </SectionField>
      </div>
    </section>
  );
}

function ReviewPreferencesTab({ draft, updateSection }) {
  const reviewPreferences = draft.review_preferences;
  const options = draft.options;
  return (
    <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8">
      <div className="space-y-4">
        <ToggleRow
          checked={Boolean(reviewPreferences.require_review_before_use)}
          description="Force a manual review step before the generated application package is used."
          label="Require Review Before Use"
          onChange={(value) =>
            updateSection("review_preferences", { require_review_before_use: value })
          }
        />
        <ToggleRow
          checked={Boolean(reviewPreferences.rejection_note_required)}
          description="Require reviewers to enter a note whenever they reject a generated job package."
          label="Rejection Note Required"
          onChange={(value) =>
            updateSection("review_preferences", { rejection_note_required: value })
          }
        />
        <ToggleRow
          checked={Boolean(reviewPreferences.auto_open_next_item)}
          description="After an approve or reject action, automatically advance the review queue."
          label="Auto Open Next Item"
          onChange={(value) => updateSection("review_preferences", { auto_open_next_item: value })}
        />
      </div>

      <div className="mt-6 max-w-md">
        <SectionField label="Default Review State">
          <select
            className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) =>
              updateSection("review_preferences", { default_decision_state: event.target.value })
            }
            value={reviewPreferences.default_decision_state || ""}
          >
            {(options.review_default_states || []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </SectionField>
      </div>
    </section>
  );
}

function AccountTab({ draft, updateSection }) {
  const account = draft.account;
  const workspaceSummary = (account.allowed_workspace_ids || []).length
    ? account.allowed_workspace_ids.join(", ")
    : "All accessible workspaces";
  return (
    <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8">
      <div className="grid gap-6 md:grid-cols-2">
        <SectionField label="Display Name">
          <TextInput
            onChange={(event) => updateSection("account", { display_name: event.target.value })}
            value={account.display_name || ""}
          />
        </SectionField>
        <SectionField label="Email">
          <TextInput
            onChange={(event) => updateSection("account", { email: event.target.value })}
            value={account.email || ""}
          />
        </SectionField>
      </div>

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <div className="rounded-lg bg-surface-container-low p-5">
          <h4 className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Role</h4>
          <p className="mt-3 text-lg font-semibold text-on-surface">{account.role || "viewer"}</p>
        </div>
        <div className="rounded-lg bg-surface-container-low p-5">
          <h4 className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">
            Workspace Access
          </h4>
          <p className="mt-3 text-sm leading-7 text-on-surface">{workspaceSummary}</p>
        </div>
      </div>
    </section>
  );
}

export default function SettingsPage() {
  const { request } = useSession();
  const [activeTab, setActiveTab] = useState("Profile");
  const [draft, setDraft] = useState(null);
  const [saveState, setSaveState] = useState({ message: "", error: "" });

  const { data, loading, error, refresh } = useApiResource(() => request("/settings"), [request]);

  useEffect(() => {
    if (data) {
      setDraft(data);
    }
  }, [data]);

  const isDirty = useMemo(() => {
    if (!draft || !data) return false;
    return JSON.stringify(draft) !== JSON.stringify(data);
  }, [data, draft]);

  function updateSection(section, patch) {
    setDraft((current) => ({
      ...current,
      [section]: {
        ...(current?.[section] || {}),
        ...patch,
      },
    }));
  }

  async function handleSave() {
    if (!draft) return;
    setSaveState({ message: "", error: "" });
    try {
      const payload = await request("/settings", {
        method: "PUT",
        body: {
          profile: draft.profile,
          defaults: draft.defaults,
          documents: draft.documents,
          review_preferences: draft.review_preferences,
          account: draft.account,
        },
      });
      setDraft(payload);
      setSaveState({ message: "Settings saved.", error: "" });
      refresh().catch(() => undefined);
    } catch (saveError) {
      setSaveState({ message: "", error: saveError.message || "Unable to save settings." });
    }
  }

  function handleDiscard() {
    if (data) {
      setDraft(data);
      setSaveState({ message: "", error: "" });
    }
  }

  const profile = draft?.profile || {};
  const account = draft?.account || {};

  return (
    <div className="space-y-10">
      <section>
        <h1 className="mb-8 font-headline text-[2rem] font-extrabold leading-tight tracking-tight text-on-surface">
          Settings
        </h1>
        <div className="inline-flex max-w-full gap-1 overflow-x-auto rounded-lg bg-surface-container-low p-1.5">
          {settingsTabs.map((tab) => (
            <button
              key={tab}
              className={[
                "whitespace-nowrap rounded-md px-5 py-2.5 text-sm font-medium transition-colors",
                activeTab === tab
                  ? "bg-surface-container-lowest text-on-surface shadow-soft"
                  : "text-on-surface-variant hover:bg-surface-container-high/50 hover:text-on-surface",
              ].join(" ")}
              onClick={() => setActiveTab(tab)}
              type="button"
            >
              {tab}
            </button>
          ))}
        </div>
      </section>

      {loading && !draft ? (
        <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8 text-on-surface-variant">
          Loading settings...
        </div>
      ) : error && !draft ? (
        <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8">
          <p className="text-error">{error}</p>
          <button
            className="mt-4 rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
            onClick={() => refresh().catch(() => undefined)}
            type="button"
          >
            Retry
          </button>
        </div>
      ) : draft ? (
        <div className="grid grid-cols-1 gap-8 xl:grid-cols-12">
          <div className="flex flex-col gap-8 xl:col-span-4">
            <section className="relative overflow-hidden rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8 text-center">
              <div className="absolute left-0 top-0 h-24 w-full bg-gradient-to-br from-surface-container-low to-surface-container-high" />
              <div className="relative z-10 mb-6">
                <div className="relative mx-auto w-fit">
                  <img
                    alt={profile.name || account.display_name}
                    className="mx-auto h-28 w-28 rounded-full border-4 border-surface-container-lowest object-cover shadow-sm"
                    src={
                      profile.avatar_url ||
                      "https://lh3.googleusercontent.com/aida-public/AB6AXuCEbDDRgu4_REnkpR4gbSify0khawEFxHuQHLBm7Xbd6BmM7LDM-dlp8wOKL0QkSDuiFg7g9UDpYPZnV2uV8Qmu5cxn1MBriXeVmXUz8EGMsgieO36lJEpcY5FCDph2ooQGzwpKRq5qwQluOCY4JB_gfySIUY2T0ozlVp3DEmdnT9aCfADFkC1BXeteFPTxYhtUsABzZLWUOD6fNpuVFVFLjuxpQaEgkpVd_bvuz61H_FfJkq5V_4CESVQjz3tEa3rwtGfzcKHXwJE"
                    }
                  />
                  <button className="absolute bottom-0 right-0 rounded-full border border-outline-variant/20 bg-surface-container-lowest p-2 text-on-surface-variant shadow-sm transition-colors hover:text-primary">
                    <span className="material-symbols-outlined text-[18px]">edit</span>
                  </button>
                </div>
              </div>

              <h2 className="relative z-10 mb-1 font-headline text-2xl font-bold tracking-tight text-on-surface">
                {profile.name || account.display_name}
              </h2>
              <p className="relative z-10 mb-4 text-sm font-medium text-primary">
                {profile.role_title || "Profile Not Set"}
              </p>

              <div className="relative z-10 mt-4 space-y-3 text-left">
                <div className="flex items-center gap-3 text-sm text-on-surface-variant">
                  <span className="material-symbols-outlined text-[18px] text-outline">mail</span>
                  {profile.email || account.email || "No email"}
                </div>
                <div className="flex items-center gap-3 text-sm text-on-surface-variant">
                  <span className="material-symbols-outlined text-[18px] text-outline">location_on</span>
                  {profile.location || "No location configured"}
                </div>
                <div className="flex items-center gap-3 text-sm text-on-surface-variant">
                  <span className="material-symbols-outlined text-[18px] text-outline">link</span>
                  {profile.website || "No website configured"}
                </div>
              </div>
            </section>

            <section className="rounded-xl bg-surface-container-low p-6">
              <h3 className="mb-4 font-headline text-lg font-bold text-on-surface">
                Quick Document Actions
              </h3>
              <div className="flex flex-col gap-3">
                <button className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-br from-primary to-primary-container px-4 py-3 text-sm font-medium text-white shadow-sm transition-all hover:saturate-150 active:scale-[0.98]">
                  <span className="material-symbols-outlined text-[20px]">upload_file</span>
                  Upload New CV
                </button>
                <button className="flex w-full items-center justify-center gap-2 rounded-lg border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm font-medium text-on-surface transition-all hover:bg-surface-container-high active:scale-[0.98]">
                  <span className="material-symbols-outlined text-[20px]">find_replace</span>
                  Replace Current CV
                </button>
              </div>
            </section>
          </div>

          <div className="flex flex-col gap-8 xl:col-span-8">
            {activeTab === "Profile" ? (
              <ProfileTab draft={draft} updateSection={updateSection} />
            ) : null}
            {activeTab === "Defaults" ? (
              <DefaultsTab draft={draft} updateSection={updateSection} />
            ) : null}
            {activeTab === "Documents" ? (
              <DocumentsTab draft={draft} updateSection={updateSection} />
            ) : null}
            {activeTab === "Review Preferences" ? (
              <ReviewPreferencesTab draft={draft} updateSection={updateSection} />
            ) : null}
            {activeTab === "Account" ? (
              <AccountTab draft={draft} updateSection={updateSection} />
            ) : null}

            <div className="sticky bottom-8 self-end rounded-xl border border-outline-variant/20 bg-surface-container-lowest/80 p-4 shadow-soft backdrop-blur-[20px]">
              <div className="flex items-center gap-4">
                <span className="mr-auto pl-2 text-sm text-on-surface-variant">
                  {saveState.error
                    ? saveState.error
                    : saveState.message || (isDirty ? "You have unsaved changes" : "Everything is saved")}
                </span>
                <button
                  className="rounded px-5 py-2.5 text-sm font-medium text-on-surface-variant transition-colors hover:text-on-surface active:scale-[0.98]"
                  onClick={handleDiscard}
                  type="button"
                >
                  Discard Changes
                </button>
                <button
                  className="flex items-center gap-2 rounded-lg bg-gradient-to-br from-primary to-primary-container px-6 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:saturate-150 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={!isDirty}
                  onClick={handleSave}
                  type="button"
                >
                  <span className="material-symbols-outlined text-[18px]">save</span>
                  Save Changes
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
