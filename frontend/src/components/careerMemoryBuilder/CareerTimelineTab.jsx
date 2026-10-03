import { useMemo } from "react";

export default function CareerTimelineTab({
  cards = [],
  onEditCard,
}) {
  const sortedCards = useMemo(() => {
    return [...(cards || [])]
      .filter((card) => card.createdAt)
      .sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
  }, [cards]);

  const timelineGroups = useMemo(() => {
    const groups = new Map();
    for (const card of sortedCards) {
      const date = new Date(card.createdAt);
      const period = `${date.getFullYear()} Q${Math.ceil((date.getMonth() + 1) / 3)}`;
      if (!groups.has(period)) groups.set(period, []);
      groups.get(period).push(card);
    }
    return groups;
  }, [sortedCards]);

  if (sortedCards.length === 0) {
    return (
      <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
        <h2 className="font-headline text-xl font-bold text-on-surface">Career Timeline</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-on-surface-variant">
          A chronological view of your career evidence. Add evidence items to see them organized by time.
        </p>
        <div className="mt-6 rounded-2xl border border-dashed border-outline-variant/20 bg-surface p-6 text-center">
          <span className="material-symbols-outlined text-[2.5rem] text-on-surface-variant">timeline</span>
          <p className="mt-3 text-sm leading-6 text-on-surface-variant">
            No evidence items with dates found. Start building your evidence library to populate the timeline.
          </p>
        </div>
      </section>
    );
  }

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        <h2 className="font-headline text-xl font-bold text-on-surface">Career Timeline</h2>
        <p className="mt-1 text-sm leading-6 text-on-surface-variant">
          Your career evidence organised chronologically. This view shows when each piece of evidence was added.
        </p>
      </section>

      <div className="relative space-y-0">
        {Array.from(timelineGroups.entries()).map(([period, periodCards]) => (
          <div className="relative pb-8 pl-8" key={period}>
            <div className="absolute left-0 top-1 h-full w-px bg-outline-variant/20" />
            <div className="absolute -left-1.5 top-0 h-4 w-4 rounded-full border-2 border-primary bg-surface-container-lowest" />
            <div className="mb-3 rounded-xl bg-surface-container-low px-4 py-2 text-sm font-semibold text-on-surface">
              {period}
            </div>
            <div className="space-y-3">
              {periodCards.map((card) => (
                <div
                  className="rounded-2xl border border-outline-variant/15 bg-surface p-4 transition-colors hover:border-primary/20"
                  key={card.id}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold text-on-surface truncate">
                        {card.title}
                      </div>
                      <div className="mt-1 text-xs leading-5 text-on-surface-variant line-clamp-2">
                        {card.rawNote || card.cvBulletSuggestion}
                      </div>
                    </div>
                    {onEditCard ? (
                      <button
                        className="shrink-0 rounded-lg border border-outline-variant/20 p-1.5 text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-primary"
                        onClick={() => onEditCard(card.id)}
                        type="button"
                        title="Edit evidence"
                      >
                        <span className="material-symbols-outlined text-[16px]">edit</span>
                      </button>
                    ) : null}
                  </div>
                  {card.createdAt ? (
                    <div className="mt-2 text-xs text-on-surface-variant/60">
                      {new Date(card.createdAt).toLocaleDateString(undefined, {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                      })}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
