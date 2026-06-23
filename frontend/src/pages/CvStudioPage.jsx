import { forwardRef, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import {
  CV_STUDIO_ROUTE,
  WEB_CV_COLOR_FIELDS,
  WEB_CV_COLOR_PRESETS,
  WEB_CV_TEMPLATES,
  buildCvStudioHtml,
  buildCvStudioState,
  buildStudioDocumentPatch,
  consumeCvStudioSeed,
  findCvTemplate,
  loadCvStudioSession,
  matchPresetByPalette,
  saveCvStudioSession,
} from "../lib/cvStudio";

function Field({ label, hint = "", children }) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-semibold text-on-surface">{label}</span>
      {children}
      {hint ? <span className="mt-2 block text-xs text-on-surface-variant">{hint}</span> : null}
    </label>
  );
}

const Input = forwardRef(function Input(props, ref) {
  return (
    <input
      {...props}
      ref={ref}
      className={[
        "w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface",
        props.className || "",
      ].join(" ")}
    />
  );
});

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

function Section({ title, description = "", children, className = "" }) {
  return (
    <section
      className={[
        "rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5",
        className,
      ].join(" ")}
    >
      <div className="mb-4">
        <h2 className="text-base font-bold text-on-surface">{title}</h2>
        {description ? (
          <p className="mt-1 text-sm leading-6 text-on-surface-variant">{description}</p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function sanitizeHexInput(value) {
  return String(value || "")
    .replace(/[^0-9a-fA-F]/g, "")
    .slice(0, 6)
    .toUpperCase();
}

function copyPreviewToWindow(html, { shouldPrint = false } = {}) {
  const openedWindow = window.open("", "_blank");
  if (!openedWindow) return false;
  openedWindow.document.open();
  openedWindow.document.write(html);
  openedWindow.document.close();
  if (shouldPrint) {
    openedWindow.focus();
    window.setTimeout(() => {
      openedWindow.print();
    }, 250);
  }
  return true;
}

let editorIdCounter = 0;

function newEditorId(prefix) {
  editorIdCounter += 1;
  return `${prefix}-${Date.now()}-${editorIdCounter}`;
}

function StructuredListEditor({ items = [], label, onChange }) {
  const inputRefs = useRef(new Map());
  const addButtonRef = useRef(null);

  function focusItem(itemId) {
    window.requestAnimationFrame(() => {
      inputRefs.current.get(itemId)?.focus();
    });
  }

  function updateItem(index, patch) {
    onChange(items.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  function addItem(index = items.length - 1) {
    const item = { id: newEditorId("bullet"), text: "", level: items[index]?.level || 0 };
    const nextItems = [...items];
    nextItems.splice(index + 1, 0, item);
    onChange(nextItems);
    focusItem(item.id);
  }

  function removeItem(index) {
    const nextItems = items.filter((_, itemIndex) => itemIndex !== index);
    const focusTarget = nextItems[Math.min(index, nextItems.length - 1)];
    onChange(nextItems);
    if (focusTarget) {
      focusItem(focusTarget.id);
    } else {
      window.requestAnimationFrame(() => addButtonRef.current?.focus());
    }
  }

  function adjustLevel(index, delta) {
    const currentLevel = Number(items[index]?.level || 0);
    const previousLevel = Number(items[index - 1]?.level || 0);
    const maxLevel = index === 0 ? 0 : Math.min(2, previousLevel + 1);
    updateItem(index, { level: Math.max(0, Math.min(maxLevel, currentLevel + delta)) });
  }

  function handleKeyDown(event, index) {
    if (event.key === "Tab") {
      event.preventDefault();
      adjustLevel(index, event.shiftKey ? -1 : 1);
      return;
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!String(items[index]?.text || "").trim()) {
        removeItem(index);
      } else {
        addItem(index);
      }
    }
  }

  return (
    <div className="space-y-3">
      {items.length ? (
        <div className="space-y-2" role="list">
          {items.map((item, index) => (
            <div
              className="flex items-start gap-2"
              key={item.id}
              role="listitem"
              style={{ paddingLeft: `${Math.min(Number(item.level || 0), 2) * 20}px` }}
            >
              <span aria-hidden="true" className="pt-3 text-sm text-on-surface-variant">•</span>
              <Input
                aria-label={`${label} ${index + 1}`}
                onChange={(event) => updateItem(index, { text: event.target.value })}
                onKeyDown={(event) => handleKeyDown(event, index)}
                placeholder="Describe a measurable result or responsibility"
                ref={(node) => {
                  if (node) inputRefs.current.set(item.id, node);
                  else inputRefs.current.delete(item.id);
                }}
                value={item.text || ""}
              />
              <div className="flex shrink-0 gap-1">
                <button
                  aria-label={`Outdent ${label.toLowerCase()} ${index + 1}`}
                  className="rounded-lg border border-outline-variant/20 px-2 py-3 text-xs text-on-surface-variant disabled:opacity-40"
                  disabled={!item.level}
                  onClick={() => adjustLevel(index, -1)}
                  type="button"
                >
                  ←
                </button>
                <button
                  aria-label={`Indent ${label.toLowerCase()} ${index + 1}`}
                  className="rounded-lg border border-outline-variant/20 px-2 py-3 text-xs text-on-surface-variant disabled:opacity-40"
                  disabled={Number(item.level || 0) >= 2 || index === 0}
                  onClick={() => adjustLevel(index, 1)}
                  type="button"
                >
                  →
                </button>
                <button
                  aria-label={`Remove ${label.toLowerCase()} ${index + 1}`}
                  className="rounded-lg border border-outline-variant/20 px-2 py-3 text-xs text-on-surface-variant hover:bg-error-container hover:text-on-error-container"
                  onClick={() => removeItem(index)}
                  type="button"
                >
                  ×
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="rounded-lg bg-surface-container-low px-3 py-2 text-sm text-on-surface-variant">
          No {label.toLowerCase()} added yet.
        </p>
      )}
      <button
        className="rounded-lg bg-surface-container-low px-3 py-2 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
        onClick={() => addItem()}
        ref={addButtonRef}
        type="button"
      >
        Add {label}
      </button>
      <p className="text-xs leading-5 text-on-surface-variant">
        Enter adds the next item. Tab indents; Shift+Tab outdents. Enter on an empty item removes it.
      </p>
    </div>
  );
}

function ExperienceEditor({ items, onChange }) {
  function updateItem(index, field, value) {
    onChange(
      items.map((item, itemIndex) =>
        itemIndex === index ? { ...item, [field]: value } : item,
      ),
    );
  }

  function addItem() {
    onChange([
      ...(items || []),
      {
        id: newEditorId("experience"),
        title: "",
        company: "",
        location: "",
        startDate: "",
        endDate: "",
        period: "",
        bullets: [],
      },
    ]);
  }

  function removeItem(index) {
    onChange(items.filter((_, itemIndex) => itemIndex !== index));
  }

  return (
    <div className="space-y-4">
      {!items?.length ? (
        <p className="rounded-xl border border-dashed border-outline-variant/30 bg-surface px-4 py-5 text-sm text-on-surface-variant">
          No experience entries are in this draft. Add one to include an Experience section.
        </p>
      ) : null}
      {(items || []).map((item, index) => (
        <div
          key={item.id || `studio-exp-${index}`}
          className="rounded-xl border border-outline-variant/15 bg-surface p-4"
        >
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-on-surface">Experience {index + 1}</h3>
            <button
              className="rounded-lg border border-outline-variant/20 px-3 py-2 text-sm font-medium text-on-surface-variant transition-colors hover:bg-error-container hover:text-on-error-container"
              onClick={() => removeItem(index)}
              type="button"
            >
              Remove
            </button>
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Field label="Role title">
              <Input
                onChange={(event) => updateItem(index, "title", event.target.value)}
                placeholder="Operations Analyst"
                value={item.title || ""}
              />
            </Field>
            <Field label="Company">
              <Input
                onChange={(event) => updateItem(index, "company", event.target.value)}
                placeholder="Example GmbH"
                value={item.company || ""}
              />
            </Field>
            <Field label="Location">
              <Input
                onChange={(event) => updateItem(index, "location", event.target.value)}
                placeholder="Berlin, Germany"
                value={item.location || ""}
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Start date">
                <Input
                  onChange={(event) => updateItem(index, "startDate", event.target.value)}
                  placeholder="Jan 2022"
                  value={item.startDate || ""}
                />
              </Field>
              <Field label="End date">
                <Input
                  onChange={(event) => updateItem(index, "endDate", event.target.value)}
                  placeholder="Present"
                  value={item.endDate || ""}
                />
              </Field>
            </div>
          </div>
          <div className="mt-4">
            <div className="mb-2 text-sm font-semibold text-on-surface">Achievements</div>
            <StructuredListEditor
              items={item.bullets || []}
              label="Achievement"
              onChange={(bullets) => updateItem(index, "bullets", bullets)}
            />
          </div>
        </div>
      ))}

      <button
        className="rounded-lg bg-surface-container-low px-4 py-2.5 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
        onClick={addItem}
        type="button"
      >
        Add Experience Block
      </button>
    </div>
  );
}

function ProjectEditor({ items, onChange }) {
  function updateItem(index, field, value) {
    onChange(
      (items || []).map((item, itemIndex) =>
        itemIndex === index ? { ...item, [field]: value } : item,
      ),
    );
  }

  function addItem() {
    onChange([
      ...(items || []),
      { id: newEditorId("project"), title: "", period: "", bullets: [] },
    ]);
  }

  function removeItem(index) {
    onChange((items || []).filter((_, itemIndex) => itemIndex !== index));
  }

  return (
    <div className="space-y-4">
      {!items?.length ? (
        <p className="rounded-xl border border-dashed border-outline-variant/30 bg-surface px-4 py-5 text-sm text-on-surface-variant">
          No projects are in this draft. Add one when it strengthens the application.
        </p>
      ) : null}
      {(items || []).map((item, index) => (
        <div
          className="rounded-xl border border-outline-variant/15 bg-surface p-4"
          key={item.id || `studio-project-${index}`}
        >
          <div className="grid gap-4 md:grid-cols-[1fr_180px_auto]">
            <Field label="Project or initiative">
              <Input
                onChange={(event) => updateItem(index, "title", event.target.value)}
                placeholder="Analytics automation"
                value={item.title || ""}
              />
            </Field>
            <Field label="Date or period">
              <Input
                onChange={(event) => updateItem(index, "period", event.target.value)}
                placeholder="2024"
                value={item.period || ""}
              />
            </Field>
            <button
              className="self-end rounded-lg border border-outline-variant/20 px-4 py-3 text-sm font-medium text-on-surface-variant transition-colors hover:bg-error-container hover:text-on-error-container"
              onClick={() => removeItem(index)}
              type="button"
            >
              Remove
            </button>
          </div>
          <div className="mt-4">
            <div className="mb-2 text-sm font-semibold text-on-surface">Results</div>
            <StructuredListEditor
              items={item.bullets || []}
              label="Project result"
              onChange={(bullets) => updateItem(index, "bullets", bullets)}
            />
          </div>
        </div>
      ))}
      <button
        className="rounded-lg bg-surface-container-low px-4 py-2.5 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
        onClick={addItem}
        type="button"
      >
        Add Project
      </button>
    </div>
  );
}

function CustomSectionEditor({ items, onChange }) {
  function updateItem(index, field, value) {
    onChange(
      (items || []).map((item, itemIndex) =>
        itemIndex === index ? { ...item, [field]: value } : item,
      ),
    );
  }

  function addItem() {
    onChange([...(items || []), { heading: "Additional Information", linesText: "" }]);
  }

  function removeItem(index) {
    onChange((items || []).filter((_, itemIndex) => itemIndex !== index));
  }

  return (
    <div className="space-y-4">
      {(items || []).map((item, index) => (
        <div
          className="rounded-xl border border-outline-variant/15 bg-surface p-4"
          key={`studio-custom-${item.id || index}`}
        >
          <div className="grid gap-4 md:grid-cols-[1fr_auto]">
            <Input
              onChange={(event) => updateItem(index, "heading", event.target.value)}
              placeholder="Section heading"
              value={item.heading || ""}
            />
            <button
              className="rounded-lg border border-outline-variant/20 px-4 py-3 text-sm font-medium text-on-surface-variant transition-colors hover:bg-surface-container-low"
              onClick={() => removeItem(index)}
              type="button"
            >
              Remove
            </button>
          </div>
          <div className="mt-4">
            <TextArea
              onChange={(event) => updateItem(index, "linesText", event.target.value)}
              placeholder="One line per item"
              value={item.linesText || ""}
            />
          </div>
        </div>
      ))}
      <button
        className="rounded-lg bg-surface-container-low px-4 py-2.5 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
        onClick={addItem}
        type="button"
      >
        Add Custom Section
      </button>
    </div>
  );
}

export default function CvStudioPage() {
  const { request } = useSession();
  const [consumedSeed] = useState(() => consumeCvStudioSeed());
  const [studioState, setStudioState] = useState(null);
  const [savedSource, setSavedSource] = useState(null);
  const [saveState, setSaveState] = useState({ message: "", error: "", saving: false });
  const [mobilePane, setMobilePane] = useState("editor");
  const returnTo = String(consumedSeed?.returnTo || "/settings");
  const sourceLabel = String(consumedSeed?.sourceLabel || "Profile and document defaults");

  const { data, loading, error, refresh } = useApiResource(() => request("/settings"), [request], {
    cacheKey: "settings",
    staleMs: Infinity,
    backgroundRefresh: false,
  });

  useEffect(() => {
    if (!data || studioState) return;
    const sessionDraft = consumedSeed ? consumedSeed.sessionDraft || {} : loadCvStudioSession() || {};
    const sourceProfile = consumedSeed?.profile || data.profile || {};
    const sourceDocuments = consumedSeed?.documents || data.documents || {};
    setSavedSource({
      profile: data.profile || {},
      documents: data.documents || {},
    });
    setStudioState(buildCvStudioState(sourceProfile, sourceDocuments, sessionDraft));
  }, [consumedSeed, data, studioState]);

  useEffect(() => {
    if (!studioState) return;
    saveCvStudioSession(studioState);
  }, [studioState]);

  const selectedPreset = useMemo(
    () => (studioState ? matchPresetByPalette(studioState.palette) : null),
    [studioState],
  );

  const previewHtml = useMemo(
    () => (studioState ? buildCvStudioHtml(studioState, { forIframe: true }) : ""),
    [studioState],
  );

  function updateState(patch) {
    setStudioState((current) => ({ ...current, ...patch }));
  }

  function updatePalette(fieldId, nextValue) {
    setStudioState((current) => ({
      ...current,
      palette: {
        ...(current?.palette || {}),
        [fieldId]: sanitizeHexInput(nextValue),
      },
    }));
  }

  function applyPreset(preset) {
    updateState({ palette: { ...preset.palette } });
  }

  function resetToSaved() {
    if (!savedSource) return;
    setStudioState(buildCvStudioState(savedSource.profile, savedSource.documents, {}));
    setSaveState({ message: "", error: "", saving: false });
  }

  async function saveDesignDefaults() {
    if (!studioState) return;
    setSaveState({ message: "", error: "", saving: true });
    try {
      const payload = await request("/settings", {
        method: "PUT",
        body: {
          documents: buildStudioDocumentPatch(studioState),
        },
      });
      setSavedSource({
        profile: payload.profile || {},
        documents: payload.documents || {},
      });
      setSaveState({
        message: "CV Studio design defaults saved.",
        error: "",
        saving: false,
      });
      refresh().catch(() => undefined);
    } catch (saveError) {
      setSaveState({
        message: "",
        error: saveError.message || "Unable to save browser CV defaults.",
        saving: false,
      });
    }
  }

  if (loading && !studioState) {
    return (
      <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8 text-on-surface-variant">
        Loading CV Studio...
      </div>
    );
  }

  if (error && !studioState) {
    return (
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
    );
  }

  if (!studioState) {
    return null;
  }

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="font-headline text-[2rem] font-extrabold leading-tight tracking-tight text-on-surface">
              CV Studio
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-on-surface-variant">
              Edit the current CV draft, preview the exact HTML output, and print or save to PDF.
              Career Memory remains separate and supplies reusable facts for future tailoring.
            </p>
            <div className="mt-3 inline-flex rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
              Editing: {sourceLabel}
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              className="rounded-lg border border-outline-variant/20 px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-low"
              to={returnTo}
            >
              Back
            </Link>
            <button
              className="rounded-lg border border-outline-variant/20 px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-low"
              onClick={() => copyPreviewToWindow(previewHtml)}
              type="button"
            >
              Open Clean HTML
            </button>
            <button
              className="rounded-lg border border-outline-variant/20 px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-low"
              onClick={() => copyPreviewToWindow(previewHtml, { shouldPrint: true })}
              type="button"
            >
              Print / Save PDF
            </button>
            <button
              className="rounded-lg bg-gradient-to-br from-primary to-primary-container px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:saturate-150"
              disabled={saveState.saving}
              onClick={saveDesignDefaults}
              type="button"
            >
              {saveState.saving ? "Saving..." : "Save Design Defaults"}
            </button>
          </div>
        </div>
        {saveState.message ? (
          <p className="mt-4 rounded-lg bg-primary/10 px-3 py-2 text-sm text-primary">
            {saveState.message}
          </p>
        ) : null}
        {saveState.error ? (
          <p className="mt-4 rounded-lg bg-error-container px-3 py-2 text-sm text-on-error-container">
            {saveState.error}
          </p>
        ) : null}
        <p className="mt-4 rounded-lg bg-surface-container-low px-3 py-2 text-xs leading-5 text-on-surface-variant">
          Draft edits autosave in this browser. Print / Save PDF exports the current draft. Save
          Design Defaults updates reusable template settings, not the original generated artifact.
        </p>
      </section>

      <div className="grid grid-cols-2 gap-2 rounded-xl bg-surface-container-low p-1 xl:hidden">
        {[
          ["editor", "Editor"],
          ["preview", "Preview"],
        ].map(([paneId, label]) => (
          <button
            aria-pressed={mobilePane === paneId}
            className={[
              "rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors",
              mobilePane === paneId
                ? "bg-surface text-primary shadow-sm"
                : "text-on-surface-variant",
            ].join(" ")}
            key={paneId}
            onClick={() => setMobilePane(paneId)}
            type="button"
          >
            {label}
          </button>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(360px,430px)_minmax(0,1fr)]">
        <div className={[mobilePane === "editor" ? "block" : "hidden", "space-y-5 xl:block"].join(" ")}>
          <Section
            description="These controls affect the browser template only. DOCX settings remain in the Settings page."
            title="Design"
          >
            <div className="space-y-5">
              <div className="grid gap-3 sm:grid-cols-2">
                {WEB_CV_TEMPLATES.map((template) => {
                  const active = studioState.templateId === template.id;
                  return (
                    <button
                      key={template.id}
                      className={[
                        "rounded-xl border p-4 text-left transition-all",
                        active
                          ? "border-primary bg-primary/10 shadow-soft"
                          : "border-outline-variant/20 bg-surface hover:border-primary/30 hover:bg-surface-container-low",
                      ].join(" ")}
                      onClick={() => updateState({ templateId: template.id })}
                      type="button"
                    >
                      <div className="text-xs font-bold uppercase tracking-[0.18em] text-primary/80">
                        {template.shortLabel}
                      </div>
                      <div className="mt-2 text-sm font-semibold text-on-surface">
                        {template.label}
                      </div>
                      <div className="mt-1 text-xs leading-6 text-on-surface-variant">
                        {template.description}
                      </div>
                    </button>
                  );
                })}
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Font Family">
                  <Input
                    onChange={(event) => updateState({ fontFamily: event.target.value })}
                    placeholder="Aptos"
                    value={studioState.fontFamily || ""}
                  />
                </Field>
                <Field label="Photo Mode" hint="Turn the slot on or off without affecting DOCX defaults.">
                  <button
                    className={[
                      "flex h-[52px] w-full items-center justify-between rounded-lg border px-4 text-sm font-medium transition-colors",
                      studioState.showPhoto
                        ? "border-primary/30 bg-primary/10 text-primary"
                        : "border-outline-variant/20 bg-surface text-on-surface-variant",
                    ].join(" ")}
                    onClick={() => updateState({ showPhoto: !studioState.showPhoto })}
                    type="button"
                  >
                    <span>{studioState.showPhoto ? "Photo enabled" : "No photo layout"}</span>
                    <span className="material-symbols-outlined text-[18px]">
                      {studioState.showPhoto ? "portrait" : "hide_image"}
                    </span>
                  </button>
                </Field>
              </div>

              <div>
                <div className="mb-3 text-sm font-semibold text-on-surface">Color Presets</div>
                <div className="grid gap-3">
                  {WEB_CV_COLOR_PRESETS.map((preset) => {
                    const active = selectedPreset?.id === preset.id;
                    return (
                      <button
                        key={preset.id}
                        className={[
                          "flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition-all",
                          active
                            ? "border-primary bg-primary/10 shadow-soft"
                            : "border-outline-variant/20 bg-surface hover:border-primary/30 hover:bg-surface-container-low",
                        ].join(" ")}
                        onClick={() => applyPreset(preset)}
                        type="button"
                      >
                        <div className="flex items-center gap-2">
                          {WEB_CV_COLOR_FIELDS.map((field) => (
                            <span
                              key={field.id}
                              className="h-5 w-5 rounded-full border border-black/10"
                              style={{ backgroundColor: `#${preset.palette[field.id]}` }}
                            />
                          ))}
                        </div>
                        <div>
                          <div className="text-sm font-semibold text-on-surface">
                            {preset.label}
                          </div>
                          <div className="text-xs text-on-surface-variant">
                            Click to replace every token.
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <div className="mb-3 text-sm font-semibold text-on-surface">Editable Hex Tokens</div>
                <div className="grid gap-4 md:grid-cols-2">
                  {WEB_CV_COLOR_FIELDS.map((field) => (
                    <Field key={field.id} hint={field.description} label={field.label}>
                      <div className="flex items-center gap-3">
                        <span
                          className="h-11 w-11 rounded-xl border border-black/10"
                          style={{
                            backgroundColor: `#${studioState.palette?.[field.id] || "FFFFFF"}`,
                          }}
                        />
                        <div className="relative flex-1">
                          <span className="pointer-events-none absolute left-4 top-3 text-sm text-on-surface-variant">
                            #
                          </span>
                          <Input
                            className="pl-7"
                            maxLength={6}
                            onChange={(event) => updatePalette(field.id, event.target.value)}
                            value={studioState.palette?.[field.id] || ""}
                          />
                        </div>
                      </div>
                    </Field>
                  ))}
                </div>
              </div>
            </div>
          </Section>

          <Section
            description="These fields are for quick job-specific tailoring in the browser. They do not overwrite your saved profile unless you save profile settings separately."
            title="Content"
          >
            <div className="space-y-5">
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Candidate Name">
                  <Input
                    onChange={(event) => updateState({ name: event.target.value })}
                    value={studioState.name || ""}
                  />
                </Field>
                <Field label="Headline">
                  <Input
                    onChange={(event) => updateState({ headline: event.target.value })}
                    placeholder="Operations and Logistics Support"
                    value={studioState.headline || ""}
                  />
                </Field>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Target Role">
                  <Input
                    onChange={(event) => updateState({ targetRole: event.target.value })}
                    placeholder="Warehouse Associate"
                    value={studioState.targetRole || ""}
                  />
                </Field>
                <Field label="Target Company">
                  <Input
                    onChange={(event) => updateState({ targetCompany: event.target.value })}
                    placeholder="Example GmbH"
                    value={studioState.targetCompany || ""}
                  />
                </Field>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Location">
                  <Input
                    onChange={(event) => updateState({ location: event.target.value })}
                    value={studioState.location || ""}
                  />
                </Field>
                <Field label="Email">
                  <Input
                    onChange={(event) => updateState({ email: event.target.value })}
                    value={studioState.email || ""}
                  />
                </Field>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <Field label="Website">
                  <Input
                    onChange={(event) => updateState({ website: event.target.value })}
                    value={studioState.website || ""}
                  />
                </Field>
                <Field label="LinkedIn">
                  <Input
                    onChange={(event) => updateState({ linkedin: event.target.value })}
                    value={studioState.linkedin || ""}
                  />
                </Field>
                <Field label="GitHub">
                  <Input
                    onChange={(event) => updateState({ github: event.target.value })}
                    value={studioState.github || ""}
                  />
                </Field>
              </div>

              <Field label="Professional Summary">
                <TextArea
                  onChange={(event) => updateState({ summary: event.target.value })}
                  value={studioState.summary || ""}
                />
              </Field>

              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Skills / Keywords" hint="One per line or comma separated.">
                  <TextArea
                    onChange={(event) => updateState({ skillsText: event.target.value })}
                    value={studioState.skillsText || ""}
                  />
                </Field>
                <Field label="Languages" hint="One per line, for example German - B2.">
                  <TextArea
                    onChange={(event) => updateState({ languagesText: event.target.value })}
                    value={studioState.languagesText || ""}
                  />
                </Field>
              </div>

              <Field label="Education / Certificates" hint="One line per item.">
                <TextArea
                  onChange={(event) => updateState({ educationText: event.target.value })}
                  value={studioState.educationText || ""}
                />
              </Field>

              <Field label="Availability">
                <Input
                  onChange={(event) => updateState({ availability: event.target.value })}
                  value={studioState.availability || ""}
                />
              </Field>

              <div>
                <div className="mb-3 text-sm font-semibold text-on-surface">Experience Blocks</div>
                <ExperienceEditor
                  items={studioState.experience || []}
                  onChange={(experience) => updateState({ experience })}
                />
              </div>

              <div>
                <div className="mb-3 text-sm font-semibold text-on-surface">Projects</div>
                <ProjectEditor
                  items={studioState.projects || []}
                  onChange={(projects) => updateState({ projects })}
                />
              </div>

              <div>
                <div className="mb-3 text-sm font-semibold text-on-surface">Custom Sections</div>
                <CustomSectionEditor
                  items={studioState.customSections || []}
                  onChange={(customSections) => updateState({ customSections })}
                />
              </div>

              <div className="flex flex-wrap gap-3">
                <button
                  className="rounded-lg border border-outline-variant/20 px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-low"
                  onClick={resetToSaved}
                  type="button"
                >
                  Reset To Saved Profile
                </button>
                <div className="rounded-lg bg-surface-container-low px-4 py-2.5 text-xs leading-5 text-on-surface-variant">
                  Active template: {findCvTemplate(studioState.templateId).label}
                </div>
              </div>
            </div>
          </Section>
        </div>

        <Section
          className={[
            mobilePane === "preview" ? "block" : "hidden",
            "overflow-hidden xl:sticky xl:top-20 xl:block xl:self-start",
          ].join(" ")}
          description="This is the actual HTML output. Open it in a new tab, keep editing here, then print or save directly from the browser."
          title="Live HTML Preview"
        >
          <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-3">
            <iframe
              className="h-[72vh] min-h-[560px] w-full rounded-xl bg-white xl:h-[calc(100vh-8rem)]"
              srcDoc={previewHtml}
              title="Browser CV preview"
            />
          </div>
        </Section>
      </div>
    </div>
  );
}

export { CV_STUDIO_ROUTE };
