import { useEffect, useMemo, useState } from "react";

function latestOutput(outputs = []) {
  return [...outputs].sort((left, right) => (
    String(right.updated_at || right.created_at || "").localeCompare(
      String(left.updated_at || left.created_at || ""),
    )
  ))[0] || null;
}

export default function FactGroundedMemoryWorkspace({ request, selectedAssetIds = [] }) {
  const [state, setState] = useState({ evidence: [], outputs: [] });
  const [feedback, setFeedback] = useState({ busy: "", message: "", error: "" });
  const [outputDraft, setOutputDraft] = useState({ cv_bullet: "", cover_letter: "" });
  const output = useMemo(() => latestOutput(state.outputs), [state.outputs]);

  async function loadState() {
    const payload = await request("/evidence-items");
    const outputsPayload = await request("/evidence-items/outputs");
    setState({
      evidence: payload.evidence || [],
      outputs: outputsPayload.outputs || outputsPayload.evidence_outputs || [],
    });
  }

  useEffect(() => {
    loadState().catch((error) => {
      setFeedback({ busy: "", message: "", error: error.message || "Unable to load evidence items." });
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setOutputDraft({
      cv_bullet: output?.cv_bullet || "",
      cover_letter: output?.cover_letter || "",
    });
  }, [output?.cover_letter, output?.cv_bullet, output?.output_id, output?.version]);

  async function extract() {
    if (!selectedAssetIds.length) {
      setFeedback({ busy: "", message: "", error: "Select at least one source in the Sources tab first." });
      return;
    }
    setFeedback({ busy: "extract", message: "", error: "" });
    try {
      const payload = await request("/evidence-items/migrate", {
        method: "POST",
        body: { profile_id: "default", source_asset_ids: selectedAssetIds },
      });
      setState((prev) => ({
        ...prev,
        evidence: [...prev.evidence, ...(payload.evidence || [])],
      }));
      setFeedback({
        busy: "",
        message: `Analysed ${payload.migrated || payload.created_count || 0} new evidence item(s).`,
        error: "",
      });
    } catch (error) {
      setFeedback({ busy: "", message: "", error: error.message || "Unable to analyse the selected documents." });
    }
  }

  async function confirmEvidence(evidenceId) {
    setFeedback({ busy: "confirm", message: "", error: "" });
    try {
      const payload = await request(`/evidence-items/${encodeURIComponent(evidenceId)}/status`, {
        method: "POST",
        body: { status: "confirmed" },
      });
      setState((prev) => ({
        ...prev,
        evidence: prev.evidence.map((ev) =>
          ev.evidence_id === evidenceId ? payload : ev
        ),
      }));
      setFeedback({ busy: "", message: "Evidence verified as confirmed.", error: "" });
    } catch (error) {
      setFeedback({ busy: "", message: "", error: error.message || "Unable to verify the evidence." });
    }
  }

  async function generate(mode = "standard") {
    setFeedback({ busy: mode, message: "", error: "" });
    try {
      const payload = output
        ? await request(`/evidence-items/outputs/${encodeURIComponent(output.output_id)}/regenerate`, {
            method: "POST",
            body: { action: mode },
          })
        : await request("/evidence-items/generate", {
            method: "POST",
            body: { mode },
          });
      setState((prev) => ({
        ...prev,
        outputs: output
          ? prev.outputs.map((o) => (o.output_id === output.output_id ? payload : o))
          : [...prev.outputs, payload],
      }));
      setFeedback({ busy: "", message: "Verified CV and cover-letter outputs generated.", error: "" });
    } catch (error) {
      setFeedback({ busy: "", message: "", error: error.message || "Unable to generate verified output." });
    }
  }

  async function saveOutputEdit() {
    if (!output) return;
    setFeedback({ busy: "edit", message: "", error: "" });
    try {
      const payload = await request(`/evidence-items/outputs/${encodeURIComponent(output.output_id)}/regenerate`, {
        method: "POST",
        body: { action: "edit", ...outputDraft },
      });
      setState((prev) => ({
        ...prev,
        outputs: prev.outputs.map((o) => (o.output_id === output.output_id ? payload : o)),
      }));
      setFeedback({ busy: "", message: "Output edit saved without changing its source evidence.", error: "" });
    } catch (error) {
      setFeedback({ busy: "", message: "", error: error.message || "Unable to save the output edit." });
    }
  }

  const activeEvidence = (state.evidence || []).filter(
    (ev) => ev.status !== "rejected" && ev.status !== "merged"
  );
  const confirmedEvidence = activeEvidence.filter((ev) => ev.status === "confirmed");

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h2 className="font-headline text-2xl font-bold text-on-surface">Evidence-based Career Memory</h2>
            <p className="mt-2 max-w-3xl text-sm leading-7 text-on-surface-variant">
              Review extracted evidence, confirm claims, then generate separate CV and cover-letter wording from verified evidence.
            </p>
          </div>
          <button
            className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
            disabled={feedback.busy === "extract"}
            onClick={extract}
            type="button"
          >
            {feedback.busy === "extract" ? "Analysing..." : "Analyse selected documents"}
          </button>
        </div>
        {feedback.message || feedback.error ? (
          <p className={`mt-4 text-sm ${feedback.error ? "text-error" : "text-primary"}`}>
            {feedback.error || feedback.message}
          </p>
        ) : null}
      </section>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <div className="space-y-6">
          <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-headline text-xl font-bold text-on-surface">Evidence</h3>
              <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                {activeEvidence.length} active ({confirmedEvidence.length} confirmed)
              </span>
            </div>
            <div className="mt-4 max-h-[34rem] space-y-3 overflow-y-auto pr-1">
              {activeEvidence.length ? activeEvidence.map((ev) => (
                <article className="rounded-2xl border border-outline-variant/15 bg-surface p-4" key={ev.evidence_id}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-surface-container-low px-2 py-1 text-[11px] font-semibold uppercase text-on-surface-variant">
                      {ev.evidence_type}
                    </span>
                    <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${
                      ev.status === "confirmed" ? "bg-primary/10 text-primary" :
                      ev.status === "needs_review" ? "bg-amber-500/10 text-amber-700" :
                      "bg-surface-container-low text-on-surface-variant"
                    }`}>
                      {ev.status}
                    </span>
                    {ev.certainty && (
                      <span className="text-[11px] text-on-surface-variant">{ev.certainty}</span>
                    )}
                    <span className="text-[11px] text-on-surface-variant">v{ev.version}</span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-on-surface">{ev.text}</p>
                  <div className="mt-3 flex items-center gap-2">
                    {ev.status !== "confirmed" && (
                      <button
                        className="rounded-lg bg-primary/10 px-3 py-1.5 text-xs font-semibold text-primary"
                        disabled={feedback.busy === "confirm"}
                        onClick={() => confirmEvidence(ev.evidence_id)}
                        type="button"
                      >
                        Confirm
                      </button>
                    )}
                    {ev.inferred_employer && (
                      <span className="text-[11px] text-on-surface-variant">
                        {ev.inferred_employer}{ev.inferred_role ? ` / ${ev.inferred_role}` : ""}
                      </span>
                    )}
                  </div>
                </article>
              )) : (
                <p className="rounded-2xl border border-dashed border-outline-variant/20 p-5 text-sm text-on-surface-variant">
                  No evidence items yet. Select sources and analyse the documents.
                </p>
              )}
            </div>
          </section>
        </div>

        <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="font-headline text-xl font-bold text-on-surface">Generate from verified evidence</h3>
              <p className="mt-1 text-sm text-on-surface-variant">Edits create output versions and never mutate evidence.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {[
                ["standard", output ? "Regenerate" : "Generate"],
                ["shorten", "Shorten"],
                ["technical", "Technical emphasis"],
              ].map(([mode, label]) => (
                <button
                  className="rounded-xl bg-surface-container-low px-3 py-2 text-xs font-semibold text-primary disabled:opacity-50"
                  disabled={!confirmedEvidence.length || Boolean(feedback.busy)}
                  key={mode}
                  onClick={() => generate(mode)}
                  type="button"
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          {output ? (
            <div className="mt-5 space-y-5">
              <label className="block">
                <span className="text-sm font-semibold text-on-surface">CV bullet</span>
                <textarea
                  className="mt-2 min-h-32 w-full rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm leading-6"
                  onChange={(event) => setOutputDraft((current) => ({ ...current, cv_bullet: event.target.value }))}
                  value={outputDraft.cv_bullet}
                />
              </label>
              <label className="block">
                <span className="text-sm font-semibold text-on-surface">Cover-letter narrative</span>
                <textarea
                  className="mt-2 min-h-44 w-full rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm leading-6"
                  onChange={(event) => setOutputDraft((current) => ({ ...current, cover_letter: event.target.value }))}
                  value={outputDraft.cover_letter}
                />
              </label>
              <button
                className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
                disabled={feedback.busy === "edit"}
                onClick={saveOutputEdit}
                type="button"
              >
                Save output edit
              </button>
              <div className={`rounded-2xl px-4 py-3 text-sm ${output.quality?.status === "passed" ? "bg-primary/10 text-primary" : "bg-error/5 text-error"}`}>
                Quality gate: {output.quality?.status || "unknown"}
                {(output.quality?.issues || []).map((issue) => <div className="mt-1" key={issue.code}>{issue.message}</div>)}
              </div>
              <div className="text-xs text-on-surface-variant">
                Evidence: {(output.evidence_ids || []).join(", ")} · output v{output.version}
              </div>
            </div>
          ) : (
            <p className="mt-5 rounded-2xl border border-dashed border-outline-variant/20 p-6 text-sm text-on-surface-variant">
              Confirm evidence items, then generate distinct CV and cover-letter output.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
