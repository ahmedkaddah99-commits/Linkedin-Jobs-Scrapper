import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import AchievementBank from "./AchievementBank";
import CareerMemoryCard from "./CareerMemoryCard";
import GuidedCareerInterview from "./GuidedCareerInterview";
import MissingContextCards from "./MissingContextCards";
import MotivationStoryBank from "./MotivationStoryBank";
import ReadinessSummary from "./ReadinessSummary";
import SourceDocumentsPanel from "./SourceDocumentsPanel";
import {
  createBlankMemoryCard,
  createInterviewMemoryCard,
  filterCardsByCategories,
  getMissingContextRecommendations,
  GUIDED_INTERVIEW_OPENING_PROMPT,
  INTERVIEW_CHIPS,
  normalizeCareerMemoryCard,
  summarizeReadiness,
} from "../../lib/careerMemoryBuilder";

function buildMessage(id, role, content) {
  return { id, role, content };
}

export default function CareerMemoryBuilder({
  assetDocuments = [],
  assetKindLabel,
  cvLikeAssets = [],
  draft,
  formatDateTime,
  guideTo = "/career-memory/guide",
  manageDocumentsTo = "/documents",
  masterCareerProfileAsset = null,
  onChangeField,
  onSave,
  onToggleSourceAsset,
  saveState,
  workspaceScopeTo = "/workspaces?focus=documents",
}) {
  const interviewRef = useRef(null);
  const [interviewStarted, setInterviewStarted] = useState(false);
  const [activeChipId, setActiveChipId] = useState(INTERVIEW_CHIPS[0].id);
  const [answer, setAnswer] = useState("");
  const [autoEditCardId, setAutoEditCardId] = useState("");
  const [messages, setMessages] = useState([
    buildMessage("opening", "assistant", GUIDED_INTERVIEW_OPENING_PROMPT),
  ]);

  const readinessItems = useMemo(
    () => summarizeReadiness(draft, assetDocuments),
    [draft, assetDocuments],
  );
  const missingContextItems = useMemo(() => getMissingContextRecommendations(draft), [draft]);
  const achievementCards = useMemo(
    () =>
      filterCardsByCategories(draft.generatedMemoryCards, [
        "achievement",
        "project",
        "stakeholder_story",
        "tool_system_experience",
      ]),
    [draft.generatedMemoryCards],
  );
  const motivationCards = useMemo(
    () => filterCardsByCategories(draft.generatedMemoryCards, ["motivation", "challenge"]),
    [draft.generatedMemoryCards],
  );
  const recentCards = useMemo(
    () => [...(draft.generatedMemoryCards || [])].slice(0, 4),
    [draft.generatedMemoryCards],
  );

  function updateCards(nextCards) {
    onChangeField("generatedMemoryCards", nextCards);
  }

  function appendAssistantMessage(content) {
    setMessages((current) => [
      ...current,
      buildMessage(`assistant_${Date.now()}_${current.length}`, "assistant", content),
    ]);
  }

  function focusInterview() {
    interviewRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function handleUsePrompt(chipId) {
    const chip = INTERVIEW_CHIPS.find((item) => item.id === chipId) || INTERVIEW_CHIPS[0];
    setInterviewStarted(true);
    setActiveChipId(chip.id);
    appendAssistantMessage(chip.focusPrompt);
    focusInterview();
  }

  function handleStartInterview(chipId) {
    handleUsePrompt(chipId || activeChipId);
  }

  function handleSubmitAnswer() {
    if (!answer.trim()) {
      return;
    }
    const nextCard = createInterviewMemoryCard({
      answer,
      chipId: activeChipId,
      existingCount: draft.generatedMemoryCards.length,
    });
    updateCards([nextCard, ...(draft.generatedMemoryCards || [])]);
    setMessages((current) => [
      ...current,
      buildMessage(`user_${Date.now()}_${current.length}`, "user", answer.trim()),
      buildMessage(
        `assistant_${Date.now()}_${current.length + 1}`,
        "assistant",
        `${nextCard.title} is now saved as a career memory card. Add a metric if you can, or pick another memory trigger to keep building evidence.`,
      ),
    ]);
    setAnswer("");
  }

  function handleSaveCard(updatedCard) {
    updateCards(
      draft.generatedMemoryCards.map((card) =>
        card.id === updatedCard.id ? normalizeCareerMemoryCard(updatedCard) : card,
      ),
    );
    if (autoEditCardId === updatedCard.id) {
      setAutoEditCardId("");
    }
  }

  function handleDeleteCard(cardId) {
    updateCards(draft.generatedMemoryCards.filter((card) => card.id !== cardId));
    if (autoEditCardId === cardId) {
      setAutoEditCardId("");
    }
  }

  function addManualCard(category) {
    const nextCard = createBlankMemoryCard({ category });
    updateCards([nextCard, ...(draft.generatedMemoryCards || [])]);
    setAutoEditCardId(nextCard.id);
  }

  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border border-outline-variant/20 bg-surface-container-lowest p-7 shadow-soft">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
          <div className="max-w-4xl">
            <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-primary">
              Career Memory Builder
            </div>
            <h2 className="mt-4 font-headline text-[2.35rem] font-extrabold leading-tight tracking-tight text-on-surface">
              Career Memory Builder
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-on-surface-variant">
              Your documents tell part of your story. Add the missing achievements, context, and
              motivation that help Runr tailor stronger applications.
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              {[
                "1. Upload documents in Asset Library",
                "2. Add what documents do not say here",
                "3. Let Runr tailor stronger CVs, letters, and answers",
              ].map((step) => (
                <span
                  className="rounded-full bg-surface-container-low px-3 py-1.5 text-sm text-on-surface"
                  key={step}
                >
                  {step}
                </span>
              ))}
            </div>
          </div>

          <div className="flex w-full flex-col gap-3 xl:max-w-xs">
            <button
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90"
              onClick={() => handleStartInterview(activeChipId)}
              type="button"
            >
              Start guided career interview
              <span className="material-symbols-outlined text-[18px]">forum</span>
            </button>
            <button
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-surface-container-low px-5 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
              onClick={() => addManualCard("achievement")}
              type="button"
            >
              Add achievement manually
              <span className="material-symbols-outlined text-[18px]">add</span>
            </button>
            <Link
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-surface-container-low px-5 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
              to={manageDocumentsTo}
            >
              Manage source documents
              <span className="material-symbols-outlined text-[18px]">folder_open</span>
            </Link>
            <button
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-gradient-to-br from-primary to-primary-container px-5 py-3 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={saveState.saving}
              onClick={onSave}
              type="button"
            >
              {saveState.saving ? "Saving..." : "Save Career Memory Builder"}
            </button>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap gap-3">
          <Link
            className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:text-primary-container"
            to={guideTo}
          >
            <span className="material-symbols-outlined text-[16px]">help</span>
            Why this improves tailoring
          </Link>
          <Link
            className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:text-primary-container"
            to={workspaceScopeTo}
          >
            <span className="material-symbols-outlined text-[16px]">tune</span>
            Review workspace scope
          </Link>
        </div>

        {saveState.message ? <p className="mt-4 text-sm text-primary">{saveState.message}</p> : null}
        {saveState.error ? <p className="mt-4 text-sm text-error">{saveState.error}</p> : null}
      </section>

      <ReadinessSummary items={readinessItems} />

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <SourceDocumentsPanel
          assetDocuments={assetDocuments}
          assetKindLabel={assetKindLabel}
          cvLikeAssets={cvLikeAssets}
          formatDateTime={formatDateTime}
          importedCareerContext={draft.importedCareerContext}
          manageDocumentsTo={manageDocumentsTo}
          masterCareerProfileAsset={masterCareerProfileAsset}
          masterProfileAssetId={draft.masterProfileAssetId}
          onChangeField={onChangeField}
          onToggleSourceAsset={onToggleSourceAsset}
          selectedAssetIds={draft.selectedAssetIds}
        />
        <MissingContextCards items={missingContextItems} onHelp={(item) => handleUsePrompt(item.chipId)} />
      </div>

      <div ref={interviewRef}>
        <GuidedCareerInterview
          activeChipId={activeChipId}
          answer={answer}
          chips={INTERVIEW_CHIPS}
          interviewStarted={interviewStarted}
          messages={messages}
          onAnswerChange={setAnswer}
          onSelectChip={handleUsePrompt}
          onStart={handleStartInterview}
          onSubmit={handleSubmitAnswer}
        />
      </div>

      <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="font-headline text-xl font-bold text-on-surface">Saved Career Memory</h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-on-surface-variant">
              Every useful answer becomes a structured memory card that Runr can later turn into
              stronger CV bullets, cover-letter angles, and application answers.
            </p>
          </div>
          <div className="text-sm text-on-surface-variant">
            {draft.generatedMemoryCards.length} saved memory
            {draft.generatedMemoryCards.length === 1 ? "" : " cards"}
          </div>
        </div>
        <div className="mt-5 space-y-4">
          {recentCards.length ? (
            recentCards.map((card) => (
              <CareerMemoryCard
                autoEdit={card.id === autoEditCardId}
                card={card}
                key={card.id}
                onDelete={handleDeleteCard}
                onSave={handleSaveCard}
              />
            ))
          ) : (
            <div className="rounded-2xl border border-dashed border-outline-variant/20 bg-surface p-6 text-sm leading-6 text-on-surface-variant">
              No memory cards yet. Start the interview to convert rough memories into reusable
              assets.
            </div>
          )}
        </div>
        {draft.generatedMemoryCards.length > recentCards.length ? (
          <div className="mt-4 text-sm text-on-surface-variant">
            Showing the latest {recentCards.length} cards. The full set remains organized below by
            bank.
          </div>
        ) : null}
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <AchievementBank
          achievementHighlights={draft.achievementHighlights}
          additionalBulletBank={draft.additionalBulletBank}
          autoEditCardId={autoEditCardId}
          cards={achievementCards}
          onChangeField={onChangeField}
          onAddManual={() => addManualCard("achievement")}
          onCardDelete={handleDeleteCard}
          onCardSave={handleSaveCard}
          onUsePrompt={handleUsePrompt}
        />
        <MotivationStoryBank
          autoEditCardId={autoEditCardId}
          cards={motivationCards}
          motivationLetterNotes={draft.motivationLetterNotes}
          onAddManual={() => addManualCard("motivation")}
          onCardDelete={handleDeleteCard}
          onCardSave={handleSaveCard}
          onChangeField={onChangeField}
          onUsePrompt={handleUsePrompt}
          professionalHurdlesContext={draft.professionalHurdlesContext}
        />
      </div>
    </div>
  );
}
