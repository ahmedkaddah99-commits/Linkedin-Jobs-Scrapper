import { labelize } from "../../lib/formatters";
import { formatDateTime } from "./workspaceFormatters";

const CV_SECTION_DECISION_OPTIONS = [
  { value: "keep", label: "Keep section" },
  { value: "hide", label: "Hide" },
  { value: "map:summary", label: "Map to summary" },
  { value: "map:skills", label: "Map to skills" },
  { value: "map:experience", label: "Map to experience" },
  { value: "map:projects", label: "Map to projects" },
  { value: "map:education", label: "Map to education" },
  { value: "map:languages", label: "Map to languages" },
];

function sectionDecisionValue(section = {}) {
  const action = String(section.action || "keep").trim().toLowerCase();
  const target = String(section.target_section || "").trim().toLowerCase();
  if (action === "hide") {
    return "hide";
  }
  if (action === "map" && target) {
    return `map:${target}`;
  }
  return "keep";
}

function decisionFromValue(section = {}, value = "keep") {
  const normalizedValue = String(value || "keep").trim().toLowerCase();
  const [action, target = ""] = normalizedValue.split(":");
  return {
    section_id: String(section.section_id || section.id || "").trim(),
    heading: String(section.heading || section.title || "").trim(),
    action: action === "hide" || action === "map" ? action : "keep",
    target_section: action === "map" ? target : "",
  };
}

export function buildNextSectionDecisions(sections = [], section = {}, value = "keep") {
  const changedSectionId = String(section.section_id || section.id || "").trim();
  const changedHeading = String(section.heading || section.title || "").trim().toLowerCase();
  const decisions = sections
    .map((item) => decisionFromValue(item, sectionDecisionValue(item)))
    .filter((item) => {
      const itemSectionId = String(item.section_id || "").trim();
      const itemHeading = String(item.heading || "").trim().toLowerCase();
      if (changedSectionId && itemSectionId === changedSectionId) {
        return false;
      }
      if (!changedSectionId && changedHeading && itemHeading === changedHeading) {
        return false;
      }
      return true;
    });
  decisions.push(decisionFromValue(section, value));
  return decisions;
}

function CustomSectionMappingPanel({ sections = [], savingKey = "", message = "", error = "", onChange }) {
  const visibleSections = Array.isArray(sections) ? sections : [];
  if (!visibleSections.length) {
    return null;
  }
  return (
    <div className="rounded-lg border border-outline-variant/10 bg-surface p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-on-surface">Detected CV sections</p>
          <p className="mt-1 text-xs leading-6 text-on-surface-variant">
            {visibleSections.length} custom section{visibleSections.length === 1 ? "" : "s"}
          </p>
        </div>
        {savingKey ? (
          <span className="rounded-full bg-surface-container-low px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-on-surface-variant">
            Saving
          </span>
        ) : null}
      </div>
      <div className="mt-4 space-y-3">
        {visibleSections.map((section) => {
          const sectionId = String(section.section_id || section.id || section.heading || "").trim();
          const lines = Array.isArray(section.lines)
            ? section.lines
            : String(section.content || "")
                .split(/\r?\n/)
                .map((line) => line.trim())
                .filter(Boolean);
          return (
            <div
              className="grid gap-3 rounded-lg border border-outline-variant/10 bg-surface-container-lowest p-3 md:grid-cols-[minmax(0,1fr)_180px]"
              key={sectionId}
            >
              <div className="min-w-0">
                <div className="text-sm font-semibold text-on-surface">
                  {section.heading || "Additional Information"}
                </div>
                {lines.length ? (
                  <div className="mt-1 line-clamp-2 text-xs leading-5 text-on-surface-variant">
                    {lines.slice(0, 2).join(" | ")}
                  </div>
                ) : null}
              </div>
              <select
                className="h-10 w-full rounded-lg border border-outline-variant/20 bg-surface px-3 text-sm text-on-surface"
                disabled={savingKey === sectionId}
                onChange={(event) => onChange(section, event.target.value)}
                value={sectionDecisionValue(section)}
              >
                {CV_SECTION_DECISION_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          );
        })}
      </div>
      {message ? <p className="mt-3 text-sm text-primary">{message}</p> : null}
      {error ? <p className="mt-3 text-sm text-error">{error}</p> : null}
    </div>
  );
}

function requiredLabel(field) {
  return field?.required ? `${field.label} *` : field?.label;
}

export function WorkspaceCvBindingSection({
  FieldRenderer,
  cvUploadState,
  dynamicOptions,
  fields,
  form,
  resolvePath,
  sectionDecisionState,
  selectedCvCustomSections,
  selectedWorkspaceCvAsset,
  showSectionMapping = true,
  showSelectedDetails = true,
  updateCvSectionDecision,
  updateSetting,
  uploadWorkspaceCv,
}) {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        {fields.map((field) => (
          <label className="space-y-2" key={field.id}>
            <span className="block text-sm font-semibold text-on-surface">{requiredLabel(field)}</span>
            <FieldRenderer
              dynamicOptions={dynamicOptions}
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
              Uploading here also adds the CV to the shared Career Assets library.
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
      {showSelectedDetails && selectedWorkspaceCvAsset ? (
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
      {showSectionMapping && selectedWorkspaceCvAsset ? (
        <CustomSectionMappingPanel
          error={sectionDecisionState.error}
          message={sectionDecisionState.message}
          onChange={updateCvSectionDecision}
          savingKey={sectionDecisionState.savingKey}
          sections={selectedCvCustomSections}
        />
      ) : null}
    </div>
  );
}
