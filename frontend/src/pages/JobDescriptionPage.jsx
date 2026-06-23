import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { trackerDescriptionForItem } from "../lib/trackerDescription";

export default function JobDescriptionPage() {
  const { reviewId = "" } = useParams();
  const { request } = useSession();
  const [copyFeedback, setCopyFeedback] = useState({ message: "", error: "" });
  const { data, loading, error } = useApiResource(
    () => request("/tracker"),
    [request, reviewId],
  );
  const item = (data?.items || []).find((candidate) => candidate.review_id === reviewId);
  const description = trackerDescriptionForItem(item);

  async function copyDescription() {
    if (!description) return;
    setCopyFeedback({ message: "", error: "" });
    try {
      await navigator.clipboard.writeText(description);
      setCopyFeedback({ message: "Full job description copied.", error: "" });
    } catch (copyError) {
      setCopyFeedback({
        message: "",
        error: copyError.message || "Unable to copy the job description.",
      });
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-3 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest px-6 py-5 text-sm text-on-surface-variant">
        <span className="material-symbols-outlined animate-spin">progress_activity</span>
        Loading job description...
      </div>
    );
  }

  if (error || !item) {
    return (
      <section className="mx-auto max-w-4xl rounded-3xl border border-error/20 bg-surface-container-lowest p-8 shadow-sm">
        <h1 className="font-headline text-2xl font-bold text-on-surface">Job description unavailable</h1>
        <p className="mt-3 text-sm leading-6 text-error">
          {error || "This tracker job could not be found."}
        </p>
        <Link className="mt-5 inline-flex text-sm font-semibold text-primary hover:underline" to="/tracker">
          Return to tracker
        </Link>
      </section>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-7 shadow-sm">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
          Job description
        </div>
        <h1 className="mt-2 font-headline text-3xl font-extrabold tracking-tight text-on-surface">
          {item.title || "Untitled role"}
        </h1>
        <p className="mt-2 text-sm text-on-surface-variant">
          {[item.company, item.location].filter(Boolean).join(" | ") || "Tracker job"}
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <button
            className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!description}
            onClick={copyDescription}
            type="button"
          >
            <span className="material-symbols-outlined text-[17px]">content_copy</span>
            Copy full description
          </button>
          {item.apply_link ? (
            <a
              className="inline-flex items-center gap-2 rounded-full bg-surface-container-low px-4 py-2 text-sm font-semibold text-on-surface transition-colors hover:bg-surface-container-high"
              href={item.apply_link}
              rel="noreferrer"
              target="_blank"
            >
              Open job posting
              <span className="material-symbols-outlined text-[17px]">open_in_new</span>
            </a>
          ) : null}
          <Link
            className="inline-flex items-center rounded-full bg-surface-container-low px-4 py-2 text-sm font-semibold text-primary transition-colors hover:bg-surface-container-high"
            to="/tracker"
          >
            Return to tracker
          </Link>
        </div>
        {copyFeedback.message || copyFeedback.error ? (
          <p className={`mt-4 text-sm ${copyFeedback.error ? "text-error" : "text-primary"}`}>
            {copyFeedback.error || copyFeedback.message}
          </p>
        ) : null}
      </header>

      <main className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-7 shadow-sm">
        <div className="whitespace-pre-wrap text-sm leading-7 text-on-surface">
          {description || "No job description is available for this tracker job."}
        </div>
      </main>
    </div>
  );
}
