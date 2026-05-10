import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CvExportPreview } from "../components/CvExportPreview";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { getApiErrorDetails, getApiErrorMessage } from "../lib/api";
import { buildWorkspacePreviewDocuments } from "../lib/cvStudio";
import { labelize } from "../lib/formatters";
import {
  deriveDefaultCities,
  getAllCountryOptions,
  getCountryByCode,
  hasCityDataset,
  loadCityOptions,
} from "../lib/locationOptions";

const DEFAULT_FLOW_ID = "tailored_documents";
const DEFAULT_CV_GENERATION_MODE = "aggressive_customization";
const CV_GENERATION_MODE_OPTIONS = [
  { value: "standard_cv", label: "Standard" },
  { value: "light_customization", label: "Light" },
  { value: "aggressive_customization", label: "Aggressive" },
];
const LIGHT_CUSTOMIZATION_EXTRA_PROMPT_FIELD = "light_customization_extra_prompt";
const LIGHT_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD = "light_customization_prompt_override";
const AGGRESSIVE_CUSTOMIZATION_EXTRA_PROMPT_FIELD = "aggressive_customization_extra_prompt";
const AGGRESSIVE_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD = "aggressive_customization_prompt_override";
const LEGACY_STAGE4_EXTRA_PROMPT_FIELD = "stage4_extra_prompt";
const LEGACY_STAGE4_PROMPT_OVERRIDE_FIELD = "stage4_prompt_override";
const SYSTEM_SETTING_KEYS = new Set([
  "automation_flow",
  "config_loader",
  "manual_sources_are_preapproved",
]);
const FIXED_TAILORED_MODULE_IDS = ["screening_filter", "tailored_document_generation"];
const OPTIONAL_PRIORITY_MODULE_ID = "priority_ranking";
const JOB_FILTERING_STRICT = "Strict Match";
const JOB_FILTERING_BROADER = "Broader Match";
const QUICK_APPLY_ROUTE = "/quick-apply";
const TARGETING_FIELD_DISPLAY_ORDER = ["keywords", "target_roles", "country_codes", "cities"];
const TARGETING_FIELD_FALLBACKS = {
  keywords: {
    id: "keywords",
    label: "Target Keywords",
    description: "Keywords the system should search for when discovering jobs.",
    type: "tag_list",
    compatible_flows: ["tailored_documents", "reusable_packages"],
    placeholder: "analyst, consultant, product manager",
    user_facing: true,
    frontend_visible: true,
    section: "targeting",
    sort_order: 20,
  },
  target_roles: {
    id: "target_roles",
    label: "Target Roles",
    description: "Add the roles this workspace should target. They shape search keywords and document emphasis.",
    type: "multi_select",
    compatible_flows: ["tailored_documents", "reusable_packages"],
    options: [
      { value: "Product Manager", label: "Product Manager" },
      { value: "Business Analyst", label: "Business Analyst" },
      { value: "Project Manager", label: "Project Manager" },
      { value: "Consultant", label: "Consultant" },
      { value: "Product Designer", label: "Product Designer" },
      { value: "Frontend Engineer", label: "Frontend Engineer" },
      { value: "Data Analyst", label: "Data Analyst" },
    ],
    user_facing: true,
    frontend_visible: true,
    section: "targeting",
    sort_order: 25,
  },
  country_codes: {
    id: "country_codes",
    label: "Target Country",
    description: "Choose the country this workspace should target.",
    type: "multi_select",
    compatible_flows: ["tailored_documents"],
    options: [],
    user_facing: true,
    frontend_visible: true,
    section: "targeting",
    sort_order: 30,
  },
  cities: {
    id: "cities",
    label: "Target City",
    description: "",
    type: "tag_list",
    compatible_flows: ["tailored_documents", "reusable_packages"],
    placeholder: "Berlin",
    user_facing: true,
    frontend_visible: true,
    section: "targeting",
    sort_order: 32,
  },
};
const EMPTY_ACTION_STATE = {
  workspaceId: "",
  loading: false,
  message: "",
  error: "",
  details: [],
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

function normalizeCountryCodeList(value, limit = 1) {
  const rawValues =
    Array.isArray(value)
      ? value
      : typeof value === "string"
        ? value.split(/[,\r\n]+/)
        : value === undefined || value === null
          ? []
          : [value];
  const codes = [];
  const seen = new Set();
  for (const rawValue of rawValues) {
    const normalized = String(rawValue || "").trim().toUpperCase();
    if (!normalized || seen.has(normalized)) {
      continue;
    }
    codes.push(normalized);
    seen.add(normalized);
    if (codes.length >= limit) {
      break;
    }
  }
  return codes;
}

function parseLineList(text) {
  return parseDelimitedList(text);
}

function buildSourceValidationPayload({ flowId, sourceIds, settings }) {
  return {
    flow_id: flowId,
    source_ids: [...(sourceIds || [])],
    settings: { ...(settings || {}) },
  };
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
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          setOpen((current) => !current);
        }}
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

function ChoiceCard({ checked, compact = false, title, description, info, onClick }) {
  return (
    <button
      className={[
        compact
          ? "rounded-xl border px-4 py-3 text-left transition-colors duration-150"
          : "rounded-xl border p-4 text-left transition-all",
        checked
          ? "border-primary/40 bg-primary/5 ring-2 ring-primary/10"
          : "border-outline-variant/20 bg-surface hover:border-primary/20 hover:bg-surface-container-low",
      ].join(" ")}
      onClick={onClick}
      type="button"
    >
      <div className={`flex justify-between gap-3 ${compact ? "items-center" : "items-start"}`}>
        <div>
          <div className="text-sm font-semibold text-on-surface">{title}</div>
          {description ? (
            <p className="mt-1 text-xs leading-6 text-on-surface-variant">{description}</p>
          ) : null}
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

function SuggestedSingleSelectInput({
  value,
  onChange,
  options = [],
  emptyLabel = "No city",
  helperText = "",
  inputDisabled = false,
  loading = false,
}) {
  const selectedValue = Array.isArray(value) ? String(value[0] || "") : String(value || "");
  const renderedOptions = useMemo(() => {
    const seen = new Set();
    const nextOptions = [];
    for (const option of [selectedValue, ...options]) {
      const normalizedOption = String(option || "").trim();
      const dedupeKey = normalizedOption.toLowerCase();
      if (!normalizedOption || seen.has(dedupeKey)) {
        continue;
      }
      nextOptions.push(normalizedOption);
      seen.add(dedupeKey);
    }
    return nextOptions;
  }, [options, selectedValue]);

  return (
    <div className="space-y-2">
      <select
        className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface disabled:cursor-not-allowed disabled:text-on-surface-variant"
        disabled={inputDisabled || loading || !renderedOptions.length}
        onChange={(event) => onChange(event.target.value ? [event.target.value] : [])}
        value={selectedValue}
      >
        <option value="">{loading ? "Loading cities..." : emptyLabel}</option>
        {renderedOptions.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      <div className="flex items-center justify-between gap-3 text-xs text-on-surface-variant">
        <span>{loading ? "Loading city suggestions..." : helperText}</span>
        <span>{selectedValue ? "1/1" : "0/1"}</span>
      </div>
    </div>
  );
}

function SuggestedTokenListInput({
  value,
  onChange,
  options = [],
  placeholder = "",
  maxItems = 1,
  helperText = "",
  inputDisabled = false,
  loading = false,
}) {
  const listId = useId();
  const tokens = useMemo(() => parseDelimitedList(value), [value]);
  const [draft, setDraft] = useState("");
  const normalizedOptionMap = useMemo(
    () =>
      new Map(
        options
          .map((option) => String(option || "").trim())
          .filter(Boolean)
          .map((option) => [option.toLowerCase(), option]),
      ),
    [options],
  );
  const filteredOptions = useMemo(() => {
    const normalizedDraft = draft.trim().toLowerCase();
    return normalizedDraft
      ? options.filter((option) => String(option || "").toLowerCase().includes(normalizedDraft))
      : options;
  }, [draft, options]);

  function commit(rawValue) {
    const normalizedValue = String(rawValue || "").trim().toLowerCase();
    const matchedOption = normalizedOptionMap.get(normalizedValue);
    if (!matchedOption) {
      setDraft("");
      return;
    }
    const nextTokens = parseDelimitedList([tokens, matchedOption]).slice(0, maxItems);
    onChange(nextTokens);
    setDraft("");
  }

  function removeToken(tokenToRemove) {
    onChange(tokens.filter((token) => token !== tokenToRemove));
  }

  const canAddMore = tokens.length < maxItems;

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
          {canAddMore ? (
            <>
              <input
                className="min-w-[16rem] flex-1 bg-transparent py-1 text-sm text-on-surface outline-none placeholder:text-on-surface-variant disabled:cursor-not-allowed disabled:text-on-surface-variant"
                disabled={inputDisabled || loading || !options.length}
                list={listId}
                onBlur={() => {
                  if (draft.trim()) {
                    commit(draft);
                  }
                }}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    if (draft.trim()) {
                      commit(draft);
                    }
                  }
                }}
                placeholder={placeholder}
                value={draft}
              />
              <datalist id={listId}>
                {filteredOptions.map((option) => (
                  <option key={`${listId}-${option}`} value={option} />
                ))}
              </datalist>
            </>
          ) : null}
        </div>
      </div>
      <div className="flex items-center justify-between gap-3 text-xs text-on-surface-variant">
        <span>{loading ? "Loading city suggestions..." : helperText}</span>
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
  if (field?.type === "select") {
    const selectedOption = (field.options || []).find(
      (option) => String(option.value) === String(value),
    );
    if (selectedOption) {
      return selectedOption.label;
    }
  }
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

function normalizeJobFilteringMode(value) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[_-]+/g, " ");
  return normalized === "strict match" ? JOB_FILTERING_STRICT : JOB_FILTERING_BROADER;
}

function cvGenerationModeDescription(mode) {
  if (mode === "standard_cv") {
    return "Reuses your saved workspace CV with no tailoring.";
  }
  if (mode === "light_customization") {
    return "Updates your summary and skills, while keeping most of your CV unchanged.";
  }
  return "Also rewrites experience bullets for a closer match, while keeping your core details unchanged.";
}

function cvGenerationModePromptFieldIds(mode) {
  if (mode === "light_customization") {
    return [
      LIGHT_CUSTOMIZATION_EXTRA_PROMPT_FIELD,
      LIGHT_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD,
    ];
  }
  if (mode === "aggressive_customization") {
    return [
      AGGRESSIVE_CUSTOMIZATION_EXTRA_PROMPT_FIELD,
      AGGRESSIVE_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD,
    ];
  }
  return [];
}

function promptFieldFallbackValue(settings, mode, fieldId) {
  const directValue = settings?.[fieldId];
  if (directValue !== undefined && directValue !== null && String(directValue) !== "") {
    return directValue;
  }
  if (mode === "aggressive_customization") {
    if (fieldId === AGGRESSIVE_CUSTOMIZATION_EXTRA_PROMPT_FIELD) {
      return settings?.[LEGACY_STAGE4_EXTRA_PROMPT_FIELD] || "";
    }
    if (fieldId === AGGRESSIVE_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD) {
      return settings?.[LEGACY_STAGE4_PROMPT_OVERRIDE_FIELD] || "";
    }
  }
  return "";
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
  if (Object.prototype.hasOwnProperty.call(settings, "country_codes")) {
    settings.country_codes = normalizeCountryCodeList(settings.country_codes, 1);
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
    const selectedValue = normalizeCountryCodeList(value, 1)[0] || "";
    return (
      <select
        className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
        onChange={(event) => onChange(event.target.value ? [event.target.value] : [])}
        value={selectedValue}
      >
        <option value="">Select a country</option>
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

  if (field.id === "cities") {
    const maxItems = formState?.flowId === "reusable_packages" ? 8 : 1;
    if (maxItems === 1) {
      return (
        <SuggestedSingleSelectInput
          emptyLabel="No city"
          helperText={dynamicOptions.city_helper_text || ""}
          inputDisabled={dynamicOptions.city_input_disabled === true}
          loading={dynamicOptions.city_loading === true}
          onChange={onChange}
          options={dynamicOptions.city_options || []}
          value={Array.isArray(value) ? value : parseDelimitedList(value)}
        />
      );
    }
    return (
      <SuggestedTokenListInput
        helperText={dynamicOptions.city_helper_text || ""}
        inputDisabled={dynamicOptions.city_input_disabled === true}
        loading={dynamicOptions.city_loading === true}
        maxItems={maxItems}
        onChange={onChange}
        options={dynamicOptions.city_options || []}
        placeholder={field.placeholder || ""}
        value={Array.isArray(value) ? value : parseDelimitedList(value)}
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
  const [cvUploadState, setCvUploadState] = useState({
    uploading: false,
    message: "",
    error: "",
  });
  const [cityOptionsState, setCityOptionsState] = useState({
    loading: false,
    options: [],
    selectedCountryCode: "",
    missingDataset: false,
  });
  const cityRequestRef = useRef(0);
  const cityScopeRef = useRef("");

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
  const { data: settingsPayload } = useApiResource(() => request("/settings"), [request]);
  const {
    data: cvAssetsPayload,
    refresh: refreshCvAssets,
  } = useApiResource(() => request("/documents?asset_kind=workspace_cv&limit=100"), [request]);

  const allCountryOptions = useMemo(() => getAllCountryOptions(), []);
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
  const cvGenerationModeField = useMemo(
    () =>
      (builderCatalog?.configuration_fields || []).find(
        (field) => field.id === "cv_generation_mode",
      ) || null,
    [builderCatalog?.configuration_fields],
  );
  const configurationFieldById = useMemo(
    () => new Map((builderCatalog?.configuration_fields || []).map((field) => [field.id, field])),
    [builderCatalog?.configuration_fields],
  );
  const cvGenerationModeOptions = cvGenerationModeField?.options?.length
    ? cvGenerationModeField.options
    : CV_GENERATION_MODE_OPTIONS;
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
          previewProfile: item.preview_profile || null,
        })),
    [cvAssetsPayload?.documents],
  );
  const workspaceCvAssetIds = useMemo(
    () => new Set(workspaceCvAssets.map((item) => item.value)),
    [workspaceCvAssets],
  );
  const selectedCountryCodes = useMemo(
    () => normalizeCountryCodeList(form.settings.country_codes, 1),
    [form.settings.country_codes],
  );
  const selectedCountryCodeForCity = selectedCountryCodes[0] || "";
  const selectedCountryForCity = useMemo(
    () => (selectedCountryCodeForCity ? getCountryByCode(selectedCountryCodeForCity) : null),
    [selectedCountryCodeForCity],
  );
  const cityHelperText = useMemo(() => {
    if (!selectedCountryCodes.length) {
      return "Select a target country first to enable city suggestions.";
    }
    const fallbackCityLabel = selectedCountryForCity?.capital || "the selected country capital";
    if (cityOptionsState.missingDataset) {
      return `No packaged city list is available for ${selectedCountryForCity?.label || "this country"} yet. Leave this blank and Runr will use ${fallbackCityLabel}.`;
    }
    if (!cityOptionsState.loading && !cityOptionsState.options.length) {
      return `No city suggestions loaded for ${selectedCountryForCity?.label || "this country"}. Leave this blank and Runr will use ${fallbackCityLabel}.`;
    }
    return "";
  }, [
    cityOptionsState.loading,
    cityOptionsState.missingDataset,
    cityOptionsState.options.length,
    selectedCountryCodes.length,
    selectedCountryForCity,
  ]);
  const dynamicFieldOptions = useMemo(
    () => ({
      all_country_options: allCountryOptions,
      city_options: cityOptionsState.options,
      city_loading: cityOptionsState.loading,
      city_input_disabled:
        !selectedCountryCodes.length ||
        cityOptionsState.missingDataset ||
        !cityOptionsState.options.length,
      city_helper_text: cityHelperText,
      workspace_cv_assets: workspaceCvAssets,
    }),
    [
      allCountryOptions,
      cityHelperText,
      cityOptionsState.loading,
      cityOptionsState.missingDataset,
      cityOptionsState.options,
      selectedCountryCodes.length,
      workspaceCvAssets,
    ],
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
  const targetingSection =
    builderSections.find((section) => section.id === "targeting") ||
    builderCatalog?.builder_sections?.find((section) => section.id === "targeting") ||
    null;
  const targetingFields = useMemo(
    () =>
      TARGETING_FIELD_DISPLAY_ORDER
        .map((fieldId) => {
          const fieldDefinition = configurationFieldById.get(fieldId);
          if (
            fieldDefinition &&
            fieldDefinition.user_facing !== false &&
            fieldDefinition.frontend_visible !== false &&
            (fieldDefinition.compatible_flows || []).includes(form.flowId)
          ) {
            return fieldDefinition;
          }
          const fallbackField = TARGETING_FIELD_FALLBACKS[fieldId];
          if (
            fallbackField &&
            fallbackField.user_facing !== false &&
            fallbackField.frontend_visible !== false &&
            (fallbackField.compatible_flows || []).includes(form.flowId)
          ) {
            return fallbackField;
          }
          return null;
        })
        .filter(Boolean),
    [configurationFieldById, form.flowId],
  );
  const visibleBuilderSections = builderSections.filter(
    (section) => section.id !== "sources" && section.id !== "targeting",
  );
  const selectedLegacySource = legacySources.find((source) => form.sourceIds.includes(source.id)) || null;
  const selectedSource =
    availableSources.find((source) => form.sourceIds.includes(source.id)) || selectedLegacySource || null;
  const priorityRankingEnabled = resolvedModuleIds.includes(OPTIONAL_PRIORITY_MODULE_ID);
  const resolvedCvGenerationMode = String(
    form.settings.cv_generation_mode ||
      cvGenerationModeField?.default ||
      DEFAULT_CV_GENERATION_MODE,
  );
  const activeCvPromptFields = useMemo(
    () =>
      cvGenerationModePromptFieldIds(resolvedCvGenerationMode)
        .map((fieldId) => configurationFieldById.get(fieldId))
        .filter(Boolean),
    [configurationFieldById, resolvedCvGenerationMode],
  );
  const jobFilteringMode = normalizeJobFilteringMode(form.settings.job_filtering_mode);
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
  const selectedWorkspaceCvAsset = useMemo(() => {
    const selectedAssetId = String(form.settings.workspace_cv_asset_id || "").trim();
    if (!selectedAssetId) {
      return null;
    }
    return workspaceCvAssets.find((item) => item.value === selectedAssetId) || null;
  }, [form.settings.workspace_cv_asset_id, workspaceCvAssets]);
  const sharedDocumentDefaults = settingsPayload?.documents || {};
  const mergedPreviewProfile = useMemo(() => {
    if (!selectedWorkspaceCvAsset) {
      return null;
    }
    const sharedProfile = settingsPayload?.profile || {};
    const previewProfile = selectedWorkspaceCvAsset.previewProfile || {};
    return {
      ...sharedProfile,
      ...previewProfile,
      photo_data_url:
        previewProfile.photo_data_url ||
        sharedProfile.photo_data_url ||
        sharedProfile.avatar_url ||
        "",
      avatar_url:
        previewProfile.avatar_url ||
        sharedProfile.avatar_url ||
        sharedProfile.photo_data_url ||
        "",
    };
  }, [selectedWorkspaceCvAsset, settingsPayload?.profile]);
  const effectiveDocumentPreviewDocuments = useMemo(
    () => buildWorkspacePreviewDocuments(sharedDocumentDefaults, form.settings),
    [form.settings, sharedDocumentDefaults],
  );
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
    return "";
  }, [
    form.name,
    form.settings.workspace_cv_asset_id,
    form.sourceIds.length,
    resolvedModuleIds.length,
    selectedWorkspaceCvMissing,
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
    cityScopeRef.current = "";
    setCityOptionsState({ loading: false, options: [], selectedCountryCode: "", missingDataset: false });
    setForm(buildBuilderForm(builderCatalog, defaultFlowId));
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
    cityScopeRef.current = "";
    setCityOptionsState({ loading: false, options: [], selectedCountryCode: "", missingDataset: false });
    setForm(hydrateFormFromWorkspace(workspace, builderCatalog));
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
    setCvUploadState({ uploading: false, message: "", error: "" });
    cityScopeRef.current = "";
    setCityOptionsState({ loading: false, options: [], selectedCountryCode: "", missingDataset: false });
    clearBuilderSearchParams();
  }

  function updateForm(patch) {
    setForm((current) => ({ ...current, ...patch }));
  }

  function updateSetting(fieldId, value) {
    const nextValue =
      fieldId === "country_codes" ? normalizeCountryCodeList(value, 1) : value;
    setForm((current) => ({
      ...current,
      settings: {
        ...current.settings,
        [fieldId]: nextValue,
      },
    }));
  }

  function selectSingleSource(sourceId) {
    setForm((current) => {
      const nextSourceIds =
        current.sourceIds.length === 1 && current.sourceIds[0] === sourceId ? [] : [sourceId];
      return { ...current, sourceIds: nextSourceIds };
    });
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

  function settingsWithDerivedLocationDefaults(settings, sourceIds) {
    const nextSettings = { ...(settings || {}) };
    nextSettings.country_codes = normalizeCountryCodeList(nextSettings.country_codes, 1);
    const selectedSourceIds = Array.isArray(sourceIds) ? sourceIds : [];
    const configuredCities = Array.isArray(nextSettings.cities)
      ? nextSettings.cities.filter((item) => String(item || "").trim())
      : parseDelimitedList(nextSettings.cities);
    if (!selectedSourceIds.includes("job_board_collection") || configuredCities.length) {
      return nextSettings;
    }
    const derivedCities = deriveDefaultCities(nextSettings.country_codes, 8);
    if (derivedCities.length) {
      nextSettings.cities = derivedCities;
    }
    return nextSettings;
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
          settings: settingsWithDerivedLocationDefaults(form.settings, form.sourceIds),
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
    if (!builderState.open) {
      return;
    }
    const nextScopeKey = selectedCountryCodes.join(",");
    if (!cityScopeRef.current) {
      cityScopeRef.current = nextScopeKey;
      return;
    }
    if (cityScopeRef.current === nextScopeKey) {
      return;
    }
    cityScopeRef.current = nextScopeKey;
    if (parseDelimitedList(form.settings.cities).length) {
      updateSetting("cities", []);
    }
  }, [builderState.open, form.settings.cities, selectedCountryCodes]);

  useEffect(() => {
    if (!builderState.open || !selectedCountryCodeForCity) {
      setCityOptionsState({
        loading: false,
        options: [],
        selectedCountryCode: selectedCountryCodeForCity,
        missingDataset: false,
      });
      return;
    }
    if (!hasCityDataset(selectedCountryCodeForCity)) {
      setCityOptionsState({
        loading: false,
        options: [],
        selectedCountryCode: selectedCountryCodeForCity,
        missingDataset: true,
      });
      return;
    }

    const requestId = cityRequestRef.current + 1;
    cityRequestRef.current = requestId;
    setCityOptionsState({
      loading: true,
      options: [],
      selectedCountryCode: selectedCountryCodeForCity,
      missingDataset: false,
    });

    loadCityOptions(selectedCountryCodeForCity)
      .then((options) => {
        if (cityRequestRef.current !== requestId) {
          return;
        }
        setCityOptionsState({
          loading: false,
          options,
          selectedCountryCode: selectedCountryCodeForCity,
          missingDataset: false,
        });
      })
      .catch(() => {
        if (cityRequestRef.current !== requestId) {
          return;
        }
        setCityOptionsState({
          loading: false,
          options: [],
          selectedCountryCode: selectedCountryCodeForCity,
          missingDataset: true,
        });
      });
  }, [builderState.open, selectedCountryCodeForCity]);

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
    const sourceIds = workspaceSourceIds(workspace, builderCatalog, flowId);
    return buildSourceValidationPayload({
      flowId,
      sourceIds,
      settings: settingsWithDerivedLocationDefaults(workspace.settings || {}, sourceIds),
    });
  }

  async function triggerRun(workspaceId, runInputOverrides = {}) {
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
      message: "Checking workspace setup before starting the run...",
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
          error: "Run blocked until the workspace source setup is fixed.",
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
          execution_mode: "queued",
          max_attempts: 1,
          run_input_overrides: runInputOverrides,
        },
      });
      setActionState({
        ...EMPTY_ACTION_STATE,
        workspaceId,
        message: `Run ${run.id} added to the queue and will start automatically.`,
      });
      await refresh();
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
    const confirmed = window.confirm(
      "Delete this workspace? Existing runs stay in the system until you delete them separately.",
    );
    if (!confirmed) {
      return;
    }
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
      <div className="w-full max-w-6xl overflow-hidden rounded-xl border border-outline-variant/20 bg-surface-container-lowest shadow-soft">
        <div className="hidden border-b border-outline-variant/10 bg-surface-container-low px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant md:grid md:grid-cols-[minmax(0,1fr)_auto] md:items-center md:gap-6">
          <div>Workspace</div>
          <div>Actions</div>
        </div>

        <div className="divide-y divide-outline-variant/10">
          {workspaces.map((workspace) => {
            const workspaceActionPending = actionState.workspaceId === workspace.id && actionState.loading;
            return (
              <article
                className="grid gap-4 px-4 py-5 transition-colors hover:bg-surface-container-low md:grid-cols-[minmax(0,1fr)_auto] md:items-start md:gap-6"
                key={workspace.id}
              >
                <div className="min-w-0">
                  <h2 className="font-headline text-lg font-bold leading-tight text-on-surface break-words">
                    {workspace.name}
                  </h2>
                  <p className="mt-2 max-w-2xl line-clamp-2 text-sm leading-6 text-on-surface-variant break-words">
                    {workspace.description || "No description provided."}
                  </p>
                </div>

                <div className="flex flex-wrap gap-2">
                  <button
                    className="inline-flex min-w-[6.5rem] items-center justify-center rounded-lg bg-gradient-to-br from-primary to-primary-container px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90"
                    onClick={() => focusWorkspace(workspace.id)}
                    type="button"
                  >
                    Open
                  </button>
                  <button
                    className="inline-flex min-w-[6.5rem] items-center justify-center rounded-lg border border-outline-variant/20 bg-surface px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-low disabled:cursor-not-allowed disabled:opacity-60"
                    disabled={workspaceActionPending}
                    onClick={() => triggerRun(workspace.id)}
                    type="button"
                  >
                    Run
                  </button>
                </div>

                <div className="md:col-span-2">{renderActionFeedback(workspace)}</div>
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
              <h2 className="font-headline text-2xl font-bold text-on-surface">{workspace.name}</h2>
              <p className="mt-2 max-w-3xl text-sm leading-7 text-on-surface-variant">
                {workspace.description || "No description provided."}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={workspaceActionPending}
                onClick={() => triggerRun(workspace.id)}
                type="button"
              >
                Run
              </button>
              <Link
                className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                to={`${QUICK_APPLY_ROUTE}?workspace_id=${workspace.id}`}
              >
                Quick Apply
              </Link>
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
            {builderLoading ? "Loading Workspace Builder..." : "Create Workspace"}
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
        <div className="space-y-6">
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
                  workspace section, so review the settings below and the related run details together.
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

            {targetingFields.length ? (
              <BuilderSection
                description={
                  targetingSection?.description ||
                  "Set the target roles, keywords, countries, and optional city that define what this workspace should pursue."
                }
                emphasized={focusedSectionId === "targeting"}
                id="workspace-builder-targeting"
                title={targetingSection?.title || "Targeting"}
              >
                <div className="grid gap-4 md:grid-cols-2">
                  {targetingFields.map((field) => (
                    <label className="space-y-2" key={field.id}>
                      <span className="block text-sm font-semibold text-on-surface">{field.label}</span>
                      <FieldRenderer
                        dynamicOptions={dynamicFieldOptions}
                        field={field}
                        formState={form}
                        onChange={(nextValue) => updateSetting(field.id, nextValue)}
                        value={form.settings[field.id]}
                      />
                      {field.description ? (
                        <span className="block text-xs leading-6 text-on-surface-variant">
                          {field.description}
                        </span>
                      ) : null}
                    </label>
                  ))}
                </div>
              </BuilderSection>
            ) : null}

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
                              ? "Choose from major global job boards here. Regional boards appear automatically after you select your target country."
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

            </BuilderSection>

            <BuilderSection
              description="Screening stays on in the background. Priority ranking is optional. Tailored CV generation is part of this workflow. Motivation letters are not included."
              title="Automation Options"
            >
              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-xl border border-outline-variant/10 bg-surface p-4">
                  <div className="flex items-center gap-2">
                    <div className="text-sm font-semibold text-on-surface">Job Filtering</div>
                    <InfoHint content="Strict Match: close title matches only. Broader Match: includes related titles too." />
                  </div>
                  <p className="mt-1 text-xs leading-6 text-on-surface-variant">
                    Choose how strict the initial job match should be.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <TogglePill
                      checked={jobFilteringMode === JOB_FILTERING_STRICT}
                      label={JOB_FILTERING_STRICT}
                      onClick={() => updateSetting("job_filtering_mode", JOB_FILTERING_STRICT)}
                    />
                    <TogglePill
                      checked={jobFilteringMode === JOB_FILTERING_BROADER}
                      label={JOB_FILTERING_BROADER}
                      onClick={() => updateSetting("job_filtering_mode", JOB_FILTERING_BROADER)}
                    />
                  </div>
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
                  <div className="flex items-center gap-2">
                    <div className="text-sm font-semibold text-on-surface">CV Generation Mode</div>
                    <InfoHint
                      content={
                        <div className="space-y-1">
                          <div>Standard: Apply with uploaded CV.</div>
                          <div>Light: Apply with tailored professional summary and skills.</div>
                          <div>
                            Aggressive: Apply with the second option plus all bullet points under
                            work experience and project sections.
                          </div>
                        </div>
                      }
                    />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {cvGenerationModeOptions.map((option) => {
                      const modeValue = String(option.value);
                      return (
                        <TogglePill
                          checked={resolvedCvGenerationMode === modeValue}
                          key={modeValue}
                          onClick={() => updateSetting("cv_generation_mode", modeValue)}
                          label={option.label}
                        />
                      );
                    })}
                  </div>
                </div>
              </div>
              <details className="mt-4 rounded-xl border border-outline-variant/10 bg-surface p-4">
                <summary className="cursor-pointer text-sm font-semibold text-on-surface">
                  Advanced Prompt Controls - Optional
                </summary>
                <p className="mt-2 text-xs leading-6 text-on-surface-variant">
                  Optional mode-specific prompt tuning. Most users can leave this closed.
                </p>
                {activeCvPromptFields.length ? (
                  <div className="mt-4 grid gap-4 md:grid-cols-2">
                    {activeCvPromptFields.map((field) => (
                      <label className="space-y-2" key={field.id}>
                        <span className="block text-sm font-semibold text-on-surface">{field.label}</span>
                        <FieldRenderer
                          dynamicOptions={dynamicFieldOptions}
                          field={field}
                          formState={form}
                          onChange={(nextValue) => updateSetting(field.id, nextValue)}
                          value={promptFieldFallbackValue(form.settings, resolvedCvGenerationMode, field.id)}
                        />
                        <span className="block text-xs leading-6 text-on-surface-variant">
                          {field.description}
                        </span>
                      </label>
                    ))}
                  </div>
                ) : (
                  <div className="mt-4 text-sm text-on-surface-variant">
                    Standard mode has no extra prompt controls.
                  </div>
                )}
              </details>
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
                    <div className="grid gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(320px,1.1fr)]">
                      <div className="space-y-4">
                        <div className="rounded-lg border border-outline-variant/10 bg-surface p-4">
                          <p className="text-sm font-semibold text-on-surface">Workspace-specific style</p>
                          <p className="mt-1 text-xs leading-6 text-on-surface-variant">
                            Blank values inherit your shared document defaults. The live preview uses
                            the selected baseline CV inside this workspace, so you can validate style
                            changes without leaving the Workspaces page.
                          </p>
                        </div>

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

                        <div className="rounded-lg border border-outline-variant/10 bg-surface px-4 py-3 text-xs leading-6 text-on-surface-variant">
                          Active export mapping: {labelize(effectiveDocumentPreviewDocuments.cv_template)},
                          {" "}
                          {labelize(effectiveDocumentPreviewDocuments.cv_color_scheme)},{" "}
                          {effectiveDocumentPreviewDocuments.cv_font || "Calibri"},{" "}
                          with {effectiveDocumentPreviewDocuments.include_photo ? "photo enabled" : "no photo"}.
                        </div>
                      </div>

                      <div className="space-y-3">
                        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                          <div>
                            <div className="text-sm font-semibold text-on-surface">Live Export Preview</div>
                            <p className="text-xs leading-6 text-on-surface-variant">
                              Uses the selected workspace baseline CV content with the active DOCX
                              template, palette, font, and photo settings.
                            </p>
                          </div>
                          {selectedWorkspaceCvAsset ? (
                            <span className="rounded-full bg-surface-container-low px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-on-surface-variant">
                              {selectedWorkspaceCvAsset.label}
                            </span>
                          ) : null}
                        </div>

                        {!form.settings.workspace_cv_asset_id ? (
                          <div className="rounded-xl border border-dashed border-outline-variant/20 bg-surface p-6 text-sm text-on-surface-variant">
                            Choose a baseline CV in the Baseline CV section to load the workspace preview.
                          </div>
                        ) : selectedWorkspaceCvMissing ? (
                          <div className="rounded-xl border border-error/30 bg-error/5 p-6 text-sm text-error">
                            The selected baseline CV is no longer available. Choose another workspace
                            CV to restore the preview.
                          </div>
                        ) : mergedPreviewProfile ? (
                          <div className="rounded-2xl border border-outline-variant/15 bg-surface p-3">
                            <CvExportPreview
                              className="min-h-[760px]"
                              documents={effectiveDocumentPreviewDocuments}
                              options={settingsPayload?.options || {}}
                              profile={mergedPreviewProfile}
                            />
                          </div>
                        ) : (
                          <div className="rounded-xl border border-outline-variant/10 bg-surface p-6 text-sm text-on-surface-variant">
                            Loading preview...
                          </div>
                        )}

                        <p className="text-xs leading-6 text-on-surface-variant">
                          This preview follows the export-template styling rather than the browser CV
                          studio. Generated DOCX and PDF artifacts use the same workspace template,
                          color scheme, font, and photo selection.
                        </p>
                      </div>
                    </div>
                  ) : section.id === "cv_binding" ? (
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
          <div className="space-y-3 rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6">
            {saveBlockedReason ? (
              <div className="rounded-lg border border-outline-variant/10 bg-surface px-4 py-3 text-sm text-on-surface-variant">
                {saveBlockedReason}
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
