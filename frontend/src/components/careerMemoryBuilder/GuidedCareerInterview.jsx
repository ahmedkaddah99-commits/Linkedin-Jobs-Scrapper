function messageClasses(role) {
  if (role === "assistant") {
    return "border-primary/20 bg-primary/10";
  }
  return "border-outline-variant/15 bg-surface";
}

export default function GuidedCareerInterview({
  interviewStarted,
  onStart,
  chips = [],
  activeChipId = "",
  onSelectChip,
  answer = "",
  onAnswerChange,
  onSubmit,
  messages = [],
}) {
  const activeChip = chips.find((chip) => chip.id === activeChipId) || chips[0] || null;

  return (
    <section className="rounded-[2rem] border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-primary">
            Guided AI interview
          </div>
          <h2 className="mt-3 font-headline text-2xl font-bold text-on-surface">
            Trigger better career memories before you need them
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-7 text-on-surface-variant">
            Documents tell part of your story. This guided interview helps you recover the impact,
            context, and motivation details they usually leave out.
          </p>
        </div>
        <button
          className="inline-flex items-center justify-center gap-2 rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90"
          onClick={() => onStart(activeChip?.id)}
          type="button"
        >
          Start guided career interview
          <span className="material-symbols-outlined text-[18px]">forum</span>
        </button>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.35fr_0.65fr]">
        <div className="rounded-3xl border border-outline-variant/15 bg-surface p-4">
          <div className="space-y-3">
            {messages.map((message) => (
              <div
                className={[
                  "rounded-2xl border p-4",
                  messageClasses(message.role),
                ].join(" ")}
                key={message.id}
              >
                <div className="text-[11px] font-semibold uppercase tracking-wide text-on-surface-variant">
                  {message.role === "assistant" ? "Runr interview coach" : "You"}
                </div>
                <p className="mt-2 text-sm leading-6 text-on-surface">{message.content}</p>
              </div>
            ))}
          </div>

          <div className="mt-5">
            <div className="text-sm font-semibold text-on-surface">Quick memory triggers</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {chips.map((chip) => {
                const isActive = activeChip?.id === chip.id;
                return (
                  <button
                    className={[
                      "rounded-full px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-primary text-white"
                        : "bg-surface-container-low text-on-surface hover:bg-surface-container-high",
                    ].join(" ")}
                    key={chip.id}
                    onClick={() => onSelectChip(chip.id)}
                    type="button"
                  >
                    {chip.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="mt-5 rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4">
            <div className="text-sm font-semibold text-on-surface">Your answer</div>
            <textarea
              className="mt-3 min-h-36 w-full rounded-2xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm text-on-surface"
              onChange={(event) => onAnswerChange(event.target.value)}
              placeholder="Answer in plain language. Rough memories are fine. Runr will turn them into reusable career memory cards."
              value={answer}
            />
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <div className="text-sm text-on-surface-variant">
                Specific examples beat polished writing here.
              </div>
              <button
                className="rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={!interviewStarted || !answer.trim()}
                onClick={onSubmit}
                type="button"
              >
                Save as career memory
              </button>
            </div>
          </div>
        </div>

        <aside className="rounded-3xl border border-outline-variant/15 bg-surface p-5">
          <div className="text-sm font-semibold text-on-surface">Current follow-up angle</div>
          {activeChip ? (
            <>
              <div className="mt-3 rounded-2xl border border-primary/20 bg-primary/10 p-4">
                <div className="font-semibold text-on-surface">{activeChip.label}</div>
                <p className="mt-2 text-sm leading-6 text-on-surface-variant">
                  {activeChip.focusPrompt}
                </p>
              </div>
              <div className="mt-4 space-y-3">
                {activeChip.followUps.map((question) => (
                  <div
                    className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-3 text-sm leading-6 text-on-surface-variant"
                    key={question}
                  >
                    {question}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="mt-3 text-sm text-on-surface-variant">
              Pick a memory trigger to get more specific follow-up questions.
            </p>
          )}
        </aside>
      </div>
    </section>
  );
}

