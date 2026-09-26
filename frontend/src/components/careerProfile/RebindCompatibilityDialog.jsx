import { useMemo, useState } from "react";
import StatusBadge from "../StatusBadge";

const SECTION_GROUPS = [
  { key: "matching_experiences", label: "Matching Experiences", icon: "check_circle", tone: "success", description: "Experiences found in both your preserved evidence and the new workspace." },
  { key: "missing_experiences", label: "Missing Experiences", icon: "warning", tone: "warning", description: "Experiences from your preserved evidence that weren't found in the new workspace. These will be carried forward." },
  { key: "changed_dates", label: "Changed Dates", icon: "edit_calendar", tone: "primary", description: "Experiences where dates differ between preserved evidence and the new workspace." },
  { key: "possible_duplicates", label: "Possible Duplicates", icon: "content_copy", tone: "neutral", description: "Experiences that appear to be duplicates within your preserved evidence." },
  { key: "conflicts", label: "Conflicts", icon: "error", tone: "error", description: "Partial matches that need your review before rebinding can proceed." },
];

function ExperienceRow({ experience, showSource = true }) {
  const sourceLabel = experience.source === "preserved" ? "Preserved" : "New workspace";
  const sourceTone = experience.source === "preserved" ? "neutral" : "primary";
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-semibold text-on-surface truncate">
              {experience.title || "Untitled experience"}
            </span>
            {showSource ? <StatusBadge tone={sourceTone}>{sourceLabel}</StatusBadge> : null}
          </div>
          {experience.company ? (
            <span className="text-xs text-on-surface-variant">{experience.company}</span>
          ) : null}
        </div>
      </div>
      {(experience.start_date || experience.end_date) ? (
        <div className="text-xs text-on-surface-variant/70">
          {experience.start_date || "?"} &mdash; {experience.end_date || "Present"}
        </div>
      ) : null}
      {experience.description ? (
        <p className="text-xs leading-5 text-on-surface-variant line-clamp-2">{experience.description}</p>
      ) : null}
      {experience.match_details ? (
        <div className="mt-1 rounded-lg bg-surface-container px-2 py-1 text-xs text-on-surface-variant">
          {experience.match_details}
        </div>
      ) : null}
    </div>
  );
}



export default function RebindCompatibilityDialog({
  profile,
  review,
  workspaces,
  onCancel,
  onConfirm,
  onRequestReview,
  confirming = false,
  error = "",
}) {
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [confirmedConflictIds, setConfirmedConflictIds] = useState(new Set());
  const [reviewData, setReviewData] = useState(review);
  const [loading, setLoading] = useState(false);
  const [reviewError, setReviewError] = useState("");
  const [step, setStep] = useState(review ? "review" : "select");

  const hasConflicts = (reviewData?.conflicts || []).length > 0;
  const allConflictsConfirmed = useMemo(() => {
    const conflictIds = new Set((reviewData?.conflicts || []).map((c) => c.experience_id));
    if (conflictIds.size === 0) return true;
    return [...conflictIds].every((id) => confirmedConflictIds.has(id));
  }, [reviewData, confirmedConflictIds]);

  function toggleConflict(experienceId) {
    setConfirmedConflictIds((prev) => {
      const next = new Set(prev);
      if (next.has(experienceId)) { next.delete(experienceId); } else { next.add(experienceId); }
      return next;
    });
  }

  function handleRequestReview() {
    if (!selectedWorkspaceId || typeof onRequestReview !== "function") return;
    setLoading(true);
    setReviewError("");
    onRequestReview(selectedWorkspaceId)
      .then((data) => { setReviewData(data); setStep("review"); })
      .catch((err) => setReviewError(String(err?.message || "Failed to load compatibility review.")))
      .finally(() => setLoading(false));
  }

  function handleConfirm() {
    if (typeof onConfirm !== "function") return;


  // Workspace selection step
  if (step === "select") {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onCancel}>
        <div className="w-full max-w-lg rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
          <h3 className="font-headline text-xl font-bold text-on-surface">Rebind Career Profile</h3>
          <p className="mt-2 text-sm leading-6 text-on-surface-variant">
            Select a new workspace to bind <strong>{profile?.name || "this profile"}</strong> to.
            A compatibility review will compare your preserved evidence against the new workspace.
          </p>
          {reviewError ? (
            <div className="mt-3 rounded-xl border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">{reviewError}</div>
          ) : null}
          <div className="mt-4 space-y-2">
            <label className="block text-sm font-semibold text-on-surface">New workspace</label>
            {!workspaces || workspaces.length === 0 ? (
              <p className="text-sm text-on-surface-variant">No workspaces available.</p>
            ) : (
              workspaces.map((ws) => (
                <button
                  className={`w-full rounded-xl border px-4 py-3 text-left text-sm transition-colors ${selectedWorkspaceId === ws.id ? "border-primary/40 bg-primary/5 font-semibold text-primary" : "border-outline-variant/20 bg-surface text-on-surface hover:border-primary/20 hover:bg-primary/5"}`}
                  key={ws.id} onClick={() => setSelectedWorkspaceId(ws.id)} type="button"
                >
                  <div className="font-semibold">{ws.name || ws.id}</div>
                  {ws.description ? <div className="mt-0.5 text-xs text-on-surface-variant line-clamp-1">{ws.description}</div> : null}
                </button>
              ))
            )}
          </div>
          <div className="mt-6 flex flex-wrap gap-3">
            <button className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={!selectedWorkspaceId || loading} onClick={handleRequestReview} type="button">
              {loading ? "Loading review..." : "Review compatibility"}
              <span className="material-symbols-outlined text-[18px]">preview</span>
            </button>
            <button className="inline-flex items-center gap-2 rounded-xl bg-surface-container-low px-5 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
              disabled={loading} onClick={onCancel} type="button">Cancel</button>
          </div>
        </div>
      </div>
    );
  }

    onConfirm({ review_id: reviewData?.review_id || "", confirmed_conflicts: [...confirmedConflictIds] });
  }


  // Review step
  if (!reviewData) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onCancel}>
      <div className="w-full max-w-2xl rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <h3 className="font-headline text-xl font-bold text-on-surface">Rebind Compatibility Review</h3>
        <p className="mt-1 text-sm leading-6 text-on-surface-variant">
          Review how your preserved evidence aligns with the new workspace before completing the rebind.
        </p>
        {reviewData.summary ? (
          <div className="mt-4 rounded-xl border border-outline-variant/10 bg-surface-container px-4 py-3">
            <p className="text-sm font-semibold text-on-surface">Summary</p>
            <p className="mt-1 text-sm leading-6 text-on-surface-variant">{reviewData.summary}</p>
          </div>
        ) : null}
        {error ? (
          <div className="mt-3 rounded-xl border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">{error}</div>
        ) : null}
        <div className="mt-5 space-y-5">
          {SECTION_GROUPS.map((group) => {
            const items = reviewData[group.key] || [];
            if (items.length === 0) return null;
            const isConflict = group.key === "conflicts";
            return (
              <div key={group.key}>
                <div className="flex items-center gap-2 mb-2">
                  <span className={`material-symbols-outlined text-[20px] text-${group.tone}`}>{group.icon}</span>
                  <h4 className="text-sm font-semibold text-on-surface">
                    {group.label} <span className="ml-2 text-xs font-normal text-on-surface-variant">({items.length})</span>
                  </h4>
                </div>
                <p className="mb-3 text-xs text-on-surface-variant">{group.description}</p>
                <div className="space-y-2">
                  {items.map((exp, idx) => (
                    <div key={exp.experience_id || idx}>
                      {isConflict ? (
                        <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-outline-variant/20 bg-surface p-3 transition-colors hover:border-warning/30">
                          <input checked={confirmedConflictIds.has(exp.experience_id)} className="mt-0.5 h-4 w-4 shrink-0 accent-primary"
                            onChange={() => toggleConflict(exp.experience_id)} type="checkbox" />
                          <div className="min-w-0 flex-1"><ExperienceRow experience={exp} showSource={true} /></div>
                        </label>
                      ) : (
                        <ExperienceRow experience={exp} showSource={group.key !== "matching_experiences"} />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}

          {/* Empty state */}
          {SECTION_GROUPS.every((g) => (reviewData[g.key] || []).length === 0) ? (
            <div className="rounded-xl border border-dashed border-outline-variant/20 p-6 text-center">
              <span className="material-symbols-outlined text-[2.5rem] text-on-surface-variant">check</span>
              <p className="mt-2 text-sm text-on-surface-variant">No compatibility issues detected. Ready to rebind.</p>
            </div>
          ) : null}
        </div>

        <div className="mt-6 flex flex-wrap gap-3">
          <button className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!allConflictsConfirmed || confirming} onClick={handleConfirm} type="button">
            {confirming ? "Rebinding..." : "Confirm rebind"}
            <span className="material-symbols-outlined text-[18px]">link</span>
          </button>
          <button className="inline-flex items-center gap-2 rounded-xl bg-surface-container-low px-5 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            disabled={confirming} onClick={() => setStep("select")} type="button">Back</button>
          <button className="inline-flex items-center gap-2 rounded-xl bg-surface-container-low px-5 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            disabled={confirming} onClick={onCancel} type="button">Cancel</button>
        </div>
        {hasConflicts && !allConflictsConfirmed ? (
          <p className="mt-3 text-xs text-warning">You must confirm all conflicts before rebinding can proceed.</p>
        ) : null}
      </div>
    </div>
  );
}

