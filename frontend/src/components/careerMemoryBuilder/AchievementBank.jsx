import CareerMemoryCard from "./CareerMemoryCard";

export default function AchievementBank({
  achievementHighlights = "",
  additionalBulletBank = "",
  autoEditCardId = "",
  cards = [],
  onChangeField,
  onAddManual,
  onCardDelete,
  onCardSave,
  onUsePrompt,
}) {
  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2 className="font-headline text-xl font-bold text-on-surface">Achievement Bank</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-on-surface-variant">
            Store wins, quantified outcomes, project examples, stakeholder proof, and system
            experience as reusable memory cards instead of leaving them in large blank textareas.
          </p>
        </div>
        <button
          className="inline-flex items-center justify-center gap-2 rounded-2xl bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
          onClick={onAddManual}
          type="button"
        >
          Add achievement manually
          <span className="material-symbols-outlined text-[16px]">add</span>
        </button>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {[
          ["saved_time", "Saved time"],
          ["automated_something", "Automated something"],
          ["improved_reporting", "Improved reporting"],
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
          <div className="text-sm font-semibold text-on-surface">Imported achievement highlights</div>
          <textarea
            className="mt-3 min-h-28 w-full rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm text-on-surface"
            onChange={(event) => onChangeField("achievementHighlights", event.target.value)}
            placeholder="Keep any broader highlights here if they are not yet split into separate cards."
            value={achievementHighlights}
          />
        </div>
        <div className="rounded-2xl border border-outline-variant/15 bg-surface p-4">
          <div className="text-sm font-semibold text-on-surface">Additional bullet bank</div>
          <textarea
            className="mt-3 min-h-28 w-full rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm text-on-surface"
            onChange={(event) => onChangeField("additionalBulletBank", event.target.value)}
            placeholder="Keep any imported or rough extra bullets here until you convert them into memory cards."
            value={additionalBulletBank}
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
            No achievement cards yet. Start the guided interview or add one manually.
          </div>
        )}
      </div>
    </section>
  );
}
