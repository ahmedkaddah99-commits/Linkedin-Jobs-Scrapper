import CareerMemoryCard from "./CareerMemoryCard";

export default function MotivationStoryBank({
  autoEditCardId = "",
  cards = [],
  onAddManual,
  onCardDelete,
  onCardSave,
  onUsePrompt,
  motivationLetterNotes = "",
  onChangeField,
  professionalHurdlesContext = "",
}) {
  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2 className="font-headline text-xl font-bold text-on-surface">
            Motivation &amp; Story Bank
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-on-surface-variant">
            Capture career transitions, hurdles, company preferences, industry interests, and
            challenge stories that help motivation letters feel specific and believable.
          </p>
        </div>
        <button
          className="inline-flex items-center justify-center gap-2 rounded-2xl bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
          onClick={onAddManual}
          type="button"
        >
          Add story manually
          <span className="material-symbols-outlined text-[16px]">note_stack</span>
        </button>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {[
          ["coordinated_stakeholders", "Stakeholder story"],
          ["solved_urgent_issue", "Solved urgent issue"],
          ["not_sure", "Memory jogger"],
        ].map(([chipId, label]) => (
          <button
            className="rounded-full bg-primary/10 px-3 py-2 text-sm font-medium text-primary transition-colors hover:bg-primary/15"
            key={chipId}
            onClick={() => onUsePrompt(chipId)}
            type="button"
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mt-5 grid gap-4">
        <div className="rounded-2xl border border-outline-variant/15 bg-surface p-4">
          <div className="text-sm font-semibold text-on-surface">
            Professional hurdles and transition context
          </div>
          <textarea
            className="mt-3 min-h-28 w-full rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm text-on-surface"
            onChange={(event) => onChangeField("professionalHurdlesContext", event.target.value)}
            placeholder="Keep any broader challenge context here if it does not belong to a single card yet."
            value={professionalHurdlesContext}
          />
        </div>
        <div className="rounded-2xl border border-outline-variant/15 bg-surface p-4">
          <div className="text-sm font-semibold text-on-surface">Motivation-letter notes</div>
          <textarea
            className="mt-3 min-h-28 w-full rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm text-on-surface"
            onChange={(event) => onChangeField("motivationLetterNotes", event.target.value)}
            placeholder="Keep any reusable motivation context here if it does not belong to a single card yet."
            value={motivationLetterNotes}
          />
        </div>
      </div>

      <div className="mt-5 space-y-4">
        {cards.length ? (
          cards.map((card) => (
            <CareerMemoryCard
              autoEdit={card.id === autoEditCardId}
              card={card}
              key={card.id}
              onDelete={onCardDelete}
              onSave={onCardSave}
            />
          ))
        ) : (
          <div className="rounded-2xl border border-dashed border-outline-variant/20 bg-surface p-6 text-sm leading-6 text-on-surface-variant">
            No motivation or story cards yet. Use the guided interview to capture challenge and
            motivation context.
          </div>
        )}
      </div>
    </section>
  );
}

