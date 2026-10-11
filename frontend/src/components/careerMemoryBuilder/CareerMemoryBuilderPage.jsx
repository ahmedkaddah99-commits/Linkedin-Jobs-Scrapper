import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useSession } from "../../context/SessionContext";
import AdvancedMemorySettings from "./AdvancedMemorySettings";
import CareerTimelineTab from "./CareerTimelineTab";
import OverviewTab from "./OverviewTab";
import UseForApplicationTab from "./UseForApplicationTab";
import CareerProfileEvidenceReview from "../careerProfile/CareerProfileEvidenceReview";
import BuildWorkspace from "./BuildWorkspace";
import MemoryBankTab from "./MemoryBankTab";
import MemoryBuilderHeader from "./MemoryBuilderHeader";
import MemoryBuilderStatusBar from "./MemoryBuilderStatusBar";
import MemoryBuilderTabs from "./MemoryBuilderTabs";
import SourcesTab from "./SourcesTab";
import {
  buildTailoringChecklist,
  createDraftReviewWarnings,
  createInterviewState,
  createManualMemoryCard,
  filterMemoryCards,
  generateDraftMemoryCard,
  getLatestMemoryCard,
  getNextBestActions,
  getQuestionSetDefinition,
  getQuestionStepAnswer,
  getSourceSummary,
  getTopStatusBarItems,
  MEMORY_BANK_FILTERS,
  LEGACY_TAB_MAP,
  MEMORY_BUILDER_TABS,
  MEMORY_TRIGGER_CHIPS,
  normalizeCareerMemoryCard,
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
  const [activeTab, setActiveTab] = useState("overview");
  const [memorySearch, setMemorySearch] = useState("");
  const [memoryFilter, setMemoryFilter] = useState("all");
  const [autoEditCardId, setAutoEditCardId] = useState("");
  const [searchParams] = useSearchParams();

  // CP-035: Legacy tab redirect via URL param.
  useEffect(() => {
    const legacyTab = searchParams.get("tab");
    if (legacyTab && LEGACY_TAB_MAP[legacyTab]) {
      setActiveTab(LEGACY_TAB_MAP[legacyTab]);
    }
  }, [searchParams]);
  const [currentAnswer, setCurrentAnswer] = useState("");
  const [interviewState, setInterviewState] = useState(() => createInterviewState());
  const questionSet = useMemo(
    () => getQuestionSetDefinition(interviewState.activeQuestionSet),
    [interviewState.activeQuestionSet],
  );
  const currentStep = questionSet.steps[interviewState.currentStepIndex] || questionSet.steps[0];
  const latestMemoryCard = useMemo(
    () => getLatestMemoryCard(draft.generatedMemoryCards),
    [draft.generatedMemoryCards],
  );
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
  const tailoringChecklist = useMemo(
    () => buildTailoringChecklist(draft, assetDocuments),
    [draft, assetDocuments],
  );
  const nextBestActions = useMemo(
    () => getNextBestActions(draft, assetDocuments),
    [draft, assetDocuments],
  );
  const readinessItems = useMemo(
    () => {
      if (!tailoringChecklist) return [];
      return [
        { title: "Sources", status: tailoringChecklist.baselineConnected ? "Ready" : "Needs setup", value: `${tailoringChecklist.selectedAssetCount} selected / ${tailoringChecklist.totalSources} available`, description: "" },
        { title: "Evidence", status: tailoringChecklist.verifiedCount > 0 ? "Ready" : "Needs setup", value: `${tailoringChecklist.awaitingReviewCount} awaiting / ${tailoringChecklist.verifiedCount} verified`, description: "" },
        { title: "Experiences", status: tailoringChecklist.mappedCount > 0 ? "Ready" : "Needs setup", value: `${tailoringChecklist.mappedCount} mapped / ${tailoringChecklist.unmappedCount} unmapped`, description: "" },
        { title: "Ready", status: tailoringChecklist.readyForTailoring ? "Ready for tailoring" : "Needs setup", value: tailoringChecklist.summary, description: "" },
      ];
    },
    [tailoringChecklist],
  );

  const sourceSummary = useMemo(
    () => getSourceSummary(draft, assetDocuments),
    [draft, assetDocuments],
  );
  const previousAnswers = useMemo(
    () =>
      questionSet.steps
        .slice(0, interviewState.currentStepIndex)
        .map((step, index) => ({
          id: step.id,
          label: `Step ${index + 1}`,
          answer: getQuestionStepAnswer(interviewState.answers, step.id),
        }))
        .filter((item) => item.answer),
    [interviewState.answers, interviewState.currentStepIndex, questionSet.steps],
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

  useEffect(() => {
    if (interviewState.isReviewingDraft) {
      return;
    }
    setCurrentAnswer(getQuestionStepAnswer(interviewState.answers, currentStep.id));
  }, [currentStep.id, interviewState.answers, interviewState.isReviewingDraft]);

  function saveCareerMemoryBuilder() {
    onSave();
  }

  function setSelectedAssetIds(assetIds) {
    onChangeField("selectedAssetIds", assetIds);
  }

  function setMasterProfileAssetId(assetId) {
    onChangeField("masterProfileAssetId", assetId);
  }

  function startGuidedInterview(questionSetType = "story_recovery") {
    const nextState = createInterviewState(questionSetType);
    setInterviewState(nextState);
    setCurrentAnswer("");
    setActiveTab("overview");
  }

  function selectMemoryTrigger(trigger) {
    setInterviewState((current) => ({
      ...current,
      selectedTrigger: trigger,
    }));
  }

  function answerCurrentQuestion(answer) {
    const normalized = String(answer || "").trim();
    return {
      ...interviewState.answers,
      [currentStep.id]: normalized,
    };
  }

  function generateDraftMemoryCardFromAnswers(answers) {
    return normalizeCareerMemoryCard(
      generateDraftMemoryCard({
        questionSetType: interviewState.activeQuestionSet,
        answers,
        selectedTrigger: interviewState.selectedTrigger,
        existingCount: (draft.generatedMemoryCards || []).length,
      }),
    );
  }

  function handleContinueStep() {
    const answers = answerCurrentQuestion(currentAnswer);
    if (interviewState.currentStepIndex >= questionSet.steps.length - 1) {
      const draftCard = generateDraftMemoryCardFromAnswers(answers);
      setInterviewState((current) => ({
        ...current,
        answers,
        draftMemoryCard: {
          ...draftCard,
          missingDetails: createDraftReviewWarnings(draftCard),
        },
        isReviewingDraft: true,
      }));
      return;
    }
    const nextStepIndex = interviewState.currentStepIndex + 1;
    const nextStep = questionSet.steps[nextStepIndex];
    setInterviewState((current) => ({
      ...current,
      answers,
      currentStepIndex: nextStepIndex,
    }));
    setCurrentAnswer(getQuestionStepAnswer(answers, nextStep.id));
  }

  function saveDraftMemoryCard(card) {
    const nextCard = normalizeCareerMemoryCard({
      ...card,
      createdAt: card.createdAt || new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
    onChangeField("generatedMemoryCards", [nextCard, ...(draft.generatedMemoryCards || [])]);
    setInterviewState(createInterviewState(interviewState.activeQuestionSet));
    setCurrentAnswer("");
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

  function addMetricToMemory(cardId) {
    setActiveTab("evidence_library");
    setAutoEditCardId(cardId);
  }

  function handleAddMetricToDraft() {
    const impactStepIndex = questionSet.steps.findIndex((step) => step.id === "impact");
    setInterviewState((current) => ({
      ...current,
      isReviewingDraft: false,
      draftMemoryCard: null,
      currentStepIndex: impactStepIndex >= 0 ? impactStepIndex : current.currentStepIndex,
    }));
    setCurrentAnswer(getQuestionStepAnswer(interviewState.answers, "impact"));
  }

  function handleImproveDraft() {
    const firstMissing = questionSet.steps.findIndex(
      (step) => !getQuestionStepAnswer(interviewState.answers, step.id),
    );
    const fallbackIndex = firstMissing >= 0 ? firstMissing : 0;
    setInterviewState((current) => ({
      ...current,
      isReviewingDraft: false,
      draftMemoryCard: null,
      currentStepIndex: fallbackIndex,
    }));
    setCurrentAnswer(getQuestionStepAnswer(interviewState.answers, questionSet.steps[fallbackIndex].id));
  }

  function handleDiscardDraft() {
    startGuidedInterview(interviewState.activeQuestionSet);
  }

  function handleManualMemory() {
    const card = createManualMemoryCard();
    onChangeField("generatedMemoryCards", [card, ...(draft.generatedMemoryCards || [])]);
    setActiveTab("evidence_library");
    setAutoEditCardId(card.id);
  }

  function handleContinueInterview() {
    setActiveTab("overview");
  }

  function handleToggleUseInCv(cardId) {
    const card = (draft.generatedMemoryCards || []).find((item) => item.id === cardId);
    if (!card) {
      return;
    }
    updateMemoryCard(cardId, { useInCv: !card.useInCv });
  }

  function handleToggleUseInLetter(cardId) {
    const card = (draft.generatedMemoryCards || []).find((item) => item.id === cardId);
    if (!card) {
      return;
    }
    updateMemoryCard(cardId, { useInLetter: !card.useInLetter });
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

      {activeTab === "overview" ? (
        <OverviewTab
          baselineCvAssetId={draft.masterProfileAssetId}
          boundWorkspaceId=""
          boundWorkspaceName=""
          nextBestActions={nextBestActions}
          onContinueInterview={handleContinueInterview}
          onStartAction={startGuidedInterview}
          profileName="Career Profile"
          profileStatus=""
          readinessItems={readinessItems}
          statusBarItems={statusBarItems}
          tailoringChecklist={tailoringChecklist}
          workspaceBindingLabel=""
        />
      ) : null}

      {/* Build workspace kept for backwards compatibility */}
      {activeTab === "build" ? (
        <BuildWorkspace
          answer={currentAnswer}
          currentStep={currentStep}
          currentStepIndex={interviewState.currentStepIndex}
          draftMemoryCard={interviewState.draftMemoryCard}
          interviewState={interviewState}
          latestMemoryCard={latestMemoryCard}
          nextBestActions={nextBestActions}
          onAddMetricToDraft={handleAddMetricToDraft}
          onAnswerChange={setCurrentAnswer}
          onContinue={handleContinueStep}
          onDiscardDraft={handleDiscardDraft}
          onImproveDraft={handleImproveDraft}
          onLatestAddMetric={addMetricToMemory}
          onLatestEdit={(cardId) => {
            setActiveTab("evidence_library");
            setAutoEditCardId(cardId);
          }}
          onLatestToggleUseInCv={handleToggleUseInCv}
          onLatestToggleUseInLetter={handleToggleUseInLetter}
          onSaveDraft={saveDraftMemoryCard}
          onSelectTrigger={selectMemoryTrigger}
          onStartAction={startGuidedInterview}
          previousAnswers={previousAnswers}
          questionSet={questionSet}
          request={request}
          selectedAssetIds={draft.selectedAssetIds}
          tailoringChecklist={tailoringChecklist}
          triggers={MEMORY_TRIGGER_CHIPS}
        />
      ) : null}

      {activeTab === "evidence_library" ? (
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

      {activeTab === "settings" ? (
        <AdvancedMemorySettings
          advancedFields={advancedFields}
          guideTo={guideTo}
          onChangeField={onChangeField}
          workspaceScopeTo={workspaceScopeTo}
        />
      ) : null}
    
      {activeTab === "review_evidence" ? (
        <CareerProfileEvidenceReview
          profileId=""
          profileName="Career Profile"
        />
      ) : null}

      {activeTab === "career_timeline" ? (
        <CareerTimelineTab
          cards={memoryCards}
          onEditCard={(cardId) => { setActiveTab("evidence_library"); setAutoEditCardId(cardId); }}
        />
      ) : null}

      {activeTab === "use_for_application" ? (
        <UseForApplicationTab
          baselineCvAssetId={draft.masterProfileAssetId}
          boundWorkspaceId=""
          boundWorkspaceName=""
          cards={memoryCards}
        />
      ) : null}
</div>
  );
}
