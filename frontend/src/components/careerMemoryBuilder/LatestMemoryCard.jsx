import { CAREER_MEMORY_STATUS_META, getCategoryLabel } from "../../lib/careerMemoryWorkspace";

export default function LatestMemoryCard({ card, onAddMetric, onEdit, onToggleUseInCv, onToggleUseInLetter }) {
  if (!card) {
    return (
      <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
        <h3 className="font-headline text-lg font-bold text-on-surface">No memory cards yet</h3>
        <p className="mt-2 text-sm leading-6 text-on-surface-variant">
          Answer a few guided questions and Runr will turn your rough notes into reusable CV
          bullets, cover-letter angles, and application answers.
        </p>
      </section>
    );
  }

  const statusMeta = CAREER_MEMORY_STATUS_META[card.status] || CAREER_MEMORY_STATUS_META.needs_detail;

  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-headline text-lg font-bold text-on-surface">Latest memory</h3>
        <span
          className={[
            "rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide",
            statusMeta.badgeClass,
          ].join(" ")}
        >
          {statusMeta.label}
        </span>
      </div>
      <div className="mt-4 rounded-2xl border border-outline-variant/15 bg-surface p-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="font-semibold text-on-surface">{card.title}</div>
          <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
            {getCategoryLabel(card.category)}
          </span>
        </div>
        <div className="mt-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
            Suggested CV bullet
          </div>
          <p className="mt-2 text-sm leading-6 text-on-surface">
            {card.cvBulletSuggestion || "No CV bullet suggestion yet."}
          </p>
        </div>
        <div className="mt-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
            Cover-letter angle
          </div>
          <p className="mt-2 text-sm leading-6 text-on-surface">
            {card.coverLetterAngle || "No cover-letter angle yet."}
          </p>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          <button
            className="rounded-xl bg-surface-container-low px-3.5 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            onClick={() => onEdit(card.id)}
            type="button"
          >
            Edit
          </button>
          <button
            className="rounded-xl bg-surface-container-low px-3.5 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            onClick={() => onAddMetric(card.id)}
            type="button"
          >
            Add metric
          </button>
          <button
            className="rounded-xl bg-surface-container-low px-3.5 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            onClick={() => onToggleUseInCv(card.id)}
            type="button"
          >
            {card.useInCv ? "Use in CV" : "Add to CV"}
          </button>
          <button
            className="rounded-xl bg-surface-container-low px-3.5 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            onClick={() => onToggleUseInLetter(card.id)}
            type="button"
          >
            {card.useInLetter ? "Use in letter" : "Add to letter"}
          </button>
        </div>
      </div>
    </section>
  );
}

