import { useEffect, useMemo, useState } from "react";
import {
  CAREER_MEMORY_CATEGORY_META,
  CAREER_MEMORY_CATEGORY_OPTIONS,
  hasMetric,
} from "../../lib/careerMemoryBuilder";

function toneClasses(enabled) {
  return enabled
    ? "bg-primary text-white"
    : "bg-surface-container-low text-on-surface hover:bg-surface-container-high";
}

export default function CareerMemoryCard({ autoEdit = false, card, onDelete, onSave }) {
  const [isEditing, setIsEditing] = useState(autoEdit);
  const [metricMode, setMetricMode] = useState(false);
  const [draftCard, setDraftCard] = useState(card);
  const [metricDraft, setMetricDraft] = useState(card.impactMetric || "");

  useEffect(() => {
    setDraftCard(card);
    setMetricDraft(card.impactMetric || "");
  }, [card]);

  useEffect(() => {
    if (autoEdit) {
      setIsEditing(true);
    }
  }, [autoEdit]);

  const tagValue = useMemo(() => (draftCard.tags || []).join(", "), [draftCard.tags]);

  function updateField(field, value) {
    setDraftCard((current) => ({ ...current, [field]: value }));
  }

  function saveCard() {
    const nextTags = String(tagValue || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    onSave({
      ...draftCard,
      tags: nextTags,
      impactMetric: metricDraft.trim(),
    });
    setIsEditing(false);
    setMetricMode(false);
  }

  function saveMetric() {
    onSave({
      ...card,
      impactMetric: metricDraft.trim(),
    });
    setMetricMode(false);
  }

  if (isEditing) {
    return (
      <article className="rounded-3xl border border-primary/25 bg-surface p-5">
        <div className="grid gap-4">
          <input
            className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface"
            onChange={(event) => updateField("title", event.target.value)}
            placeholder="Title"
            type="text"
            value={draftCard.title}
          />
          <div className="grid gap-4 md:grid-cols-2">
            <select
              className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface"
              onChange={(event) => updateField("category", event.target.value)}
              value={draftCard.category}
            >
              {CAREER_MEMORY_CATEGORY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <input
              className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface"
              onChange={(event) => setMetricDraft(event.target.value)}
              placeholder="Impact metric or rough estimate"
              type="text"
              value={metricDraft}
            />
          </div>
          <textarea
            className="min-h-28 rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateField("rawNote", event.target.value)}
            placeholder="Raw note"
            value={draftCard.rawNote}
          />
          <textarea
            className="min-h-24 rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateField("polishedCvBullet", event.target.value)}
            placeholder="Polished CV bullet suggestion"
            value={draftCard.polishedCvBullet}
          />
          <textarea
            className="min-h-24 rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateField("coverLetterAngle", event.target.value)}
            placeholder="Cover-letter angle"
            value={draftCard.coverLetterAngle}
          />
          <input
            className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface"
            onChange={(event) => updateField("tags", event.target.value.split(",").map((item) => item.trim()))}
            placeholder="Tags, separated by commas"
            type="text"
            value={tagValue}
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
                setMetricDraft(card.impactMetric || "");
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
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-headline text-lg font-bold text-on-surface">{card.title}</h3>
            <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
              {CAREER_MEMORY_CATEGORY_META[card.category]?.label || card.category}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap gap-2 text-[11px] font-semibold uppercase tracking-wide text-on-surface-variant">
            <span className="rounded-full bg-surface-container-low px-2.5 py-1">
              {card.sourceLabel}
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
            {hasMetric(card) ? "Edit metric" : "Add metric"}
          </button>
          <button
            className={["rounded-xl px-3.5 py-2 text-sm font-medium transition-colors", toneClasses(card.useInCv)].join(" ")}
            onClick={() => onSave({ ...card, useInCv: !card.useInCv })}
            type="button"
          >
            {card.useInCv ? "Use in CV" : "Add to CV"}
          </button>
          <button
            className={[
              "rounded-xl px-3.5 py-2 text-sm font-medium transition-colors",
              toneClasses(card.useInLetter),
            ].join(" ")}
            onClick={() => onSave({ ...card, useInLetter: !card.useInLetter })}
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
              placeholder="Example: saved 4 hours per week, reduced errors, supported 12 stakeholders"
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
            {card.rawNote || "Add the rough memory first. Specific facts matter more than polished wording."}
          </p>
          {card.impactMetric ? (
            <div className="mt-3 rounded-xl bg-primary/10 px-3 py-2 text-sm text-primary">
              Impact estimate: {card.impactMetric}
            </div>
          ) : null}
        </div>
        <div className="space-y-4">
          <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
              Polished CV bullet suggestion
            </div>
            <p className="mt-2 text-sm leading-6 text-on-surface">
              {card.polishedCvBullet || "No CV bullet drafted yet."}
            </p>
          </div>
          <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
              Cover-letter angle
            </div>
            <p className="mt-2 text-sm leading-6 text-on-surface">
              {card.coverLetterAngle || "No cover-letter angle drafted yet."}
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
    </article>
  );
}

