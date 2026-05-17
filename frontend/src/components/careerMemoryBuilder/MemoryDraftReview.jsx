import {
  CAREER_MEMORY_STATUS_META,
  getCategoryLabel,
  getSourceLabel,
} from "../../lib/careerMemoryWorkspace";

export default function MemoryDraftReview({
  card,
  onAddMetric,
  onDiscard,
  onImprove,
  onSave,
}) {
  if (!card) {
    return null;
  }

  const statusMeta = CAREER_MEMORY_STATUS_META[card.status] || CAREER_MEMORY_STATUS_META.needs_detail;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-on-surface">Generated Career Memory</div>
          <div className="mt-1 text-sm text-on-surface-variant">
            Review the draft before saving it to your reusable memory bank.
          </div>
        </div>
        <span
          className={[
            "rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide",
            statusMeta.badgeClass,
          ].join(" ")}
        >
          {statusMeta.label}
        </span>
      </div>

      <div className="rounded-3xl border border-outline-variant/15 bg-surface p-5">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-headline text-xl font-bold text-on-surface">{card.title}</h3>
          <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
            {getCategoryLabel(card.category)}
          </span>
          <span className="rounded-full bg-surface-container-low px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-on-surface-variant">
            {getSourceLabel(card.source)}
          </span>
        </div>

        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
              Raw user note
            </div>
            <p className="mt-2 text-sm leading-6 text-on-surface">{card.rawNote}</p>
          </div>
          <div className="space-y-4">
            <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                Polished CV bullet suggestion
              </div>
              <p className="mt-2 text-sm leading-6 text-on-surface">
                {card.cvBulletSuggestion || "No CV bullet suggestion yet."}
              </p>
            </div>
            <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                Cover-letter angle
              </div>
              <p className="mt-2 text-sm leading-6 text-on-surface">
                {card.coverLetterAngle || "No cover-letter angle yet."}
              </p>
            </div>
          </div>
        </div>

        {card.tags?.length ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {card.tags.map((tag) => (
              <span
                className="rounded-full bg-surface-container-low px-3 py-1 text-sm text-on-surface-variant"
                key={`${card.id}-${tag}`}
              >
                {tag}
              </span>
            ))}
          </div>
        ) : null}

        {card.missingDetails?.length ? (
          <div className="mt-5 rounded-2xl border border-amber-500/20 bg-amber-500/5 p-4">
            <div className="text-sm font-semibold text-on-surface">Missing detail warnings</div>
            <div className="mt-3 space-y-2">
              {card.missingDetails.map((detail) => (
                <div className="text-sm text-on-surface-variant" key={detail}>
                  {detail}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <div className="mt-5 flex flex-wrap gap-3">
          <button
            className="rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90"
            onClick={() => onSave(card)}
            type="button"
          >
            Save memory
          </button>
          <button
            className="rounded-xl bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            onClick={onImprove}
            type="button"
          >
            Improve it
          </button>
          <button
            className="rounded-xl bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            onClick={onAddMetric}
            type="button"
          >
            Add metric
          </button>
          <button
            className="rounded-xl bg-error/10 px-4 py-2.5 text-sm font-medium text-error transition-colors hover:bg-error/15"
            onClick={onDiscard}
            type="button"
          >
            Discard
          </button>
        </div>
      </div>
    </div>
  );
}

