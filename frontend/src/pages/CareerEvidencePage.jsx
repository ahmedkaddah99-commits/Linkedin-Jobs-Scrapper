// CP-038R: Career Evidence guided flow — one primary action per lifecycle state.
// Replaces the seven-tab Career Memory dashboard with a narrow task column.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import {
  applyCanonicalJourneyState,
  buildLifecycleSummary,
  LIFECYCLE_STATE,
  SOURCE_PROCESSING_STATE,
  SOURCE_PROCESSING_LABELS,
  SOURCE_PROCESSING_DESCRIPTIONS,
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
    error: documentsError,
    loading: documentsLoading,
    refresh: refreshDocuments,
  } = useApiResource(
    () => request("/documents?limit=500", { timeoutMs: DOCUMENTS_REQUEST_TIMEOUT_MS }),
    [request],
    { cacheKey: "documents:all", staleMs: 30000, backgroundRefresh: true },
  );

  const {
    data: settingsPayload,
    error: settingsError,
    loading: settingsLoading,
    refresh: refreshSettings,
  } = useApiResource(
    () => request("/settings", { timeoutMs: 60000 }),
    [request],
    { cacheKey: "settings", staleMs: Infinity, backgroundRefresh: false },
  );

  const allDocuments = documentsPayload?.documents || [];
  const settingsDocuments = settingsPayload?.documents || {};

  const {
    data: journeyPayload,
    loading: journeyLoading,
    refresh: refreshJourneyState,
    setData: setJourneyPayload,
  } = useApiResource(
    () => request("/evidence-items/journey-state"),
    [request],
    { cacheKey: "career-evidence:journey", staleMs: 0, backgroundRefresh: true },
  );

  const evidenceItems = useMemo(
    () => journeyPayload?.evidence_items ||
      (journeyPayload?.evidence ? [journeyPayload.evidence] : null) ||
      settingsPayload?.documents?.evidence_items || [],
    [journeyPayload, settingsPayload],
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

  const lifecycle = useMemo(() => {
    const settingsDerived = buildLifecycleSummary({
        sources: sourceDocuments,
        selectedSourceIds,
        evidenceItems,
        experienceLinks,
        pendingQuestions,
      });
    return applyCanonicalJourneyState(settingsDerived, journeyPayload);
  }, [sourceDocuments, selectedSourceIds, evidenceItems, experienceLinks, pendingQuestions, journeyPayload]);



  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  // CP-039R: Source processing state machine
  const [processingState, setProcessingState] = useState(null);
  const [processingError, setProcessingError] = useState("");
  const processingRef = useRef(null);
  const headingRef = useRef(null);

  // CP-040R: One-at-a-time evidence review state
  const [reviewItem, setReviewItem] = useState(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewError, setReviewError] = useState("");
  // CP-041R: Question state shown inline after confirmation
  const [activeQuestion, setActiveQuestion] = useState(null);
  // CP-044R: Ready actions with CV/motivation provenance
  const [readyActions, setReadyActions] = useState([]);


  const processSelectedSources = useCallback(async (fileBytesMap = null, sourceIdsOverride = null) => {
    const sourceIds = sourceIdsOverride || selectedSourceIds;
    if (sourceIds.length === 0 || processingRef.current) return;
    processingRef.current = true;
    setProcessingState({ state: SOURCE_PROCESSING_STATE.QUEUED, extracted_count: 0 });
    setProcessingError("");

    try {
      // Build sources payload from selected documents or file bytes map
      const sources = [];
      for (const docId of sourceIds) {
        const doc = sourceDocuments.find(
          (d) => normalizeDocumentId(d) === docId
        );
        const fileBytes = fileBytesMap?.get(docId) || null;
        if (fileBytes) {
          // Convert ArrayBuffer to base64
          let binary = "";
          const bytes = new Uint8Array(fileBytes);
          for (let i = 0; i < bytes.length; i++) {
            binary += String.fromCharCode(bytes[i]);
          }
          sources.push({
            asset_id: docId,
            file_name: doc?.display_name || docId,
            file_bytes: btoa(binary),
          });
        }
      }

      // CP-043R: Never send fake filename as content (was btoa(display_name))
      // Backend will look up real file bytes from asset storage
      const assetIdsParam = sources.length === 0 ? sourceIds : [];

      // CP-043R: Send asset_ids for backend content lookup, sources for new uploads
      const response = await request("/evidence-items/process-sources", {
        method: "POST",
        body: {
          profile_id: "",
          sources,
          asset_ids: assetIdsParam,
        },
      });

      const state = response?.state || {};
      setProcessingState(state);

      if (state.state === "completed") {
        const journey = response?.journey || await refreshJourneyState().catch(() => null);
        if (journey) setJourneyPayload(journey);
        if (journey?.next_review) setReviewItem(journey.next_review);
      } else if (state.state === "failed" || state.state === "timeout") {
        setProcessingError(state.error || "Processing failed.");
      }
    } catch (err) {
      setProcessingState({
        state: SOURCE_PROCESSING_STATE.FAILED,
        extracted_count: 0,
        error: err.message || "Processing request failed.",
      });
      setProcessingError(err.message || "Processing request failed.");
    } finally {
      processingRef.current = false;
    }
  }, [selectedSourceIds, sourceDocuments, request, refreshJourneyState, setJourneyPayload]);




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

  // CP-043R: Selection auto-starts real processing
  async function handleSourceSelect(assetId) {
    const nextIds = selectedSourceIds.includes(assetId)
      ? selectedSourceIds.filter((id) => id !== assetId)
      : [...selectedSourceIds, assetId];
    await saveToSettings({ selectedAssetIds: nextIds });
    await refreshSettings().catch(() => undefined);
    // Auto-trigger processing when sources are selected
    if (nextIds.length > 0) {
      await processSelectedSources(null, nextIds);
    }
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
      // CP-043R: Auto-start processing after upload
      if (assetId) {
        await processSelectedSources(null, [...new Set([...selectedSourceIds, assetId])]);
      }
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

  // CP-040R: Fetch next review item from backend
  const fetchNextReviewItem = useCallback(async () => {
    try {
      const response = await request("/evidence-items/next-review");
      if (response?.state) {
        setReviewItem(response);
      } else {
        setReviewItem(null);
      }
    } catch {
      // Fall back to client-side review if endpoint unavailable
      setReviewItem(null);
    }
  }, [request]);

  const applyJourneyResponse = useCallback((response) => {
    if (!response) return;
    setJourneyPayload(response);
    setReviewError("");
    if (response.state === "question" && response.question) {
      setActiveQuestion(response.question);
      setReviewItem(null);
    } else {
      setActiveQuestion(null);
      setReviewItem(response.next_review || null);
    }
    if (response.primary_actions) {
      setReadyActions(response.primary_actions);
    }
  }, [setJourneyPayload]);

  // CP-044R: Restore the exact server-side journey step after transitions or
  // reloads. Mapping and questions remain inline in the single review screen.
  useEffect(() => {
    if (lifecycle.state === LIFECYCLE_STATE.REVIEW) {
      if (journeyPayload?.state === "question" && journeyPayload.question) {
        setActiveQuestion(journeyPayload.question);
        setReviewItem(null);
      } else if (journeyPayload?.state === "review") {
        setActiveQuestion(null);
        setReviewItem(journeyPayload.next_review || null);
      }
    } else if (lifecycle.state === LIFECYCLE_STATE.READY) {
      if (journeyPayload?.primary_actions) {
        setReadyActions(journeyPayload.primary_actions);
      } else {
        request("/evidence-items/ready-actions")
          .then((response) => setReadyActions(response?.primary_actions || []))
          .catch(() => undefined);
      }
    }
  }, [lifecycle.state, journeyPayload, request]);

  // CP-040R: Reject evidence via review service
  async function handleRejectEvidence(evidenceId) {
    setReviewLoading(true);
    setReviewError("");
    try {
      const response = await request("/evidence-items/review-action", {
        method: "POST",
        body: {
          evidence_id: evidenceId,
          action: "reject",
        },
      });
      applyJourneyResponse(response);
    } catch (error) {
      setReviewError(error?.message || "Could not reject this evidence. Please retry.");
    } finally {
      setReviewLoading(false);
    }
  }

  // CP-040R: Edit evidence via review service
  async function handleEditEvidence(evidenceId, updates, mapping) {
    setReviewLoading(true);
    setReviewError("");
    try {
      const response = await request("/evidence-items/confirm-inspect", {
        method: "POST",
        body: {
          evidence_id: evidenceId,
          edited_text: updates?.text,
          mapping: mapping || undefined,
        },
      });
      applyJourneyResponse(response);
    } catch (error) {
      setReviewError(error?.message || "Could not save this evidence. Please retry.");
    } finally {
      setReviewLoading(false);
    }
  }

  async function handleLinkExperience() {
    const links = [
      ...experienceLinks,
      { link_id: `lnk_${Date.now()}`, mapped: true, linked_at: new Date().toISOString() },
    ];
    await saveToSettings({ experience_links: links });
  }

  // CP-044R: Confirm evidence with inspect — next item comes inline
  async function handleConfirmWithInspect(evidenceId, mapping) {
    setReviewLoading(true);
    setReviewError("");
    setActiveQuestion(null);
    try {
      const response = await request("/evidence-items/confirm-inspect", {
        method: "POST",
        body: {
          evidence_id: evidenceId,
          mapping: mapping || undefined,
        },
      });
      if (response) {
        applyJourneyResponse(response);

        if (response.state === "question" && response.question) {
          // CP-044R: Show one missing-detail question inline
          setActiveQuestion(response.question);
        } else if (response.next_review) {
          // CP-044R: Next review item returned inline — no separate fetch
          setActiveQuestion(null);
          setReviewItem(response.next_review);
        } else {
          // Ready state — no more items
          setActiveQuestion(null);
          setReviewItem(null);
        }
      }
    } catch (error) {
      setReviewError(error?.message || "Could not confirm this evidence. Please retry.");
    } finally {
      setReviewLoading(false);
    }
  }

  // CP-044R: Answer the inline question — next item comes inline
  async function handleAnswerQuestion(answerText) {
    if (!activeQuestion) return;
    setReviewLoading(true);
    setReviewError("");
    try {
      const response = await request("/evidence-items/answer-enrich", {
        method: "POST",
        body: {
          question_id: activeQuestion.question_id,
          answer_text: answerText,
          evidence_id: activeQuestion.evidence_id,
        },
      });
      if (response) {
        applyJourneyResponse(response);
        // CP-044R: Use next_review from response (inline — no separate fetch)
        if (response.next_review) {
          setReviewItem(response.next_review);
        } else if (response.state === "ready") {
          setReviewItem(null);
        }
      }
    } catch (error) {
      setReviewError(error?.message || "Could not save your answer. Please retry.");
    } finally {
      setReviewLoading(false);
    }
  }

  // CP-044R: Skip the inline question — next item comes inline
  async function handleSkipQuestion() {
    if (!activeQuestion) return;
    setReviewError("");
    try {
      const response = await request("/evidence-items/skip-question", {
        method: "POST",
        body: {
          question_id: activeQuestion.question_id,
        },
      });
      applyJourneyResponse(response);
      // CP-044R: Use next_review from response (inline)
      if (response?.next_review) {
        setReviewItem(response.next_review);
      }
    } catch (error) {
      setReviewError(error?.message || "Could not skip this question. Please retry.");
    }
  }


  const { state, label, description, primaryAction, progress, progressLabel: stepLabel } =
    lifecycle;

  // CP-043R: Track previous state for focus management
  const prevStateRef = useRef(state);

  // A reload may interrupt the browser request while the server-side source
  // selection is already persisted. Resume that same production operation
  // automatically instead of leaving the user on a dead processing screen.
  useEffect(() => {
    if (
      state === LIFECYCLE_STATE.PROCESSING &&
      !journeyLoading &&
      selectedSourceIds.length > 0 &&
      (!processingState || ["queued", "processing"].includes(processingState.state)) &&
      !processingRef.current
    ) {
      processSelectedSources().catch(() => undefined);
    }
  }, [state, journeyLoading, selectedSourceIds, processingState, processSelectedSources]);

  // CP-044R: Auto-advance when processing completes — fetch first review item
  useEffect(() => {
    if (processingState?.state === "completed" && state === LIFECYCLE_STATE.PROCESSING) {
      refreshJourneyState().then((journey) => {
        if (journey?.next_review) setReviewItem(journey.next_review);
      }).catch(() => fetchNextReviewItem());
    }
  }, [processingState?.state, state, refreshJourneyState, fetchNextReviewItem]);

  // CP-043R: Focus management - move focus to heading on state transition
  useEffect(() => {
    const prev = prevStateRef.current;
    prevStateRef.current = state;
    if (prev !== state && headingRef.current) {
      headingRef.current.focus();
    }
  }, [state]);

  const needsSourceResources = !journeyPayload || journeyPayload.state === "empty";
  if (journeyLoading || (needsSourceResources && (
    (documentsLoading && !documentsPayload) || (settingsLoading && !settingsPayload)
  ))) {
    return (
      <div className="mx-auto max-w-2xl space-y-5 px-4 py-8" aria-busy="true" aria-label="Loading Career Assets">
        <div className="h-6 w-36 animate-pulse rounded-full bg-surface-container" />
        <div className="h-10 w-2/3 animate-pulse rounded-xl bg-surface-container" />
        <div className="h-56 animate-pulse rounded-2xl bg-surface-container" />
      </div>
    );
  }

  if (needsSourceResources && (
    (documentsError && !documentsPayload) || (settingsError && !settingsPayload)
  )) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-8">
        <section className="rounded-2xl border border-error/30 bg-surface-container-lowest p-6 shadow-soft" role="alert">
          <h1 className="font-headline text-2xl font-bold text-on-surface">Career Assets could not load</h1>
          <p className="mt-2 text-sm text-on-surface-variant">{documentsError || settingsError}</p>
          <button
            className="mt-4 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white"
            onClick={() => Promise.all([refreshDocuments(), refreshSettings()]).catch(() => undefined)}
            type="button"
          >
            Retry
          </button>
        </section>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8 px-4 py-8">
      <header>
        <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-primary">
          Career Evidence
        </div>
        <h1 ref={headingRef} tabIndex={-1} className="mt-3 font-headline text-3xl font-extrabold tracking-tight text-on-surface outline-none">
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
            processingState={processingState}
            processingError={processingError}
            onRetry={() => processSelectedSources()}

          />
        ) : state === LIFECYCLE_STATE.PROCESSING ? (
          <ProcessingState
            processingState={processingState}
            processingError={processingError}
            selectedSourceCount={selectedSourceIds.length}
            onRetry={() => processSelectedSources()}
          />
        ) : state === LIFECYCLE_STATE.REVIEW ? (
          <ReviewState
            evidenceItems={evidenceItems}
            onConfirm={handleConfirmWithInspect}
            onReject={handleRejectEvidence}
            onEdit={handleEditEvidence}
            reviewItem={reviewItem}
            reviewLoading={reviewLoading}
            reviewError={reviewError}
            activeQuestion={activeQuestion}
            onAnswerQuestion={handleAnswerQuestion}
            onSkipQuestion={handleSkipQuestion}
          />
        ) : state === LIFECYCLE_STATE.READY ? (
          <ReadyState
            confirmedCount={lifecycle.confirmedCount}
            mappedCount={lifecycle.mappedCount}
            onToggleHistory={() => setShowHistory((v) => !v)}
            readyActions={readyActions}
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
        <nav aria-label="Career Assets secondary tools" className="mb-4 flex justify-center gap-4 text-xs">
          <Link className="font-medium text-on-surface-variant hover:text-primary" to="/documents">
            Asset Library
          </Link>
          <Link className="font-medium text-on-surface-variant hover:text-primary" to="/cv-studio">
            CV Studio
          </Link>
        </nav>
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



function ProcessingState({ processingState, processingError, selectedSourceCount, onRetry }) {
  const pState = processingState?.state || "processing";
  const extractedCount = processingState?.extracted_count || 0;
  return (
    <div className="space-y-4" role="status">
      <h2 className="font-headline text-lg font-bold text-on-surface">Processing evidence</h2>
      <p className="text-sm text-on-surface-variant">
        {pState === "completed"
          ? `Evidence extracted from ${selectedSourceCount} source(s). Advancing...`
          : pState === "failed" || pState === "timeout"
            ? `Processing ${pState}. ${processingError || ""}`
            : `Gemini is extracting evidence from ${selectedSourceCount} source(s)...`}
      </p>
      {(pState === "failed" || pState === "timeout") && onRetry ? (
        <button
          className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90"
          onClick={onRetry}
          type="button"
        >
          <span className="material-symbols-outlined text-[18px]">refresh</span>
          Retry processing
        </button>
      ) : pState !== "completed" ? (
        <div className="flex items-center gap-2 text-sm text-on-surface-variant">
          <span className="material-symbols-outlined animate-spin text-[18px]">progress_activity</span>
          Processing{extractedCount > 0 ? ` (${extractedCount} items found)` : ""}...
        </div>
      ) : null}
    </div>
  );
}

// CP-040R + CP-041R: One-item-at-a-time evidence review with suggested mapping
// and inline question after confirmation
function ReviewState({ evidenceItems, onConfirm, onReject, onEdit, reviewItem, reviewLoading, reviewError, activeQuestion, onAnswerQuestion, onSkipQuestion }) {
  const [editMode, setEditMode] = useState(false);
  const [editText, setEditText] = useState("");
  const [selectedMapping, setSelectedMapping] = useState(null);

  // CP-041R: Question answer state
  const [questionAnswer, setQuestionAnswer] = useState("");
  const currentItem = reviewItem?.evidence || (
    (activeQuestion?.evidence_id
      ? (evidenceItems || []).find((ev) => ev?.evidence_id === activeQuestion.evidence_id)
      : null) ||
    (evidenceItems || []).find(
      (ev) => ev && ev.status !== "confirmed" && ev.status !== "rejected",
    ) || null
  );

  const suggestedMapping = reviewItem?.suggested_mapping || null;
  const isAmbiguous = reviewItem?.is_ambiguous || false;
  const alternatives = reviewItem?.alternatives || [];
  const provenance = reviewItem?.provenance || null;
  const progress = reviewItem?.progress || { cursor: 0, remaining: 0, total: 0 };

  if (!currentItem) {
    return (
      <div className="space-y-4">
        <h2 className="font-headline text-lg font-bold text-on-surface">Confirm evidence</h2>
        <p className="text-sm text-on-surface-variant">No evidence items to review.</p>
      </div>
    );
  }

  const itemLabel = currentItem.inferred_employer || currentItem.inferred_role
    ? [currentItem.inferred_role, currentItem.inferred_employer]
        .filter(Boolean)
        .join(" at ")
    : "Unattributed";

  const hasDates = currentItem.dates && currentItem.dates.length > 0;
  const evidenceType = (currentItem.evidence_type || "responsibility")
    .replace(/_/g, " ");

  if (editMode) {
    return (
      <div className="space-y-4">
        <h2 className="font-headline text-lg font-bold text-on-surface">Edit evidence</h2>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (editText.trim()) {
              onEdit(currentItem.evidence_id, { text: editText }, selectedMapping);
              setEditMode(false);
              setEditText("");
            }
          }}
        >
          <textarea
            className="min-h-32 w-full rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm text-on-surface"
            onChange={(e) => setEditText(e.target.value)}
            placeholder="Edit the evidence text..."
            value={editText}
          />
          <div className="flex items-center gap-2">
            <button
              className="rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
              disabled={!editText.trim() || reviewLoading}
              type="submit"
            >
              {reviewLoading ? "Saving..." : "Save & advance"}
            </button>
            <button
              className="rounded-lg border border-outline-variant/20 bg-surface px-4 py-2 text-xs font-medium text-on-surface hover:bg-surface-container-low"
              onClick={() => { setEditMode(false); setEditText(""); }}
              type="button"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {reviewError ? (
        <p className="rounded-xl border border-error/30 bg-error/5 px-4 py-3 text-sm text-error" role="alert">
          {reviewError}
        </p>
      ) : null}
      <div className="flex items-center justify-between">
        <h2 className="font-headline text-lg font-bold text-on-surface">
          Confirm evidence
        </h2>
        {progress.total > 0 ? (
          <span className="text-xs text-on-surface-variant">
            {progress.cursor}/{progress.total}
          </span>
        ) : null}
      </div>

      {progress.total > 0 ? (
        <div className="h-1 w-full overflow-hidden rounded-full bg-surface-container-highest">
          <div
            className="h-full rounded-full bg-primary transition-all duration-300"
            style={{
              width: `${Math.round(
                ((progress.total - progress.remaining) / Math.max(progress.total, 1)) * 100,
              )}%`,
            }}
          />
        </div>
      ) : null}

      <div className="rounded-xl border border-outline-variant/20 bg-surface p-4">
        <div className="mb-2 flex items-center gap-2">
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-primary">
            {evidenceType}
          </span>
          <span className="text-xs text-on-surface-variant">{itemLabel}</span>
        </div>
        <p className="text-sm leading-relaxed text-on-surface">
          {currentItem.text || currentItem.label || currentItem.evidence_id}
        </p>
      </div>

      {provenance ? (
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest px-4 py-2.5">
          <p className="text-xs text-on-surface-variant">
            <span className="font-medium">Source:</span>{" "}
            {provenance.source_asset || currentItem.source_asset || "Unknown"}
            {hasDates ? " · " + currentItem.dates.join(" – ") : ""}
            {provenance.confidence > 0 ? (
              <span className="ml-1 text-[10px]">
                (confidence: {Math.round(provenance.confidence * 100)}%)
              </span>
            ) : null}
          </p>
        </div>
      ) : null}

      {suggestedMapping ? (
        <div className="rounded-xl border border-primary/20 bg-primary/5 p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-wide text-primary">
                Suggested experience
              </p>
              <p className="mt-1 text-sm font-medium text-on-surface">
                {suggestedMapping.label || suggestedMapping.role}
              </p>
              {suggestedMapping.reason ? (
                <p className="mt-0.5 text-xs text-on-surface-variant">
                  {suggestedMapping.reason}
                </p>
              ) : null}
            </div>
            <span className="shrink-0 rounded-full bg-primary/20 px-2 py-0.5 text-[10px] font-semibold text-primary">
              {Math.round((suggestedMapping.confidence || 0) * 100)}%
            </span>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest px-4 py-3">
          <p className="text-xs text-on-surface-variant">
            No matching experience found. Add this evidence without mapping.
          </p>
        </div>
      )}

      {isAmbiguous && alternatives.length > 0 ? (
        <div className="rounded-xl border border-amber-500/20 bg-amber-50/50 p-4">
          <p className="mb-2 text-xs font-semibold text-amber-700">
            Multiple matches found. Select the correct one:
          </p>
          <div className="space-y-1.5">
            {[suggestedMapping, ...alternatives].map((alt) => (
              <button
                className={`flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
                  (selectedMapping || suggestedMapping)?.experience_id === alt.experience_id
                    ? "border-primary/30 bg-primary/10 text-on-surface"
                    : "border-outline-variant/10 hover:bg-surface-container-low text-on-surface-variant"
                }`}
                key={alt.experience_id || alt.label}
                onClick={() => setSelectedMapping(alt)}
                type="button"
              >
                <span className="material-symbols-outlined text-[14px]">
                  {(selectedMapping || suggestedMapping)?.experience_id === alt.experience_id
                    ? "radio_button_checked"
                    : "radio_button_unchecked"}
                </span>
                <span className="truncate">{alt.label}</span>
                <span className="ml-auto shrink-0 text-[10px]">
                  {Math.round((alt.confidence || 0) * 100)}%
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : null}


      {/* CP-041R: Inline question after confirmation */}
      {activeQuestion ? (
        <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 space-y-3">
          <div className="flex items-start gap-2">
            <span className="material-symbols-outlined text-primary text-[18px] mt-0.5">help</span>
            <div>
              <p className="text-sm font-medium text-on-surface">
                {activeQuestion.question || activeQuestion.text}
              </p>
              <p className="mt-1 text-xs text-on-surface-variant">
                One missing detail — answer to enrich your evidence.
              </p>
            </div>
          </div>
          <form
            className="space-y-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (questionAnswer.trim()) {
                onAnswerQuestion(questionAnswer.trim());
                setQuestionAnswer("");
              }
            }}
          >
            <textarea
              className="min-h-20 w-full rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 text-sm text-on-surface"
              onChange={(e) => setQuestionAnswer(e.target.value)}
              placeholder="Type your answer..."
              value={questionAnswer}
            />
            <div className="flex items-center gap-2">
              <button
                className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
                disabled={!questionAnswer.trim() || reviewLoading}
                type="submit"
              >
                <span className="material-symbols-outlined text-[14px]">check</span>
                {reviewLoading ? "Saving..." : "Answer"}
              </button>
              <button
                className="rounded-lg border border-outline-variant/20 bg-surface px-4 py-2 text-xs font-medium text-on-surface-variant hover:bg-surface-container-low"
                onClick={onSkipQuestion}
                type="button"
              >
                Skip
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {!activeQuestion ? <div className="flex flex-wrap items-center gap-2">
        <button
          className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          disabled={reviewLoading}
          onClick={() =>
            onConfirm(currentItem.evidence_id, selectedMapping || suggestedMapping)
          }
          type="button"
        >
          <span className="material-symbols-outlined text-[16px]">check</span>
          {reviewLoading ? "Saving..." : "Confirm"}
        </button>

        <button
          className="inline-flex items-center gap-1.5 rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-low disabled:opacity-50"
          disabled={reviewLoading}
          onClick={() => {
            setEditMode(true);
            setEditText(currentItem.text || "");
          }}
          type="button"
        >
          <span className="material-symbols-outlined text-[16px]">edit</span>
          Edit
        </button>

        <button
          className="inline-flex items-center gap-1.5 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-medium text-red-700 transition-colors hover:bg-red-100 disabled:opacity-50"
          disabled={reviewLoading}
          onClick={() => onReject(currentItem.evidence_id)}
          type="button"
        >
          <span className="material-symbols-outlined text-[16px]">close</span>
          Reject
        </button>
      </div> : null}
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

function ReadyState({ confirmedCount, mappedCount, onToggleHistory, readyActions = [] }) {
  const cvAction = readyActions.find((a) => a.action === "cv_bullet");
  const mlAction = readyActions.find((a) => a.action === "motivation_letter");
  const libAction = readyActions.find((a) => a.action === "evidence_library");

  return (
    <div className="space-y-5">
      <h2 className="font-headline text-lg font-bold text-on-surface">Ready to use</h2>
      <p className="text-sm text-on-surface-variant">
        Your career evidence is complete. {confirmedCount} confirmed.
      </p>

      {cvAction ? (
        <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 space-y-2">
          <div className="flex items-start gap-2">
            <span className="material-symbols-outlined text-primary text-[18px] mt-0.5">article</span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-on-surface">{cvAction.label}</p>
              <p className="text-xs text-on-surface-variant mt-0.5">{cvAction.description}</p>
            </div>
          </div>
          <p className="text-xs text-on-surface-variant">
            Evidence: {cvAction.evidence_ids?.length || 0} items · Source: {cvAction.source}
          </p>
          <Link
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-white hover:opacity-90"
            to="/workspaces"
          >
            <span className="material-symbols-outlined text-[14px]">workspaces</span>
            Use in workspace
          </Link>
        </div>
      ) : null}

      {mlAction ? (
        <div className="rounded-xl border border-outline-variant/20 bg-surface p-4 space-y-2">
          <div className="flex items-start gap-2">
            <span className="material-symbols-outlined text-on-surface-variant text-[18px] mt-0.5">description</span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-on-surface">{mlAction.label}</p>
              <p className="text-xs text-on-surface-variant mt-0.5">{mlAction.description}</p>
            </div>
          </div>
          <p className="text-xs text-on-surface-variant">
            Evidence: {mlAction.evidence_ids?.length || 0} items · Source: {mlAction.source}
          </p>
        </div>
      ) : null}

      <div className="flex flex-wrap gap-3 pt-2">
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
