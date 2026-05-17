import GuidedInterviewPanel from "./GuidedInterviewPanel";
import LatestMemoryCard from "./LatestMemoryCard";
import NextBestActions from "./NextBestActions";
import TailoringProgressPanel from "./TailoringProgressPanel";

export default function BuildWorkspace({
  answer,
  currentStep,
  currentStepIndex,
  draftMemoryCard,
  interviewState,
  latestMemoryCard,
  nextBestActions,
  onAddMetricToDraft,
  onAnswerChange,
  onContinue,
  onDiscardDraft,
  onImproveDraft,
  onLatestAddMetric,
  onLatestEdit,
  onLatestToggleUseInCv,
  onLatestToggleUseInLetter,
  onSaveDraft,
  onSelectTrigger,
  onStartAction,
  previousAnswers,
  questionSet,
  tailoringChecklist,
  triggers,
}) {
  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <GuidedInterviewPanel
          answer={answer}
          currentStep={currentStep}
          currentStepIndex={currentStepIndex}
          draftMemoryCard={draftMemoryCard}
          interviewState={interviewState}
          onAddMetric={onAddMetricToDraft}
          onAnswerChange={onAnswerChange}
          onContinue={onContinue}
          onDiscardDraft={onDiscardDraft}
          onImproveDraft={onImproveDraft}
          onSaveDraft={onSaveDraft}
          onSelectTrigger={onSelectTrigger}
          previousAnswers={previousAnswers}
          questionSet={questionSet}
          triggers={triggers}
        />
        <div className="space-y-6">
          <TailoringProgressPanel checklist={tailoringChecklist} />
          <LatestMemoryCard
            card={latestMemoryCard}
            onAddMetric={onLatestAddMetric}
            onEdit={onLatestEdit}
            onToggleUseInCv={onLatestToggleUseInCv}
            onToggleUseInLetter={onLatestToggleUseInLetter}
          />
        </div>
      </div>

      <NextBestActions items={nextBestActions} onStart={onStartAction} />
    </div>
  );
}

