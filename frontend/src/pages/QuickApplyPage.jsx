import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { WorkspaceCvBindingSection, buildNextSectionDecisions } from "../components/workspaces/WorkspaceCvBindingSection";
import { WorkspaceDocumentPreviewSection } from "../components/workspaces/WorkspaceDocumentPreviewSection";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { useWorkspaceCvAssets } from "../hooks/useWorkspaceCvAssets";
import { getApiErrorDetails, getApiErrorMessage } from "../lib/api";

const DEFAULT_FLOW_ID = "tailored_documents";
const DEFAULT_CV_GENERATION_MODE = "aggressive_customization";
const CV_GENERATION_MODE_OPTIONS = [
  { value: "standard_cv", label: "Standard CV" },
  { value: "light_customization", label: "Light Customization" },
  { value: "aggressive_customization", label: "Aggressive Customization" },
];
const QUICK_APPLY_FIELD_IDS = [
  "workspace_cv_asset_id",
  "cv_generation_mode",
  "personalization_scope",
  "cv_template",
  "cv_color_scheme",
  "cv_font",
  "include_photo",
];
const DOCUMENT_FIELD_IDS = [
  "personalization_scope",
  "cv_template",
  "cv_color_scheme",
  "cv_font",
  "include_photo",
];
const BASELINE_CV_FIELD_IDS = ["workspace_cv_asset_id"];

function parseDelimitedList(value) {
  const rawValues = Array.isArray(value) ? value : [value];
  const tokens = [];
  const seen = new Set();
  for (const rawValue of rawValues) {
    for (const item of String(rawValue || "").split(/[\r\n,]+/)) {
      const normalized = item.trim();
      if (!normalized) continue;
      const dedupeKey = normalized.toLowerCase();
      if (seen.has(dedupeKey)) continue;
      tokens.push(normalized);
      seen.add(dedupeKey);
      if (tokens.length >= 50) {
        return tokens;
      }
    }
  }
  return tokens;
}

function workspaceAutomationFlow(workspace) {
  return String(
    workspace?.automation_flow ||
      workspace?.metadata?.automation_flow ||
      workspace?.settings?.automation_flow ||
      "",
  ).trim();
}

function workspaceSupportsQuickApply(workspace) {
  if (workspaceAutomationFlow(workspace) === "tailored_documents") {
    return true;
  }
  if (workspace?.feature_flags?.enable_manual_urls) {
    return true;
  }
  return (workspace?.sources || []).some((source) => {
    const connectorId = String(source?.connector_id || source?.connectorId || "").trim();
    return connectorId === "manual_url" || connectorId === "curated_job_urls";
  });
}

function formatInvalidEntry(entry) {
  const url = String(entry?.url || "").trim();
  const lineNumber = Number(entry?.line_number || 0);
  const reason = String(entry?.error || entry?.stage || "invalid_entry")
    .replace(/_/g, " ")
    .trim();
  const prefix = lineNumber > 0 ? `Line ${lineNumber}` : "Entry";
  return [prefix, url, reason].filter(Boolean).join(" | ");
}

function settingDisplayValue(field, value) {
  if (field.type === "asset_select") {
    return value === undefined || value === null ? "" : String(value);
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

function fieldById(catalog, fieldId) {
  return (catalog?.configuration_fields || []).find((field) => field.id === fieldId) || null;
}

function fieldsByIds(catalog, fieldIds) {
  return fieldIds.map((fieldId) => fieldById(catalog, fieldId)).filter(Boolean);
}

function fieldDefault(catalog, fieldId, fallback = "") {
  const field = fieldById(catalog, fieldId);
  return Object.prototype.hasOwnProperty.call(field || {}, "default") ? field.default : fallback;
}

function firstAvailableCvAssetId(workspaceCvAssets) {
  return String(workspaceCvAssets?.[0]?.value || "").trim();
}

function buildInitialQuickApplySettings({
  builderCatalog,
  selectedWorkspace,
  settingsPayload,
  workspaceCvAssets,
}) {
  const documents = settingsPayload?.documents || {};
  const assetIds = new Set(workspaceCvAssets.map((asset) => String(asset.value || "").trim()));
  const workspaceAssetId = String(selectedWorkspace?.settings?.workspace_cv_asset_id || "").trim();
  const selectedAssetId = assetIds.has(workspaceAssetId)
    ? workspaceAssetId
    : firstAvailableCvAssetId(workspaceCvAssets);

  return {
    workspace_cv_asset_id: selectedAssetId,
    cv_generation_mode: fieldDefault(
      builderCatalog,
      "cv_generation_mode",
      DEFAULT_CV_GENERATION_MODE,
    ),
    personalization_scope: fieldDefault(
      builderCatalog,
      "personalization_scope",
      "baseline_cv_only",
    ),
    cv_template: String(documents.cv_template || "classic"),
    cv_color_scheme: String(documents.cv_color_scheme || "classic_navy"),
    cv_font: String(documents.cv_font || "Calibri"),
    include_photo: documents.include_photo ?? fieldDefault(builderCatalog, "include_photo", true),
  };
}

function buildQuickApplyRunSettings(settings) {
  return Object.fromEntries(
    QUICK_APPLY_FIELD_IDS
      .map((fieldId) => [fieldId, settings[fieldId]])
      .filter(([, value]) => value !== undefined && value !== null && value !== ""),
  );
}

function TokenListInput({ value, onChange, placeholder }) {
  const tokens = useMemo(() => parseDelimitedList(value), [value]);
  const [draft, setDraft] = useState("");

  function commit(rawValue) {
    onChange(parseDelimitedList([tokens, rawValue]));
    setDraft("");
  }

  return (
    <div className="space-y-2">
      <div className="rounded-xl border border-outline-variant/20 bg-surface px-3 py-3">
        <div className="flex flex-wrap gap-2">
          {tokens.map((token) => (
            <span
              className="inline-flex items-center gap-2 rounded-full bg-surface-container-low px-3 py-1.5 text-sm text-on-surface"
              key={token}
            >
              <span>{token}</span>
              <button
                aria-label={`Remove ${token}`}
                className="text-on-surface-variant transition-colors hover:text-error"
                onClick={() => onChange(tokens.filter((item) => item !== token))}
                type="button"
              >
                x
              </button>
            </span>
          ))}
          {tokens.length < 50 ? (
            <input
              className="min-w-[18rem] flex-1 bg-transparent py-1 text-sm text-on-surface outline-none placeholder:text-on-surface-variant"
              onBlur={() => {
                if (draft.trim()) {
                  commit(draft);
                }
              }}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === ",") {
                  event.preventDefault();
                  if (draft.trim()) {
                    commit(draft);
                  }
                }
              }}
              onPaste={(event) => {
                const pastedText = event.clipboardData.getData("text");
                if (/[\r\n,]/.test(pastedText)) {
                  event.preventDefault();
                  commit(pastedText);
                }
              }}
              placeholder={placeholder}
              value={draft}
            />
          ) : null}
        </div>
      </div>
      <div className="flex items-center justify-between gap-3 text-xs text-on-surface-variant">
        <span>Separate each exact job URL with Enter or a comma.</span>
        <span>{tokens.length}/50</span>
      </div>
    </div>
  );
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

function InfoHint({ content }) {
  return (
    <span
      className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-outline-variant/30 text-[11px] font-bold text-on-surface-variant"
      title={content}
    >
      i
    </span>
  );
}

function QuickApplyFieldRenderer({ field, value, onChange, dynamicOptions = {} }) {
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

  if (field.type === "boolean") {
    return (
      <select
        className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
        onChange={(event) => {
          const nextValue = event.target.value;
          onChange(nextValue ? nextValue === "true" : undefined);
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
      value={settingDisplayValue(field, value)}
    />
  );
}

function CvGenerationModeSection({ field, settings, updateSetting }) {
  const options = field?.options?.length ? field.options : CV_GENERATION_MODE_OPTIONS;
  const selectedMode = String(
    settings.cv_generation_mode || field?.default || DEFAULT_CV_GENERATION_MODE,
  );
  return (
    <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
      <div className="flex items-center gap-2">
        <h2 className="font-headline text-xl font-bold text-on-surface">CV Generation Mode</h2>
        <InfoHint content="Standard: use the selected CV. Light: tailor summary and skills. Aggressive: also tailor experience and project bullets." />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {options.map((option) => (
          <TogglePill
            checked={selectedMode === String(option.value)}
            key={String(option.value)}
            label={option.label}
            onClick={() => updateSetting("cv_generation_mode", String(option.value))}
          />
        ))}
      </div>
    </section>
  );
}

export default function QuickApplyPage() {
  const [searchParams] = useSearchParams();
  const { request, resolvePath } = useSession();
  const initializedSettingsRef = useRef(false);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [quickApplySettings, setQuickApplySettings] = useState({});
  const [manualUrls, setManualUrls] = useState([]);
  const [cvUploadState, setCvUploadState] = useState({
    uploading: false,
    message: "",
    error: "",
  });
  const [sectionDecisionState, setSectionDecisionState] = useState({
    savingKey: "",
    message: "",
    error: "",
  });
  const [submitState, setSubmitState] = useState({
    submitting: false,
    message: "",
    error: "",
    details: [],
    invalidEntries: [],
    acceptedUrlCount: 0,
    runId: "",
  });

  const {
    data: workspacesPayload,
    loading,
    error,
  } = useApiResource(() => request("/workspaces?limit=100"), [request]);
  const {
    data: builderCatalog,
    loading: builderLoading,
    error: builderError,
  } = useApiResource(() => request("/workspace-builder/catalog"), [request]);
  const {
    data: settingsPayload,
    loading: settingsLoading,
    error: settingsError,
  } = useApiResource(() => request("/settings"), [request]);
  const {
    data: cvAssetsPayload,
    loading: cvAssetsLoading,
    error: cvAssetsError,
    refresh: refreshCvAssets,
  } = useApiResource(() => request("/documents?asset_kind=workspace_cv&limit=100"), [request]);

  const eligibleWorkspaces = useMemo(
    () => (workspacesPayload?.workspaces || []).filter((workspace) => workspaceSupportsQuickApply(workspace)),
    [workspacesPayload?.workspaces],
  );
  const selectedWorkspace = useMemo(
    () => eligibleWorkspaces.find((workspace) => workspace.id === selectedWorkspaceId) || null,
    [eligibleWorkspaces, selectedWorkspaceId],
  );
  const quickApplyForm = useMemo(
    () => ({
      flowId: DEFAULT_FLOW_ID,
      settings: quickApplySettings,
    }),
    [quickApplySettings],
  );
  const {
    effectiveBrowserPreviewHtml,
    effectiveDocumentPreviewDocuments,
    mergedPreviewProfile,
    selectedCvCustomSections,
    selectedWorkspaceCvAsset,
    selectedWorkspaceCvMissing,
    workspaceCvAssets,
  } = useWorkspaceCvAssets({
    cvAssetsPayload,
    formSettings: quickApplySettings,
    settingsPayload,
  });
  const dynamicFieldOptions = useMemo(
    () => ({
      workspace_cv_assets: workspaceCvAssets,
    }),
    [workspaceCvAssets],
  );
  const cvGenerationModeField = fieldById(builderCatalog, "cv_generation_mode");
  const documentFields = useMemo(
    () => fieldsByIds(builderCatalog, DOCUMENT_FIELD_IDS),
    [builderCatalog],
  );
  const baselineCvFields = useMemo(
    () => fieldsByIds(builderCatalog, BASELINE_CV_FIELD_IDS),
    [builderCatalog],
  );
  const loadingOptions =
    loading ||
    builderLoading ||
    settingsLoading ||
    cvAssetsLoading ||
    (eligibleWorkspaces.length > 0 && !initializedSettingsRef.current);
  const resourceError = error || builderError || settingsError || cvAssetsError;
  const submitBlockedReason = useMemo(() => {
    if (!selectedWorkspaceId) {
      return "Quick Apply is still loading.";
    }
    if (!quickApplySettings.workspace_cv_asset_id) {
      return "Choose a baseline CV.";
    }
    if (selectedWorkspaceCvMissing) {
      return "The selected baseline CV is no longer available. Upload or choose another one.";
    }
    if (!manualUrls.length) {
      return "Add at least one exact job URL.";
    }
    return "";
  }, [
    manualUrls.length,
    quickApplySettings.workspace_cv_asset_id,
    selectedWorkspaceCvMissing,
    selectedWorkspaceId,
  ]);

  useEffect(() => {
    if (selectedWorkspaceId || !eligibleWorkspaces.length || !settingsPayload) {
      return;
    }
    const requestedWorkspaceId = searchParams.get("workspace_id") || "";
    const defaultWorkspaceId = settingsPayload?.defaults?.default_workspace_id || "";
    const preferredWorkspaceId = [requestedWorkspaceId, defaultWorkspaceId].find((workspaceId) =>
      eligibleWorkspaces.some((workspace) => workspace.id === workspaceId),
    );
    setSelectedWorkspaceId(preferredWorkspaceId || eligibleWorkspaces[0].id);
  }, [eligibleWorkspaces, searchParams, selectedWorkspaceId, settingsPayload?.defaults?.default_workspace_id]);

  useEffect(() => {
    if (
      initializedSettingsRef.current ||
      !builderCatalog ||
      !selectedWorkspaceId ||
      !settingsPayload ||
      !cvAssetsPayload
    ) {
      return;
    }
    setQuickApplySettings(
      buildInitialQuickApplySettings({
        builderCatalog,
        selectedWorkspace,
        settingsPayload,
        workspaceCvAssets,
      }),
    );
    initializedSettingsRef.current = true;
  }, [
    builderCatalog,
    cvAssetsPayload,
    selectedWorkspace,
    selectedWorkspaceId,
    settingsPayload,
    workspaceCvAssets,
  ]);

  function resetSubmitFeedback() {
    setSubmitState((current) => {
      if (
        !current.message &&
        !current.error &&
        !current.details.length &&
        !current.invalidEntries.length &&
        !current.runId
      ) {
        return current;
      }
      return {
        ...current,
        message: "",
        error: "",
        details: [],
        invalidEntries: [],
        acceptedUrlCount: 0,
        runId: "",
      };
    });
  }

  function updateSetting(fieldId, value) {
    resetSubmitFeedback();
    setQuickApplySettings((current) => ({
      ...current,
      [fieldId]: value,
    }));
  }

  async function uploadWorkspaceCv(file) {
    if (!file) return;
    resetSubmitFeedback();
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
        message: uploadedAssetId ? `Uploaded ${file.name} and selected it.` : `Uploaded ${file.name}.`,
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

  async function updateCvSectionDecision(section, value) {
    const assetId = String(selectedWorkspaceCvAsset?.assetId || selectedWorkspaceCvAsset?.value || "").trim();
    if (!assetId) {
      return;
    }
    const sectionId = String(section.section_id || section.id || section.heading || "").trim();
    const sectionDecisions = buildNextSectionDecisions(selectedCvCustomSections, section, value);
    setSectionDecisionState({ savingKey: sectionId, message: "", error: "" });
    try {
      await request(`/documents/assets/${encodeURIComponent(assetId)}/sections`, {
        method: "PUT",
        body: { section_decisions: sectionDecisions },
      });
      await refreshCvAssets().catch(() => undefined);
      setSectionDecisionState({
        savingKey: "",
        message: "Section mapping saved.",
        error: "",
      });
    } catch (updateError) {
      setSectionDecisionState({
        savingKey: "",
        message: "",
        error: updateError.message || "Unable to save section mapping.",
      });
    }
  }

  async function submitQuickApply() {
    if (submitBlockedReason) {
      return;
    }
    setSubmitState({
      submitting: true,
      message: "",
      error: "",
      details: [],
      invalidEntries: [],
      acceptedUrlCount: 0,
      runId: "",
    });
    try {
      const payload = await request("/quick-apply/runs", {
        method: "POST",
        body: {
          workspace_id: selectedWorkspaceId,
          execution_mode: "queued",
          manual_urls: manualUrls,
          settings: buildQuickApplyRunSettings(quickApplySettings),
        },
      });
      const run = payload.run || {};
      const invalidEntries = payload.invalid_entries || [];
      const acceptedUrlCount = Number(payload.accepted_url_count || run.metadata?.accepted_url_count || 0);
      setSubmitState({
        submitting: false,
        message: `Quick application ${run.id} added to the queue. Accepted ${acceptedUrlCount} exact job URL${acceptedUrlCount === 1 ? "" : "s"}.`,
        error: "",
        details: [],
        invalidEntries,
        acceptedUrlCount,
        runId: run.id || "",
      });
    } catch (submitError) {
      setSubmitState({
        submitting: false,
        message: "",
        error: getApiErrorMessage(submitError, "Unable to start the quick application."),
        details: getApiErrorDetails(submitError),
        invalidEntries: [],
        acceptedUrlCount: 0,
        runId: "",
      });
    }
  }

  if (loadingOptions) {
    return (
      <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 text-on-surface-variant shadow-soft">
        Loading quick-apply options...
      </div>
    );
  }

  if (resourceError) {
    return (
      <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        <p className="text-error">{resourceError}</p>
      </div>
    );
  }

  if (!eligibleWorkspaces.length) {
    return (
      <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
        <h1 className="font-headline text-2xl font-bold text-on-surface">Quick Apply</h1>
        <p className="mt-3 max-w-2xl text-sm leading-7 text-on-surface-variant">
          Quick Apply needs one tailored-documents workspace first so the app can queue document generation runs.
        </p>
        <Link
          className="mt-5 inline-flex rounded bg-gradient-to-br from-primary to-primary-container px-5 py-3 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90"
          to="/workspaces"
        >
          Create a Workspace
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
          Quick Apply
        </h1>
        <p className="max-w-3xl text-sm leading-7 text-on-surface-variant">
          Already have a job posting link? Paste the URL, choose how the CV should be generated, and review the export preview.
        </p>
        <p className="text-xs uppercase tracking-wider text-on-surface-variant/80">
          Exact job links only. No company-site crawling or motivation letters.
        </p>
      </header>

      <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        <label className="space-y-2">
          <span className="block text-sm font-semibold text-on-surface">Exact Job URLs</span>
          <TokenListInput
            onChange={(nextManualUrls) => {
              resetSubmitFeedback();
              setManualUrls(nextManualUrls);
            }}
            placeholder="https://company.example/jobs/123"
            value={manualUrls}
          />
          <span className="block text-xs leading-6 text-on-surface-variant">
            Paste one or more exact job posting links. Up to 50 URLs.
          </span>
        </label>
      </section>

      <CvGenerationModeSection
        field={cvGenerationModeField}
        settings={quickApplySettings}
        updateSetting={updateSetting}
      />

      <section className="space-y-4 rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        <div>
          <h2 className="font-headline text-xl font-bold text-on-surface">Baseline CV</h2>
          <p className="mt-1 text-sm leading-6 text-on-surface-variant">
            Choose the CV Quick Apply should use as its baseline before any job-specific tailoring happens.
          </p>
        </div>
        <WorkspaceCvBindingSection
          FieldRenderer={QuickApplyFieldRenderer}
          cvUploadState={cvUploadState}
          dynamicOptions={dynamicFieldOptions}
          fields={baselineCvFields}
          form={quickApplyForm}
          resolvePath={resolvePath}
          sectionDecisionState={sectionDecisionState}
          selectedCvCustomSections={selectedCvCustomSections}
          selectedWorkspaceCvAsset={selectedWorkspaceCvAsset}
          showSectionMapping={false}
          showSelectedDetails={false}
          updateCvSectionDecision={updateCvSectionDecision}
          updateSetting={updateSetting}
          uploadWorkspaceCv={uploadWorkspaceCv}
        />
      </section>

      <section className="space-y-4 rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        <div>
          <h2 className="font-headline text-xl font-bold text-on-surface">Personalization & Style</h2>
          <p className="mt-1 text-sm leading-6 text-on-surface-variant">
            Choose how much candidate knowledge Quick Apply may use, then set CV styling defaults for this run.
          </p>
        </div>
        <WorkspaceDocumentPreviewSection
          FieldRenderer={QuickApplyFieldRenderer}
          dynamicOptions={dynamicFieldOptions}
          effectiveBrowserPreviewHtml={effectiveBrowserPreviewHtml}
          effectiveDocumentPreviewDocuments={effectiveDocumentPreviewDocuments}
          fields={documentFields}
          form={quickApplyForm}
          mergedPreviewProfile={mergedPreviewProfile}
          selectedWorkspaceCvAsset={selectedWorkspaceCvAsset}
          selectedWorkspaceCvMissing={selectedWorkspaceCvMissing}
          updateSetting={updateSetting}
        />
      </section>

      <section className="space-y-4 rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        {submitState.error ? (
          <div className="rounded-lg bg-error-container px-4 py-3 text-sm text-on-error-container">
            <div>{submitState.error}</div>
            {submitState.details.length ? (
              <div className="mt-2 space-y-1 text-xs leading-6">
                {submitState.details.map((detail) => (
                  <div key={detail}>{detail}</div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        {submitState.message ? (
          <div className="rounded-lg bg-surface-container-low px-4 py-3 text-sm text-on-surface">
            <div>{submitState.message}</div>
            {submitState.runId ? (
              <Link
                className="mt-3 inline-flex rounded bg-surface px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                to={`/runs/${submitState.runId}`}
              >
                Open Run
              </Link>
            ) : null}
          </div>
        ) : null}
        {submitState.invalidEntries.length ? (
          <div className="rounded-lg border border-error/20 bg-error/5 px-4 py-3 text-sm text-on-surface">
            <div className="font-semibold text-on-surface">
              Ignored {submitState.invalidEntries.length} invalid URL entr{submitState.invalidEntries.length === 1 ? "y" : "ies"}
            </div>
            <div className="mt-2 space-y-1 text-xs leading-6 text-on-surface-variant">
              {submitState.invalidEntries.map((entry, index) => (
                <div key={`${formatInvalidEntry(entry)}-${index}`}>{formatInvalidEntry(entry)}</div>
              ))}
            </div>
          </div>
        ) : null}
        {submitBlockedReason && (quickApplySettings.workspace_cv_asset_id || manualUrls.length) ? (
          <div className="rounded-lg border border-outline-variant/10 bg-surface px-4 py-3 text-sm text-on-surface-variant">
            {submitBlockedReason}
          </div>
        ) : null}

        <div className="flex flex-wrap gap-3">
          <button
            className="rounded bg-gradient-to-br from-primary to-primary-container px-5 py-3 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={submitState.submitting || Boolean(submitBlockedReason)}
            onClick={submitQuickApply}
            type="button"
          >
            {submitState.submitting ? "Starting..." : "Run Quick Application"}
          </button>
          <Link
            className="rounded bg-surface-container-low px-5 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            to="/workspaces"
          >
            Back to Workspaces
          </Link>
        </div>
      </section>
    </div>
  );
}
