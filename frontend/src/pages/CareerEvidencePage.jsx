// CP-038R: Career Evidence guided flow — one primary action per lifecycle state.
// Replaces the seven-tab Career Memory dashboard with a narrow task column.

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import {
  buildLifecycleSummary,
  LIFECYCLE_STATE,
} from "../lib/careerEvidenceFlow";

const DOCUMENTS_REQUEST_TIMEOUT_MS = 60000;

function normalizeDocumentId(document) {
  return String(
    document?.document_id || document?.asset_id || document?.id || "",
  ).trim();
}

export default function CareerEvidencePage() {
  const { request } = useSession();
  const navigate = useNavigate();

  const {
    data: documentsPayload,
    loading: documentsLoading,
    refresh: refreshDocuments,
  } = useApiResource(
    () => request("/documents?limit=500", { timeoutMs: DOCUMENTS_REQUEST_TIMEOUT_MS }),
    [request],
    { cacheKey: "documents:all", staleMs: 30000, backgroundRefresh: true },
  );

  const { data: settingsPayload, refresh: refreshSettings } = useApiResource(
    () => request("/settings", { timeoutMs: 60000 }),
    [request],
    { cacheKey: "settings", staleMs: Infinity, backgroundRefresh: false },
  );

  const allDocuments = documentsPayload?.documents || [];
  const settingsDocuments = settingsPayload?.documents || {};

  const evidenceItems = useMemo(
    () => settingsPayload?.documents?.evidence_items || [],
    [settingsPayload],
  );

  const experienceLinks = useMemo(
    () => settingsDocuments.experience_links || [],
    [settingsDocuments],
  );

  const pendingQuestions = useMemo(
    () => settingsDocuments.pending_questions || [],
    [settingsDocuments],
  );

  const selectedSourceIds = useMemo(
    () =>
      settingsDocuments.selectedAssetIds ||
      settingsDocuments.ai_canvas_source_asset_ids ||
      [],
    [settingsDocuments],
  );

  const sourceDocuments = useMemo(
    () =>
      allDocuments.filter((item) => {
        const origin = String(item.source_origin || "").trim().toLowerCase();
        return origin === "upload";
      }),
    [allDocuments],
  );

  const lifecycle = useMemo(
    () =>
      buildLifecycleSummary({
        sources: sourceDocuments,
        selectedSourceIds,
        evidenceItems,
        experienceLinks,
        pendingQuestions,
      }),
    [sourceDocuments, selectedSourceIds, evidenceItems, experienceLinks, pendingQuestions],
  );



  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const saveToSettings = useCallback(
    async (updates) => {
      try {
        await request("/settings", {
          method: "PUT",
          body: { documents: { ...settingsDocuments, ...updates } },
        });
        await refreshSettings().catch(() => undefined);
      } catch {
        // Retry on next action.
      }
    },
    [request, settingsDocuments, refreshSettings],
  );

  async function handleSourceSelect(assetId) {
    const nextIds = selectedSourceIds.includes(assetId)
      ? selectedSourceIds.filter((id) => id !== assetId)
      : [...selectedSourceIds, assetId];
    await saveToSettings({ selectedAssetIds: nextIds });
    await refreshSettings().catch(() => undefined);
  }

  async function handleUploadSource(file) {
    setUploading(true);
    setUploadMessage("");
    setUploadError("");
    try {
      const formData = new FormData();
      formData.append("document_file", file);
      const params = new URLSearchParams();
      params.set("asset_kind", "uploaded_document");
      params.set("display_name", file.name);
      const response = await request(`/documents/upload?${params.toString()}`, {
        method: "POST",
        body: formData,
      });
      if (response?.status_url) {
        let ready = false;
        setUploadMessage(`Uploaded ${file.name}. Extracting text...`);
        for (let i = 0; i < 60; i += 1) {
          await new Promise((r) => window.setTimeout(r, 1500));
          const p = await request(response.status_url);
          if (p.status === "ready") { ready = true; break; }
          if (p.status === "failed") throw new Error(p.error || "Extraction failed.");
        }
        if (!ready) throw new Error("Still processing. Refresh in a moment.");
      }
      const assetId = normalizeDocumentId(response?.asset || {});
      if (assetId) {
        await saveToSettings({ selectedAssetIds: [...selectedSourceIds, assetId] });
      }
      await refreshDocuments().catch(() => undefined);
      await refreshSettings().catch(() => undefined);
      setUploading(false);
      setUploadMessage(`Uploaded ${file.name}.`);
    } catch (err) {
      setUploading(false);
      setUploadError(err.message || "Upload failed.");
      await refreshDocuments().catch(() => undefined);
    }
  }

  function handleFileChange(e) {
    const file = e.target.files?.[0];
    if (file) handleUploadSource(file);
  }

  async function handleAnswerQuestion(questionId, answer) {
    const updated = pendingQuestions.map((q) =>
      q.question_id === questionId ? { ...q, resolved: true, answer } : q,
    );
    await saveToSettings({ pending_questions: updated });
  }

  async function handleConfirmEvidence(evidenceId) {
    const updated = evidenceItems.map((ev) =>
      ev.evidence_id === evidenceId ? { ...ev, status: "confirmed" } : ev,
    );
    await saveToSettings({ evidence_items: updated });
  }

  async function handleLinkExperience() {
    const links = [
      ...experienceLinks,
      { link_id: `lnk_${Date.now()}`, mapped: true, linked_at: new Date().toISOString() },
    ];
    await saveToSettings({ experience_links: links });
  }

  const { state, label, description, primaryAction, progress, progressLabel: stepLabel } =
    lifecycle;

  return (
    <div className="mx-auto max-w-2xl space-y-8 px-4 py-8">
      <header>
        <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-primary">
          Career Evidence
        </div>
        <h1 className="mt-3 font-headline text-3xl font-extrabold tracking-tight text-on-surface">
          {label}
        </h1>
        <p className="mt-2 max-w-xl text-sm leading-6 text-on-surface-variant">
          {description}
        </p>
      </header>

      <div
        aria-label="Progress"
        className="space-y-2"
        role="progressbar"
        aria-valuenow={Math.round(progress * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="flex items-center justify-between text-xs font-medium text-on-surface-variant">
          <span>{stepLabel}</span>
          <span>{Math.round(progress * 100)}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-surface-container-highest">
          <div
            className="h-full rounded-full bg-primary transition-all duration-500 motion-reduce:transition-none"
            style={{ width: `${Math.round(progress * 100)}%` }}
          />
        </div>
      </div>

      {/* ── One primary action ──────────────────────────── */}
      <section className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        {state === LIFECYCLE_STATE.SOURCE ? (
          <SourceState
            onFileChange={handleFileChange}
            onSourceSelect={handleSourceSelect}
            selectedSourceIds={selectedSourceIds}
            sourceDocuments={sourceDocuments}
            uploadError={uploadError}
            uploadMessage={uploadMessage}
            uploading={uploading}
          />
        ) : state === LIFECYCLE_STATE.PROCESSING ? (
          <ProcessingState
            navigate={navigate}
            selectedSourceCount={selectedSourceIds.length}
          />
        ) : state === LIFECYCLE_STATE.REVIEW ? (
          <ReviewState
            evidenceItems={evidenceItems}
            onConfirm={handleConfirmEvidence}
          />
        ) : state === LIFECYCLE_STATE.MAPPING ? (
          <MappingState
            confirmedCount={lifecycle.confirmedCount}
            onLink={handleLinkExperience}
          />
        ) : state === LIFECYCLE_STATE.FOLLOW_UP ? (
          <FollowUpState
            onAnswer={handleAnswerQuestion}
            pendingQuestions={pendingQuestions}
          />
        ) : state === LIFECYCLE_STATE.READY ? (
          <ReadyState
            confirmedCount={lifecycle.confirmedCount}
            mappedCount={lifecycle.mappedCount}
            onToggleHistory={() => setShowHistory((v) => !v)}
          />
        ) : null}
      </section>

      {/* ── Secondary: History ──────────────────────────── */}
      {showHistory ? (
        <HistoryPanel
          evidenceItems={evidenceItems}
          onClose={() => setShowHistory(false)}
        />
      ) : null}

      {/* ── Secondary: Settings ─────────────────────────── */}
      <div className="text-center">
        <button
          className="text-xs font-medium text-on-surface-variant underline decoration-outline-variant hover:text-on-surface"
          onClick={() => setShowSettings((v) => !v)}
          type="button"
        >
          {showSettings ? "Hide settings" : "Settings"}
        </button>
        {showSettings ? (
          <div className="mt-3 rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-4 text-left">
            <p className="text-xs text-on-surface-variant">
              Manage your career evidence profile settings.
            </p>
            <Link
              className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
              to="/settings"
            >
              <span className="material-symbols-outlined text-[14px]">settings</span>
              Open full settings
            </Link>
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────

function SourceState({ onFileChange, onSourceSelect, selectedSourceIds, sourceDocuments, uploadError, uploadMessage, uploading }) {
  return (
    <div className="space-y-4">
      <h2 className="font-headline text-lg font-bold text-on-surface">Upload source</h2>
      <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90">
        <span className="material-symbols-outlined text-[18px]">upload_file</span>
        Upload source document
        <input accept=".pdf,.docx,.doc,.txt" className="sr-only" disabled={uploading} onChange={onFileChange} type="file" />
      </label>
      {uploading ? <p className="text-sm text-on-surface-variant">{uploadMessage || "Uploading..."}</p> : null}
      {uploadError ? <p className="text-sm text-red-600" role="alert">{uploadError}</p> : null}
      {sourceDocuments.length > 0 ? (
        <div className="mt-4 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
            Available sources ({sourceDocuments.length})
          </p>
          {sourceDocuments.slice(0, 5).map((doc) => {
            const docId = String(doc?.document_id || doc?.asset_id || doc?.id || "").trim();
            const isSelected = selectedSourceIds.includes(docId);
            return (
              <button
                className={`flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left text-sm transition-colors ${
                  isSelected ? "border-primary/30 bg-primary/5 text-on-surface" : "border-outline-variant/20 text-on-surface-variant hover:bg-surface-container-low"
                }`}
                key={docId}
                onClick={() => onSourceSelect(docId)}
                type="button"
              >
                <span className="material-symbols-outlined text-[18px]">{isSelected ? "check_circle" : "circle"}</span>
                <span className="truncate">{doc.display_name || docId}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}



function ProcessingState({ navigate, selectedSourceCount }) {
  return (
    <div className="space-y-4" role="status">
      <h2 className="font-headline text-lg font-bold text-on-surface">View progress</h2>
      <p className="text-sm text-on-surface-variant">
        Evidence extraction will begin once sources are confirmed. {selectedSourceCount} selected.
      </p>
      <button
        className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90"
        onClick={() => navigate("/documents")}
        type="button"
      >
        <span className="material-symbols-outlined text-[18px]">description</span>
        Open Asset Library
      </button>
    </div>
  );
}

function ReviewState({ evidenceItems, onConfirm }) {
  const pending = (evidenceItems || []).filter(
    (ev) => ev && ev.status !== "confirmed" && ev.status !== "rejected",
  );
  return (
    <div className="space-y-4">
      <h2 className="font-headline text-lg font-bold text-on-surface">Confirm evidence</h2>
      <p className="text-sm text-on-surface-variant">
        {evidenceItems.length} item{evidenceItems.length !== 1 ? "s" : ""} extracted.
      </p>
      <div className="max-h-64 space-y-2 overflow-y-auto">
        {pending.slice(0, 5).map((ev) => (
          <div className="flex items-start gap-3 rounded-xl border border-outline-variant/20 bg-surface p-3" key={ev.evidence_id}>
            <span className="mt-0.5 flex-1 text-sm leading-relaxed text-on-surface">
              {ev.text || ev.label || ev.evidence_id}
            </span>
            <button
              className="shrink-0 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-white transition-opacity hover:opacity-90"
              onClick={() => onConfirm(ev.evidence_id)}
              type="button"
            >
              Confirm
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function MappingState({ confirmedCount, onLink }) {
  return (
    <div className="space-y-4">
      <h2 className="font-headline text-lg font-bold text-on-surface">Link to experience</h2>
      <p className="text-sm text-on-surface-variant">
        {confirmedCount} item{confirmedCount !== 1 ? "s" : ""} confirmed.
      </p>
      <button
        className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90"
        onClick={onLink}
        type="button"
      >
        <span className="material-symbols-outlined text-[18px]">link</span>
        Link evidence to experience
      </button>
    </div>
  );
}

function FollowUpState({ onAnswer, pendingQuestions }) {
  const [answer, setAnswer] = useState("");
  const question = (pendingQuestions || []).find((q) => !q.resolved && !q.dismissed);
  if (!question) {
    return (
      <div className="space-y-4">
        <h2 className="font-headline text-lg font-bold text-on-surface">Answer question</h2>
        <p className="text-sm text-on-surface-variant">No pending questions.</p>
      </div>
    );
  }
  function handleSubmit(e) {
    e.preventDefault();
    if (answer.trim()) onAnswer(question.question_id, answer.trim());
  }
  return (
    <div className="space-y-4">
      <h2 className="font-headline text-lg font-bold text-on-surface">Answer question</h2>
      <form className="space-y-3" onSubmit={handleSubmit}>
        <p className="text-sm font-medium text-on-surface">{question.text || question.label}</p>
        <textarea
          className="min-h-24 w-full rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm text-on-surface"
          onChange={(e) => setAnswer(e.target.value)}
          placeholder="Type your answer..."
          value={answer}
        />
        <button
          className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          disabled={!answer.trim()}
          type="submit"
        >
          <span className="material-symbols-outlined text-[16px]">check</span>
          Answer
        </button>
      </form>
    </div>
  );
}

function ReadyState({ confirmedCount, mappedCount, onToggleHistory }) {
  return (
    <div className="space-y-4">
      <h2 className="font-headline text-lg font-bold text-on-surface">View profile</h2>
      <p className="text-sm text-on-surface-variant">
        Your career evidence is complete. {confirmedCount} confirmed, {mappedCount} linked.
      </p>
      <div className="flex flex-wrap gap-3">
        <Link
          className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90"
          to="/workspaces"
        >
          <span className="material-symbols-outlined text-[18px]">workspaces</span>
          Use in workspace
        </Link>
        <button
          className="inline-flex items-center gap-2 rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-5 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-low"
          onClick={onToggleHistory}
          type="button"
        >
          <span className="material-symbols-outlined text-[18px]">history</span>
          View history
        </button>
      </div>
    </div>
  );
}

function HistoryPanel({ evidenceItems, onClose }) {
  return (
    <section className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-6">
      <div className="flex items-center justify-between">
        <h2 className="font-headline text-lg font-bold text-on-surface">Evidence history</h2>
        <button className="text-sm text-on-surface-variant hover:text-on-surface" onClick={onClose} type="button">Close</button>
      </div>
      {!evidenceItems || evidenceItems.length === 0 ? (
        <p className="mt-3 text-sm text-on-surface-variant">No evidence items yet.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {evidenceItems.map((ev) => (
            <li className="flex items-center gap-2 rounded-lg border border-outline-variant/10 bg-surface px-3 py-2 text-sm" key={ev.evidence_id}>
              <span className={`inline-block h-2 w-2 rounded-full ${ev.status === "confirmed" ? "bg-green-500" : ev.status === "rejected" ? "bg-red-400" : "bg-amber-400"}`} />
              <span className="truncate text-on-surface">{ev.text || ev.evidence_id}</span>
              <span className="ml-auto shrink-0 text-xs text-on-surface-variant">{ev.status || "unknown"}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
