import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { labelize } from "../lib/formatters";

const DEFAULT_FLOW_ID = "tailored_documents";
const SYSTEM_SETTING_KEYS = new Set([
  "automation_flow",
  "config_loader",
  "manual_sources_are_preapproved",
]);

const EMPTY_BUILDER_FORM = {
  name: "",
  description: "",
  flowId: DEFAULT_FLOW_ID,
  sourceIds: [],
  moduleIds: [],
  profileLabel: "",
  promptFamily: "",
  manualSourcesArePreapproved: true,
  settings: {},
};

function TogglePill({ checked, label, onClick }) {
  return (
    <button
      className={[
        "rounded-full border px-3 py-1.5 text-sm font-medium transition-colors",
        checked
          ? "border-primary/30 bg-primary/10 text-primary"
          : "border-outline-variant/20 bg-surface-container-low text-on-surface-variant hover:bg-surface-container-high",
      ].join(" ")}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  );
}

function BuilderSection({ title, description, children }) {
  return (
    <section className="space-y-3 rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6">
      <div>
        <h3 className="font-headline text-lg font-bold text-on-surface">{title}</h3>
        <p className="mt-1 text-sm leading-6 text-on-surface-variant">{description}</p>
      </div>
      {children}
    </section>
  );
}

function buildDefaultSettings(catalog, flowId) {
  const defaults = {};
  for (const field of catalog?.configuration_fields || []) {
    if (!(field.compatible_flows || []).includes(flowId)) {
      continue;
    }
    if (Object.prototype.hasOwnProperty.call(field, "default")) {
      defaults[field.id] = field.default;
    }
  }
  return defaults;
}

function defaultModuleIdsForFlow(catalog, flowId) {
  return (catalog?.modules || [])
    .filter((item) => (item.compatible_flows || []).includes(flowId) && item.default_enabled)
    .map((item) => item.id);
}

function selectedSourcesForFields(form, availableSources) {
  if (form.sourceIds.length) {
    return new Set(form.sourceIds);
  }
  return new Set((availableSources || []).map((item) => item.id));
}

function fieldMatchesSelection(field, form, availableSources) {
  if (!(field.compatible_flows || []).includes(form.flowId)) {
    return false;
  }
  const fieldSourceIds = field.source_ids || [];
  if (!fieldSourceIds.length) {
    return true;
  }
  const activeSources = selectedSourcesForFields(form, availableSources);
  return fieldSourceIds.some((sourceId) => activeSources.has(sourceId));
}

function normalizeWorkspaceSettingValue(value) {
  if (Array.isArray(value)) {
    return [...value];
  }
  if (value && typeof value === "object") {
    return { ...value };
  }
  return value;
}

function formatSettingValue(value) {
  if (Array.isArray(value)) {
    return value.length ? value.join(", ") : "Not set";
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (value && typeof value === "object") {
    return JSON.stringify(value);
  }
  if (value === undefined || value === null || value === "") {
    return "Not set";
  }
  return String(value);
}

function settingDisplayValue(field, value) {
  if (field.type === "tag_list") {
    return Array.isArray(value) ? value.join(", ") : "";
  }
  if (field.type === "multi_select") {
    return Array.isArray(value) ? value : [];
  }
  if (value === undefined || value === null) {
    return "";
  }
  return String(value);
}

function workspaceAutomationFlow(workspace) {
  return (
    workspace.automation_flow ||
    workspace.metadata?.automation_flow ||
    workspace.settings?.automation_flow ||
    DEFAULT_FLOW_ID
  );
}

function workspaceSourceIds(workspace, catalog, flowId) {
  const explicitSourceIds = workspace.metadata?.source_ids || [];
  if (explicitSourceIds.length) {
    return [...explicitSourceIds];
  }
  const sourceByConnector = new Map(
    (catalog?.sources || []).map((source) => [source.connector_id, source.id]),
  );
  const derived = (workspace.sources || [])
    .map((source) => sourceByConnector.get(source.connector_id))
    .filter(Boolean);
  if (derived.length) {
    return derived;
  }
  return (catalog?.sources || [])
    .filter((source) => (source.compatible_flows || []).includes(flowId))
    .map((source) => source.id);
}

function hydrateFormFromWorkspace(workspace, catalog) {
  const flowId = workspaceAutomationFlow(workspace);
  const fieldIds = new Set((catalog?.configuration_fields || []).map((field) => field.id));
  const settings = {};
  for (const [key, value] of Object.entries(workspace.settings || {})) {
    if (!fieldIds.has(key)) {
      continue;
    }
    settings[key] = normalizeWorkspaceSettingValue(value);
  }

  return {
    name: workspace.name || "",
    description: workspace.description || "",
    flowId,
    sourceIds: workspaceSourceIds(workspace, catalog, flowId),
    moduleIds:
      workspace.metadata?.modules?.length
        ? [...workspace.metadata.modules]
        : defaultModuleIdsForFlow(catalog, flowId),
    profileLabel: workspace.profiles?.[0]?.label || "",
    promptFamily: workspace.prompt_sets?.[0]?.family || flowId,
    manualSourcesArePreapproved: Boolean(
      workspace.settings?.manual_sources_are_preapproved ?? true,
    ),
    settings,
  };
}

function workspaceSettingEntries(workspace, catalog) {
  const fieldMap = new Map(
    (catalog?.configuration_fields || []).map((field) => [field.id, field]),
  );
  return Object.entries(workspace.settings || {}).map(([key, value]) => ({
    key,
    label: fieldMap.get(key)?.label || labelize(key),
    value: formatSettingValue(value),
    internal: SYSTEM_SETTING_KEYS.has(key),
  }));
}

function FieldRenderer({ field, value, onChange }) {
  if (field.type === "multi_select") {
    const selectedValues = Array.isArray(value) ? value : [];
    return (
      <div className="space-y-2">
        <div className="flex flex-wrap gap-3">
          {(field.options || []).map((option) => {
            const checked = selectedValues.some((item) => String(item) === String(option.value));
            return (
              <TogglePill
                checked={checked}
                key={`${field.id}-${option.value}`}
                label={option.label}
                onClick={() => {
                  const next = checked
                    ? selectedValues.filter((item) => String(item) !== String(option.value))
                    : [...selectedValues, option.value];
                  onChange(next);
                }}
              />
            );
          })}
        </div>
      </div>
    );
  }

  if (field.type === "select") {
    return (
      <select
        className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
        onChange={(event) => onChange(event.target.value)}
        value={settingDisplayValue(field, value)}
      >
        <option value="">Use workspace default</option>
        {(field.options || []).map((option) => (
          <option key={`${field.id}-${option.value}`} value={String(option.value)}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }

  return (
    <input
      className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
      onChange={(event) => onChange(event.target.value)}
      placeholder={field.placeholder || ""}
      type={field.type === "number" ? "number" : "text"}
      value={settingDisplayValue(field, value)}
    />
  );
}

export default function WorkspacesPage() {
  const navigate = useNavigate();
  const { request } = useSession();
  const [actionState, setActionState] = useState({
    workspaceId: "",
    message: "",
    error: "",
  });
  const [builderState, setBuilderState] = useState({
    open: false,
    mode: "create",
    editingWorkspaceId: "",
    submitting: false,
    deleting: "",
    error: "",
    message: "",
  });
  const [form, setForm] = useState(EMPTY_BUILDER_FORM);

  const {
    data: workspacesData,
    loading,
    error,
    refresh,
  } = useApiResource(() => request("/workspaces?limit=100"), [request]);
  const {
    data: builderCatalog,
    loading: builderLoading,
    error: builderError,
  } = useApiResource(() => request("/workspace-builder/catalog"), [request]);

  const workspaces = workspacesData?.workspaces || [];
  const flows = builderCatalog?.flows || [];
  const availableSources = useMemo(
    () =>
      (builderCatalog?.sources || []).filter((item) =>
        (item.compatible_flows || []).includes(form.flowId),
      ),
    [builderCatalog, form.flowId],
  );
  const availableModules = useMemo(
    () =>
      (builderCatalog?.modules || []).filter((item) =>
        (item.compatible_flows || []).includes(form.flowId),
      ),
    [builderCatalog, form.flowId],
  );
  const availableConfigurationFields = useMemo(
    () =>
      (builderCatalog?.configuration_fields || []).filter((field) =>
        fieldMatchesSelection(field, form, availableSources),
      ),
    [builderCatalog, form, availableSources],
  );

  function resetBuilderState(overrides = {}) {
    setBuilderState({
      open: false,
      mode: "create",
      editingWorkspaceId: "",
      submitting: false,
      deleting: "",
      error: "",
      message: "",
      ...overrides,
    });
  }

  function openBuilder() {
    const defaultFlowId = flows[0]?.id || DEFAULT_FLOW_ID;
    setForm({
      ...EMPTY_BUILDER_FORM,
      flowId: defaultFlowId,
      moduleIds: defaultModuleIdsForFlow(builderCatalog, defaultFlowId),
      promptFamily: defaultFlowId,
      profileLabel:
        defaultFlowId === "reusable_packages"
          ? "Operations Profile"
          : "Primary Job Seeker Profile",
      settings: buildDefaultSettings(builderCatalog, defaultFlowId),
    });
    resetBuilderState({ open: true });
  }

  function openEditor(workspace) {
    setForm(hydrateFormFromWorkspace(workspace, builderCatalog));
    resetBuilderState({
      open: true,
      mode: "edit",
      editingWorkspaceId: workspace.id,
    });
  }

  function closeBuilder() {
    resetBuilderState();
    setForm(EMPTY_BUILDER_FORM);
  }

  function updateForm(patch) {
    setForm((current) => ({ ...current, ...patch }));
  }

  function updateSetting(fieldId, value) {
    setForm((current) => ({
      ...current,
      settings: {
        ...current.settings,
        [fieldId]: value,
      },
    }));
  }

  function setFlow(flowId) {
    setForm((current) => ({
      ...current,
      flowId,
      sourceIds: [],
      moduleIds: defaultModuleIdsForFlow(builderCatalog, flowId),
      promptFamily: flowId,
      profileLabel:
        flowId === "reusable_packages"
          ? "Operations Profile"
          : "Primary Job Seeker Profile",
      settings: buildDefaultSettings(builderCatalog, flowId),
    }));
  }

  function toggleValue(key, value) {
    setForm((current) => {
      const currentValues = new Set(current[key] || []);
      if (currentValues.has(value)) {
        currentValues.delete(value);
      } else {
        currentValues.add(value);
      }
      return { ...current, [key]: [...currentValues] };
    });
  }

  async function submitWorkspace() {
    const isEditing = builderState.mode === "edit";
    const path = isEditing
      ? `/workspace-builder/workspaces/${builderState.editingWorkspaceId}`
      : "/workspace-builder/workspaces";

    setBuilderState((current) => ({
      ...current,
      submitting: true,
      error: "",
      message: "",
    }));

    try {
      const workspace = await request(path, {
        method: isEditing ? "PUT" : "POST",
        body: {
          name: form.name,
          description: form.description,
          flow_id: form.flowId,
          source_ids: form.sourceIds,
          module_ids: form.moduleIds,
          profile_label: form.profileLabel,
          prompt_family: form.promptFamily,
          manual_sources_are_preapproved: form.manualSourcesArePreapproved,
          settings: form.settings,
        },
      });
      resetBuilderState({
        message: `${isEditing ? "Updated" : "Created"} ${workspace.name}`,
      });
      setForm(EMPTY_BUILDER_FORM);
      await refresh();
    } catch (submitError) {
      setBuilderState((current) => ({
        ...current,
        submitting: false,
        error: submitError.message || "Unable to save workspace.",
      }));
    }
  }

  async function triggerRun(workspaceId, executionMode) {
    setActionState({ workspaceId, message: "", error: "" });
    try {
      const run = await request("/runs", {
        method: "POST",
        body: {
          workspace_id: workspaceId,
          execution_mode: executionMode,
          max_attempts: 1,
        },
      });
      setActionState({
        workspaceId,
        message:
          executionMode === "sync"
            ? `Run ${run.id} finished with status ${labelize(run.status)}`
            : `Queued ${run.id}`,
        error: "",
      });
      await refresh();
      if (executionMode === "sync") {
        navigate(`/runs/${run.id}`);
      }
    } catch (runError) {
      setActionState({
        workspaceId,
        message: "",
        error: runError.message || "Unable to start run.",
      });
    }
  }

  async function deleteWorkspace(workspaceId) {
    setBuilderState((current) => ({
      ...current,
      deleting: workspaceId,
      message: "",
      error: "",
    }));
    try {
      await request(`/workspaces/${workspaceId}`, { method: "DELETE" });
      setActionState({
        workspaceId,
        message: `Deleted ${workspaceId}`,
        error: "",
      });
      setBuilderState((current) => ({ ...current, deleting: "", message: "", error: "" }));
      await refresh();
    } catch (deleteError) {
      setActionState({
        workspaceId,
        message: "",
        error: deleteError.message || "Unable to delete workspace.",
      });
      setBuilderState((current) => ({ ...current, deleting: "", message: "", error: "" }));
    }
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="flex flex-col gap-2">
          <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
            Workspaces
          </h1>
          <p className="text-sm text-on-surface-variant">
            Build each job-seeker workspace from scratch, inspect all saved settings, edit them later, and run directly from the app.
          </p>
          <p className="text-xs uppercase tracking-wider text-on-surface-variant/80">
            Run Now executes inside the app. Queue Run only waits for a worker.
          </p>
        </div>
        <button
          className="rounded bg-gradient-to-br from-primary to-primary-container px-5 py-3 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90"
          onClick={openBuilder}
          type="button"
        >
          Create Workspace From Scratch
        </button>
      </header>

      {builderState.message ? (
        <div className="rounded-xl bg-surface-container-low px-4 py-3 text-sm text-on-surface">
          {builderState.message}
        </div>
      ) : null}

      {builderState.open ? (
        <div className="grid gap-6 xl:grid-cols-12">
          <div className="space-y-6 xl:col-span-8">
            <BuilderSection
              description="Give the workspace a clear name and describe what kind of search or application output it should handle."
              title="Workspace Identity"
            >
              <div className="grid gap-4 md:grid-cols-2">
                <input
                  className="rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
                  onChange={(event) => updateForm({ name: event.target.value })}
                  placeholder="Workspace name"
                  value={form.name}
                />
                <input
                  className="rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
                  onChange={(event) => updateForm({ promptFamily: event.target.value })}
                  placeholder="Prompt family"
                  value={form.promptFamily}
                />
              </div>
              <textarea
                className="min-h-28 w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
                onChange={(event) => updateForm({ description: event.target.value })}
                placeholder="Describe what this workspace is for."
                value={form.description}
              />
            </BuilderSection>

            <BuilderSection
              description="Choose the outcome this workspace should produce. This decides the available sources and modules."
              title="Automation Flow"
            >
              <div className="flex flex-wrap gap-3">
                {flows.map((flow) => (
                  <TogglePill
                    checked={form.flowId === flow.id}
                    key={flow.id}
                    label={flow.name}
                    onClick={() => setFlow(flow.id)}
                  />
                ))}
              </div>
              <p className="text-sm text-on-surface-variant">
                {flows.find((flow) => flow.id === form.flowId)?.description || ""}
              </p>
            </BuilderSection>

            <BuilderSection
              description="Pick where jobs should come from. One workspace can blend multiple compatible sources."
              title="Sources"
            >
              {availableSources.length ? (
                <div className="flex flex-wrap gap-3">
                  {availableSources.map((source) => (
                    <TogglePill
                      checked={form.sourceIds.includes(source.id)}
                      key={source.id}
                      label={source.name}
                      onClick={() => toggleValue("sourceIds", source.id)}
                    />
                  ))}
                </div>
              ) : (
                <p className="text-sm text-on-surface-variant">No sources are available for this flow.</p>
              )}
            </BuilderSection>

            <BuilderSection
              description="Choose the baseline automation modules that should run after jobs are sourced."
              title="Automation Modules"
            >
              {availableModules.length ? (
                <div className="space-y-3">
                  {availableModules.map((module) => (
                    <label
                      className="flex items-start gap-3 rounded-lg border border-outline-variant/10 bg-surface p-4"
                      key={module.id}
                    >
                      <input
                        checked={form.moduleIds.includes(module.id)}
                        className="mt-1"
                        onChange={() => toggleValue("moduleIds", module.id)}
                        type="checkbox"
                      />
                      <span>
                        <span className="block text-sm font-semibold text-on-surface">{module.name}</span>
                        <span className="mt-1 block text-xs leading-6 text-on-surface-variant">
                          {module.description}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-on-surface-variant">No modules are available for this flow.</p>
              )}
            </BuilderSection>

            <BuilderSection
              description="Set the search and routing values that make this workspace behave like a real job-seeker setup rather than a fixed preset."
              title="Search And Routing Settings"
            >
              {availableConfigurationFields.length ? (
                <div className="grid gap-4 md:grid-cols-2">
                  {availableConfigurationFields.map((field) => (
                    <label className="space-y-2" key={field.id}>
                      <span className="block text-sm font-semibold text-on-surface">{field.label}</span>
                      <FieldRenderer
                        field={field}
                        onChange={(nextValue) => updateSetting(field.id, nextValue)}
                        value={form.settings[field.id]}
                      />
                      <span className="block text-xs leading-6 text-on-surface-variant">
                        {field.description}
                      </span>
                    </label>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-on-surface-variant">
                  Select a source to see the settings that apply to that workspace.
                </p>
              )}
            </BuilderSection>
          </div>

          <div className="space-y-6 xl:col-span-4">
            <BuilderSection
              description="Set the baseline job-seeker profile and how curated sources should be treated."
              title="Profile Defaults"
            >
              <input
                className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
                onChange={(event) => updateForm({ profileLabel: event.target.value })}
                placeholder="Profile label"
                value={form.profileLabel}
              />
              <label className="flex items-center gap-3 rounded-lg border border-outline-variant/10 bg-surface p-4 text-sm text-on-surface">
                <input
                  checked={form.manualSourcesArePreapproved}
                  onChange={(event) =>
                    updateForm({ manualSourcesArePreapproved: event.target.checked })
                  }
                  type="checkbox"
                />
                Treat curated job URLs as already reviewed by the user
              </label>
            </BuilderSection>

            <BuilderSection
              description="Review the selected baseline before saving the workspace."
              title="Workspace Summary"
            >
              <div className="space-y-2 text-sm text-on-surface-variant">
                <div>
                  <span className="font-semibold text-on-surface">Flow:</span>{" "}
                  {labelize(form.flowId)}
                </div>
                <div>
                  <span className="font-semibold text-on-surface">Sources:</span>{" "}
                  {form.sourceIds.length ? form.sourceIds.map(labelize).join(", ") : "None selected"}
                </div>
                <div>
                  <span className="font-semibold text-on-surface">Modules:</span>{" "}
                  {form.moduleIds.length ? form.moduleIds.map(labelize).join(", ") : "None selected"}
                </div>
                <div>
                  <span className="font-semibold text-on-surface">Profile:</span>{" "}
                  {form.profileLabel || "Not set"}
                </div>
              </div>

              {builderError ? <p className="text-sm text-error">{builderError}</p> : null}
              {builderState.error ? <p className="text-sm text-error">{builderState.error}</p> : null}

              <div className="flex gap-3">
                <button
                  className="flex-1 rounded bg-surface-container-low px-4 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                  onClick={closeBuilder}
                  type="button"
                >
                  Cancel
                </button>
                <button
                  className="flex-1 rounded bg-gradient-to-br from-primary to-primary-container px-4 py-3 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={
                    builderLoading ||
                    builderState.submitting ||
                    !form.name.trim() ||
                    !form.sourceIds.length ||
                    !form.moduleIds.length
                  }
                  onClick={submitWorkspace}
                  type="button"
                >
                  {builderState.submitting
                    ? builderState.mode === "edit"
                      ? "Saving..."
                      : "Creating..."
                    : builderState.mode === "edit"
                      ? "Save Workspace"
                      : "Create Workspace"}
                </button>
              </div>
            </BuilderSection>
          </div>
        </div>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-2">
        {loading ? (
          <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 text-on-surface-variant shadow-soft xl:col-span-2">
            Loading workspaces...
          </div>
        ) : error ? (
          <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft xl:col-span-2">
            <p className="text-error">{error}</p>
            <button
              className="mt-4 rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
              onClick={() => refresh().catch(() => undefined)}
              type="button"
            >
              Retry
            </button>
          </div>
        ) : workspaces.length ? (
          workspaces.map((workspace) => {
            const moduleLabels = (workspace.metadata?.modules || [])
              .map((moduleId) => labelize(moduleId))
              .join(", ");
            const sourceLabels = (workspace.sources || [])
              .map((source) => labelize(source.connector_id))
              .join(", ");
            const settingEntries = workspaceSettingEntries(workspace, builderCatalog);

            return (
              <article
                key={workspace.id}
                className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="font-headline text-xl font-bold text-on-surface">{workspace.name}</h2>
                    <p className="mt-1 text-xs uppercase tracking-wider text-primary">
                      {labelize(workspaceAutomationFlow(workspace))}
                    </p>
                  </div>
                </div>

                <p className="mt-4 text-sm leading-7 text-on-surface-variant">
                  {workspace.description || "No description provided."}
                </p>

                <div className="mt-5 space-y-3 text-sm text-on-surface-variant">
                  <div>
                    <span className="font-semibold text-on-surface">Sources:</span>{" "}
                    {sourceLabels || "N/A"}
                  </div>
                  <div>
                    <span className="font-semibold text-on-surface">Modules:</span>{" "}
                    {moduleLabels || "N/A"}
                  </div>
                  <div>
                    <span className="font-semibold text-on-surface">Profile:</span>{" "}
                    {workspace.profiles?.[0]?.label || "N/A"}
                  </div>
                  <div>
                    <span className="font-semibold text-on-surface">Prompt Family:</span>{" "}
                    {workspace.prompt_sets?.[0]?.family || "N/A"}
                  </div>
                </div>

                {settingEntries.length ? (
                  <div className="mt-5 space-y-3">
                    <h3 className="text-sm font-semibold text-on-surface">Saved Configuration</h3>
                    <div className="grid gap-3 md:grid-cols-2">
                      {settingEntries.map((entry) => (
                        <div
                          className="rounded-lg border border-outline-variant/10 bg-surface p-3"
                          key={`${workspace.id}-${entry.key}`}
                        >
                          <div className="text-[11px] uppercase tracking-wider text-on-surface-variant">
                            {entry.label}
                            {entry.internal ? " · Internal" : ""}
                          </div>
                          <div className="mt-1 text-sm text-on-surface">{entry.value}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

                {actionState.workspaceId === workspace.id &&
                (actionState.message || actionState.error) ? (
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

                <div className="mt-6 flex flex-wrap gap-3">
                  <button
                    className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90"
                    onClick={() => triggerRun(workspace.id, "sync")}
                    type="button"
                  >
                    Run Now
                  </button>
                  <button
                    className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                    onClick={() => triggerRun(workspace.id, "queued")}
                    type="button"
                  >
                    Queue Run
                  </button>
                  <button
                    className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                    onClick={() => openEditor(workspace)}
                    type="button"
                  >
                    Edit Workspace
                  </button>
                  <Link
                    className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                    to={`/runs?workspace_id=${workspace.id}`}
                  >
                    View Runs
                  </Link>
                  <button
                    className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-error-container hover:text-on-error-container disabled:cursor-not-allowed disabled:opacity-60"
                    disabled={builderState.deleting === workspace.id}
                    onClick={() => deleteWorkspace(workspace.id)}
                    type="button"
                  >
                    {builderState.deleting === workspace.id ? "Deleting..." : "Delete"}
                  </button>
                </div>
              </article>
            );
          })
        ) : (
          <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft xl:col-span-2">
            <h2 className="font-headline text-xl font-bold text-on-surface">No workspaces yet</h2>
            <p className="mt-2 max-w-2xl text-sm leading-7 text-on-surface-variant">
              Start by creating a workspace from scratch. You choose the job sources, the screening and generation modules, and the search settings that define that job-seeker workflow.
            </p>
            <button
              className="mt-5 rounded bg-gradient-to-br from-primary to-primary-container px-5 py-3 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90"
              onClick={openBuilder}
              type="button"
            >
              Create Your First Workspace
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
