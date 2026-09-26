import { useEffect, useMemo, useState } from "react";
import {
  CAREER_MEMORY_CATEGORY_META,
  CAREER_MEMORY_STATUS_META,
  getSourceLabel,
  normalizeCareerMemoryCard,
} from "../../lib/careerMemoryWorkspace";

function toneClasses(enabled) {
  return enabled
    ? "bg-primary text-white"
    : "bg-surface-container-low text-on-surface hover:bg-surface-container-high";
}

export default function MemoryCard({
  autoEdit = false,
  card,
  onDelete,
  onSave,
}) {
  const [isEditing, setIsEditing] = useState(autoEdit);
  const [metricMode, setMetricMode] = useState(false);
  const [draftCard, setDraftCard] = useState(card);
  const [tagText, setTagText] = useState((card.tags || []).join(", "));
  const [metricDraft, setMetricDraft] = useState(card.structuredNotes?.impactEstimate || "");

  useEffect(() => {
    setDraftCard(card);
    setTagText((card.tags || []).join(", "));
    setMetricDraft(card.structuredNotes?.impactEstimate || "");
  }, [card]);

  useEffect(() => {
    if (autoEdit) {
      setIsEditing(true);
    }
  }, [autoEdit]);

  const statusMeta = useMemo(
    () => CAREER_MEMORY_STATUS_META[card.status] || CAREER_MEMORY_STATUS_META.needs_detail,
    [card.status],
  );

  function updateField(field, value) {
    setDraftCard((current) => ({ ...current, [field]: value }));
  }

  function saveCard() {
    const nextCard = normalizeCareerMemoryCard({
      ...draftCard,
      tags: tagText.split(",").map((item) => item.trim()).filter(Boolean),
      structuredNotes: {
        ...(draftCard.structuredNotes || {}),
        impactEstimate: metricDraft.trim(),
      },
      updatedAt: new Date().toISOString(),
    });
    onSave(nextCard);
    setIsEditing(false);
    setMetricMode(false);
  }

  function saveMetric() {
    onSave(
      normalizeCareerMemoryCard({
        ...card,
        structuredNotes: {
          ...(card.structuredNotes || {}),
          impactEstimate: metricDraft.trim(),
        },
        updatedAt: new Date().toISOString(),
      }),
    );
    setMetricMode(false);
  }

  if (isEditing) {
    return (
      <article className="rounded-3xl border border-primary/20 bg-surface p-5">
        <div className="grid gap-4">
          <input
            className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface"
            onChange={(event) => updateField("title", event.target.value)}
            placeholder="Title"
            type="text"
            value={draftCard.title}
          />
          <select
            className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface"
            onChange={(event) => updateField("category", event.target.value)}
            value={draftCard.category}
          >
            {Object.entries(CAREER_MEMORY_CATEGORY_META).map(([value, meta]) => (
              <option key={value} value={value}>
                {meta.label}
              </option>
            ))}
          </select>
          <textarea
            className="min-h-28 rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateField("rawNote", event.target.value)}
            placeholder="Raw note"
            value={draftCard.rawNote}
          />
          <textarea
            className="min-h-24 rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateField("cvBulletSuggestion", event.target.value)}
            placeholder="CV bullet suggestion"
            value={draftCard.cvBulletSuggestion}
          />
          <textarea
            className="min-h-24 rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateField("coverLetterAngle", event.target.value)}
            placeholder="Cover-letter angle"
            value={draftCard.coverLetterAngle}
          />
          <input
            className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface"
            onChange={(event) => setMetricDraft(event.target.value)}
            placeholder="Impact metric or rough estimate"
            type="text"
            value={metricDraft}
          />
          <input
            className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface"
            onChange={(event) => setTagText(event.target.value)}
            placeholder="Tags, separated by commas"
            type="text"
            value={tagText}
          />
          <div className="flex flex-wrap gap-3">
            <button
              className="rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90"
              onClick={saveCard}
              type="button"
            >
              Save card
            </button>
            <button
              className="rounded-xl bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
              onClick={() => {
                setDraftCard(card);
                setTagText((card.tags || []).join(", "));
                setMetricDraft(card.structuredNotes?.impactEstimate || "");
                setIsEditing(false);
              }}
              type="button"
            >
              Cancel
            </button>
          </div>
        </div>
      </article>
    );
  }

  return (
    <article className="rounded-3xl border border-outline-variant/15 bg-surface p-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-headline text-lg font-bold text-on-surface">{card.title}</h3>
            <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
              {CAREER_MEMORY_CATEGORY_META[card.category]?.label || card.category}
            </span>
            <span
              className={[
                "rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide",
                statusMeta.badgeClass,
              ].join(" ")}
            >
              {statusMeta.label}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap gap-2 text-[11px] font-semibold uppercase tracking-wide text-on-surface-variant">
            <span className="rounded-full bg-surface-container-low px-2.5 py-1">
              {getSourceLabel(card.source)}
            </span>
            <span className="rounded-full bg-surface-container-low px-2.5 py-1">
              {card.confidenceLabel}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            className="rounded-xl bg-surface-container-low px-3.5 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            onClick={() => setIsEditing(true)}
            type="button"
          >
            Edit
          </button>
          <button
            className="rounded-xl bg-surface-container-low px-3.5 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            onClick={() => setMetricMode((current) => !current)}
            type="button"
          >
            Add metric
          </button>
          <button
            className={["rounded-xl px-3.5 py-2 text-sm font-medium transition-colors", toneClasses(card.useInCv)].join(" ")}
            onClick={() => onSave({ ...card, useInCv: !card.useInCv, updatedAt: new Date().toISOString() })}
            type="button"
          >
            {card.useInCv ? "Use in CV" : "Add to CV"}
          </button>
          <button
            className={["rounded-xl px-3.5 py-2 text-sm font-medium transition-colors", toneClasses(card.useInLetter)].join(" ")}
            onClick={() =>
              onSave({ ...card, useInLetter: !card.useInLetter, updatedAt: new Date().toISOString() })
            }
            type="button"
          >
            {card.useInLetter ? "Use in letter" : "Add to letter"}
          </button>
          <button
            className="rounded-xl bg-error/10 px-3.5 py-2 text-sm font-medium text-error transition-colors hover:bg-error/15"
            onClick={() => onDelete(card.id)}
            type="button"
          >
            Delete
          </button>
        </div>
      </div>

      {metricMode ? (
        <div className="mt-4 rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4">
          <div className="text-sm font-semibold text-on-surface">Impact metric or estimate</div>
          <div className="mt-3 flex flex-col gap-3 md:flex-row">
            <input
              className="flex-1 rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface"
              onChange={(event) => setMetricDraft(event.target.value)}
              placeholder="Example: saved 4 hours per week, reduced errors, supported 12 people"
              type="text"
              value={metricDraft}
            />
            <button
              className="rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90"
              onClick={saveMetric}
              type="button"
            >
              Save metric
            </button>
          </div>
        </div>
      ) : null}

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
            Raw note
          </div>
          <p className="mt-2 text-sm leading-6 text-on-surface">
            {card.rawNote || "No raw note yet."}
          </p>
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
        <div className="mt-4 rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
            Missing details
          </div>
          <div className="mt-2 space-y-1">
            {card.missingDetails.map((detail) => (
              <div className="text-sm text-on-surface-variant" key={detail}>
                {detail}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </article>
  );
}

