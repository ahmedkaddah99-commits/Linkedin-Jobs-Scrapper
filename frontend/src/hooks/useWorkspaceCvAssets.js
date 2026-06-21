import { useMemo } from "react";
import {
  buildCvStudioHtml,
  buildWorkspacePreviewDocuments,
  buildWorkspacePreviewState,
} from "../lib/cvStudio";

function normalizeStringList(value) {
  return (Array.isArray(value) ? value : [])
    .map((item) => String(item || "").trim())
    .filter(Boolean);
}

export function deriveFocusedWorkspaceCvDocuments(workspace, documentsPayload) {
  if (!workspace) {
    return [];
  }
  const selectedAssetId = String(workspace.settings?.workspace_cv_asset_id || "").trim();
  return (documentsPayload?.documents || [])
    .filter((document) => {
      const assetKind = String(document.asset_kind || "").trim();
      if (assetKind === "generated_cv") {
        return String(document.workspace_id || "").trim() === workspace.id;
      }
      if (assetKind === "workspace_cv") {
        return selectedAssetId && String(document.asset_id || "").trim() === selectedAssetId;
      }
      return false;
    })
    .sort((left, right) => String(right.created_at || "").localeCompare(String(left.created_at || "")))
    .slice(0, 6);
}

export function useWorkspaceCvAssets({ cvAssetsPayload, formSettings, settingsPayload }) {
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
  const readyWorkspaceCvAssets = useMemo(
    () => workspaceCvAssets.filter((item) => String(item.status || "ready").toLowerCase() === "ready"),
    [workspaceCvAssets],
  );
  const workspaceCvAssetIds = useMemo(
    () => new Set(readyWorkspaceCvAssets.map((item) => item.value)),
    [readyWorkspaceCvAssets],
  );
  const selectedWorkspaceCvAsset = useMemo(() => {
    const selectedAssetId = String(formSettings.workspace_cv_asset_id || "").trim();
    if (!selectedAssetId) {
      return null;
    }
    return readyWorkspaceCvAssets.find((item) => item.value === selectedAssetId) || null;
  }, [formSettings.workspace_cv_asset_id, readyWorkspaceCvAssets]);
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
      website: previewProfile.website || sharedProfile.website || "",
      linkedin_url: previewProfile.linkedin_url || sharedProfile.linkedin_url || "",
      github_url: previewProfile.github_url || sharedProfile.github_url || "",
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
  const selectedCvCustomSections = useMemo(() => {
    const previewProfile = selectedWorkspaceCvAsset?.previewProfile || {};
    const detectedSections = Array.isArray(previewProfile.detected_custom_sections)
      ? previewProfile.detected_custom_sections
      : [];
    if (detectedSections.length) {
      return detectedSections;
    }
    return Array.isArray(previewProfile.custom_sections) ? previewProfile.custom_sections : [];
  }, [selectedWorkspaceCvAsset]);
  const effectiveLanguageLines = useMemo(() => {
    const previewLanguageLines = normalizeStringList(selectedWorkspaceCvAsset?.previewProfile?.languages);
    if (previewLanguageLines.length) {
      return previewLanguageLines;
    }
    return normalizeStringList(settingsPayload?.profile?.languages);
  }, [selectedWorkspaceCvAsset, settingsPayload?.profile?.languages]);
  const effectiveDocumentPreviewDocuments = useMemo(
    () => buildWorkspacePreviewDocuments(sharedDocumentDefaults, formSettings),
    [formSettings, sharedDocumentDefaults],
  );
  const effectiveBrowserPreviewState = useMemo(
    () =>
      mergedPreviewProfile
        ? buildWorkspacePreviewState(
            mergedPreviewProfile,
            sharedDocumentDefaults,
            formSettings,
          )
        : null,
    [formSettings, mergedPreviewProfile, sharedDocumentDefaults],
  );
  const effectiveBrowserPreviewHtml = useMemo(
    () =>
      effectiveBrowserPreviewState
        ? buildCvStudioHtml(effectiveBrowserPreviewState, { forIframe: true })
        : "",
    [effectiveBrowserPreviewState],
  );
  const workspaceCvAssetsLoaded = cvAssetsPayload !== undefined;
  const selectedWorkspaceCvMissing = Boolean(
    workspaceCvAssetsLoaded &&
      formSettings.workspace_cv_asset_id &&
      !workspaceCvAssetIds.has(formSettings.workspace_cv_asset_id),
  );

  return {
    effectiveBrowserPreviewHtml,
    effectiveDocumentPreviewDocuments,
    effectiveLanguageLines,
    mergedPreviewProfile,
    selectedCvCustomSections,
    selectedWorkspaceCvAsset,
    selectedWorkspaceCvMissing,
    sharedDocumentDefaults,
    workspaceCvAssetIds,
    workspaceCvAssets: readyWorkspaceCvAssets,
    allWorkspaceCvAssets: workspaceCvAssets,
    workspaceCvAssetsLoaded,
  };
}
