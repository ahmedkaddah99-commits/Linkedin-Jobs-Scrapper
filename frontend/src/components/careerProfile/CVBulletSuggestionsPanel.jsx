/**
 * CV Bullet Suggestions Panel (CP-036R)
 *
 * Displays role-specific bullet suggestions generated from baseline CV,
 * job description, and selected verified canonical evidence.
 * Supports Accept, Edit, Reject, and Replace actions.
 */
import { useState, useCallback } from "react";

const STATUS_LABELS = {
  pending: "Pending", accepted: "Accepted", edited: "Edited",
  rejected: "Rejected", replaced: "Replaced",
};

const STATUS_CLASSES = {
  pending: "bg-amber-100 text-amber-800",
  accepted: "bg-emerald-100 text-emerald-800",
  edited: "bg-blue-100 text-blue-800",
  rejected: "bg-red-100 text-red-800",
  replaced: "bg-purple-100 text-purple-800",
};

export default function CVBulletSuggestionsPanel({
  suggestions = [], onAction, loading = false, error = "",
}) {
  const [editingId, setEditingId] = useState(null);
  const [editText, setEditText] = useState("");

  const startEdit = (s) => {
    setEditingId(s.suggestion_id);
    setEditText(s.effective_text || s.bullet_text);
  };

  if (loading) return <p className="p-4 text-sm animate-pulse">Loading...</p>;
  if (error) return <p className="p-4 text-sm text-red-600">{error}</p>;
  if (!suggestions.length) return null;

  const badgeClass = (status) => {
    const map = { pending: "bg-amber-100 text-amber-800",
      accepted: "bg-emerald-100 text-emerald-800",
      edited: "bg-blue-100 text-blue-800",
      rejected: "bg-red-100 text-red-800",
      replaced: "bg-purple-100 text-purple-800" };
    return map[status] || "bg-gray-100 text-gray-600";
  };

  const label = (status) => {
    const map = { pending: "Pending", accepted: "Accepted",
      edited: "Edited", rejected: "Rejected", replaced: "Replaced" };
    return map[status] || status;
  };

  return (
    <div className="space-y-4">
      <h3 className="font-headline text-lg font-bold">CV Bullet Suggestions</h3>
      <div className="space-y-3">
        {suggestions.map((s) => (
          <div key={s.suggestion_id}
            className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-4">
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className="text-xs text-on-surface-variant">
                {s.label || "Bullet"}</span>
              <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${badgeClass(s.status)}`}>
                {label(s.status)}</span>
            </div>

            {editingId === s.suggestion_id ? (
              <div className="space-y-2">
                <textarea className="w-full rounded-xl border px-3 py-2 text-sm"
                  rows={2} value={editText}
                  onChange={(e) => setEditText(e.target.value)} />
                <div className="flex gap-2">
                  <button className="rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-on-primary"
                    onClick={() => { onAction(s.suggestion_id, "edit", editText); setEditingId(null); }}>
                    Save</button>
                  <button className="rounded-lg bg-gray-200 px-3 py-1.5 text-xs"
                    onClick={() => setEditingId(null)}>Cancel</button>
                </div>
              </div>
            ) : (
              <p className="text-sm">{s.effective_text || s.bullet_text}</p>
            )}

            {s.evidence_ids?.length > 0 && (
              <div className="mt-2 text-[11px] text-on-surface-variant">
                Evidence: {s.evidence_ids.length} item(s)
                {s.baseline_cv_version && ` | CV: ${s.baseline_cv_version}`}
              </div>
            )}

            {s.status === "pending" && (
              <div className="mt-3 flex flex-wrap gap-2">
                {["accept", "edit", "reject", "replace"].map((action) => (
                  <button key={action}
                    className="rounded-lg bg-gray-700 px-3 py-1.5 text-xs font-semibold text-white"
                    onClick={() => action === "edit" || action === "replace"
                      ? startEdit(s) : onAction(s.suggestion_id, action)}>
                    {action.charAt(0).toUpperCase() + action.slice(1)}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
