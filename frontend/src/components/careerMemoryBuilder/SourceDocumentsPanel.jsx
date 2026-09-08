import { Link } from "react-router-dom";

function assetRowClasses(isSelected) {
  return isSelected
    ? "border-primary/30 bg-primary/10"
    : "border-outline-variant/15 bg-surface hover:bg-surface-container-low";
}

export default function SourceDocumentsPanel({
  assetDocuments = [],
  cvLikeAssets = [],
  selectedAssetIds = [],
  masterProfileAssetId = "",
  masterCareerProfileAsset = null,
  importedCareerContext = "",
  onToggleSourceAsset,
  onChangeField,
  assetKindLabel,
  formatDateTime,
  manageDocumentsTo = "/career-assets",
}) {
  const selectedAssets = assetDocuments.filter((item) =>
    selectedAssetIds.includes(String(item.asset_id || "")),
  );

  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <h2 className="font-headline text-xl font-bold text-on-surface">Source documents</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-on-surface-variant">
            The Asset Library is where documents live. This builder only decides which sources Runr
            can consult and where your imported career context comes from.
          </p>
        </div>
        <Link
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
          to={manageDocumentsTo}
        >
          Manage source documents
          <span className="material-symbols-outlined text-[16px]">folder_open</span>
        </Link>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="space-y-4">
          <div className="rounded-2xl border border-outline-variant/15 bg-surface p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-on-surface">Connected source assets</div>
                <div className="mt-1 text-sm text-on-surface-variant">
                  {selectedAssets.length
                    ? `${selectedAssets.length} source asset${selectedAssets.length === 1 ? "" : "s"} selected`
                    : "No source assets selected yet"}
                </div>
              </div>
              <span className="rounded-full bg-surface-container-low px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-on-surface-variant">
                Compact view
              </span>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {selectedAssets.length ? (
                selectedAssets.map((asset) => (
                  <span
                    className="rounded-full bg-primary/10 px-3 py-1.5 text-sm text-primary"
                    key={asset.document_id}
                  >
                    {asset.display_name}
                  </span>
                ))
              ) : (
                <span className="text-sm text-on-surface-variant">
                  Select a baseline CV, certifications, letters, or supporting files below.
                </span>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-outline-variant/15 bg-surface p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-on-surface">Selected source assets</div>
                <div className="mt-1 text-sm text-on-surface-variant">
                  Keep this list tight. These are the uploaded documents Runr may use for tailoring.
                </div>
              </div>
            </div>
            <div className="mt-4 max-h-[22rem] space-y-3 overflow-y-auto pr-1">
              {assetDocuments.length ? (
                assetDocuments.map((asset) => {
                  const assetId = String(asset.asset_id || "");
                  const isSelected = selectedAssetIds.includes(assetId);
                  return (
                    <label
                      className={[
                        "flex cursor-pointer items-start gap-3 rounded-2xl border p-4 transition-colors",
                        assetRowClasses(isSelected),
                      ].join(" ")}
                      key={asset.document_id}
                    >
                      <input
                        checked={isSelected}
                        className="mt-1 h-4 w-4 rounded border-outline-variant/40 text-primary focus:ring-primary"
                        onChange={() => onToggleSourceAsset(asset.asset_id)}
                        type="checkbox"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="font-semibold text-on-surface">{asset.display_name}</div>
                          <span className="rounded-full bg-surface-container-low px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-on-surface-variant">
                            {assetKindLabel(asset.asset_kind)}
                          </span>
                        </div>
                        <div className="mt-2 text-sm text-on-surface-variant">
                          {[asset.workspace_name || "Shared", formatDateTime(asset.created_at)]
                            .filter(Boolean)
                            .join(" | ")}
                        </div>
                      </div>
                    </label>
                  );
                })
              ) : (
                <div className="rounded-2xl border border-dashed border-outline-variant/20 bg-surface p-5 text-sm text-on-surface-variant">
                  Upload a baseline CV or supporting documents in the Asset Library first.
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-2xl border border-outline-variant/15 bg-surface p-4">
            <div>
              <div>
                <div className="text-sm font-semibold text-on-surface">Primary career source</div>
                <p className="mt-1 text-sm leading-6 text-on-surface-variant">
                  Link an existing baseline CV or supporting document. Upload new files in the
                  Asset Library first.
                </p>
              </div>
            </div>

            <label className="mt-4 block space-y-2">
              <span className="block text-sm font-semibold text-on-surface">Linked career source</span>
              <select
                className="w-full rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface"
                onChange={(event) => onChangeField("masterProfileAssetId", event.target.value)}
                value={masterProfileAssetId}
              >
                <option value="">Choose a baseline CV or supporting document</option>
                {cvLikeAssets.map((item) => (
                  <option key={item.asset_id || item.document_id} value={String(item.asset_id || "")}>
                    {item.display_name} ({assetKindLabel(item.asset_kind)})
                  </option>
                ))}
              </select>
            </label>

            {masterCareerProfileAsset ? (
              <div className="mt-4 rounded-2xl border border-primary/20 bg-primary/10 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="font-semibold text-on-surface">
                    {masterCareerProfileAsset.display_name}
                  </div>
                  <span className="rounded-full bg-surface-container-low px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-on-surface-variant">
                    {assetKindLabel(masterCareerProfileAsset.asset_kind)}
                  </span>
                </div>
                <div className="mt-2 text-sm text-on-surface-variant">
                  {[masterCareerProfileAsset.workspace_name || "Shared", formatDateTime(masterCareerProfileAsset.created_at)]
                    .filter(Boolean)
                    .join(" | ")}
                </div>
              </div>
            ) : (
              <div className="mt-4 rounded-2xl border border-dashed border-outline-variant/20 bg-surface-container-low p-4 text-sm text-on-surface-variant">
                No primary career source linked yet.
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-outline-variant/15 bg-surface p-4">
            <div className="text-sm font-semibold text-on-surface">Imported career context</div>
            <p className="mt-1 text-sm leading-6 text-on-surface-variant">
              This is the long-form source text imported from your detailed CV or master profile.
              Documents handle the baseline facts. The interview below adds the details they miss.
            </p>
            <textarea
              className="mt-4 min-h-40 w-full rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm text-on-surface"
              onChange={(event) => onChangeField("importedCareerContext", event.target.value)}
              placeholder="Imported long-form profile text appears here. You can refine it before saving."
              value={importedCareerContext}
            />
          </div>
        </div>
      </div>
    </section>
  );
}
