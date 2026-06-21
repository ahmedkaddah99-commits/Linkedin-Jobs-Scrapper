import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { PROFILE_PLACEHOLDER_URL } from "../components/CvExportPreview";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import {
  CV_STUDIO_ROUTE,
  WEB_CV_COLOR_FIELDS,
  WEB_CV_COLOR_PRESETS,
  WEB_CV_TEMPLATES,
  buildCvStudioHtml,
  buildCvStudioState,
  buildWorkspacePreviewState,
  matchPresetByPalette,
  stashCvStudioSeed,
} from "../lib/cvStudio";

const settingsTabs = [
  "Profile",
  "Defaults",
  "Document Defaults",
  "Account",
];

const usageLabels = {
  runs_per_month: "Runs",
  applications_per_month: "Applications",
  cv_exports_per_month: "CV exports",
  referral_drafts_per_month: "Referral drafts",
  runner_credits_per_month: "Runner credits",
  workspaces: "Workspaces",
};

function formatUsageLimit(limit) {
  return Number(limit) === -1 ? "Unlimited" : String(limit ?? 0);
}

function formatDateTime(value) {
  const normalizedValue = String(value || "").trim();
  if (!normalizedValue) return "Not available";
  const parsed = new Date(normalizedValue);
  if (Number.isNaN(parsed.getTime())) return normalizedValue;
  return parsed.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function UsageMetric({ label, quota }) {
  const used = Number(quota?.used || 0);
  const limit = Number(quota?.limit ?? 0);
  const isUnlimited = Boolean(quota?.is_unlimited) || limit === -1;
  const width = isUnlimited
    ? 24
    : Math.max(8, Math.min(100, (used / Math.max(1, limit)) * 100));

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-4 text-sm">
        <span className="font-medium text-on-surface">{label}</span>
        <span className="text-on-surface-variant">
          {used} / {formatUsageLimit(limit)}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface-container-high">
        <div
          className="h-full rounded-full bg-primary"
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

async function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Unable to read selected image."));
    reader.readAsDataURL(file);
  });
}

async function loadImageElement(src) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Unable to load selected image."));
    image.src = src;
  });
}

async function cropImageToSquare(file) {
  const dataUrl = await readFileAsDataUrl(file);
  const image = await loadImageElement(dataUrl);
  const size = Math.min(image.width, image.height);
  const startX = Math.floor((image.width - size) / 2);
  const startY = Math.floor((image.height - size) / 2);
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const context = canvas.getContext("2d");
  context.drawImage(image, startX, startY, size, size, 0, 0, 512, 512);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png", 0.95));
  if (!blob) {
    throw new Error("Unable to prepare cropped image.");
  }
  const outputFileName = file.name.replace(/\.[^.]+$/, "") || "profile-photo";
  return new File([blob], `${outputFileName}.png`, { type: "image/png" });
}

function mergeUploadedProfile(currentProfile = {}, parsedProfile = {}) {
  const nextProfile = { ...(currentProfile || {}) };
  const scalarFields = [
    "name",
    "role_title",
    "industry",
    "email",
    "location",
    "website",
    "linkedin_url",
    "github_url",
    "summary",
  ];

  scalarFields.forEach((field) => {
    const value = String(parsedProfile?.[field] || "").trim();
    if (value) {
      nextProfile[field] = value;
    }
  });

  ["competencies", "languages", "recent_experience", "education", "projects", "custom_sections"].forEach((field) => {
    if (Array.isArray(parsedProfile?.[field]) && parsedProfile[field].length) {
      nextProfile[field] = parsedProfile[field];
    }
  });

  return nextProfile;
}

function getProfilePhotoSrc(profile = {}) {
  return profile.photo_data_url || profile.avatar_url || PROFILE_PLACEHOLDER_URL;
}

function sanitizeHexInput(value) {
  return String(value || "")
    .replace(/[^0-9a-fA-F]/g, "")
    .slice(0, 6)
    .toUpperCase();
}

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
    onChange([...(items || []), { title: "", company: "", period: "", bulletsText: "" }]);
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
          <div className="mt-4">
            <TextArea
              onChange={(event) => updateItem(index, "bulletsText", event.target.value)}
              placeholder={"One bullet per line\nKeep the wording factual to the source CV"}
              value={item.bulletsText || ""}
            />
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

function EducationEditor({ items, onChange }) {
  function updateItem(index, field, value) {
    const nextItems = items.map((item, itemIndex) =>
      itemIndex === index ? { ...item, [field]: value } : item,
    );
    onChange(nextItems);
  }

  function addItem() {
    onChange([...(items || []), { degree_title: "", institution: "", period: "", detailsText: "" }]);
  }

  function removeItem(index) {
    onChange(items.filter((_, itemIndex) => itemIndex !== index));
  }

  return (
    <div className="space-y-4">
      {(items || []).map((item, index) => (
        <div
          key={`${item.degree_title || item.institution || "education"}-${index}`}
          className="rounded-lg border border-outline-variant/10 bg-surface p-4"
        >
          <div className="grid gap-4 md:grid-cols-3">
            <TextInput
              onChange={(event) => updateItem(index, "degree_title", event.target.value)}
              placeholder="Degree or certificate"
              value={item.degree_title || ""}
            />
            <TextInput
              onChange={(event) => updateItem(index, "institution", event.target.value)}
              placeholder="Institution"
              value={item.institution || ""}
            />
            <div className="flex gap-3">
              <TextInput
                className="flex-1"
                onChange={(event) => updateItem(index, "period", event.target.value)}
                placeholder="2019 - 2022"
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
          <div className="mt-4">
            <TextArea
              onChange={(event) => updateItem(index, "detailsText", event.target.value)}
              placeholder={"Optional details, thesis, or certificate notes\nOne line per detail"}
              value={item.detailsText || ""}
            />
          </div>
        </div>
      ))}
      <button
        className="rounded-lg bg-surface-container-low px-4 py-2.5 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
        onClick={addItem}
        type="button"
      >
        Add Education
      </button>
    </div>
  );
}

function ProfileTab({ draft, updateSection }) {
  const profile = draft.profile;
  const competenciesText = (profile.competencies || []).join("\n");
  const languagesText = (profile.languages || []).join("\n");

  return (
    <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8">
      <div className="space-y-6">
        <div className="grid gap-6 md:grid-cols-2">
          <SectionField label={<>Full Name <span className="text-error">*</span></>}>
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

        <div className="max-w-xl">
          <SectionField label="Industry">
            <TextInput
              onChange={(event) => updateSection("profile", { industry: event.target.value })}
              placeholder="Fintech"
              value={profile.industry || ""}
            />
          </SectionField>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          <SectionField label={<>Email <span className="text-error">*</span></>}>
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

        <div className="grid gap-6 md:grid-cols-2">
          <SectionField label="LinkedIn URL" hint="Used when generating application documents.">
            <div className="relative">
              <span className="material-symbols-outlined absolute left-3 top-3 text-[18px] text-on-surface-variant">link</span>
              <TextInput
                className="pl-10"
                onChange={(event) => updateSection("profile", { linkedin_url: event.target.value })}
                placeholder="https://linkedin.com/in/yourname"
                value={profile.linkedin_url || ""}
              />
            </div>
          </SectionField>
          <SectionField label="GitHub URL" hint="Embedded as a clickable link in your CV.">
            <div className="relative">
              <span className="material-symbols-outlined absolute left-3 top-3 text-[18px] text-on-surface-variant">code</span>
              <TextInput
                className="pl-10"
                onChange={(event) => updateSection("profile", { github_url: event.target.value })}
                placeholder="https://github.com/yourusername"
                value={profile.github_url || ""}
              />
            </div>
          </SectionField>
        </div>

        <SectionField label="Avatar URL" hint="Used by the frontend card view.">
          <TextInput
            onChange={(event) => updateSection("profile", { avatar_url: event.target.value })}
            value={profile.avatar_url || ""}
          />
        </SectionField>

        <SectionField
          label={<>Professional Summary <span className="text-error">*</span></>}
          hint="This is used both in your profile card and as context for AI document generation."
        >
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

        <SectionField
          label="Languages"
          hint="One language per line, e.g. German - B2. Used in CV generation and job language filtering."
        >
          <TextArea
            onChange={(event) =>
              updateSection("profile", {
                languages: event.target.value
                  .split("\n")
                  .map((item) => item.trim())
                  .filter(Boolean),
              })
            }
            value={languagesText}
          />
        </SectionField>

        <div>
          <div className="mb-2 text-sm font-semibold text-on-surface">Recent Experience</div>
          <ExperienceEditor
            items={profile.recent_experience || []}
            onChange={(value) => updateSection("profile", { recent_experience: value })}
          />
        </div>

        <div>
          <div className="mb-2 text-sm font-semibold text-on-surface">Education And Certificates</div>
          <EducationEditor
            items={profile.education || []}
            onChange={(value) => updateSection("profile", { education: value })}
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

function TemplateCard({ template, selected, onSelect }) {
  return (
    <button
      className={[
        "rounded-xl border p-4 text-left transition-all",
        selected
          ? "border-primary bg-primary/10 shadow-soft"
          : "border-outline-variant/20 bg-surface hover:border-primary/30 hover:bg-surface-container-low",
      ].join(" ")}
      onClick={onSelect}
      type="button"
    >
      <div className="mb-3 h-28 rounded-lg border border-outline-variant/10 bg-surface-container-low p-3">
        <div className="mb-2 h-3 w-20 rounded-full bg-primary/50" />
        <div className="mb-3 h-1.5 w-full rounded-full bg-outline-variant/30" />
        <div className="space-y-2">
          <div className="h-2 w-full rounded-full bg-outline-variant/20" />
          <div className="h-2 w-4/5 rounded-full bg-outline-variant/20" />
          <div className="h-2 w-5/6 rounded-full bg-outline-variant/20" />
        </div>
      </div>
      <div className="text-sm font-semibold text-on-surface">{template.label}</div>
      <div className="mt-1 text-xs leading-6 text-on-surface-variant">{template.description}</div>
    </button>
  );
}

function ColorSchemeButton({ scheme, selected, onSelect }) {
  return (
    <button
      className={[
        "flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition-all",
        selected
          ? "border-primary bg-primary/10 shadow-soft"
          : "border-outline-variant/20 bg-surface hover:border-primary/30 hover:bg-surface-container-low",
      ].join(" ")}
      onClick={onSelect}
      type="button"
    >
      <div className="flex items-center gap-2">
        <span className="h-5 w-5 rounded-full border border-black/10" style={{ backgroundColor: `#${scheme.primary}` }} />
        <span className="h-5 w-5 rounded-full border border-black/10" style={{ backgroundColor: `#${scheme.accent}` }} />
        <span className="h-5 w-5 rounded-full border border-black/10" style={{ backgroundColor: `#${scheme.surface}` }} />
      </div>
      <div>
        <div className="text-sm font-semibold text-on-surface">{scheme.label}</div>
        <div className="text-xs text-on-surface-variant">Primary, accent, and surface tones</div>
      </div>
    </button>
  );
}

function WebTemplateCard({ template, selected, onSelect }) {
  return (
    <button
      className={[
        "rounded-xl border p-4 text-left transition-all",
        selected
          ? "border-primary bg-primary/10 shadow-soft"
          : "border-outline-variant/20 bg-surface hover:border-primary/30 hover:bg-surface-container-low",
      ].join(" ")}
      onClick={onSelect}
      type="button"
    >
      <div className="mb-3 flex items-center justify-between gap-3 rounded-lg border border-outline-variant/10 bg-surface-container-low p-3">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-[0.18em] text-primary/80">
            {template.shortLabel}
          </div>
          <div className="mt-2 text-sm font-semibold text-on-surface">{template.label}</div>
        </div>
        <div className="rounded-full bg-primary/10 px-3 py-1 text-[11px] font-semibold text-primary">
          HTML
        </div>
      </div>
      <div className="text-xs leading-6 text-on-surface-variant">{template.description}</div>
      <div className="mt-2 text-[11px] uppercase tracking-[0.16em] text-on-surface-variant/80">
        {template.mood}
      </div>
    </button>
  );
}

function WebColorPresetButton({ preset, selected, onSelect }) {
  return (
    <button
      className={[
        "flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition-all",
        selected
          ? "border-primary bg-primary/10 shadow-soft"
          : "border-outline-variant/20 bg-surface hover:border-primary/30 hover:bg-surface-container-low",
      ].join(" ")}
      onClick={onSelect}
      type="button"
    >
      <div className="flex items-center gap-1.5">
        {WEB_CV_COLOR_FIELDS.map((field) => (
          <span
            key={field.id}
            className="h-5 w-5 rounded-full border border-black/10"
            style={{ backgroundColor: `#${preset.palette[field.id]}` }}
          />
        ))}
      </div>
      <div>
        <div className="text-sm font-semibold text-on-surface">{preset.label}</div>
        <div className="text-xs text-on-surface-variant">Editable hex palette</div>
      </div>
    </button>
  );
}

function DocumentsTab({ draft, updateSection }) {
  const documents = draft.documents;
  const options = draft.options;
  const browserStudioState = useMemo(
    () => buildCvStudioState(draft.profile, documents),
    [documents, draft.profile],
  );
  const browserPreviewHtml = useMemo(
    () => buildCvStudioHtml(browserStudioState, { forIframe: true }),
    [browserStudioState],
  );
  const exportPreviewState = useMemo(
    () => buildWorkspacePreviewState(draft.profile, documents, {}),
    [draft.profile, documents],
  );
  const exportPreviewHtml = useMemo(
    () => buildCvStudioHtml(exportPreviewState, { forIframe: true }),
    [exportPreviewState],
  );
  const selectedBrowserPreset = useMemo(
    () => matchPresetByPalette(documents.web_cv_palette || {}),
    [documents.web_cv_palette],
  );

  function updateBrowserPalette(fieldId, value) {
    updateSection("documents", {
      web_cv_palette: {
        ...(documents.web_cv_palette || {}),
        [fieldId]: sanitizeHexInput(value),
      },
    });
  }

  function applyBrowserPreset(preset) {
    updateSection("documents", {
      web_cv_palette: { ...preset.palette },
    });
  }

  function openBrowserStudio() {
    stashCvStudioSeed({
      returnTo: "/settings",
      sourceLabel: "Profile and document defaults",
      profile: draft.profile,
      documents,
    });
    window.open(CV_STUDIO_ROUTE, "_blank", "noopener,noreferrer");
  }

  return (
    <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8">
      <div className="space-y-10">
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.05fr)_minmax(360px,0.95fr)]">
          <div className="space-y-6 rounded-2xl border border-outline-variant/15 bg-surface p-6">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <div className="text-xs font-bold uppercase tracking-[0.18em] text-primary/80">
                  CV Studio
                </div>
                <h3 className="mt-2 text-lg font-bold text-on-surface">
                  Edit the HTML CV directly in the browser
                </h3>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-on-surface-variant">
                  These templates are meant for on-the-spot editing. Open the studio, tailor the role,
                  company, bullets, and colors, then print or save PDF directly from the browser.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  className="rounded-lg border border-outline-variant/20 px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-low"
                  onClick={openBrowserStudio}
                  type="button"
                >
                  Open CV Studio
                </button>
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              {WEB_CV_TEMPLATES.map((template) => (
                <WebTemplateCard
                  key={template.id}
                  onSelect={() => updateSection("documents", { web_cv_template: template.id })}
                  selected={browserStudioState.templateId === template.id}
                  template={template}
                />
              ))}
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              {WEB_CV_COLOR_PRESETS.map((preset) => (
                <WebColorPresetButton
                  key={preset.id}
                  onSelect={() => applyBrowserPreset(preset)}
                  preset={preset}
                  selected={selectedBrowserPreset?.id === preset.id}
                />
              ))}
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              {WEB_CV_COLOR_FIELDS.map((field) => (
                <SectionField key={field.id} hint={field.description} label={field.label}>
                  <div className="flex items-center gap-3">
                    <span
                      className="h-11 w-11 rounded-xl border border-black/10"
                      style={{ backgroundColor: `#${browserStudioState.palette?.[field.id] || "FFFFFF"}` }}
                    />
                    <div className="relative flex-1">
                      <span className="pointer-events-none absolute left-4 top-3 text-sm text-on-surface-variant">
                        #
                      </span>
                      <TextInput
                        className="pl-7"
                        maxLength={6}
                        onChange={(event) => updateBrowserPalette(field.id, event.target.value)}
                        value={documents.web_cv_palette?.[field.id] || browserStudioState.palette?.[field.id] || ""}
                      />
                    </div>
                  </div>
                </SectionField>
              ))}
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <SectionField label="Studio Font">
                <TextInput
                  onChange={(event) => updateSection("documents", { web_cv_font: event.target.value })}
                  placeholder="Aptos"
                  value={documents.web_cv_font || documents.cv_font || ""}
                />
              </SectionField>
              <ToggleRow
                checked={Boolean(documents.web_cv_show_photo ?? documents.include_photo)}
                description="Keeps an optional image slot in the browser templates."
                label="Show Photo In HTML CV"
                onChange={(value) => updateSection("documents", { web_cv_show_photo: value })}
              />
            </div>

            <p className="rounded-xl bg-surface-container-low px-4 py-3 text-xs leading-6 text-on-surface-variant">
              The studio launch uses your current unsaved profile and browser-CV settings from this page.
              Color codes stay editable as raw hex values.
            </p>
          </div>

          <div className="rounded-2xl border border-outline-variant/15 bg-surface p-5">
            <div className="mb-3 text-sm font-semibold text-on-surface">Live HTML Preview</div>
            <div className="rounded-2xl border border-outline-variant/10 bg-surface-container-low p-3">
              <iframe
                className="h-[840px] w-full rounded-xl bg-white"
                srcDoc={browserPreviewHtml}
                title="Browser CV HTML preview"
              />
            </div>
            <p className="mt-3 text-xs leading-6 text-on-surface-variant">
              This is the actual browser template output. The full studio adds job-specific text editing and
              print controls.
            </p>
          </div>
        </div>

        <div className="rounded-2xl border border-outline-variant/15 bg-surface p-6">
          <div className="mb-6">
            <div className="text-xs font-bold uppercase tracking-[0.18em] text-primary/80">
              Export Renderer
            </div>
            <h3 className="mt-2 text-lg font-bold text-on-surface">DOCX / PDF generation defaults</h3>
            <p className="mt-2 text-sm leading-6 text-on-surface-variant">
              These controls remain the defaults for the repo's generated application artifacts.
            </p>
          </div>

          <div className="space-y-8">
            <div className="grid gap-4 lg:grid-cols-2">
              {(options.cv_templates || []).map((template) => (
                <TemplateCard
                  key={template.id}
                  onSelect={() => updateSection("documents", { cv_template: template.id })}
                  selected={documents.cv_template === template.id}
                  template={template}
                />
              ))}
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              {(options.cv_color_schemes || []).map((scheme) => (
                <ColorSchemeButton
                  key={scheme.id}
                  onSelect={() => updateSection("documents", { cv_color_scheme: scheme.id })}
                  scheme={scheme}
                  selected={documents.cv_color_scheme === scheme.id}
                />
              ))}
            </div>

            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(320px,360px)]">
              <div className="space-y-4">
                <div className="max-w-md">
                  <SectionField label="CV Font">
                    <select
                      className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
                      onChange={(event) => updateSection("documents", { cv_font: event.target.value })}
                      value={documents.cv_font || ""}
                    >
                      {(options.cv_fonts || []).map((font) => (
                        <option key={font.id} value={font.id}>
                          {font.label}
                        </option>
                      ))}
                    </select>
                  </SectionField>
                </div>

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
                  <ToggleRow
                    checked={Boolean(documents.include_photo)}
                    description="Embed your uploaded square profile photo in the top-right of generated CVs."
                    label="Include Photo In CV"
                    onChange={(value) => updateSection("documents", { include_photo: value })}
                  />
                </div>

                <div className="max-w-md">
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
              </div>

              <div>
                <div className="mb-3 text-sm font-semibold text-on-surface">Export Preview</div>
                <div className="rounded-2xl border border-outline-variant/10 bg-surface-container-low p-3">
                  <iframe
                    className="h-[840px] w-full rounded-xl bg-white"
                    srcDoc={exportPreviewHtml}
                    title="Generated PDF export preview"
                  />
                </div>
                <p className="mt-3 text-xs leading-6 text-on-surface-variant">
                  The generated PDF uses this browser HTML renderer. The generated DOCX uses the
                  same structured content in a Word-editable layout.
                </p>
              </div>
            </div>
          </div>
        </div>
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
  const { request, getAccessToken, resolvePath } = useSession();
  const [activeTab, setActiveTab] = useState("Profile");
  const [draft, setDraft] = useState(null);
  const [saveState, setSaveState] = useState({ message: "", error: "" });
  const [cvUploadState, setCvUploadState] = useState({ uploading: false, message: "", error: "" });
  const [photoUploadState, setPhotoUploadState] = useState({ uploading: false, message: "", error: "" });
  const [billingPortalState, setBillingPortalState] = useState({ loading: false, error: "" });
  const cvFileInputRef = useRef(null);
  const photoFileInputRef = useRef(null);

  const { data, loading, error, refresh } = useApiResource(() => request("/settings"), [request]);
  const {
    data: subscriptionData,
    loading: usageLoading,
    error: usageError,
    refresh: refreshUsage,
  } = useApiResource(() => request("/billing/subscription"), [request]);

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

  async function handleCvUpload(file) {
    if (!file) return;
    setCvUploadState({ uploading: true, message: "", error: "" });
    try {
      const formData = new FormData();
      formData.append("cv_file", file, file.name);
      const json = await request("/cv-upload", {
        method: "POST",
        body: formData,
        timeoutMs: 90000,
      });
      const parsed = json.parsed || {};
      const extractionProvider = String(json?.extraction?.provider || "").trim();
      setDraft((current) => ({
        ...current,
        profile: mergeUploadedProfile(current?.profile || {}, parsed),
      }));
      setCvUploadState({
        uploading: false,
        message: `CV uploaded (${json.char_count?.toLocaleString()} chars). ${extractionProvider || "Profile"} data populated in the profile blocks - review and save.`,
        error: "",
      });
    } catch (uploadError) {
      setCvUploadState({
        uploading: false,
        message: "",
        error: uploadError.message || "Upload failed.",
      });
    }
  }

  async function handlePhotoUpload(file) {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      setPhotoUploadState({
        uploading: false,
        message: "",
        error: "Profile photo must be 2MB or smaller.",
      });
      return;
    }
    setPhotoUploadState({ uploading: true, message: "", error: "" });
    try {
      const accessToken = await getAccessToken();
      const croppedFile = await cropImageToSquare(file);
      const formData = new FormData();
      formData.append("photo_file", croppedFile, croppedFile.name);
      const res = await fetch(resolvePath("/profile-photo-upload"), {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
        body: formData,
      });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(json?.error?.message || "Profile photo upload failed");
      }
      setDraft((current) => ({
        ...current,
        profile: {
          ...(current?.profile || {}),
          photo_data_url: json.photo_data_url || "",
          avatar_url: json.photo_data_url || current?.profile?.avatar_url || "",
        },
      }));
      setPhotoUploadState({
        uploading: false,
        message: "Profile photo uploaded and saved.",
        error: "",
      });
      refresh().catch(() => undefined);
    } catch (uploadError) {
      setPhotoUploadState({
        uploading: false,
        message: "",
        error: uploadError.message || "Profile photo upload failed.",
      });
    }
  }

  function handlePhotoRemove() {
    updateSection("profile", {
      photo_data_url: "",
      avatar_url: "",
      photo_path: "",
    });
    setPhotoUploadState({
      uploading: false,
      message: "Profile photo removed. Save settings to keep this change.",
      error: "",
    });
  }

  function handleDiscard() {
    if (data) {
      setDraft(data);
      setSaveState({ message: "", error: "" });
    }
  }

  async function handleManageBilling() {
    setBillingPortalState({ loading: true, error: "" });
    try {
      const payload = await request("/billing/portal", {
        method: "POST",
        body: {},
      });
      window.location.assign(payload.portal_url);
    } catch (requestError) {
      setBillingPortalState({
        loading: false,
        error: requestError.message || "Unable to open billing portal.",
      });
    }
  }

  const profile = draft?.profile || {};
  const account = draft?.account || {};
  const hasProfilePhoto = Boolean(String(profile.photo_data_url || profile.avatar_url || "").trim());
  const usageQuotas = subscriptionData?.usage?.quotas || {};
  const currentPlanId = String(subscriptionData?.plan_id || "none").trim() || "none";
  const currentPlanName = String(subscriptionData?.plan?.display_name || "No subscription").trim() || "No subscription";
  const subscriptionDetails = subscriptionData?.subscription || {};
  const hasBillingPortalAccess =
    currentPlanId !== "none" || Boolean(String(subscriptionData?.subscription?.creem_customer_id || "").trim());
  const scrapeopsPolicy = subscriptionData?.scrapeops_usage?.policy || {};

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
                  <input
                    accept="image/png,image/jpeg"
                    className="hidden"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) handlePhotoUpload(file);
                      event.target.value = "";
                    }}
                    ref={photoFileInputRef}
                    type="file"
                  />
                  <img
                    alt={profile.name || account.display_name}
                    className="mx-auto h-28 w-28 rounded-full border-4 border-surface-container-lowest object-cover shadow-sm"
                    src={getProfilePhotoSrc(profile)}
                  />
                  <button
                    className="absolute bottom-0 right-0 rounded-full border border-outline-variant/20 bg-surface-container-lowest p-2 text-on-surface-variant shadow-sm transition-colors hover:text-primary"
                    onClick={() => photoFileInputRef.current?.click()}
                    type="button"
                  >
                    <span className="material-symbols-outlined text-[18px]">edit</span>
                  </button>
                </div>
                <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
                  <button
                    className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/20 bg-surface-container-lowest px-3 py-2 text-sm font-medium text-on-surface transition-colors hover:border-primary/30 hover:text-primary"
                    onClick={() => photoFileInputRef.current?.click()}
                    type="button"
                  >
                    <span className="material-symbols-outlined text-[18px]">upload</span>
                    {hasProfilePhoto ? "Choose new photo" : "Choose photo"}
                  </button>
                  {hasProfilePhoto ? (
                    <button
                      className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/20 bg-surface-container-lowest px-3 py-2 text-sm font-medium text-on-surface-variant transition-colors hover:border-error/30 hover:text-error"
                      onClick={handlePhotoRemove}
                      type="button"
                    >
                      <span className="material-symbols-outlined text-[18px]">delete</span>
                      Remove photo
                    </button>
                  ) : null}
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
              {photoUploadState.message ? (
                <p className="relative z-10 mt-4 rounded-lg bg-primary/10 px-3 py-2 text-xs leading-5 text-primary">
                  {photoUploadState.message}
                </p>
              ) : null}
              {photoUploadState.error ? (
                <p className="relative z-10 mt-4 rounded-lg bg-error-container px-3 py-2 text-xs leading-5 text-on-error-container">
                  {photoUploadState.error}
                </p>
              ) : null}
            </section>

            <section className="rounded-xl bg-surface-container-low p-6">
              <h3 className="mb-4 font-headline text-lg font-bold text-on-surface">
                Quick Document Actions
              </h3>
              <div className="flex flex-col gap-3">
                {/* Hidden file input for CV upload */}
                <input
                  accept=".txt,.docx,.pdf"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) handleCvUpload(file);
                    event.target.value = "";
                  }}
                  ref={cvFileInputRef}
                  type="file"
                />
                <button
                  className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-br from-primary to-primary-container px-4 py-3 text-sm font-medium text-white shadow-sm transition-all hover:saturate-150 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={cvUploadState.uploading}
                  onClick={() => cvFileInputRef.current?.click()}
                  type="button"
                >
                  <span className="material-symbols-outlined text-[20px]">
                    {cvUploadState.uploading ? "hourglass_empty" : "upload_file"}
                  </span>
                  {cvUploadState.uploading ? "Uploading..." : "Upload New CV"}
                </button>
                <button
                  className="flex w-full items-center justify-center gap-2 rounded-lg border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm font-medium text-on-surface transition-all hover:bg-surface-container-high active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={cvUploadState.uploading}
                  onClick={() => cvFileInputRef.current?.click()}
                  type="button"
                >
                  <span className="material-symbols-outlined text-[20px]">find_replace</span>
                  Replace Current CV
                </button>
                {cvUploadState.message ? (
                  <p className="rounded-lg bg-primary/10 px-3 py-2 text-xs leading-5 text-primary">
                    {cvUploadState.message}
                  </p>
                ) : null}
                {cvUploadState.error ? (
                  <p className="rounded-lg bg-error-container px-3 py-2 text-xs leading-5 text-on-error-container">
                    {cvUploadState.error}
                  </p>
                ) : null}
              </div>
            </section>

            <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="font-headline text-lg font-bold text-on-surface">Usage this month</h3>
                  <p className="mt-2 text-sm text-on-surface-variant">
                    Current plan:
                    {" "}
                    <span className="font-semibold text-on-surface">{currentPlanName}</span>
                  </p>
                </div>
                <button
                  className="rounded-full border border-outline-variant/20 bg-surface-container-low px-3 py-1.5 text-xs font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                  onClick={() => refreshUsage().catch(() => undefined)}
                  type="button"
                >
                  Refresh
                </button>
              </div>

              {hasBillingPortalAccess ? (
                <div className="mt-4 rounded-lg border border-primary/10 bg-primary/10 p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="text-sm font-semibold text-primary">
                        You are subscribed to {currentPlanName}.
                      </p>
                      <p className="mt-1 text-xs leading-5 text-on-surface-variant">
                        Period: {formatDateTime(subscriptionDetails.current_period_start)} to{" "}
                        {formatDateTime(subscriptionDetails.current_period_end)}.
                      </p>
                      <p className="mt-1 text-xs leading-5 text-on-surface-variant">
                        Use the billing portal to manage payment details, invoices, and cancellation.
                      </p>
                    </div>
                    <button
                      className="inline-flex items-center justify-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                      disabled={billingPortalState.loading}
                      onClick={handleManageBilling}
                      type="button"
                    >
                      <span className="material-symbols-outlined text-[18px]">credit_card</span>
                      {billingPortalState.loading ? "Opening..." : "Manage billing"}
                    </button>
                  </div>
                  {billingPortalState.error ? (
                    <p className="mt-3 rounded-lg bg-error-container px-3 py-2 text-xs leading-5 text-on-error-container">
                      {billingPortalState.error}
                    </p>
                  ) : null}
                </div>
              ) : null}

              <div className="mt-5 space-y-4">
                {usageLoading && !Object.keys(usageQuotas).length ? (
                  <p className="text-sm text-on-surface-variant">Loading usage...</p>
                ) : null}
                {usageError ? (
                  <p className="rounded-lg bg-error-container px-3 py-2 text-xs leading-5 text-on-error-container">
                    {usageError}
                  </p>
                ) : null}
                {Object.entries(usageLabels).map(([quotaType, label]) => (
                  <UsageMetric
                    key={quotaType}
                    label={label}
                    quota={usageQuotas[quotaType] || { used: 0, limit: 0 }}
                  />
                ))}
              </div>

              <div className="mt-5 rounded-lg border border-outline-variant/10 bg-surface p-4 text-sm text-on-surface-variant">
                <div className="font-semibold text-on-surface">Company-site policy</div>
                <div className="mt-2">
                  Company sites per run:{" "}
                  <span className="font-medium text-on-surface">
                    {Number(scrapeopsPolicy.company_sites_per_run) === -1
                      ? "Unlimited"
                      : String(scrapeopsPolicy.company_sites_per_run ?? 0)}
                  </span>
                </div>
                <div className="mt-1">
                  Runner-credit budget per run:{" "}
                  <span className="font-medium text-on-surface">
                    {Number(scrapeopsPolicy.effective_runner_credits_per_run) === -1
                      ? "Unlimited"
                      : String(scrapeopsPolicy.effective_runner_credits_per_run ?? 0)}
                  </span>
                </div>
              </div>

              {currentPlanId === "none" ? (
                <Link
                  className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-primary transition-colors hover:text-primary"
                  to="/pricing"
                >
                  <span className="material-symbols-outlined text-[18px]">trending_up</span>
                  Choose a plan
                </Link>
              ) : null}
            </section>
          </div>

          <div className="flex flex-col gap-8 xl:col-span-8">
            {activeTab === "Profile" ? (
              <ProfileTab draft={draft} updateSection={updateSection} />
            ) : null}
            {activeTab === "Defaults" ? (
              <DefaultsTab draft={draft} updateSection={updateSection} />
            ) : null}
            {activeTab === "Document Defaults" ? (
              <DocumentsTab draft={draft} updateSection={updateSection} />
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
