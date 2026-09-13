import { useEffect, useState } from "react";

/**
 * EvidenceQuestions — interactive prompt that asks users to fill missing
 * details (outcome, metric, tool, etc.) on canonical evidence items.
 *
 * Props:
 *   request        — (path, opts?) => Promise<json>
 *   onEvidenceRefresh — callback to reload evidence list after an answer
 */
export default function EvidenceQuestions({ request, onEvidenceRefresh }) {
  const [question, setQuestion] = useState(null);
  const [feedback, setFeedback] = useState({ busy: "", message: "", error: "" });
  const [answerText, setAnswerText] = useState("");

  async function loadQuestion() {
    try {
      const payload = await request("/evidence-items/questions");
      setQuestion(payload);
      setAnswerText("");
      setFeedback({ busy: "", message: "", error: "" });
    } catch (error) {
      setFeedback({ busy: "", message: "", error: error.message || "Unable to load question." });
    }
  }

  useEffect(() => {
    loadQuestion();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleAnswer() {
    if (!question?.question_id || !answerText.trim()) return;
    setFeedback({ busy: "answer", message: "", error: "" });
    try {
      await request(
        `/evidence-items/questions/${encodeURIComponent(question.question_id)}/answer`,
        { method: "POST", body: { text: answerText.trim() } },
      );
      setFeedback({ busy: "", message: "Answer saved — evidence updated.", error: "" });
      if (onEvidenceRefresh) onEvidenceRefresh();
      await loadQuestion();
    } catch (error) {
      setFeedback({ busy: "", message: "", error: error.message || "Unable to save answer." });
    }
  }

  async function handleSkip() {
    if (!question?.question_id) return;
    setFeedback({ busy: "skip", message: "", error: "" });
    try {
      await request(
        `/evidence-items/questions/${encodeURIComponent(question.question_id)}/skip`,
        { method: "POST" },
      );
      setFeedback({ busy: "", message: "Question skipped.", error: "" });
      await loadQuestion();
    } catch (error) {
      setFeedback({ busy: "", message: "", error: error.message || "Unable to skip question." });
    }
  }

  async function handleDismiss() {
    if (!question?.question_id) return;
    setFeedback({ busy: "dismiss", message: "", error: "" });
    try {
      await request(
        `/evidence-items/questions/${encodeURIComponent(question.question_id)}/dismiss`,
        { method: "POST" },
      );
      setFeedback({ busy: "", message: "Question dismissed.", error: "" });
      await loadQuestion();
    } catch (error) {
      setFeedback({ busy: "", message: "", error: error.message || "Unable to dismiss question." });
    }
  }

  // Complete state — no useful questions remain
  if (question?.state === "complete") {
    return (
      <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        <h3 className="font-headline text-xl font-bold text-on-surface">Evidence Completeness</h3>
        <p className="mt-2 text-sm leading-6 text-on-surface-variant">
          All evidence items are complete — no useful questions remain.
        </p>
      </section>
    );
  }

  if (!question) {
    return (
      <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        <h3 className="font-headline text-xl font-bold text-on-surface">Evidence Completeness</h3>
        {feedback.error ? (
          <p className="mt-2 text-sm text-error">{feedback.error}</p>
        ) : (
          <p className="mt-2 text-sm text-on-surface-variant">Loading questions...</p>
        )}
      </section>
    );
  }

  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-headline text-xl font-bold text-on-surface">Fill in missing detail</h3>
          <p className="mt-1 text-sm text-on-surface-variant">
            {question.evidence_label} &middot; {question.evidence_type} &middot; priority {question.priority}
          </p>
        </div>
        {question.missing_type && (
          <span className="rounded-full bg-amber-500/10 px-3 py-1 text-xs font-semibold text-amber-700">
            {question.missing_type.replace(/_/g, " ")}
          </span>
        )}
      </div>

      <p className="mt-4 text-sm leading-6 text-on-surface">{question.question}</p>

      <div className="mt-4">
        <textarea
          className="min-h-20 w-full rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm leading-6"
          onChange={(event) => setAnswerText(event.target.value)}
          placeholder="Type your answer..."
          value={answerText}
        />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
          disabled={!answerText.trim() || Boolean(feedback.busy)}
          onClick={handleAnswer}
          type="button"
        >
          {feedback.busy === "answer" ? "Saving..." : "Answer"}
        </button>
        <button
          className="rounded-xl bg-surface-container-low px-4 py-2.5 text-sm font-semibold text-on-surface-variant disabled:opacity-50"
          disabled={Boolean(feedback.busy)}
          onClick={handleSkip}
          type="button"
        >
          {feedback.busy === "skip" ? "Skipping..." : "Skip"}
        </button>
        <button
          className="rounded-xl bg-surface-container-low px-4 py-2.5 text-sm font-semibold text-on-surface-variant disabled:opacity-50"
          disabled={Boolean(feedback.busy)}
          onClick={handleDismiss}
          type="button"
        >
          {feedback.busy === "dismiss" ? "Dismissing..." : "Dismiss"}
        </button>
      </div>

      {feedback.message || feedback.error ? (
        <p className={`mt-3 text-sm ${feedback.error ? "text-error" : "text-primary"}`}>
          {feedback.error || feedback.message}
        </p>
      ) : null}

      <p className="mt-3 text-xs text-on-surface-variant">
        &ldquo;{question.evidence_text?.slice(0, 100)}{question.evidence_text?.length > 100 ? "\u2026" : ""}&rdquo;
      </p>
    </section>
  );
}