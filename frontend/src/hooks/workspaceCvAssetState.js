export function normalizeWorkspaceCvAssetStatus(item) {
  return String(item?.display_status || item?.status || "ready").trim().toLowerCase() || "ready";
}

export function toWorkspaceCvAssetOption(item) {
  const status = normalizeWorkspaceCvAssetStatus(item);
  const displayName = String(item?.display_name || "").trim();
  return {
    value: item.asset_id,
    label: status === "ready" ? displayName : `${displayName} (${status})`,
    assetId: item.asset_id,
    createdAt: item.created_at,
    downloadUrl: item.download_url,
    sourceOrigin: item.source_origin,
    status,
    previewProfile: item.preview_profile || null,
  };
}

export function selectedWorkspaceCvMissingFromPayload(cvAssetsPayload, selectedAssetId) {
  const normalizedSelectedAssetId = String(selectedAssetId || "").trim();
  if (!cvAssetsPayload || !normalizedSelectedAssetId) {
    return false;
  }
  return !(cvAssetsPayload.documents || []).some(
    (item) =>
      item.asset_kind === "workspace_cv" &&
      String(item.asset_id || "").trim() === normalizedSelectedAssetId,
  );
}
