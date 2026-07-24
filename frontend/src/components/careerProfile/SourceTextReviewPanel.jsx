import { useCallback, useEffect, useState } from "react";
import { useSession } from "../../context/SessionContext";

const STATUS_LABELS = {
  pending: { text: "Needs Review", tone: "warning" },
  in_progress: { text: "In Progress", tone: "primary" },
  confirmed: { text: "Verified", tone: "success" },
  rejected: { text: "Rejected", tone: "error" },
};

export default function SourceTextReviewPanel({
  profileId, sourceId, sourceName, onReviewComplete,
}) {
  const { request } = useSession();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [review, setReview] = useState(null);
  const [correctedText, setCorrectedText] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const loadReview = useCallback(async () => {
    if (!profileId || !sourceId) return;
    setLoading(true); setError("");
    try {
      const data = await request(
        `/career-profiles/${encodeURIComponent(profileId)}/sources/${encodeURIComponent(sourceId)}/review`,
        { method: "GET" }, { rawPath: true }
      );
      setReview(data);
      setCorrectedText(data.corrected_text || data.original_text || "");
    } catch (err) {
      setError(String(err?.message || "Failed to load source review."));
    } finally { setLoading(false); }
  }, [profileId, sourceId, request]);

  useEffect(() => { loadReview(); }, [loadReview]);

  const handleSaveCorrection = async () => {
    if (!review) return;
    setSaving(true);
    try {
      const updated = await request(
        `/career-profiles/${encodeURIComponent(profileId)}/sources/${encodeURIComponent(sourceId)}/review`,
        { method: "PUT", body: JSON.stringify({ corrected_text: correctedText }) },
        { rawPath: true }
      );
      setReview(updated); setError("");
    } catch (err) {
      setError(String(err?.message || "Failed to save correction."));
    } finally { setSaving(false); }
  };

  const handleConfirm = async () => {
    if (!review) return;
    setConfirming(true);
    try {
      const updated = await request(
        `/career-profiles/${encodeURIComponent(profileId)}/sources/${encodeURIComponent(sourceId)}/confirm`,
        { method: "POST" }, { rawPath: true }
      );
      setReview(updated);
      if (onReviewComplete) onReviewComplete(updated);
    } catch (err) {
      setError(String(err?.message || "Failed to confirm review."));
    } finally { setConfirming(false); }
  };

  const handleReject = async () => {
    if (!review) return;
    try {
      const updated = await request(
        `/career-profiles/${encodeURIComponent(profileId)}/sources/${encodeURIComponent(sourceId)}/reject`,
        { method: "POST" }, { rawPath: true }
      );
      setReview(updated);
      if (onReviewComplete) onReviewComplete(updated);
    } catch (err) {
      setError(String(err?.message || "Failed to reject source."));
    }
  };


  if (loading) {
    return (
      <div className="animate-pulse space-y-3 p-4">
        <div className="h-6 w-48 rounded bg-surface-container" />
        <div className="h-32 w-full rounded bg-surface-container" />
      </div>
    );
  }
  if (error && !review) {
    return (
      <div className="rounded-2xl border border-error/20 bg-error/5 p-4 text-sm text-error">
        {error}
      </div>
    );
  }
  if (!review) return null;

  const statusInfo = STATUS_LABELS[review.status] || STATUS_LABELS.pending;
  const isConfirmed = review.status === "confirmed";
  const isLowConfidence = review.is_low_confidence_ocr;
  const isEditable = !isConfirmed && review.status !== "rejected";

  return (
    <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-headline text-lg font-bold text-on-surface">
            {sourceName || review.file_name || "Source Text Review"}
          </h3>
          <p className="mt-1 text-xs text-on-surface-variant">
            Review and correct the extracted text before it becomes evidence.
          </p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${
          statusInfo.tone === "warning" ? "bg-warning/10 text-warning" :
          statusInfo.tone === "success" ? "bg-success/10 text-success" :
          statusInfo.tone === "error" ? "bg-error/10 text-error" :
          "bg-primary/10 text-primary"
        }`}>
          {statusInfo.text}
        </span>
      </div>



      {review.warnings?.length > 0 && (
        <div className="mt-4 rounded-xl border border-warning/20 bg-warning/5 p-3">
          <div className="flex items-start gap-2">
            <span className="material-symbols-outlined mt-0.5 text-[18px] text-warning">warning</span>
            <div>
              <p className="text-sm font-semibold text-warning">Extraction Warnings</p>
              <ul className="mt-1 list-inside list-disc space-y-1 text-xs text-warning/80">
                {review.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          </div>
        </div>
      )}
      {isLowConfidence && (
        <div className="mt-3 rounded-xl border border-error/20 bg-error/5 p-3">
          <p className="text-sm font-medium text-error">
            Low confidence extraction ({Math.round(review.original_confidence * 100)}%).
            Review is required before this text can be used as evidence.
          </p>
        </div>
      )}

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div>
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">Extracted Text</h4>
            <span className="text-[10px] text-on-surface-variant">
              {review.original_method || "unknown"} · {review.original_provider ? `${review.original_provider} / ` : ""}{Math.round(review.original_confidence * 100)}%
            </span>
          </div>
          <div className="mt-2 rounded-xl border border-outline-variant/20 bg-surface p-4">
            <pre className="whitespace-pre-wrap break-words text-sm text-on-surface font-sans">
              {review.original_text || "(No text extracted)"}
            </pre>
          </div>
        </div>
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
            {isEditable ? "Corrected Text" : "Verified Text"}
          </h4>
          {isEditable ? (
            <textarea
              className="mt-2 w-full rounded-xl border border-outline-variant/20 bg-surface p-4 text-sm text-on-surface focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              onChange={(e) => setCorrectedText(e.target.value)}
              placeholder="Edit the extracted text to fix OCR errors..."
              rows={10} value={correctedText}
            />
          ) : (
            <div className="mt-2 rounded-xl border border-outline-variant/20 bg-surface p-4">
              <pre className="whitespace-pre-wrap break-words text-sm text-on-surface font-sans">
                {review.corrected_text || review.original_text}
              </pre>
            </div>
          )}
        </div>
      </div>

      {review.correction_history?.length > 0 && (
        <details className="group mt-4">
          <summary className="cursor-pointer text-xs font-medium text-on-surface-variant hover:text-on-surface">
            Correction History ({review.correction_history.length} change{review.correction_history.length !== 1 ? "s" : ""})
          </summary>
          <div className="mt-2 space-y-2">
            {review.correction_history.map((entry, i) => (
              <div className="rounded-lg border border-outline-variant/10 bg-surface-container px-3 py-2 text-xs text-on-surface-variant" key={i}>
                <span className="font-medium">{entry.timestamp ? new Date(entry.timestamp).toLocaleString() : ""}</span>
                {" · "}<span className="text-primary">{entry.changed_by || "user"}</span>
                {" · "}<span>{entry.char_diff > 0 ? "+" : ""}{entry.char_diff} chars</span>
              </div>
            ))}
          </div>
        </details>
      )}
      {error && (
        <div className="mt-4 rounded-xl border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">{error}</div>
      )}
      {isEditable && (
        <div className="mt-6 flex flex-wrap gap-3">
          <button
            className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={saving} onClick={handleSaveCorrection} type="button"
          >
            {saving ? "Saving..." : "Save Correction"}
          </button>
          <button
            className="inline-flex items-center gap-2 rounded-xl bg-success px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={confirming} onClick={handleConfirm} type="button"
          >
            {confirming ? "Confirming..." : "Confirm & Create Evidence"}
          </button>
          <button
            className="inline-flex items-center gap-2 rounded-xl bg-surface-container-high px-5 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-60"
            onClick={handleReject} type="button"
          >
            Reject Source
          </button>
        </div>
      )}
    </div>
  );
}
