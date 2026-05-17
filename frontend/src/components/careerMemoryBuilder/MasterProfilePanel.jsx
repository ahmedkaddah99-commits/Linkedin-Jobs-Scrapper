export default function MasterProfilePanel({
  assetKindLabel,
  cvLikeAssets = [],
  importedCareerContext,
  masterCareerProfileAsset,
  masterProfileAssetId,
  masterProfileUploadState,
  onChangeImportedCareerContext,
  onChangeMasterProfile,
  onUploadMasterProfile,
}) {
  return (
    <section className="space-y-4">
      <div className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h3 className="font-headline text-lg font-bold text-on-surface">Master profile</h3>
            <p className="mt-1 text-sm leading-6 text-on-surface-variant">
              Link your detailed CV or master profile here. This stays administrative and out of
              the main Build workflow.
            </p>
          </div>
          <label className="inline-flex cursor-pointer items-center justify-center rounded-xl bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high">
            <input
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) {
                  onUploadMasterProfile(file);
                  event.target.value = "";
                }
              }}
              type="file"
            />
            {masterProfileUploadState.uploading ? "Uploading..." : "Upload detailed CV"}
          </label>
        </div>

        <label className="mt-4 block space-y-2">
          <span className="block text-sm font-semibold text-on-surface">Linked master profile</span>
          <select
            className="w-full rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface"
            onChange={(event) => onChangeMasterProfile(event.target.value)}
            value={masterProfileAssetId}
          >
            <option value="">Choose an uploaded detailed CV or master profile</option>
            {cvLikeAssets.map((item) => (
              <option key={item.asset_id || item.document_id} value={String(item.asset_id || "")}>
                {item.display_name} ({assetKindLabel(item.asset_kind)})
              </option>
            ))}
          </select>
        </label>

        <div className="mt-4 rounded-2xl border border-outline-variant/15 bg-surface p-4">
          <div className="text-sm font-semibold text-on-surface">Status</div>
          <div className="mt-2 text-sm text-on-surface-variant">
            {masterCareerProfileAsset
              ? `${masterCareerProfileAsset.display_name} is linked.`
              : "No master profile linked yet."}
          </div>
        </div>

        {masterProfileUploadState.message ? (
          <p className="mt-3 text-sm text-primary">{masterProfileUploadState.message}</p>
        ) : null}
        {masterProfileUploadState.error ? (
          <p className="mt-3 text-sm text-error">{masterProfileUploadState.error}</p>
        ) : null}
      </div>

      <details className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
        <summary className="cursor-pointer text-sm font-semibold text-on-surface">
          Imported career context
        </summary>
        <p className="mt-3 text-sm leading-6 text-on-surface-variant">
          Expand only if you need to review or refine the imported long-form profile text.
        </p>
        <textarea
          className="mt-4 min-h-48 w-full rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
          onChange={(event) => onChangeImportedCareerContext(event.target.value)}
          placeholder="Imported career context"
          value={importedCareerContext}
        />
      </details>
    </section>
  );
}
