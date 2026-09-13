import InterviewQuestionStep from "./InterviewQuestionStep";
import MemoryDraftReview from "./MemoryDraftReview";

export default function GuidedInterviewPanel({
  answer,
  currentStep,
  currentStepIndex,
  draftMemoryCard,
  interviewState,
  onAddMetric,
  onAnswerChange,
  onContinue,
  onDiscardDraft,
  onImproveDraft,
  onSaveDraft,
  onSelectTrigger,
  previousAnswers,
  questionSet,
  triggers,
}) {
  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
      <div>
        <h3 className="font-headline text-2xl font-bold text-on-surface">{questionSet.title}</h3>
        <p className="mt-2 text-sm leading-6 text-on-surface-variant">{questionSet.description}</p>
      </div>

      <div className="mt-6">
        {interviewState.isReviewingDraft ? (
          <MemoryDraftReview
            card={draftMemoryCard}
            onAddMetric={onAddMetric}
            onDiscard={onDiscardDraft}
            onImprove={onImproveDraft}
            onSave={onSaveDraft}
          />
        ) : (
          <InterviewQuestionStep
            activeTrigger={interviewState.selectedTrigger}
            answer={answer}
            onAnswerChange={onAnswerChange}
            onContinue={onContinue}
            onSelectTrigger={onSelectTrigger}
            previousAnswers={previousAnswers}
            question={currentStep.question}
            stepIndex={currentStepIndex}
            totalSteps={questionSet.steps.length}
            triggers={triggers}
          />
        )}
      </div>
    </section>
  );
}

