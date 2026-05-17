import MasterProfilePanel from "./MasterProfilePanel";
import SourceAssetSelector from "./SourceAssetSelector";
import SourceDocumentsSummary from "./SourceDocumentsSummary";

export default function SourcesTab({
  assetDocuments = [],
  assetKindLabel,
  cvLikeAssets = [],
  formatDateTime,
  importedCareerContext,
  masterCareerProfileAsset,
  masterProfileAssetId,
  masterProfileUploadState,
  onChangeImportedCareerContext,
  onChangeMasterProfile,
  onToggleAsset,
  onUploadMasterProfile,
  selectedAssetIds = [],
  sourceSummary,
}) {
  return (
    <div className="space-y-6">
      <SourceDocumentsSummary summary={sourceSummary} />
      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <SourceAssetSelector
          assetDocuments={assetDocuments}
          assetKindLabel={assetKindLabel}
          formatDateTime={formatDateTime}
          onToggleAsset={onToggleAsset}
          selectedAssetIds={selectedAssetIds}
        />
        <MasterProfilePanel
          assetKindLabel={assetKindLabel}
          cvLikeAssets={cvLikeAssets}
          importedCareerContext={importedCareerContext}
          masterCareerProfileAsset={masterCareerProfileAsset}
          masterProfileAssetId={masterProfileAssetId}
          masterProfileUploadState={masterProfileUploadState}
          onChangeImportedCareerContext={onChangeImportedCareerContext}
          onChangeMasterProfile={onChangeMasterProfile}
          onUploadMasterProfile={onUploadMasterProfile}
        />
      </div>
    </div>
  );
}
