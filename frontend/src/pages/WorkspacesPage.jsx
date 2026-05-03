import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
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

function parseLineList(text) {
  return String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function formatCompanySiteEntries(entries) {
  if (!Array.isArray(entries)) return "Not set";
  const lines = entries
    .map((entry) => {
      if (!entry || typeof entry !== "object") {
        return String(entry || "").trim();
      }
      const companyName = String(entry.company_name || entry.company || "").trim();
      const url = String(entry.url || "").trim();
      if (companyName && url) return `${companyName} | ${url}`;
      return url || companyName;
    })
    .filter(Boolean);
  return lines.length ? lines.join("\n") : "Not set";
}

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

function BuilderSection({ id, title, description, children, emphasized = false }) {
  return (
    <section
      className={[
        "space-y-3 rounded-xl bg-surface-container-lowest p-6 transition-all",
        emphasized
          ? "border border-primary/30 ring-2 ring-primary/10"
          : "border border-outline-variant/20",
      ].join(" ")}
      id={id}
    >
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h3 className="font-headline text-lg font-bold text-on-surface">{title}</h3>
          {emphasized ? (
            <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
              Review Focus
            </span>
          ) : null}
        </div>
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
  if (Array.isArray(value) && value.some((item) => item && typeof item === "object")) {
    return formatCompanySiteEntries(value);
  }
  if (Array.isArray(value)) {
    const separator = value.some((item) => String(item || "").includes("http")) ? "\n" : ", ";
    return value.length ? value.join(separator) : "Not set";
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
  if (field.type === "asset_select") {
    return value === undefined || value === null ? "" : String(value);
  }
  if (field.type === "tag_list") {
    return Array.isArray(value) ? value.join(", ") : "";
  }
  if (field.type === "url_list") {
    return Array.isArray(value) ? value.join("\n") : "";
  }
  if (field.type === "company_site_list") {
    return formatCompanySiteEntries(value === undefined ? [] : value);
  }
  if (field.type === "multi_select") {
    return Array.isArray(value) ? value : [];
  }
  if (field.type === "boolean") {
    if (value === undefined || value === null || value === "") {
      return "";
    }
    return value ? "true" : "false";
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
    internal: SYSTEM_SETTING_KEYS.has(key) || fieldMap.get(key)?.user_facing === false,
  }));
}

function workspaceHasConnector(workspace, connectorId) {
  return (workspace.sources || []).some((source) => source.connector_id === connectorId);
}

function compactListLabel(items, fallback = "N/A") {
  const labels = (items || []).filter(Boolean);
  if (!labels.length) {
    return fallback;
  }
  if (labels.length <= 2) {
    return labels.join(", ");
  }
  return `${labels.slice(0, 2).join(", ")} +${labels.length - 2}`;
}

function FieldRenderer({ field, value, onChange, dynamicOptions = {} }) {
  if (field.type === "asset_select") {
    const options = dynamicOptions[field.dynamic_source] || [];
    return (
      <select
        className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
        onChange={(event) => onChange(event.target.value)}
        value={settingDisplayValue(field, value)}
      >
        <option value="">{options.length ? "Select a CV" : "Upload a CV first"}</option>
        {options.map((option) => (
          <option key={`${field.id}-${option.value}`} value={String(option.value)}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }

  if (field.type === "multi_select") {
    const selectedValues = Array.isArray(value) ? value : [];
    return (
      <div className="space-y-2">
        <div className="flex flex-wrap gap-3">
          {(field.options || []).map((option) => {
            const checked = selectedValues.some((item) => String(item) === String(option.value));
            const selectionLimitReached =
              field.id === "target_roles" && !checked && selectedValues.length >= 3;
            return (
              <TogglePill
                checked={checked}
                key={`${field.id}-${option.value}`}
                label={option.label}
                onClick={() => {
                  if (selectionLimitReached) {
                    return;
                  }
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

  if (field.type === "boolean") {
    return (
      <select
        className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
        onChange={(event) => {
          const nextValue = event.target.value;
          if (!nextValue) {
            onChange(undefined);
            return;
          }
          onChange(nextValue === "true");
        }}
        value={settingDisplayValue(field, value)}
      >
        <option value="">Use workspace default</option>
        {(field.options || []).map((option) => (
          <option key={`${field.id}-${String(option.value)}`} value={String(option.value)}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }

  if (
    field.type === "url_list" ||
    field.type === "company_site_list" ||
    field.type === "textarea"
  ) {
    return (
      <textarea
        className="min-h-32 w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
        onChange={(event) => onChange(event.target.value)}
        placeholder={field.placeholder || ""}
        rows={field.type === "company_site_list" ? 5 : field.rows || 4}
        value={settingDisplayValue(field, value)}
      />
    );
  }

  return (
    <input
      className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
      onChange={(event) => onChange(event.target.value)}
      placeholder={field.placeholder || ""}
      step={field.type === "float" ? "0.1" : undefined}
      type={field.type === "number" || field.type === "float" ? "number" : "text"}
      value={settingDisplayValue(field, value)}
    />
  );
}

export default function WorkspacesPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const focusedSectionId = searchParams.get("focus") || "";
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
  const [quickManualUrls, setQuickManualUrls] = useState({});
  const [sourceValidation, setSourceValidation] = useState({
    loading: false,
    valid: true,
    sourceResults: [],
    error: "",
  });
  const [cvUploadState, setCvUploadState] = useState({
    uploading: false,
    message: "",
    error: "",
  });

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
  const {
    data: cvAssetsPayload,
    refresh: refreshCvAssets,
  } = useApiResource(() => request("/documents?asset_kind=workspace_cv&limit=100"), [request]);

  const workspaces = workspacesData?.workspaces || [];
  const focusedWorkspaceId = searchParams.get("workspace_id") || "";
  const focusedWorkspace = useMemo(
    () => workspaces.find((workspace) => workspace.id === focusedWorkspaceId) || null,
    [focusedWorkspaceId, workspaces],
  );
  const flows = useMemo(
    () => (builderCatalog?.flows || []).filter((flow) => flow.frontend_visible !== false),
    [builderCatalog?.flows],
  );
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
        field.user_facing !== false && fieldMatchesSelection(field, form, availableSources),
      ),
    [builderCatalog, form, availableSources],
  );
  const builderSections = useMemo(
    () =>
      (builderCatalog?.builder_sections || []).filter((section) =>
        availableConfigurationFields.some((field) => field.section === section.id),
      ),
    [availableConfigurationFields, builderCatalog?.builder_sections],
  );
  const focusedSection = useMemo(
    () => builderSections.find((section) => section.id === focusedSectionId) || null,
    [builderSections, focusedSectionId],
  );
  const sectionFields = useMemo(
    () =>
      availableConfigurationFields.reduce((accumulator, field) => {
        const sectionId = field.section || "advanced";
        if (!accumulator[sectionId]) {
          accumulator[sectionId] = [];
        }
        accumulator[sectionId].push(field);
        return accumulator;
      }, {}),
    [availableConfigurationFields],
  );
  const dynamicFieldOptions = useMemo(
    () => ({
      workspace_cv_assets: (cvAssetsPayload?.documents || [])
        .filter((item) => item.asset_kind === "workspace_cv")
        .map((item) => ({
          value: item.asset_id,
          label: item.display_name,
        })),
    }),
    [cvAssetsPayload?.documents],
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

  function focusWorkspace(workspaceId) {
    const next = new URLSearchParams(searchParams);
    next.set("workspace_id", workspaceId);
    setSearchParams(next);
  }

  function showAllWorkspaces() {
    const next = new URLSearchParams(searchParams);
    next.delete("workspace_id");
    setSearchParams(next);
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
    setSourceValidation({ loading: false, valid: true, sourceResults: [], error: "" });
    setCvUploadState({ uploading: false, message: "", error: "" });
    resetBuilderState({ open: true });
  }

  function openEditor(workspace) {
    setForm(hydrateFormFromWorkspace(workspace, builderCatalog));
    setSourceValidation({ loading: false, valid: true, sourceResults: [], error: "" });
    setCvUploadState({ uploading: false, message: "", error: "" });
    resetBuilderState({
      open: true,
      mode: "edit",
      editingWorkspaceId: workspace.id,
    });
  }

  function closeBuilder() {
    resetBuilderState();
    setForm(EMPTY_BUILDER_FORM);
    setSourceValidation({ loading: false, valid: true, sourceResults: [], error: "" });
    setCvUploadState({ uploading: false, message: "", error: "" });
    if (searchParams.get("edit")) {
      const next = new URLSearchParams(searchParams);
      next.delete("edit");
      next.delete("focus");
      setSearchParams(next);
    }
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
    setSourceValidation({ loading: false, valid: true, sourceResults: [], error: "" });
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

  async function validateSources() {
    setSourceValidation({ loading: true, valid: true, sourceResults: [], error: "" });
    try {
      const payload = await request("/workspace-builder/source-validation", {
        method: "POST",
        body: {
          flow_id: form.flowId,
          source_ids: form.sourceIds,
          settings: form.settings,
        },
      });
      setSourceValidation({
        loading: false,
        valid: Boolean(payload.valid),
        sourceResults: payload.source_results || [],
        error: "",
      });
    } catch (validationError) {
      setSourceValidation({
        loading: false,
        valid: false,
        sourceResults: [],
        error: validationError.message || "Unable to validate sources.",
      });
    }
  }

  async function uploadWorkspaceCv(file) {
    if (!file) return;
    setCvUploadState({ uploading: true, message: "", error: "" });
    try {
      const formData = new FormData();
      formData.append("cv_file", file, file.name);
      const response = await request("/cv-upload", {
        method: "POST",
        body: formData,
      });
      const uploadedAssetId = response?.asset?.asset_id || "";
      if (uploadedAssetId) {
        updateSetting("workspace_cv_asset_id", uploadedAssetId);
      }
      await refreshCvAssets().catch(() => undefined);
      setCvUploadState({
        uploading: false,
        message: uploadedAssetId
          ? `Uploaded ${file.name} and selected it for this workspace.`
          : `Uploaded ${file.name}.`,
        error: "",
      });
    } catch (uploadError) {
      setCvUploadState({
        uploading: false,
        message: "",
        error: uploadError.message || "Unable to upload CV.",
      });
    }
  }

  useEffect(() => {
    if (!builderCatalog || builderState.open) {
      return;
    }
    const editWorkspaceId = searchParams.get("edit");
    if (!editWorkspaceId) {
      return;
    }
    const workspace = workspaces.find((item) => item.id === editWorkspaceId);
    if (workspace) {
      openEditor(workspace);
    }
  }, [builderCatalog, builderState.open, searchParams, workspaces]);

  useEffect(() => {
    if (!builderState.open || !focusedSectionId) {
      return;
    }
    const targetId = `workspace-builder-${focusedSectionId}`;
    const timer = window.setTimeout(() => {
      document.getElementById(targetId)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 80);
    return () => window.clearTimeout(timer);
  }, [builderState.open, focusedSectionId]);

  async function triggerRun(workspaceId, executionMode, runInputOverrides = {}) {
    setActionState({ workspaceId, message: "", error: "" });
    try {
      const run = await request("/runs", {
        method: "POST",
        body: {
          workspace_id: workspaceId,
          execution_mode: executionMode,
          max_attempts: 1,
          run_input_overrides: runInputOverrides,
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

  function quickManualValue(workspace) {
    if (Object.prototype.hasOwnProperty.call(quickManualUrls, workspace.id)) {
      return quickManualUrls[workspace.id];
    }
    const savedUrls = workspace.settings?.manual_url_seed_list;
    return Array.isArray(savedUrls) ? savedUrls.join("\n") : "";
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

  function workspacePresentation(workspace) {
    const moduleNames = (workspace.metadata?.modules || []).map((moduleId) => labelize(moduleId));
    const sourceNames = (workspace.sources || []).map((source) => labelize(source.connector_id));
    return {
      flowLabel: labelize(workspaceAutomationFlow(workspace)),
      moduleNames,
      sourceNames,
      modulesLabel: compactListLabel(moduleNames, "Default modules"),
      sourcesLabel: compactListLabel(sourceNames),
      profileLabel: workspace.profiles?.[0]?.label || "N/A",
      promptFamily: workspace.prompt_sets?.[0]?.family || "N/A",
    };
  }

  function renderActionFeedback(workspace) {
    if (actionState.workspaceId !== workspace.id || (!actionState.message && !actionState.error)) {
      return null;
    }
    return (
      <div
        className={[
          "rounded-lg px-4 py-3 text-sm",
          actionState.error
            ? "bg-error-container text-on-error-container"
            : "bg-surface-container-low text-on-surface",
        ].join(" ")}
      >
        {actionState.error || actionState.message}
      </div>
    );
  }

  function renderWorkspaceRows() {
    return (
      <div className="overflow-hidden rounded-xl border border-outline-variant/20 bg-surface-container-lowest shadow-soft">
        <div className="hidden border-b border-outline-variant/10 bg-surface-container-low px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant md:grid md:grid-cols-12 md:items-center">
          <div className="md:col-span-4">Workspace</div>
          <div className="md:col-span-2">Sources</div>
          <div className="md:col-span-2">Profile</div>
          <div className="text-right md:col-span-4">Actions</div>
        </div>

        <div className="divide-y divide-outline-variant/10">
          {workspaces.map((workspace) => {
            const summary = workspacePresentation(workspace);
            return (
              <article
                className="grid gap-4 px-4 py-4 transition-colors hover:bg-surface-container-low md:grid-cols-12 md:items-center"
                key={workspace.id}
              >
                <div className="min-w-0 md:col-span-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="truncate font-headline text-lg font-bold text-on-surface">
                      {workspace.name}
                    </h2>
                    <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
                      {summary.flowLabel}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-sm text-on-surface-variant">
                    {workspace.description || "No description provided."}
                  </p>
                  <p className="mt-1 text-xs text-on-surface-variant">
                    {summary.modulesLabel}
                  </p>
                </div>

                <div className="text-sm text-on-surface-variant md:col-span-2">
                  <span className="font-semibold text-on-surface md:hidden">Sources: </span>
                  {summary.sourcesLabel}
                </div>

                <div className="text-sm text-on-surface-variant md:col-span-2">
                  <span className="font-semibold text-on-surface md:hidden">Profile: </span>
                  {summary.profileLabel}
                </div>

                <div className="flex flex-wrap gap-2 md:col-span-4 md:justify-end">
                  <button
                    className="rounded bg-gradient-to-br from-primary to-primary-container px-3 py-2 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90"
                    onClick={() => focusWorkspace(workspace.id)}
                    type="button"
                  >
                    Open
                  </button>
                  <button
                    className="rounded bg-surface-container-low px-3 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                    onClick={() => triggerRun(workspace.id, "sync")}
                    type="button"
                  >
                    Run
                  </button>
                  <button
                    className="rounded bg-surface-container-low px-3 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                    onClick={() => triggerRun(workspace.id, "queued")}
                    type="button"
                  >
                    Queue
                  </button>
                  <button
                    className="rounded bg-surface-container-low px-3 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                    onClick={() => openEditor(workspace)}
                    type="button"
                  >
                    Edit
                  </button>
                </div>

                <div className="md:col-span-12">{renderActionFeedback(workspace)}</div>
              </article>
            );
          })}
        </div>
      </div>
    );
  }

  function renderFocusedWorkspace(workspace) {
    const summary = workspacePresentation(workspace);
    const settingEntries = workspaceSettingEntries(workspace, builderCatalog);
    const pastedUrlCount = parseLineList(quickManualValue(workspace)).length;

    return (
      <div className="space-y-5">
        <div className="rounded-xl border border-primary/20 bg-primary/5 px-4 py-3">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-sm font-semibold text-on-surface">
                Showing one workspace: {workspace.name}
              </div>
              <div className="text-xs text-on-surface-variant">
                Other workspaces are hidden until you go back.
              </div>
            </div>
            <button
              className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
              onClick={showAllWorkspaces}
              type="button"
            >
              Back to all workspaces
            </button>
          </div>
        </div>

        <article className="space-y-6 rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-headline text-2xl font-bold text-on-surface">
                  {workspace.name}
                </h2>
                <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
                  {summary.flowLabel}
                </span>
              </div>
              <p className="mt-2 max-w-3xl text-sm leading-7 text-on-surface-variant">
                {workspace.description || "No description provided."}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
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
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-4">
            {[
              ["Sources", summary.sourcesLabel],
              ["Modules", summary.modulesLabel],
              ["Profile", summary.profileLabel],
              ["Prompt Family", summary.promptFamily],
            ].map(([label, value]) => (
              <div className="rounded-lg border border-outline-variant/10 bg-surface p-4" key={label}>
                <div className="text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant">
                  {label}
                </div>
                <div className="mt-1 text-sm font-medium text-on-surface">{value}</div>
              </div>
            ))}
          </div>

          {workspaceHasConnector(workspace, "curated_job_urls") ? (
            <div className="space-y-3 rounded-xl border border-outline-variant/10 bg-surface p-4">
              <div>
                <h3 className="text-sm font-semibold text-on-surface">Quick Paste Job URLs</h3>
                <p className="mt-1 text-xs leading-6 text-on-surface-variant">
                  Paste one URL per line and run this workspace without editing any local files.
                </p>
              </div>
              <textarea
                className="min-h-28 w-full rounded-lg border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm text-on-surface"
                onChange={(event) =>
                  setQuickManualUrls((current) => ({
                    ...current,
                    [workspace.id]: event.target.value,
                  }))
                }
                placeholder="https://company.example/jobs/123"
                value={quickManualValue(workspace)}
              />
              <div className="flex flex-wrap gap-3">
                <button
                  className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={!pastedUrlCount}
                  onClick={() =>
                    triggerRun(workspace.id, "sync", {
                      manual_urls_inline: parseLineList(quickManualValue(workspace)),
                    })
                  }
                  type="button"
                >
                  Run Pasted URLs
                </button>
                <button
                  className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={!pastedUrlCount}
                  onClick={() =>
                    triggerRun(workspace.id, "queued", {
                      manual_urls_inline: parseLineList(quickManualValue(workspace)),
                    })
                  }
                  type="button"
                >
                  Queue Pasted URLs
                </button>
              </div>
            </div>
          ) : null}

          {renderActionFeedback(workspace)}

          {settingEntries.length ? (
            <details className="rounded-xl border border-outline-variant/10 bg-surface p-4">
              <summary className="cursor-pointer text-sm font-semibold text-on-surface">
                Saved configuration
              </summary>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                {settingEntries.map((entry) => (
                  <div
                    className="rounded-lg border border-outline-variant/10 bg-surface-container-lowest p-3"
                    key={`${workspace.id}-${entry.key}`}
                  >
                    <div className="text-[11px] uppercase tracking-wider text-on-surface-variant">
                      {entry.label}
                      {entry.internal ? " | Internal" : ""}
                    </div>
                    <div className="mt-1 whitespace-pre-wrap text-sm text-on-surface">
                      {entry.value}
                    </div>
                  </div>
                ))}
              </div>
            </details>
          ) : null}

          <div className="flex flex-wrap gap-3 border-t border-outline-variant/10 pt-5">
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
              {builderState.deleting === workspace.id ? "Deleting..." : "Delete Workspace"}
            </button>
          </div>
        </article>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="flex flex-col gap-2">
          <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
            Workspaces
          </h1>
          <p className="text-sm text-on-surface-variant">
            Browse workspaces as simple rows. Open one workspace to review its settings, edit it, or run it without other workspaces getting in the way.
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
            {focusedSectionId ? (
              <div className="rounded-xl border border-primary/20 bg-primary/5 px-4 py-3 text-sm text-on-surface">
                {focusedSection ? (
                  <>
                    Opened from rejected-job review. The workspace editor is focused on{" "}
                    <span className="font-semibold text-primary">{focusedSection.title}</span>.
                  </>
                ) : (
                  <>
                    Opened from rejected-job review. This rejection does not map to a specific
                    workspace section, so review the settings below and the review queue together.
                  </>
                )}
              </div>
            ) : null}

            <BuilderSection
              description="Give the workspace a clear name and describe what kind of search or application output it should handle."
              title="Workspace Identity"
            >
              <div className="grid gap-4">
                <input
                  className="rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
                  onChange={(event) => updateForm({ name: event.target.value })}
                  placeholder="Workspace name"
                  value={form.name}
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
              description="This remediation flow stays focused on sourcing jobs, screening them, and generating tailored application documents."
              title="Automation Flow"
            >
              {flows.length > 1 ? (
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
              ) : (
                <div className="rounded-lg border border-outline-variant/10 bg-surface p-4 text-sm text-on-surface">
                  {flows[0]?.name || "Tailored Application Documents"}
                </div>
              )}
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
              description="The core automation path is fixed for this remediation: source jobs, screen them, prioritize them, and generate documents."
              title="Automation Modules"
            >
              {availableModules.length ? (
                <div className="flex flex-wrap gap-3">
                  {availableModules
                    .filter((module) => form.moduleIds.includes(module.id))
                    .map((module) => (
                      <div
                        className="rounded-full border border-primary/20 bg-primary/10 px-3 py-2 text-sm font-medium text-primary"
                        key={module.id}
                      >
                        {module.name}
                      </div>
                    ))}
                </div>
              ) : (
                <p className="text-sm text-on-surface-variant">No modules are available for this flow.</p>
              )}
            </BuilderSection>

            {builderSections.map((section) => {
              const fields = sectionFields[section.id] || [];
              if (!fields.length) {
                return null;
              }
              return (
                <BuilderSection
                  description={section.description}
                  emphasized={section.id === focusedSectionId}
                  id={`workspace-builder-${section.id}`}
                  key={section.id}
                  title={section.title}
                >
                  {section.id === "cv_binding" ? (
                    <div className="space-y-4">
                      <div className="grid gap-4 md:grid-cols-2">
                        {fields.map((field) => (
                          <label className="space-y-2" key={field.id}>
                            <span className="block text-sm font-semibold text-on-surface">{field.label}</span>
                            <FieldRenderer
                              dynamicOptions={dynamicFieldOptions}
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
                      <div className="rounded-lg border border-dashed border-outline-variant/20 bg-surface p-4">
                        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                          <div>
                            <p className="text-sm font-semibold text-on-surface">Upload a new workspace CV</p>
                            <p className="text-xs leading-6 text-on-surface-variant">
                              Uploading here also adds the CV to the shared documents library.
                            </p>
                          </div>
                          <label className="inline-flex cursor-pointer items-center rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high">
                            <input
                              className="hidden"
                              onChange={(event) => {
                                const file = event.target.files?.[0];
                                if (file) {
                                  uploadWorkspaceCv(file);
                                  event.target.value = "";
                                }
                              }}
                              type="file"
                            />
                            {cvUploadState.uploading ? "Uploading..." : "Upload CV"}
                          </label>
                        </div>
                        {cvUploadState.message ? (
                          <p className="mt-3 text-sm text-primary">{cvUploadState.message}</p>
                        ) : null}
                        {cvUploadState.error ? (
                          <p className="mt-3 text-sm text-error">{cvUploadState.error}</p>
                        ) : null}
                      </div>
                    </div>
                  ) : (
                    <div className="grid gap-4 md:grid-cols-2">
                      {fields.map((field) => (
                        <label className="space-y-2" key={field.id}>
                          <span className="block text-sm font-semibold text-on-surface">{field.label}</span>
                          <FieldRenderer
                            dynamicOptions={dynamicFieldOptions}
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
                  )}
                </BuilderSection>
              );
            })}
          </div>

          <div className="space-y-6 xl:col-span-4">
            <BuilderSection
              description="Check the selected sources before you save or run so broken setup is visible early."
              title="Source Validation"
            >
              <button
                className="w-full rounded bg-surface-container-low px-4 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-60"
                disabled={sourceValidation.loading || !form.sourceIds.length}
                onClick={validateSources}
                type="button"
              >
                {sourceValidation.loading ? "Validating..." : "Validate Selected Sources"}
              </button>
              {sourceValidation.error ? (
                <p className="text-sm text-error">{sourceValidation.error}</p>
              ) : null}
              {sourceValidation.sourceResults.length ? (
                <div className="space-y-3">
                  {sourceValidation.sourceResults.map((result) => (
                    <div
                      className="rounded-lg border border-outline-variant/10 bg-surface p-4"
                      key={result.source_id}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm font-semibold text-on-surface">
                          {labelize(result.source_id)}
                        </span>
                        <span
                          className={[
                            "rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide",
                            result.status === "valid"
                              ? "bg-primary/10 text-primary"
                              : "bg-error/10 text-error",
                          ].join(" ")}
                        >
                          {result.status}
                        </span>
                      </div>
                      <p className="mt-2 text-sm text-on-surface-variant">{result.summary}</p>
                      {result.details?.length ? (
                        <div className="mt-2 space-y-1 text-xs leading-6 text-on-surface-variant">
                          {result.details.map((detail) => (
                            <div key={detail}>{detail}</div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-on-surface-variant">
                  Validation will summarize country-to-source defaults, pasted URL readiness, and job-board setup.
                </p>
              )}
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
                  {form.moduleIds.length ? form.moduleIds.map(labelize).join(", ") : "Default remediation path"}
                </div>
                <div>
                  <span className="font-semibold text-on-surface">Workspace CV:</span>{" "}
                  {dynamicFieldOptions.workspace_cv_assets.find(
                    (item) => item.value === form.settings.workspace_cv_asset_id,
                  )?.label || "Not selected"}
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
                    !form.moduleIds.length ||
                    !form.settings.workspace_cv_asset_id
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

      <section className="space-y-4">
        {loading ? (
          <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 text-on-surface-variant shadow-soft">
            Loading workspaces...
          </div>
        ) : error ? (
          <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
            <p className="text-error">{error}</p>
            <button
              className="mt-4 rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
              onClick={() => refresh().catch(() => undefined)}
              type="button"
            >
              Retry
            </button>
          </div>
        ) : focusedWorkspace ? (
          renderFocusedWorkspace(focusedWorkspace)
        ) : focusedWorkspaceId ? (
          <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
            <h2 className="font-headline text-xl font-bold text-on-surface">
              Workspace not found
            </h2>
            <p className="mt-2 text-sm text-on-surface-variant">
              The selected workspace is no longer available. Return to the workspace list.
            </p>
            <button
              className="mt-4 rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
              onClick={showAllWorkspaces}
              type="button"
            >
              Back to all workspaces
            </button>
          </div>
        ) : workspaces.length ? (
          renderWorkspaceRows()
        ) : (
          <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
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
