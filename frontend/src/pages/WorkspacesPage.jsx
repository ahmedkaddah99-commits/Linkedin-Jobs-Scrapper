import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { getApiErrorDetails, getApiErrorMessage } from "../lib/api";
import { labelize } from "../lib/formatters";

const DEFAULT_FLOW_ID = "tailored_documents";
const SYSTEM_SETTING_KEYS = new Set([
  "automation_flow",
  "config_loader",
  "manual_sources_are_preapproved",
]);
const FIXED_TAILORED_MODULE_IDS = ["screening_filter", "tailored_document_generation"];
const OPTIONAL_PRIORITY_MODULE_ID = "priority_ranking";
const QUICK_APPLY_ROUTE = "/quick-apply";
const SOURCE_VALIDATION_DEBOUNCE_MS = 350;
const EMPTY_ACTION_STATE = {
  workspaceId: "",
  loading: false,
  message: "",
  error: "",
  details: [],
};
const EMPTY_SOURCE_VALIDATION = {
  loading: false,
  valid: true,
  sourceResults: [],
  error: "",
  validationKey: "",
};

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

function defaultProfileLabelForFlow(flowId) {
  return flowId === "reusable_packages"
    ? "Operations Profile"
    : "Primary Job Seeker Profile";
}

function buildBuilderForm(catalog, flowId = DEFAULT_FLOW_ID) {
  return {
    ...EMPTY_BUILDER_FORM,
    flowId,
    moduleIds: defaultModuleIdsForFlow(catalog, flowId),
    promptFamily: flowId,
    profileLabel: defaultProfileLabelForFlow(flowId),
    settings: buildDefaultSettings(catalog, flowId),
  };
}

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
    }
  }
  return tokens;
}

function parseLineList(text) {
  return parseDelimitedList(text);
}

function stableSerialize(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableSerialize(item)).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableSerialize(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function buildSourceValidationPayload({ flowId, sourceIds, settings }) {
  return {
    flow_id: flowId,
    source_ids: [...(sourceIds || [])],
    settings: { ...(settings || {}) },
  };
}

function sourceValidationKey(payload) {
  return stableSerialize(payload);
}

function buildCountryOptions() {
  try {
    if (typeof Intl !== "undefined" && typeof Intl.DisplayNames === "function") {
      const supportedValues =
        typeof Intl.supportedValuesOf === "function"
          ? Intl.supportedValuesOf("region")
          : [];
      const displayNames = new Intl.DisplayNames(["en"], { type: "region" });
      if (supportedValues.length) {
        return supportedValues
          .map((code) => ({
            value: code,
            label: displayNames.of(code) || code,
          }))
          .sort((left, right) => left.label.localeCompare(right.label));
      }
    }
  } catch {
    return [];
  }
  return [];
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

function formatDateTime(value) {
  if (!value) {
    return "Unknown";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return parsed.toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function portalOptionsForSelection(field, countryCodes, selectedValues) {
  const selectedCountries = new Set(
    (Array.isArray(countryCodes) ? countryCodes : [])
      .map((item) => String(item || "").trim().toUpperCase())
      .filter(Boolean),
  );
  const selectedPortalIds = new Set((selectedValues || []).map((item) => String(item || "")));
  return (field.options || [])
    .filter((option) => {
      const requiredCountries = Array.isArray(option.country_codes)
        ? option.country_codes.map((item) => String(item || "").trim().toUpperCase()).filter(Boolean)
        : [];
      if (!requiredCountries.length) {
        return true;
      }
      const available = requiredCountries.some((countryCode) => selectedCountries.has(countryCode));
      return available || selectedPortalIds.has(String(option.value));
    })
    .map((option) => {
      const requiredCountries = Array.isArray(option.country_codes)
        ? option.country_codes.map((item) => String(item || "").trim().toUpperCase()).filter(Boolean)
        : [];
      const available =
        !requiredCountries.length ||
        requiredCountries.some((countryCode) => selectedCountries.has(countryCode));
      return {
        ...option,
        label:
          !available && selectedPortalIds.has(String(option.value))
            ? `${option.label} (selected outside its region)`
            : option.label,
      };
    });
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
  const [open, setOpen] = useState(false);
  const triggerRef = useRef(null);
  const popupRef = useRef(null);
  const [popupStyle, setPopupStyle] = useState({
    left: 0,
    top: 0,
    maxWidth: 320,
  });

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    function updatePosition() {
      const trigger = triggerRef.current;
      const popup = popupRef.current;
      if (!trigger || !popup) {
        return;
      }

      const viewportPadding = 12;
      const gap = 8;
      const maxWidth = Math.min(320, window.innerWidth - viewportPadding * 2);
      popup.style.maxWidth = `${maxWidth}px`;

      const triggerRect = trigger.getBoundingClientRect();
      const popupRect = popup.getBoundingClientRect();
      let left = triggerRect.left;
      if (left + popupRect.width > window.innerWidth - viewportPadding) {
        left = window.innerWidth - popupRect.width - viewportPadding;
      }
      left = Math.max(viewportPadding, left);

      let top = triggerRect.bottom + gap;
      if (top + popupRect.height > window.innerHeight - viewportPadding) {
        top = triggerRect.top - popupRect.height - gap;
      }
      top = Math.max(viewportPadding, top);

      setPopupStyle({
        left,
        top,
        maxWidth,
      });
    }

    const frameId = window.requestAnimationFrame(updatePosition);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.cancelAnimationFrame(frameId);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [content, open]);

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      ref={triggerRef}
    >
      <button
        aria-label="More information"
        aria-expanded={open}
        className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-outline-variant/30 text-[11px] font-bold text-on-surface-variant transition-colors hover:border-primary/40 hover:text-primary"
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((current) => !current)}
        onFocus={() => setOpen(true)}
        type="button"
      >
        i
      </button>
      {open ? (
        <div
          className="fixed z-50 rounded-lg border border-outline-variant/20 bg-surface px-3 py-2 text-xs leading-6 text-on-surface shadow-soft"
          ref={popupRef}
          style={popupStyle}
        >
          {content}
        </div>
      ) : null}
    </span>
  );
}

function ChoiceCard({ checked, title, description, info, onClick }) {
  return (
    <button
      className={[
        "rounded-xl border p-4 text-left transition-all",
        checked
          ? "border-primary/40 bg-primary/5 ring-2 ring-primary/10"
          : "border-outline-variant/20 bg-surface hover:border-primary/20 hover:bg-surface-container-low",
      ].join(" ")}
      onClick={onClick}
      type="button"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-on-surface">{title}</div>
          <p className="mt-1 text-xs leading-6 text-on-surface-variant">{description}</p>
        </div>
        {info ? <InfoHint content={info} /> : null}
      </div>
    </button>
  );
}

function TokenListInput({
  value,
  onChange,
  placeholder = "",
  maxItems = 50,
  helperText = "",
}) {
  const tokens = useMemo(() => parseDelimitedList(value), [value]);
  const [draft, setDraft] = useState("");

  function commit(rawValue) {
    const nextTokens = parseDelimitedList([tokens, rawValue]).slice(0, maxItems);
    onChange(nextTokens);
    setDraft("");
  }

  function removeToken(tokenToRemove) {
    onChange(tokens.filter((token) => token !== tokenToRemove));
  }

  return (
    <div className="space-y-2">
      <div className="rounded-lg border border-outline-variant/20 bg-surface px-3 py-3">
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
                onClick={() => removeToken(token)}
                type="button"
              >
                x
              </button>
            </span>
          ))}
          {tokens.length < maxItems ? (
            <input
              className="min-w-[16rem] flex-1 bg-transparent py-1 text-sm text-on-surface outline-none placeholder:text-on-surface-variant"
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
        <span>{helperText}</span>
        <span>
          {tokens.length}/{maxItems}
        </span>
      </div>
    </div>
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
  return new Set();
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

function formatSettingValue(value, field = null) {
  if (field?.id === "portals" && Array.isArray(value)) {
    const labelByValue = new Map(
      (field.options || []).map((option) => [String(option.value), option.label]),
    );
    return value.length
      ? value.map((item) => labelByValue.get(String(item)) || labelize(item)).join(", ")
      : "Not set";
  }
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
  return Object.entries(workspace.settings || {}).map(([key, value]) => {
    const field = fieldMap.get(key) || null;
    return {
      key,
      label: field?.label || labelize(key),
      value: formatSettingValue(value, field),
      internal: SYSTEM_SETTING_KEYS.has(key) || field?.user_facing === false,
    };
  });
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

function sourceValidationStatusLabel(validation, isCurrent) {
  if (validation.loading) {
    return "Checking";
  }
  if (!isCurrent) {
    return "Pending";
  }
  if (validation.error) {
    return "Retry needed";
  }
  if (!validation.valid) {
    return "Needs attention";
  }
  return "Ready";
}

function sourceValidationStatusClasses(validation, isCurrent) {
  if (validation.loading || !isCurrent) {
    return "bg-surface-container-low text-on-surface";
  }
  if (validation.error || !validation.valid) {
    return "bg-error/10 text-error";
  }
  return "bg-primary/10 text-primary";
}

function FieldRenderer({ field, value, onChange, dynamicOptions = {}, formState = null }) {
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

  if (field.id === "country_codes") {
    const options = dynamicOptions.all_country_options?.length
      ? dynamicOptions.all_country_options
      : field.options || [];
    const selectedValues = new Set(Array.isArray(value) ? value : []);
    return (
      <select
        className="min-h-44 w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
        multiple
        onChange={(event) => {
          const nextValues = [...event.target.selectedOptions].map((option) => option.value);
          onChange(nextValues);
        }}
        value={[...selectedValues]}
      >
        {options.map((option) => (
          <option key={`${field.id}-${option.value}`} value={String(option.value)}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }

  if (field.id === "target_roles") {
    return (
      <TokenListInput
        helperText="Add roles with Enter or a comma. They will be saved as blocks."
        maxItems={10}
        onChange={onChange}
        placeholder="Business Analyst, Product Manager"
        value={Array.isArray(value) ? value : []}
      />
    );
  }

  if (field.type === "tag_list") {
    return (
      <TokenListInput
        helperText="Add items with Enter or a comma."
        maxItems={50}
        onChange={onChange}
        placeholder={field.placeholder || ""}
        value={Array.isArray(value) ? value : parseDelimitedList(value)}
      />
    );
  }

  if (field.type === "multi_select") {
    const selectedValues = Array.isArray(value) ? value : [];
    const renderedOptions =
      field.id === "portals"
        ? portalOptionsForSelection(field, formState?.settings?.country_codes, selectedValues)
        : field.options || [];
    return (
      <div className="space-y-2">
        <div className="flex flex-wrap gap-3">
          {renderedOptions.map((option) => {
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

  if (field.type === "url_list" || field.type === "company_site_list") {
    const tokenValue =
      field.type === "company_site_list" && Array.isArray(value)
        ? value.map((entry) => {
            if (!entry || typeof entry !== "object") {
              return String(entry || "");
            }
            const companyName = String(entry.company_name || entry.company || "").trim();
            const url = String(entry.url || "").trim();
            return companyName && url ? `${companyName} | ${url}` : url || companyName;
          })
        : Array.isArray(value)
          ? value
          : parseDelimitedList(value);
    return (
      <TokenListInput
        helperText="Separate each URL with Enter or a comma."
        maxItems={50}
        onChange={onChange}
        placeholder={field.placeholder || ""}
        value={tokenValue}
      />
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

  if (field.type === "textarea") {
    return (
      <textarea
        className="min-h-32 w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
        onChange={(event) => onChange(event.target.value)}
        placeholder={field.placeholder || ""}
        rows={field.rows || 4}
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
  const { request, resolvePath } = useSession();
  const [actionState, setActionState] = useState(EMPTY_ACTION_STATE);
  const [builderState, setBuilderState] = useState({
    open: false,
    mode: "create",
    editingWorkspaceId: "",
    submitting: false,
    deleting: "",
    error: "",
    details: [],
    message: "",
  });
  const [form, setForm] = useState(EMPTY_BUILDER_FORM);
  const [sourceValidation, setSourceValidation] = useState(EMPTY_SOURCE_VALIDATION);
  const [cvUploadState, setCvUploadState] = useState({
    uploading: false,
    message: "",
    error: "",
  });
  const sourceValidationRequestIdRef = useRef(0);

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
    refresh: refreshBuilderCatalog,
  } = useApiResource(() => request("/workspace-builder/catalog"), [request]);
  const {
    data: cvAssetsPayload,
    refresh: refreshCvAssets,
  } = useApiResource(() => request("/documents?asset_kind=workspace_cv&limit=100"), [request]);

  const workspaces = workspacesData?.workspaces || [];
  const builderCatalogReady = Boolean(builderCatalog && !builderLoading);
  const focusedWorkspaceId = searchParams.get("workspace_id") || "";
  const focusedWorkspace = useMemo(
    () => workspaces.find((workspace) => workspace.id === focusedWorkspaceId) || null,
    [focusedWorkspaceId, workspaces],
  );
  const {
    data: focusedWorkspaceDocumentsPayload,
    loading: focusedWorkspaceDocumentsLoading,
    error: focusedWorkspaceDocumentsError,
  } = useApiResource(
    () =>
      focusedWorkspaceId
        ? request(`/documents?workspace_id=${encodeURIComponent(focusedWorkspaceId)}&limit=60`)
        : Promise.resolve({ documents: [] }),
    [request, focusedWorkspaceId],
    { immediate: Boolean(focusedWorkspaceId) },
  );
  const flows = useMemo(
    () => (builderCatalog?.flows || []).filter((flow) => flow.frontend_visible !== false),
    [builderCatalog?.flows],
  );
  const allFlowSources = useMemo(
    () =>
      (builderCatalog?.sources || []).filter((item) =>
        (item.compatible_flows || []).includes(form.flowId),
      ),
    [builderCatalog?.sources, form.flowId],
  );
  const availableSources = useMemo(
    () => allFlowSources.filter((item) => item.frontend_visible !== false && !item.legacy),
    [allFlowSources],
  );
  const legacySources = useMemo(
    () => allFlowSources.filter((item) => item.legacy),
    [allFlowSources],
  );
  const availableConfigurationFields = useMemo(
    () =>
      (builderCatalog?.configuration_fields || []).filter((field) =>
        field.user_facing !== false &&
        field.frontend_visible !== false &&
        fieldMatchesSelection(field, form, availableSources),
      ),
    [builderCatalog, form, availableSources],
  );
  const builderSections = useMemo(
    () =>
      (builderCatalog?.builder_sections || []).filter((section) =>
        section.frontend_visible !== false &&
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
  const workspaceCvAssets = useMemo(
    () =>
      (cvAssetsPayload?.documents || [])
        .filter((item) => item.asset_kind === "workspace_cv")
        .map((item) => ({
          value: item.asset_id,
          label: item.display_name,
          assetId: item.asset_id,
          createdAt: item.created_at,
          downloadUrl: item.download_url,
          sourceOrigin: item.source_origin,
          status: item.display_status || item.status || "ready",
        })),
    [cvAssetsPayload?.documents],
  );
  const workspaceCvAssetIds = useMemo(
    () => new Set(workspaceCvAssets.map((item) => item.value)),
    [workspaceCvAssets],
  );
  const dynamicFieldOptions = useMemo(
    () => ({
      all_country_options: buildCountryOptions(),
      workspace_cv_assets: workspaceCvAssets,
    }),
    [workspaceCvAssets],
  );
  const workspaceCvAssetsLoaded = cvAssetsPayload !== undefined;
  const resolvedModuleIds = useMemo(
    () =>
      form.moduleIds.length
        ? form.moduleIds
        : defaultModuleIdsForFlow(builderCatalog, form.flowId),
    [builderCatalog, form.flowId, form.moduleIds],
  );
  const sourceFields = sectionFields.sources || [];
  const visibleBuilderSections = builderSections.filter((section) => section.id !== "sources");
  const selectedLegacySource = legacySources.find((source) => form.sourceIds.includes(source.id)) || null;
  const selectedSource =
    availableSources.find((source) => form.sourceIds.includes(source.id)) || selectedLegacySource || null;
  const priorityRankingEnabled = resolvedModuleIds.includes(OPTIONAL_PRIORITY_MODULE_ID);
  const activeSourceValidationPayload = useMemo(
    () =>
      buildSourceValidationPayload({
        flowId: form.flowId,
        sourceIds: form.sourceIds,
        settings: form.settings,
      }),
    [form.flowId, form.settings, form.sourceIds],
  );
  const activeSourceValidationKey = useMemo(
    () => sourceValidationKey(activeSourceValidationPayload),
    [activeSourceValidationPayload],
  );
  const sourceDefinitionById = useMemo(
    () => new Map((builderCatalog?.sources || []).map((source) => [source.id, source])),
    [builderCatalog?.sources],
  );
  const resolveSourceName = (sourceId, { includeLegacyBadge = true } = {}) => {
    const source = sourceDefinitionById.get(sourceId);
    if (!source) {
      return labelize(sourceId);
    }
    const baseName = source.name || labelize(source.id);
    return source.legacy && includeLegacyBadge ? `${baseName} (Legacy)` : baseName;
  };
  const selectedSourceValidationResult = useMemo(
    () =>
      sourceValidation.sourceResults.find((result) => form.sourceIds.includes(result.source_id)) || null,
    [form.sourceIds, sourceValidation.sourceResults],
  );
  const sourceValidationIsCurrent = !form.sourceIds.length || sourceValidation.validationKey === activeSourceValidationKey;
  const sourceValidationIssues = useMemo(
    () =>
      sourceValidation.sourceResults
        .filter((result) => result.status !== "valid")
        .flatMap((result) => {
          const prefix = resolveSourceName(result.source_id);
          if (result.details?.length) {
            return result.details.map((detail) => `${prefix}: ${detail}`);
          }
          return [`${prefix}: ${result.summary}`];
        }),
    [resolveSourceName, sourceValidation.sourceResults],
  );
  const selectedWorkspaceCvLabel = useMemo(() => {
    const selectedAssetId = String(form.settings.workspace_cv_asset_id || "").trim();
    if (!selectedAssetId) {
      return "Not selected";
    }
    if (!workspaceCvAssetsLoaded) {
      return "Loading...";
    }
    return workspaceCvAssets.find((item) => item.value === selectedAssetId)?.label || "No longer available";
  }, [form.settings.workspace_cv_asset_id, workspaceCvAssets, workspaceCvAssetsLoaded]);
  const selectedWorkspaceCvAsset = useMemo(() => {
    const selectedAssetId = String(form.settings.workspace_cv_asset_id || "").trim();
    if (!selectedAssetId) {
      return null;
    }
    return workspaceCvAssets.find((item) => item.value === selectedAssetId) || null;
  }, [form.settings.workspace_cv_asset_id, workspaceCvAssets]);
  const selectedWorkspaceCvMissing = Boolean(
    workspaceCvAssetsLoaded &&
      form.settings.workspace_cv_asset_id &&
      !workspaceCvAssetIds.has(form.settings.workspace_cv_asset_id),
  );
  const focusedWorkspaceCvDocuments = useMemo(() => {
    if (!focusedWorkspace) {
      return [];
    }
    const selectedAssetId = String(focusedWorkspace.settings?.workspace_cv_asset_id || "").trim();
    return (focusedWorkspaceDocumentsPayload?.documents || [])
      .filter((document) => {
        const assetKind = String(document.asset_kind || "").trim();
        if (assetKind === "generated_cv") {
          return String(document.workspace_id || "").trim() === focusedWorkspace.id;
        }
        if (assetKind === "workspace_cv") {
          return selectedAssetId && String(document.asset_id || "").trim() === selectedAssetId;
        }
        return false;
      })
      .sort((left, right) => String(right.created_at || "").localeCompare(String(left.created_at || "")))
      .slice(0, 6);
  }, [focusedWorkspace, focusedWorkspaceDocumentsPayload?.documents]);
  const saveBlockedReason = useMemo(() => {
    if (!form.name.trim()) {
      return "Enter a workspace name.";
    }
    if (!form.sourceIds.length) {
      return "Choose one job source.";
    }
    if (!resolvedModuleIds.length) {
      return "At least one automation module must stay enabled.";
    }
    if (!form.settings.workspace_cv_asset_id) {
      return "Choose a baseline CV.";
    }
    if (selectedWorkspaceCvMissing) {
      return "The selected baseline CV is no longer available. Upload or choose another one.";
    }
    if (sourceValidation.loading) {
      return "Checking the selected source with the backend...";
    }
    if (!sourceValidationIsCurrent) {
      return "Source setup changed. Waiting for backend validation.";
    }
    if (sourceValidation.error) {
      return sourceValidation.error;
    }
    if (!sourceValidation.valid) {
      return "Resolve the source setup issues below before saving.";
    }
    return "";
  }, [
    form.name,
    form.settings.workspace_cv_asset_id,
    form.sourceIds.length,
    resolvedModuleIds.length,
    selectedWorkspaceCvMissing,
    sourceValidation.error,
    sourceValidation.loading,
    sourceValidation.valid,
    sourceValidationIsCurrent,
  ]);
  const saveDisabled = Boolean(builderLoading || builderState.submitting || saveBlockedReason);

  function resetBuilderState(overrides = {}) {
    setBuilderState({
      open: false,
      mode: "create",
      editingWorkspaceId: "",
      submitting: false,
      deleting: "",
      error: "",
      details: [],
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

  function clearBuilderSearchParams() {
    if (!searchParams.get("create") && !searchParams.get("edit") && !searchParams.get("focus")) {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete("create");
    next.delete("edit");
    next.delete("focus");
    setSearchParams(next);
  }

  function openBuilder() {
    if (!builderCatalogReady) {
      return;
    }
    const defaultFlowId = flows[0]?.id || DEFAULT_FLOW_ID;
    setForm(buildBuilderForm(builderCatalog, defaultFlowId));
    setSourceValidation(EMPTY_SOURCE_VALIDATION);
    setCvUploadState({ uploading: false, message: "", error: "" });
    resetBuilderState({ open: true });
    if (searchParams.get("create")) {
      const next = new URLSearchParams(searchParams);
      next.delete("create");
      setSearchParams(next);
    }
  }

  function openEditor(workspace) {
    if (!builderCatalogReady) {
      return;
    }
    setForm(hydrateFormFromWorkspace(workspace, builderCatalog));
    setSourceValidation(EMPTY_SOURCE_VALIDATION);
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
    setSourceValidation(EMPTY_SOURCE_VALIDATION);
    setCvUploadState({ uploading: false, message: "", error: "" });
    clearBuilderSearchParams();
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

  function selectSingleSource(sourceId) {
    setForm((current) => {
      const nextSourceIds =
        current.sourceIds.length === 1 && current.sourceIds[0] === sourceId ? [] : [sourceId];
      return { ...current, sourceIds: nextSourceIds };
    });
    setSourceValidation(EMPTY_SOURCE_VALIDATION);
  }

  function setPriorityRankingEnabled(enabled) {
    setForm((current) => {
      const currentModules = new Set(
        current.moduleIds.length
          ? current.moduleIds
          : defaultModuleIdsForFlow(builderCatalog, current.flowId),
      );
      for (const moduleId of FIXED_TAILORED_MODULE_IDS) {
        currentModules.add(moduleId);
      }
      if (enabled) {
        currentModules.add(OPTIONAL_PRIORITY_MODULE_ID);
      } else {
        currentModules.delete(OPTIONAL_PRIORITY_MODULE_ID);
      }
      return { ...current, moduleIds: [...currentModules] };
      });
  }

  async function loadSourceValidationState(payload, requestId) {
    try {
      const response = await request("/workspace-builder/source-validation", {
        method: "POST",
        body: payload,
      });
      const nextState = {
        loading: false,
        valid: Boolean(response.valid),
        sourceResults: response.source_results || [],
        error: "",
        validationKey: sourceValidationKey(payload),
      };
      if (sourceValidationRequestIdRef.current === requestId) {
        setSourceValidation(nextState);
      }
      return nextState;
    } catch (validationError) {
      const nextState = {
        loading: false,
        valid: false,
        sourceResults: [],
        error: getApiErrorMessage(validationError, "Unable to validate sources."),
        validationKey: sourceValidationKey(payload),
      };
      if (sourceValidationRequestIdRef.current === requestId) {
        setSourceValidation(nextState);
      }
      return nextState;
    }
  }

  async function validateSourcesNow(payload = activeSourceValidationPayload) {
    const requestId = sourceValidationRequestIdRef.current + 1;
    sourceValidationRequestIdRef.current = requestId;
    setSourceValidation((current) => ({
      ...current,
      loading: true,
      error: "",
    }));
    return loadSourceValidationState(payload, requestId);
  }

  async function ensureCurrentSourceValidation() {
    if (!form.sourceIds.length) {
      return {
        ...EMPTY_SOURCE_VALIDATION,
        validationKey: activeSourceValidationKey,
      };
    }
    if (
      sourceValidationIsCurrent &&
      !sourceValidation.loading &&
      !sourceValidation.error &&
      sourceValidation.sourceResults.length
    ) {
      return sourceValidation;
    }
    return validateSourcesNow(activeSourceValidationPayload);
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
      details: [],
      message: "",
    }));

    try {
      const validationResult = await ensureCurrentSourceValidation();
      if (validationResult.error) {
        setBuilderState((current) => ({
          ...current,
          submitting: false,
          error: validationResult.error,
          details: [],
        }));
        return;
      }
      if (!validationResult.valid) {
        const validationDetails = (validationResult.sourceResults || [])
          .filter((result) => result.status !== "valid")
          .flatMap((result) => {
            const prefix = resolveSourceName(result.source_id);
            if (result.details?.length) {
              return result.details.map((detail) => `${prefix}: ${detail}`);
            }
            return [`${prefix}: ${result.summary}`];
          });
        setBuilderState((current) => ({
          ...current,
          submitting: false,
          error: "Resolve the source setup issues before saving this workspace.",
          details: validationDetails,
        }));
        return;
      }
      const workspace = await request(path, {
        method: isEditing ? "PUT" : "POST",
        body: {
          name: form.name,
          description: form.description,
          flow_id: form.flowId,
          source_ids: form.sourceIds,
          module_ids: resolvedModuleIds,
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
      clearBuilderSearchParams();
      await refresh();
    } catch (submitError) {
      setBuilderState((current) => ({
        ...current,
        submitting: false,
        error: getApiErrorMessage(submitError, "Unable to save workspace."),
        details: getApiErrorDetails(submitError),
      }));
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
    if (!builderState.open || !form.sourceIds.length) {
      return undefined;
    }
    const payload = activeSourceValidationPayload;
    const requestId = sourceValidationRequestIdRef.current + 1;
    sourceValidationRequestIdRef.current = requestId;
    const timer = window.setTimeout(() => {
      if (sourceValidationRequestIdRef.current !== requestId) {
        return;
      }
      setSourceValidation((current) => ({
        ...current,
        loading: true,
        error: "",
      }));
      loadSourceValidationState(payload, requestId).catch(() => undefined);
    }, SOURCE_VALIDATION_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [activeSourceValidationKey, activeSourceValidationPayload, builderState.open, form.sourceIds.length, request]);

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
    if (!builderCatalogReady || builderState.open || searchParams.get("edit")) {
      return;
    }
    if (searchParams.get("create")) {
      const defaultFlowId = flows[0]?.id || DEFAULT_FLOW_ID;
      setForm(buildBuilderForm(builderCatalog, defaultFlowId));
      setSourceValidation(EMPTY_SOURCE_VALIDATION);
      setCvUploadState({ uploading: false, message: "", error: "" });
      resetBuilderState({ open: true });
      const next = new URLSearchParams(searchParams);
      next.delete("create");
      setSearchParams(next);
    }
  }, [builderCatalog, builderCatalogReady, builderState.open, flows, searchParams, setSearchParams]);

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

  function buildWorkspaceValidationPayload(workspace) {
    const flowId = workspaceAutomationFlow(workspace);
    return buildSourceValidationPayload({
      flowId,
      sourceIds: workspaceSourceIds(workspace, builderCatalog, flowId),
      settings: workspace.settings || {},
    });
  }

  async function triggerRun(workspaceId, executionMode, runInputOverrides = {}) {
    const workspace = workspaces.find((item) => item.id === workspaceId);
    if (!workspace) {
      setActionState({
        ...EMPTY_ACTION_STATE,
        workspaceId,
        error: "The selected workspace is no longer available.",
      });
      return;
    }
    if (
      workspaceCvAssetsLoaded &&
      workspace.settings?.workspace_cv_asset_id &&
      !workspaceCvAssetIds.has(String(workspace.settings.workspace_cv_asset_id))
    ) {
      setActionState({
        ...EMPTY_ACTION_STATE,
        workspaceId,
        error: "Run blocked because the selected workspace CV is no longer available.",
        details: ["Open this workspace and choose or upload a new baseline CV before starting another run."],
      });
      return;
    }
    setActionState({
      ...EMPTY_ACTION_STATE,
      workspaceId,
      loading: true,
      message: executionMode === "sync" ? "Checking workspace setup before running..." : "Checking workspace setup before queueing...",
    });
    try {
      const validationPayload = buildWorkspaceValidationPayload(workspace);
      const validation = await request("/workspace-builder/source-validation", {
        method: "POST",
        body: validationPayload,
      });
      if (!validation.valid) {
        setActionState({
          ...EMPTY_ACTION_STATE,
          workspaceId,
          error:
            executionMode === "sync"
              ? "Run blocked until the workspace source setup is fixed."
              : "Queue request blocked until the workspace source setup is fixed.",
          details: (validation.source_results || [])
            .filter((result) => result.status !== "valid")
            .flatMap((result) => {
              const prefix = resolveSourceName(result.source_id);
              if (result.details?.length) {
                return result.details.map((detail) => `${prefix}: ${detail}`);
              }
              return [`${prefix}: ${result.summary}`];
            }),
        });
        return;
      }
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
        ...EMPTY_ACTION_STATE,
        workspaceId,
        message:
          executionMode === "sync"
            ? `Run ${run.id} finished with status ${labelize(run.status)}`
            : `Queued ${run.id}`,
      });
      await refresh();
      if (executionMode === "sync") {
        navigate(`/runs/${run.id}`);
      }
    } catch (runError) {
      setActionState({
        ...EMPTY_ACTION_STATE,
        workspaceId,
        error: getApiErrorMessage(runError, "Unable to start run."),
        details: getApiErrorDetails(runError),
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
        ...EMPTY_ACTION_STATE,
        workspaceId,
        message: `Deleted ${workspaceId}`,
      });
      setBuilderState((current) => ({ ...current, deleting: "", message: "", error: "" }));
      await refresh();
    } catch (deleteError) {
      setActionState({
        ...EMPTY_ACTION_STATE,
        workspaceId,
        error: getApiErrorMessage(deleteError, "Unable to delete workspace."),
        details: getApiErrorDetails(deleteError),
      });
      setBuilderState((current) => ({ ...current, deleting: "", message: "", error: "" }));
    }
  }

  function workspacePresentation(workspace) {
    const moduleNames = (workspace.metadata?.modules || []).map((moduleId) => labelize(moduleId));
    const sourceNames = workspaceSourceIds(
      workspace,
      builderCatalog,
      workspaceAutomationFlow(workspace),
    ).map((sourceId) => resolveSourceName(sourceId));
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
        <div>{actionState.error || actionState.message}</div>
        {actionState.details.length ? (
          <div className="mt-2 space-y-1 text-xs leading-6">
            {actionState.details.map((detail) => (
              <div key={`${workspace.id}-${detail}`}>{detail}</div>
            ))}
          </div>
        ) : null}
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
            const workspaceActionPending = actionState.workspaceId === workspace.id && actionState.loading;
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
                    className="rounded bg-surface-container-low px-3 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-60"
                    disabled={workspaceActionPending}
                    onClick={() => triggerRun(workspace.id, "sync")}
                    type="button"
                  >
                    Run
                  </button>
                  <Link
                    className="rounded bg-surface-container-low px-3 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                    to={`${QUICK_APPLY_ROUTE}?workspace_id=${workspace.id}`}
                  >
                    Quick Apply
                  </Link>
                  <button
                    className="rounded bg-surface-container-low px-3 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-60"
                    disabled={workspaceActionPending}
                    onClick={() => triggerRun(workspace.id, "queued")}
                    type="button"
                  >
                    Queue
                  </button>
                  <button
                    className="rounded bg-surface-container-low px-3 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-60"
                    disabled={!builderCatalogReady}
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
    const workspaceActionPending = actionState.workspaceId === workspace.id && actionState.loading;

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
                className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={workspaceActionPending}
                onClick={() => triggerRun(workspace.id, "sync")}
                type="button"
              >
                Run Now
              </button>
              <Link
                className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                to={`${QUICK_APPLY_ROUTE}?workspace_id=${workspace.id}`}
              >
                Quick Apply
              </Link>
              <button
                className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-60"
                disabled={workspaceActionPending}
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

          <div className="rounded-xl border border-outline-variant/10 bg-surface p-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <h3 className="text-sm font-semibold text-on-surface">Quick Application</h3>
                <p className="mt-1 text-xs leading-6 text-on-surface-variant">
                  Found an exact job link yourself? Use this workspace as the baseline and generate documents from a pasted job URL without creating a separate workspace.
                </p>
              </div>
              <Link
                className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90"
                to={`${QUICK_APPLY_ROUTE}?workspace_id=${workspace.id}`}
              >
                Create Quick Application
              </Link>
            </div>
          </div>

          <div className="rounded-xl border border-outline-variant/10 bg-surface p-4">
            <div>
              <h3 className="text-sm font-semibold text-on-surface">Workspace CVs</h3>
              <p className="mt-1 text-xs leading-6 text-on-surface-variant">
                The baseline CV for this workspace and the tailored CVs generated from it stay
                visible here, so you do not have to jump into another section to review them.
              </p>
            </div>
            {focusedWorkspaceDocumentsLoading ? (
              <div className="mt-4 rounded-lg border border-outline-variant/10 bg-surface-container-lowest p-4 text-sm text-on-surface-variant">
                Loading workspace CVs...
              </div>
            ) : focusedWorkspaceDocumentsError ? (
              <div className="mt-4 rounded-lg border border-outline-variant/10 bg-surface-container-lowest p-4 text-sm text-error">
                {focusedWorkspaceDocumentsError}
              </div>
            ) : focusedWorkspaceCvDocuments.length ? (
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                {focusedWorkspaceCvDocuments.map((document) => (
                  <article
                    className="rounded-lg border border-outline-variant/10 bg-surface-container-lowest p-4"
                    key={document.document_id}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="text-sm font-semibold text-on-surface">
                        {document.display_name}
                      </div>
                      <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
                        {document.document_type}
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-on-surface-variant">
                      {[document.job_title, document.company].filter(Boolean).join(" at ") ||
                        "Baseline workspace CV"}
                    </p>
                    <div className="mt-3 grid gap-2 text-xs leading-6 text-on-surface-variant md:grid-cols-2">
                      <div>
                        <span className="font-semibold text-on-surface">Status:</span>{" "}
                        {labelize(document.display_status || document.status || "ready")}
                      </div>
                      <div>
                        <span className="font-semibold text-on-surface">Created:</span>{" "}
                        {formatDateTime(document.created_at)}
                      </div>
                    </div>
                    {document.download_url ? (
                      <div className="mt-4">
                        <a
                          className="inline-flex items-center rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                          href={resolvePath(document.preview_url || document.download_url)}
                          rel="noreferrer"
                          target="_blank"
                        >
                          Open Document
                        </a>
                      </div>
                    ) : null}
                  </article>
                ))}
              </div>
            ) : (
              <div className="mt-4 rounded-lg border border-outline-variant/10 bg-surface-container-lowest p-4 text-sm text-on-surface-variant">
                No workspace CVs are visible yet. Upload a baseline CV while editing this workspace,
                or run the workspace to generate tailored CVs here.
              </div>
            )}
          </div>

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
              className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-60"
              disabled={!builderCatalogReady}
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
            Browse workspaces as simple rows. Use them for recurring sourcing workflows, and use Quick Apply when you already have an exact job link.
          </p>
          <p className="text-xs uppercase tracking-wider text-on-surface-variant/80">
            Run Now executes inside the app. Queue Run only waits for a worker.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link
            className="rounded bg-surface-container-low px-5 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            to={QUICK_APPLY_ROUTE}
          >
            Quick Apply
          </Link>
          <button
            className="rounded bg-gradient-to-br from-primary to-primary-container px-5 py-3 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!builderCatalogReady}
            onClick={openBuilder}
            type="button"
          >
            {builderLoading ? "Loading Workspace Builder..." : "Create Workspace From Scratch"}
          </button>
        </div>
      </header>

      {builderError && !builderState.open ? (
        <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm shadow-soft">
          <p className="text-error">{builderError}</p>
          <button
            className="mt-3 rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
            onClick={() => refreshBuilderCatalog().catch(() => undefined)}
            type="button"
          >
            Retry Workspace Builder
          </button>
        </div>
      ) : null}

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
              description="Give the workspace a clear name and a short description so it is obvious what kind of jobs and applications it should handle."
              title="Workspace Basics"
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
              description="Choose one recurring source type for this workspace. Source-specific setup appears immediately after you select it."
              id="workspace-builder-sources"
              title="Job Source"
            >
              {availableSources.length ? (
                <div className="grid gap-4 md:grid-cols-3">
                  {availableSources.map((source) => (
                    <ChoiceCard
                      checked={form.sourceIds.includes(source.id)}
                      description={source.description}
                      info={
                        source.id === "academic_career_sites"
                          ? "Use this for universities, departments, chairs, institutes, and research organizations. The saved academic website list is used automatically, and you can still add up to 50 academic URLs of your own."
                          : source.id === "company_career_sites"
                            ? "Use this when you want roles from major company career sites worldwide. You can also add up to 50 company or careers URLs of your own."
                            : source.id === "job_board_collection"
                              ? "Choose from major global job boards here. Regional boards appear automatically after you select matching target countries."
                              : source.description
                      }
                      key={source.id}
                      onClick={() => selectSingleSource(source.id)}
                      title={source.name}
                    />
                  ))}
                </div>
              ) : (
                <p className="text-sm text-on-surface-variant">No sources are available for this flow.</p>
              )}

              {selectedLegacySource ? (
                <details
                  className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4"
                  open
                >
                  <summary className="cursor-pointer text-sm font-semibold text-on-surface">
                    Legacy Sources
                  </summary>
                  <div className="mt-3 space-y-4">
                    <p className="text-xs leading-6 text-on-surface-variant">
                      This workspace already uses a retired source. It stays editable here so the
                      workspace is not misleading, but new workspaces cannot select it.
                    </p>
                    <div className="grid gap-4 md:grid-cols-3">
                      <div className="rounded-xl border border-amber-500/20 bg-surface p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="text-sm font-semibold text-on-surface">
                              {selectedLegacySource.name}
                            </div>
                            <p className="mt-1 text-xs leading-6 text-on-surface-variant">
                              {selectedLegacySource.description}
                            </p>
                          </div>
                          <span className="rounded-full bg-amber-500/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-amber-600">
                            Legacy
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </details>
              ) : null}

              {selectedSource && sourceFields.length ? (
                <div className="space-y-4 rounded-xl border border-outline-variant/10 bg-surface p-4">
                  <div>
                    <div className="text-sm font-semibold text-on-surface">
                      {selectedSource.name} setup
                    </div>
                    <p className="mt-1 text-xs leading-6 text-on-surface-variant">
                      Only settings relevant to the selected source are shown here.
                    </p>
                  </div>
                  <div className="grid gap-4 md:grid-cols-2">
                    {sourceFields.map((field) => (
                      <label className="space-y-2" key={field.id}>
                        <span className="block text-sm font-semibold text-on-surface">{field.label}</span>
                        <FieldRenderer
                          dynamicOptions={dynamicFieldOptions}
                          field={field}
                          formState={form}
                          onChange={(nextValue) => updateSetting(field.id, nextValue)}
                          value={form.settings[field.id]}
                        />
                        <span className="block text-xs leading-6 text-on-surface-variant">
                          {field.description}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              ) : null}

              {form.sourceIds.length ? (
                <div className="rounded-xl border border-outline-variant/10 bg-surface p-4">
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div>
                      <div className="text-sm font-semibold text-on-surface">Backend source validation</div>
                      <p className="mt-1 text-xs leading-6 text-on-surface-variant">
                        Save stays disabled until this source check is current and valid.
                      </p>
                    </div>
                    <span
                      className={[
                        "rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide",
                        sourceValidationStatusClasses(sourceValidation, sourceValidationIsCurrent),
                      ].join(" ")}
                    >
                      {sourceValidationStatusLabel(sourceValidation, sourceValidationIsCurrent)}
                    </span>
                  </div>

                  {!sourceValidationIsCurrent && !sourceValidation.loading ? (
                    <p className="mt-3 text-sm text-on-surface-variant">
                      Source setup changed. Rechecking it with the backend now.
                    </p>
                  ) : null}

                  {sourceValidation.error ? (
                    <p className="mt-3 text-sm text-error">{sourceValidation.error}</p>
                  ) : null}

                  {sourceValidationIsCurrent && selectedSourceValidationResult ? (
                    <div className="mt-3 rounded-lg border border-outline-variant/10 bg-surface-container-lowest p-4">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm font-semibold text-on-surface">
                          {resolveSourceName(selectedSourceValidationResult.source_id)}
                        </span>
                        <span
                          className={[
                            "rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide",
                            selectedSourceValidationResult.status === "valid"
                              ? "bg-primary/10 text-primary"
                              : "bg-error/10 text-error",
                          ].join(" ")}
                        >
                          {selectedSourceValidationResult.status}
                        </span>
                      </div>
                      <p className="mt-2 text-sm text-on-surface-variant">
                        {selectedSourceValidationResult.summary}
                      </p>
                      {selectedSourceValidationResult.details?.length ? (
                        <div className="mt-2 space-y-1 text-xs leading-6 text-on-surface-variant">
                          {selectedSourceValidationResult.details.map((detail) => (
                            <div key={`${selectedSourceValidationResult.source_id}-${detail}`}>{detail}</div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </BuilderSection>

            <BuilderSection
              description="Screening stays on in the background. Priority ranking is optional. Tailored CV generation is part of this workflow. Motivation letters are not included."
              title="Automation Options"
            >
              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-xl border border-outline-variant/10 bg-surface p-4">
                  <div className="text-sm font-semibold text-on-surface">Job Filtering</div>
                  <p className="mt-1 text-xs leading-6 text-on-surface-variant">
                    Always on. It removes obvious mismatches before documents are generated.
                  </p>
                </div>
                <div className="rounded-xl border border-outline-variant/10 bg-surface p-4">
                  <div className="flex items-center gap-2">
                    <div className="text-sm font-semibold text-on-surface">Priority Ranking</div>
                    <InfoHint content="When enabled, matching jobs are ranked so the workspace can push stronger opportunities forward first. This is most useful for broad search-heavy sources and older legacy LinkedIn workspaces." />
                  </div>
                  <p className="mt-1 text-xs leading-6 text-on-surface-variant">
                    Turn this on if you want jobs ranked before document generation.
                  </p>
                  <div className="mt-3 flex gap-2">
                    <TogglePill
                      checked={priorityRankingEnabled}
                      label="Enabled"
                      onClick={() => setPriorityRankingEnabled(true)}
                    />
                    <TogglePill
                      checked={!priorityRankingEnabled}
                      label="Disabled"
                      onClick={() => setPriorityRankingEnabled(false)}
                    />
                  </div>
                </div>
                <div className="rounded-xl border border-outline-variant/10 bg-surface p-4">
                  <div className="text-sm font-semibold text-on-surface">Tailored CV Generation</div>
                  <p className="mt-1 text-xs leading-6 text-on-surface-variant">
                    Generates role-specific application documents from your baseline CV. Motivation letters are not generated here.
                  </p>
                </div>
              </div>
            </BuilderSection>

            {visibleBuilderSections.map((section) => {
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
                  {section.id === "filters" ? (
                    <div className="rounded-lg border border-outline-variant/10 bg-surface p-4 text-xs leading-6 text-on-surface-variant">
                      Language filtering uses the languages saved in your profile. Update them in Settings if your CV language baseline changes.
                    </div>
                  ) : null}
                  {section.id === "documents" ? (
                    <div className="rounded-lg border border-outline-variant/10 bg-surface p-4">
                      <p className="text-sm font-semibold text-on-surface">Document style stays shared</p>
                      <p className="mt-1 text-xs leading-6 text-on-surface-variant">
                        This workspace uses your saved template, font, color, and photo defaults. The
                        baseline CV selected below stays visible here so you can review it without
                        leaving the workspace page.
                      </p>
                    </div>
                  ) : null}
                  {section.id === "cv_binding" ? (
                    <div className="space-y-4">
                      <div className="grid gap-4 md:grid-cols-2">
                        {fields.map((field) => (
                          <label className="space-y-2" key={field.id}>
                            <span className="block text-sm font-semibold text-on-surface">{field.label}</span>
                            <FieldRenderer
                              dynamicOptions={dynamicFieldOptions}
                              field={field}
                              formState={form}
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
                      {selectedWorkspaceCvAsset ? (
                        <div className="rounded-lg border border-outline-variant/10 bg-surface p-4">
                          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                            <div>
                              <p className="text-sm font-semibold text-on-surface">Selected workspace CV</p>
                              <p className="mt-1 text-xs leading-6 text-on-surface-variant">
                                {selectedWorkspaceCvAsset.label}
                              </p>
                            </div>
                            {selectedWorkspaceCvAsset.downloadUrl ? (
                              <a
                                className="inline-flex items-center rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                                href={resolvePath(selectedWorkspaceCvAsset.downloadUrl)}
                                rel="noreferrer"
                                target="_blank"
                              >
                                Open CV
                              </a>
                            ) : null}
                          </div>
                          <div className="mt-4 grid gap-3 text-sm text-on-surface-variant md:grid-cols-3">
                            <div>
                              <span className="font-semibold text-on-surface">Status:</span>{" "}
                              {labelize(selectedWorkspaceCvAsset.status)}
                            </div>
                            <div>
                              <span className="font-semibold text-on-surface">Created:</span>{" "}
                              {formatDateTime(selectedWorkspaceCvAsset.createdAt)}
                            </div>
                            <div>
                              <span className="font-semibold text-on-surface">Origin:</span>{" "}
                              {labelize(selectedWorkspaceCvAsset.sourceOrigin || "upload")}
                            </div>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <div className="grid gap-4 md:grid-cols-2">
                      {fields.map((field) => (
                        <label className="space-y-2" key={field.id}>
                          <span className="block text-sm font-semibold text-on-surface">{field.label}</span>
                          <FieldRenderer
                            dynamicOptions={dynamicFieldOptions}
                            field={field}
                            formState={form}
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
                  {form.sourceIds.length ? form.sourceIds.map((sourceId) => resolveSourceName(sourceId)).join(", ") : "None selected"}
                </div>
                <div>
                  <span className="font-semibold text-on-surface">Modules:</span>{" "}
                  {resolvedModuleIds.length
                    ? resolvedModuleIds.map(labelize).join(", ")
                    : "Default remediation path"}
                </div>
                <div>
                  <span className="font-semibold text-on-surface">Workspace CV:</span>{" "}
                  {selectedWorkspaceCvLabel}
                </div>
              </div>

              {saveBlockedReason ? (
                <div className="rounded-lg border border-outline-variant/10 bg-surface px-4 py-3 text-sm text-on-surface-variant">
                  {saveBlockedReason}
                </div>
              ) : null}

              {sourceValidationIsCurrent && sourceValidationIssues.length ? (
                <div className="rounded-lg bg-error-container px-4 py-3 text-sm text-on-error-container">
                  <div className="font-semibold">Source issues to fix</div>
                  <div className="mt-2 space-y-1 text-xs leading-6">
                    {sourceValidationIssues.map((issue) => (
                      <div key={issue}>{issue}</div>
                    ))}
                  </div>
                </div>
              ) : null}

              {builderError ? <p className="text-sm text-error">{builderError}</p> : null}
              {builderState.error ? <p className="text-sm text-error">{builderState.error}</p> : null}
              {builderState.details.length ? (
                <div className="space-y-1 text-xs leading-6 text-error">
                  {builderState.details.map((detail) => (
                    <div key={detail}>{detail}</div>
                  ))}
                </div>
              ) : null}

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
                  disabled={saveDisabled}
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
              className="mt-5 rounded bg-gradient-to-br from-primary to-primary-container px-5 py-3 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={!builderCatalogReady}
              onClick={openBuilder}
              type="button"
            >
              {builderLoading ? "Loading Workspace Builder..." : "Create Your First Workspace"}
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
