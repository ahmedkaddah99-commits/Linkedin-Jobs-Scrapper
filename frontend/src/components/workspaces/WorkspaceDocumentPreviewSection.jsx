import { labelize } from "../../lib/formatters";

export function WorkspaceDocumentPreviewSection({
  FieldRenderer,
  dynamicOptions,
  effectiveBrowserPreviewHtml,
  effectiveDocumentPreviewDocuments,
  fields,
  form,
  mergedPreviewProfile,
  selectedWorkspaceCvAsset,
  selectedWorkspaceCvMissing,
  updateSetting,
}) {
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(320px,1.1fr)]">
      <div className="space-y-4">
        <div className="rounded-lg border border-outline-variant/10 bg-surface p-4">
          <p className="text-sm font-semibold text-on-surface">Workspace personalization and style</p>
          <p className="mt-1 text-xs leading-6 text-on-surface-variant">
            Personalization scope decides whether this workspace can use only the
            baseline CV, selected Career Assets, or the full master career profile.
            Blank style values still inherit your shared document defaults.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {fields.map((field) => (
            <label className="space-y-2" key={field.id}>
              <span className="block text-sm font-semibold text-on-surface">{field.label}</span>
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

        <div className="rounded-lg border border-outline-variant/10 bg-surface px-4 py-3 text-xs leading-6 text-on-surface-variant">
          Active export mapping: {labelize(effectiveDocumentPreviewDocuments.cv_template)},{" "}
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
              Uses the same browser HTML renderer that generates the final PDF.
              The DOCX remains available as the editable Word companion.
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
            <iframe
              className="h-[840px] w-full rounded-xl bg-white"
              srcDoc={effectiveBrowserPreviewHtml}
              title="Workspace CV PDF preview"
            />
          </div>
        ) : (
          <div className="rounded-xl border border-outline-variant/10 bg-surface p-6 text-sm text-on-surface-variant">
            Loading preview...
          </div>
        )}

        <p className="text-xs leading-6 text-on-surface-variant">
          The generated PDF follows this HTML preview. The generated DOCX uses the
          same structured CV content in a Word-editable layout.
        </p>
      </div>
    </div>
  );
}
