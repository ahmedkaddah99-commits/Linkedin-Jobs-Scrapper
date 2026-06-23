import { useMemo, useState } from "react";
import { useSession } from "../../context/SessionContext";
import AdvancedMemorySettings from "./AdvancedMemorySettings";
import FactGroundedMemoryWorkspace from "./FactGroundedMemoryWorkspace";
import MemoryBankTab from "./MemoryBankTab";
import MemoryBuilderHeader from "./MemoryBuilderHeader";
import MemoryBuilderStatusBar from "./MemoryBuilderStatusBar";
import MemoryBuilderTabs from "./MemoryBuilderTabs";
import SourcesTab from "./SourcesTab";
import {
  createManualMemoryCard,
  filterMemoryCards,
  getSourceSummary,
  getTopStatusBarItems,
  MEMORY_BANK_FILTERS,
  MEMORY_BUILDER_TABS,
  sortMemoryCards,
  updateCardCollection,
} from "../../lib/careerMemoryWorkspace";

export default function CareerMemoryBuilderPage({
  assetDocuments = [],
  assetKindLabel,
  cvLikeAssets = [],
  draft,
  formatDateTime,
  guideTo = "/career-memory/guide",
  masterCareerProfileAsset = null,
  onChangeField,
  onSave,
  saveState,
  workspaceScopeTo = "/workspaces?focus=documents",
}) {
  const { request } = useSession();
  const [activeTab, setActiveTab] = useState("build");
  const [memorySearch, setMemorySearch] = useState("");
  const [memoryFilter, setMemoryFilter] = useState("all");
  const [autoEditCardId, setAutoEditCardId] = useState("");
  const memoryCards = useMemo(
    () => sortMemoryCards(draft.generatedMemoryCards || []),
    [draft.generatedMemoryCards],
  );
  const filteredMemoryCards = useMemo(
    () => filterMemoryCards(memoryCards, memorySearch, memoryFilter),
    [memoryCards, memorySearch, memoryFilter],
  );
  const statusBarItems = useMemo(
    () => getTopStatusBarItems(draft, assetDocuments),
    [draft, assetDocuments],
  );
  const sourceSummary = useMemo(
    () => getSourceSummary(draft, assetDocuments),
    [draft, assetDocuments],
  );

  const advancedFields = useMemo(
    () => [
      {
        id: "importedCareerContext",
        label: "Imported long-form profile text",
        description: "The imported source text from your detailed CV or master profile.",
        placeholder: "Imported long-form profile text",
        value: draft.importedCareerContext,
      },
      {
        id: "achievementHighlights",
        label: "Imported achievement highlights",
        description: "Broader notes that are not yet split into individual memory cards.",
        placeholder: "Imported achievement highlights",
        value: draft.achievementHighlights,
      },
      {
        id: "additionalBulletBank",
        label: "Additional bullet bank",
        description: "Extra bullet fragments or alternate bullets that still need curation.",
        placeholder: "Additional bullet bank",
        value: draft.additionalBulletBank,
      },
      {
        id: "professionalHurdlesContext",
        label: "Professional hurdles and transition context",
        description: "Low-frequency narrative context that does not belong in the main Build flow.",
        placeholder: "Professional hurdles and transition context",
        value: draft.professionalHurdlesContext,
      },
      {
        id: "motivationLetterNotes",
        label: "Motivation-letter notes",
        description: "Reusable motivation language and company/industry preferences.",
        placeholder: "Motivation-letter notes",
        value: draft.motivationLetterNotes,
      },
    ],
    [
      draft.additionalBulletBank,
      draft.achievementHighlights,
      draft.importedCareerContext,
      draft.motivationLetterNotes,
      draft.professionalHurdlesContext,
    ],
  );

  function saveCareerMemoryBuilder() {
    onSave();
  }

  function setSelectedAssetIds(assetIds) {
    onChangeField("selectedAssetIds", assetIds);
  }

  function setMasterProfileAssetId(assetId) {
    onChangeField("masterProfileAssetId", assetId);
  }

  function updateMemoryCard(cardId, updates) {
    onChangeField(
      "generatedMemoryCards",
      updateCardCollection(draft.generatedMemoryCards || [], cardId, updates),
    );
    if (autoEditCardId === cardId) {
      setAutoEditCardId("");
    }
  }

  function deleteMemoryCard(cardId) {
    onChangeField(
      "generatedMemoryCards",
      (draft.generatedMemoryCards || []).filter((card) => card.id !== cardId),
    );
    if (autoEditCardId === cardId) {
      setAutoEditCardId("");
    }
  }

  function handleManualMemory() {
    const card = createManualMemoryCard();
    onChangeField("generatedMemoryCards", [card, ...(draft.generatedMemoryCards || [])]);
    setActiveTab("memory_bank");
    setAutoEditCardId(card.id);
  }

  function handleContinueInterview() {
    setActiveTab("build");
  }

  function toggleSelectedAsset(assetId) {
    const nextIds = draft.selectedAssetIds.includes(assetId)
      ? draft.selectedAssetIds.filter((item) => item !== assetId)
      : [...draft.selectedAssetIds, assetId];
    setSelectedAssetIds(nextIds);
  }

  return (
    <div className="space-y-6">
      <MemoryBuilderHeader
        onContinueInterview={handleContinueInterview}
        saveState={saveState}
      />

      <MemoryBuilderStatusBar items={statusBarItems} />

      <MemoryBuilderTabs
        activeTab={activeTab}
        onChangeTab={setActiveTab}
        onSave={saveCareerMemoryBuilder}
        saveState={saveState}
        tabs={MEMORY_BUILDER_TABS}
      />

      {activeTab === "build" ? (
        <FactGroundedMemoryWorkspace request={request} selectedAssetIds={draft.selectedAssetIds} />
      ) : null}

      {activeTab === "memory_bank" ? (
        <MemoryBankTab
          autoEditCardId={autoEditCardId}
          cards={filteredMemoryCards}
          filters={MEMORY_BANK_FILTERS}
          onAddManual={handleManualMemory}
          onCardDelete={deleteMemoryCard}
          onCardSave={(card) => updateMemoryCard(card.id, card)}
          onChangeFilter={setMemoryFilter}
          onSearchChange={setMemorySearch}
          searchValue={memorySearch}
          selectedFilter={memoryFilter}
        />
      ) : null}

      {activeTab === "sources" ? (
        <SourcesTab
          assetDocuments={assetDocuments}
          assetKindLabel={assetKindLabel}
          cvLikeAssets={cvLikeAssets}
          formatDateTime={formatDateTime}
          importedCareerContext={draft.importedCareerContext}
          masterCareerProfileAsset={masterCareerProfileAsset}
          masterProfileAssetId={draft.masterProfileAssetId}
          onChangeImportedCareerContext={(value) => onChangeField("importedCareerContext", value)}
          onChangeMasterProfile={setMasterProfileAssetId}
          onToggleAsset={toggleSelectedAsset}
          selectedAssetIds={draft.selectedAssetIds}
          sourceSummary={sourceSummary}
        />
      ) : null}

      {activeTab === "advanced" ? (
        <AdvancedMemorySettings
          advancedFields={advancedFields}
          guideTo={guideTo}
          onChangeField={onChangeField}
          workspaceScopeTo={workspaceScopeTo}
        />
      ) : null}
    </div>
  );
}
