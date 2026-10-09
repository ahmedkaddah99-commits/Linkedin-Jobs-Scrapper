export default function SourceAssetSelector({
  assetDocuments = [],
  assetKindLabel,
  formatDateTime,
  onToggleAsset,
  selectedAssetIds = [],
}) {
  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
      <h3 className="font-headline text-lg font-bold text-on-surface">Available source assets</h3>
      <div className="mt-4 max-h-[30rem] space-y-3 overflow-y-auto pr-1">
        {assetDocuments.length ? (
          assetDocuments.map((asset) => {
            const assetId = String(asset.asset_id || "");
            const selected = selectedAssetIds.includes(assetId);
            return (
              <label
                className={[
                  "flex cursor-pointer items-start gap-3 rounded-2xl border p-4 transition-colors",
                  selected
                    ? "border-primary/30 bg-primary/10"
                    : "border-outline-variant/15 bg-surface hover:bg-surface-container-low",
                ].join(" ")}
                key={asset.document_id}
              >
                <input
                  checked={selected}
                  className="mt-1 h-4 w-4 rounded border-outline-variant/40 text-primary focus:ring-primary"
                  onChange={() => onToggleAsset(assetId)}
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
            Upload a baseline CV or supporting files in Asset Library first.
          </div>
        )}
      </div>
    </section>
  );
}

