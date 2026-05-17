import MemoryTriggerChips from "./MemoryTriggerChips";

export default function InterviewQuestionStep({
  activeTrigger,
  answer,
  onAnswerChange,
  onContinue,
  onSelectTrigger,
  previousAnswers = [],
  question,
  stepIndex,
  totalSteps,
  triggers = [],
}) {
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-semibold text-on-surface">
          Step {stepIndex + 1} of {totalSteps}
        </div>
        <div className="h-2 flex-1 rounded-full bg-surface-container-low">
          <div
            className="h-2 rounded-full bg-primary transition-all"
            style={{ width: `${((stepIndex + 1) / totalSteps) * 100}%` }}
          />
        </div>
      </div>

      <div className="rounded-3xl border border-outline-variant/15 bg-surface p-5">
        <div className="text-base font-semibold leading-7 text-on-surface">{question}</div>
        <div className="mt-4">
          <MemoryTriggerChips
            activeTrigger={activeTrigger}
            onSelectTrigger={onSelectTrigger}
            triggers={triggers}
          />
        </div>
        <textarea
          className="mt-4 min-h-40 w-full rounded-2xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm text-on-surface"
          onChange={(event) => onAnswerChange(event.target.value)}
          placeholder="Write the rough version. Runr will turn it into a reusable career memory."
          value={answer}
        />
        <div className="mt-4 flex items-center justify-between gap-3">
          <div className="text-sm text-on-surface-variant">
            One concrete example is enough to move forward.
          </div>
          <button
            className="rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!answer.trim()}
            onClick={onContinue}
            type="button"
          >
            Continue
          </button>
        </div>
      </div>

      {previousAnswers.length ? (
        <details className="rounded-2xl border border-outline-variant/15 bg-surface p-4">
          <summary className="cursor-pointer text-sm font-semibold text-on-surface">
            Previous answers
          </summary>
          <div className="mt-4 space-y-3">
            {previousAnswers.map((item) => (
              <div
                className="rounded-2xl bg-surface-container-low px-4 py-3 text-sm leading-6 text-on-surface-variant"
                key={item.id}
              >
                <div className="font-medium text-on-surface">{item.label}</div>
                <div className="mt-1">{item.answer}</div>
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );
}

