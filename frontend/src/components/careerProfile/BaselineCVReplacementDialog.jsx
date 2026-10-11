import { useEffect, useMemo, useState } from "react";
import StatusBadge from "../StatusBadge";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DIFF_CATEGORY_LABELS = {
  matching: "Matching",
  added: "Added",
  removed: "Removed",
  changed_title: "Changed title",
  changed_company: "Changed company",
  changed_dates: "Changed dates",
  changed_bullets: "Changed bullets",
};

const DIFF_CATEGORY_TONES = {
  matching: "success",
  added: "primary",
  removed: "warning",
  changed_title: "primary",
  changed_company: "primary",
  changed_dates: "primary",
  changed_bullets: "primary",
};

const DIFF_CATEGORY_ICONS = {
  matching: "check_circle",
  added: "add_circle",
  removed: "remove_circle",
  changed_title: "edit",
  changed_company: "business",
  changed_dates: "edit_calendar",
  changed_bullets: "format_list_bulleted",
};

const SORT_ORDER = [
  "changed_title",
  "changed_company",
  "changed_dates",
  "changed_bullets",
  "added",
  "removed",
  "matching",
];

const ACTION_LABELS = {
  add: "Accept",
  ignore: "Skip",
  needs_review: "Review later",
};

const ACTION_ICONS = {
  add: "check",
  ignore: "close",
  needs_review: "schedule",
};

const ACTION_TONES = {
  add: "success",
  ignore: "neutral",
  needs_review: "warning",
};


// ---------------------------------------------------------------------------
// BulletDiffRow
// ---------------------------------------------------------------------------

function BulletDiffRow({ bullet }) {
  const category = bullet.diff_category || "matching";

  if (category === "matching") {
    return (
      <li className="flex items-start gap-2 rounded-lg bg-surface-container-low px-3 py-2 text-sm text-on-surface">
        <span className="material-symbols-outlined mt-0.5 shrink-0 text-[16px] text-on-surface-variant">
          check
        </span>
        <span>{bullet.text || bullet.old_text || bullet.new_text}</span>
      </li>
    );
  }

  if (category === "added") {
    return (
      <li className="flex items-start gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm dark:bg-emerald-950/30">
        <span className="material-symbols-outlined mt-0.5 shrink-0 text-[16px] text-emerald-600 dark:text-emerald-400">
          add
        </span>
        <span className="text-emerald-800 dark:text-emerald-200">
          {bullet.new_text || bullet.text}
        </span>
      </li>
    );
  }

  if (category === "removed") {
    return (
      <li className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm line-through dark:bg-red-950/30">
        <span className="material-symbols-outlined mt-0.5 shrink-0 text-[16px] text-red-500 dark:text-red-400">
          remove
        </span>
        <span className="text-red-700 dark:text-red-300">
          {bullet.old_text || bullet.text}
        </span>
      </li>
    );
  }

  // changed bullet — show old vs new
  return (
    <li className="space-y-1.5 rounded-lg bg-surface-container-low px-3 py-2">
      <div className="flex items-start gap-2">
        <span className="material-symbols-outlined mt-0.5 shrink-0 text-[16px] text-red-400">
          remove
        </span>
        <span className="text-sm text-red-600 line-through dark:text-red-300">
          {bullet.old_text}
        </span>
      </div>
      <div className="flex items-start gap-2">
        <span className="material-symbols-outlined mt-0.5 shrink-0 text-[16px] text-emerald-500">
          add
        </span>
        <span className="text-sm text-emerald-700 dark:text-emerald-300">
          {bullet.new_text}
        </span>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// ExperienceDiffCard
// ---------------------------------------------------------------------------

function ExperienceDiffCard({ diff, action, onChangeAction }) {
  const [expanded, setExpanded] = useState(false);

  const category = diff.diff_category || "matching";
  const categoryLabel = DIFF_CATEGORY_LABELS[category] || category;
  const categoryTone = DIFF_CATEGORY_TONES[category] || "neutral";
  const categoryIcon = DIFF_CATEGORY_ICONS[category] || "info";

  const hasBulletDiffs =
    Array.isArray(diff.bullet_diffs) && diff.bullet_diffs.length > 0;
  const hasChanges = category !== "matching" || hasBulletDiffs;

  const titleChanged =
    category === "changed_title" ||
    (diff.old_title && diff.new_title && diff.old_title !== diff.new_title);
  const companyChanged =
    category === "changed_company" ||
    (diff.old_company && diff.new_company && diff.old_company !== diff.new_company);
  const datesChanged =
    category === "changed_dates" ||
    ((diff.old_start_date || diff.new_start_date) &&
      (diff.old_start_date !== diff.new_start_date ||
       diff.old_end_date !== diff.new_end_date));

  return (
    <div
      className={[
        "rounded-xl border transition-colors",
        category === "added"
          ? "border-emerald-300/40 bg-emerald-50/30 dark:border-emerald-700/30 dark:bg-emerald-950/20"
          : category === "removed"
            ? "border-red-300/40 bg-red-50/30 dark:border-red-700/30 dark:bg-red-950/20"
            : "border-outline-variant/20 bg-surface-container-lowest",
      ].join(" ")}
    >
      {/* Header */}
      <button
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        onClick={() => setExpanded((v) => !v)}
        type="button"
      >
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <span
            className={[
              "material-symbols-outlined shrink-0 text-[20px]",
              category === "added"
                ? "text-emerald-600 dark:text-emerald-400"
                : category === "removed"
                  ? "text-red-500 dark:text-red-400"
                  : "text-on-surface-variant",
            ].join(" ")}
          >
            {categoryIcon}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="truncate text-sm font-semibold text-on-surface">
                {diff.new_title || diff.old_title || "Untitled experience"}
              </span>
              <StatusBadge tone={categoryTone}>{categoryLabel}</StatusBadge>
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-1 text-xs text-on-surface-variant">
              <span>{diff.new_company || diff.old_company || "\u2014"}</span>
              <span aria-hidden="true">&middot;</span>
              <span>
                {diff.new_start_date || diff.old_start_date || "?"} &mdash;{" "}
                {diff.new_end_date || diff.old_end_date || "Present"}
              </span>
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {diff.match_score != null ? (
            <span className="rounded-full bg-surface-container px-2 py-0.5 text-[11px] font-semibold text-on-surface-variant">
              {Math.round(diff.match_score * 100)}%
            </span>
          ) : null}
          <span className="material-symbols-outlined text-[20px] text-on-surface-variant transition-transform">
            {expanded ? "expand_less" : "expand_more"}
          </span>
        </div>
      </button>

      {/* Expanded body */}
      {expanded ? (
        <div className="border-t border-outline-variant/15 px-4 py-4 space-y-4">
          {/* Side-by-side when changed */}
          {titleChanged || companyChanged || datesChanged ? (
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-lg border border-outline-variant/15 bg-surface-container-low p-3">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant">
                  Current baseline
                </p>
                <div className="mt-2 space-y-1 text-sm">
                  {titleChanged && diff.old_title ? (
                    <p className="font-medium text-on-surface">{diff.old_title}</p>
                  ) : null}
                  {companyChanged && diff.old_company ? (
                    <p className="text-on-surface-variant">{diff.old_company}</p>
                  ) : null}
                  {datesChanged ? (
                    <p className="text-xs text-on-surface-variant/70">
                      {diff.old_start_date || "?"} &mdash; {diff.old_end_date || "Present"}
                    </p>
                  ) : null}
                </div>
              </div>
              <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-primary">
                  Proposed
                </p>
                <div className="mt-2 space-y-1 text-sm">
                  {titleChanged && diff.new_title ? (
                    <p className="font-medium text-on-surface">{diff.new_title}</p>
                  ) : null}
                  {companyChanged && diff.new_company ? (
                    <p className="text-on-surface-variant">{diff.new_company}</p>
                  ) : null}
                  {datesChanged ? (
                    <p className="text-xs text-on-surface-variant/70">
                      {diff.new_start_date || "?"} &mdash; {diff.new_end_date || "Present"}
                    </p>
                  ) : null}
                </div>
              </div>
            </div>
          ) : null}

          {/* Bullet diffs */}
          {hasBulletDiffs ? (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
                Bullet changes ({diff.bullet_diffs.length})
              </p>
              <ul className="space-y-1.5">
                {diff.bullet_diffs.map((bullet, idx) => (
                  <BulletDiffRow
                    key={bullet.bullet_id || idx}
                    bullet={bullet}
                  />
                ))}
              </ul>
            </div>
          ) : null}

          {/* No changes notice */}
          {!hasChanges ? (
            <div className="flex items-center gap-2 rounded-lg bg-surface-container-low px-3 py-2 text-sm text-on-surface-variant">
              <span className="material-symbols-outlined text-[18px]">info</span>
              No changes detected for this experience.
            </div>
          ) : null}

          {/* Action dropdown */}
          <div className="flex items-center justify-between gap-3 border-t border-outline-variant/15 pt-3">
            <span className="text-xs text-on-surface-variant">
              Suggested:{" "}
              <span className="font-semibold text-on-surface">
                {ACTION_LABELS[diff.suggested_action] || diff.suggested_action || "Review"}
              </span>
            </span>
            <select
              className="rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-1.5 text-sm font-medium text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/30"
              onChange={(e) => onChangeAction(diff.diff_id, e.target.value)}
              value={action || diff.suggested_action || "needs_review"}
            >
              {Object.entries(ACTION_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// BaselineCVReplacementDialog
// ---------------------------------------------------------------------------

export default function BaselineCVReplacementDialog({
  profile,
  preview,
  workspaces,
  userDocuments,
  onCancel,
  onPreview,
  onConfirm,
  previewing = false,
  confirming = false,
  error = "",
}) {
  const [step, setStep] = useState(preview ? "review" : "select");
  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [actions, setActions] = useState({});
  const [expandedSections, setExpandedSections] = useState(new Set());

  // Filter CV documents from userDocuments
  const cvDocuments = useMemo(
    () =>
      (userDocuments || []).filter(
        (doc) => String(doc.asset_kind || "") === "workspace_cv"
      ),
    [userDocuments]
  );

  // Group diffs by category
  const groupedDiffs = useMemo(() => {
    if (!preview?.experience_diffs) return {};
    const groups = {};
    for (const diff of preview.experience_diffs) {
      const cat = diff.diff_category || "matching";
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(diff);
    }
    return groups;
  }, [preview]);

  // Sorted categories per SORT_ORDER
  const sortedCategories = useMemo(
    () => SORT_ORDER.filter((cat) => (groupedDiffs[cat] || []).length > 0),
    [groupedDiffs]
  );

  // Action summary counts
  const actionSummary = useMemo(() => {
    const summary = { add: 0, ignore: 0, needs_review: 0 };
    Object.values(actions).forEach((act) => {
      if (act in summary) summary[act]++;
    });
    return summary;
  }, [actions]);

  // Initialize actions from preview data
  useEffect(() => {
    if (!preview?.experience_diffs) return;
    const initial = {};
    for (const diff of preview.experience_diffs) {
      initial[diff.diff_id] = diff.suggested_action || "needs_review";
    }
    setActions((prev) => {
      const missing = {};
      for (const diff of preview.experience_diffs) {
        if (prev[diff.diff_id] == null) {
          missing[diff.diff_id] = diff.suggested_action || "needs_review";
        }
      }
      if (Object.keys(missing).length === 0) return prev;
      return { ...prev, ...missing };
    });
  }, [preview]);

  // Toggle a section expand/collapse
  function toggleSection(category) {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  }

  // Change action for a diff
  function handleActionChange(diffId, action) {
    setActions((prev) => ({ ...prev, [diffId]: action }));
  }

  // Handle preview request
  function handlePreview() {
    if (!selectedAssetId || previewing) return;
    onPreview(selectedAssetId);
  }

  // Handle confirm
  function handleConfirm() {
    if (confirming) return;
    onConfirm(preview, actions);
  }

  // Current baseline info
  const currentBaselineLabel =
    profile?.baseline_cv_display_name || "No baseline CV set";
  const proposedLabel =
    preview?.proposed_baseline_cv_display_name || "Proposed CV";

  // -------------------------------------------------------------------
  // Render: SELECT step
  // -------------------------------------------------------------------

  if (step === "select") {
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4"
        role="presentation"
      >
        <div
          className="w-full max-w-2xl rounded-3xl border border-outline-variant/20 bg-surface-container-lowest shadow-soft"
          role="dialog"
          aria-modal="true"
          aria-label="Replace baseline CV"
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-4 border-b border-outline-variant/15 px-6 py-5">
            <div>
              <h2 className="font-headline text-xl font-bold text-on-surface">
                Replace baseline CV
              </h2>
              <p className="mt-1 text-sm text-on-surface-variant">
                Select a workspace CV to replace the current baseline for{" "}
                <span className="font-semibold text-on-surface">
                  {profile?.name || "this profile"}
                </span>
              </p>
            </div>
            <button
              aria-label="Close"
              className="rounded-full p-2 text-on-surface-variant hover:bg-surface-container"
              onClick={onCancel}
              type="button"
            >
              <span className="material-symbols-outlined">close</span>
            </button>
          </div>

          {/* Body */}
          <div className="px-6 py-5 space-y-5">
            {/* Current baseline info */}
            <div className="flex items-center gap-3 rounded-xl border border-outline-variant/20 bg-surface-container-low p-4">
              <span className="material-symbols-outlined text-[24px] text-on-surface-variant">
                description
              </span>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
                  Current baseline
                </p>
                <p className="mt-0.5 text-sm font-medium text-on-surface">
                  {currentBaselineLabel}
                </p>
              </div>
            </div>

            {/* CV selection */}
            <div>
              <p className="text-sm font-semibold text-on-surface">
                Choose a replacement CV
              </p>
              <p className="mt-1 text-xs text-on-surface-variant">
                Only workspace CVs are shown below.
              </p>

              {cvDocuments.length === 0 ? (
                <div className="mt-3 rounded-xl border border-dashed border-outline-variant/20 p-6 text-center">
                  <span className="material-symbols-outlined text-[2.5rem] text-on-surface-variant">
                    folder_off
                  </span>
                  <p className="mt-2 text-sm text-on-surface-variant">
                    No workspace CVs available. Upload a CV in the Asset Library
                    first.
                  </p>
                </div>
              ) : (
                <div className="mt-3 space-y-2">
                  {cvDocuments.map((doc) => {
                    const isSelected = doc.asset_id === selectedAssetId;
                    const isCurrentBaseline =
                      doc.asset_id === profile?.baseline_cv_asset_id;
                    return (
                      <label
                        key={doc.asset_id}
                        className={[
                          "flex cursor-pointer items-center gap-3 rounded-xl border p-3 transition-colors",
                          isSelected
                            ? "border-primary/40 bg-primary/5"
                            : "border-outline-variant/20 hover:border-outline-variant/40",
                        ].join(" ")}
                      >
                        <input
                          checked={isSelected}
                          className="h-4 w-4 shrink-0 accent-primary"
                          onChange={() => setSelectedAssetId(doc.asset_id)}
                          type="radio"
                          name="cvSelect"
                        />
                        <div className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium text-on-surface">
                            {doc.display_name || doc.file_name}
                          </span>
                          <span className="text-xs text-on-surface-variant">
                            {isCurrentBaseline
                              ? "Current baseline"
                              : "workspace_cv"}
                          </span>
                        </div>
                        {isCurrentBaseline ? (
                          <StatusBadge tone="neutral">Current</StatusBadge>
                        ) : null}
                      </label>
                    );
                  })}
                </div>
              )}
            </div>


            {/* Error */}
            {error ? (
              <div className="rounded-xl bg-error/10 p-3 text-sm text-error" role="alert">
                {error}
              </div>
            ) : null}
          </div>

          {/* Footer */}
          <div className="flex flex-wrap items-center justify-end gap-3 border-t border-outline-variant/15 px-6 py-4">
            <button
              className="inline-flex items-center gap-2 rounded-xl bg-surface-container-low px-5 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
              onClick={onCancel}
              type="button"
            >
              Cancel
            </button>
            <button
              className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={!selectedAssetId || previewing}
              onClick={handlePreview}
              type="button"
            >
              {previewing ? (
                <>
                  <span className="material-symbols-outlined animate-spin text-[18px]">
                    progress_activity
                  </span>
                  Analyzing…
                </>
              ) : (
                <>
                  Preview changes
                  <span className="material-symbols-outlined text-[18px]">
                    visibility
                  </span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    );
  }


  // -------------------------------------------------------------------
  // Render: REVIEW step
  // -------------------------------------------------------------------

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4"
      role="presentation"
    >
      <div
        className="w-full max-w-3xl max-h-[90vh] flex flex-col rounded-3xl border border-outline-variant/20 bg-surface-container-lowest shadow-soft"
        role="dialog"
        aria-modal="true"
        aria-label="Review baseline CV replacement"
      >
        {/* Header */}
        <div className="shrink-0 flex items-start justify-between gap-4 border-b border-outline-variant/15 px-6 py-5">
          <div>
            <h2 className="font-headline text-xl font-bold text-on-surface">
              Review baseline CV changes
            </h2>
            <p className="mt-1 text-sm text-on-surface-variant">
              <span className="font-medium text-on-surface">
                {preview?.old_baseline_cv_display_name || "Current baseline"}
              </span>
              {" → "}
              <span className="font-medium text-primary">
                {proposedLabel}
              </span>
            </p>
          </div>
          <button
            aria-label="Close"
            className="rounded-full p-2 text-on-surface-variant hover:bg-surface-container"
            onClick={onCancel}
            type="button"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {/* Summary */}
          {preview?.summary ? (
            <div className="rounded-xl border border-outline-variant/20 bg-surface-container-low p-4">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[20px] text-on-surface-variant">
                  summary
                </span>
                <p className="text-sm font-semibold text-on-surface">Summary</p>
              </div>
              <p className="mt-2 text-sm leading-6 text-on-surface-variant">
                {preview.summary}
              </p>
              {preview.existing_evidence_count != null ? (
                <p className="mt-2 text-xs text-on-surface-variant">
                  {preview.existing_evidence_count} existing evidence items will
                  be preserved.
                </p>
              ) : null}
            </div>
          ) : null}

          {/* Action summary bar */}
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-outline-variant/20 bg-surface-container-low px-4 py-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
              Decisions:
            </span>
            {Object.entries(ACTION_LABELS).map(([key, label]) => (
              <span
                key={key}
                className={[
                  "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold",
                  ACTION_TONES[key] === "success"
                    ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
                    : ACTION_TONES[key] === "warning"
                      ? "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
                      : "bg-surface-container-high text-on-surface-variant",
                ].join(" ")}
              >
                {actionSummary[key] || 0} {label}
              </span>
            ))}
          </div>

          {/* Error */}
          {error ? (
            <div className="rounded-xl bg-error/10 p-3 text-sm text-error" role="alert">
              {error}
            </div>
          ) : null}


          {/* Diff categories */}
          {sortedCategories.length === 0 ? (
            <div className="rounded-xl border border-dashed border-outline-variant/20 p-8 text-center">
              <span className="material-symbols-outlined text-[2.5rem] text-on-surface-variant">
                check
              </span>
              <p className="mt-2 text-sm text-on-surface-variant">
                No differences detected. The proposed CV matches the current
                baseline.
              </p>
            </div>
          ) : (
            sortedCategories.map((category) => {
              const diffs = groupedDiffs[category] || [];
              const isExpanded = expandedSections.has(category);
              const categoryLabel =
                DIFF_CATEGORY_LABELS[category] || category;
              const categoryTone =
                DIFF_CATEGORY_TONES[category] || "neutral";
              const categoryIcon =
                DIFF_CATEGORY_ICONS[category] || "info";

              return (
                <div key={category}>
                  {/* Category header */}
                  <button
                    className="flex w-full items-center justify-between gap-3 rounded-xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 text-left transition-colors hover:border-outline-variant/40"
                    onClick={() => toggleSection(category)}
                    type="button"
                  >
                    <div className="flex items-center gap-3">
                      <span className="material-symbols-outlined text-[20px] text-on-surface-variant">
                        {categoryIcon}
                      </span>
                      <div>
                        <span className="text-sm font-semibold text-on-surface">
                          {categoryLabel}
                        </span>
                        <span className="ml-2 text-xs text-on-surface-variant">
                          ({diffs.length})
                        </span>
                      </div>
                    </div>
                    <span className="material-symbols-outlined text-[20px] text-on-surface-variant transition-transform">
                      {isExpanded ? "expand_less" : "expand_more"}
                    </span>
                  </button>

                  {/* Category diffs */}
                  {isExpanded ? (
                    <div className="mt-2 space-y-2">
                      {diffs.map((diff) => (
                        <ExperienceDiffCard
                          key={diff.diff_id}
                          diff={diff}
                          action={actions[diff.diff_id]}
                          onChangeAction={handleActionChange}
                        />
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            })
          )}
        </div>


        {/* Footer */}
        <div className="shrink-0 flex flex-wrap items-center justify-between gap-3 border-t border-outline-variant/15 px-6 py-4">
          <button
            className="inline-flex items-center gap-2 rounded-xl bg-surface-container-low px-5 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            onClick={() => setStep("select")}
            type="button"
          >
            <span className="material-symbols-outlined text-[18px]">
              arrow_back
            </span>
            Back
          </button>
          <div className="flex flex-wrap items-center gap-3">
            <button
              className="inline-flex items-center gap-2 rounded-xl bg-surface-container-low px-5 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
              onClick={onCancel}
              type="button"
            >
              Cancel
            </button>
            <button
              className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={confirming}
              onClick={handleConfirm}
              type="button"
            >
              {confirming ? (
                <>
                  <span className="material-symbols-outlined animate-spin text-[18px]">
                    progress_activity
                  </span>
                  Applying…
                </>
              ) : (
                <>
                  Confirm replacement
                  <span className="material-symbols-outlined text-[18px]">
                    check
                  </span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
