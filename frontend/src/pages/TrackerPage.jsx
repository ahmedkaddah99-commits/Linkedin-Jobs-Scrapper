import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useTracker } from "../hooks/useTracker";
import { CV_STUDIO_ROUTE, stashCvStudioSeed } from "../lib/cvStudio";

const COLUMNS = [
  {
    key: "not_applied",
    label: "Not Applied",
    icon: "radio_button_unchecked",
    accent: "text-on-surface-variant",
    badge: "bg-surface-container text-on-surface-variant",
    border: "border-outline-variant/30",
    glow: "shadow-black/0",
  },
  {
    key: "applied",
    label: "Applied",
    icon: "send",
    accent: "text-primary",
    badge: "bg-primary/10 text-primary",
    border: "border-primary/30",
    glow: "shadow-primary/10",
  },
  {
    key: "interview_invited",
    label: "Interviewing",
    icon: "calendar_month",
    accent: "text-amber-500",
    badge: "bg-amber-500/10 text-amber-500",
    border: "border-amber-500/30",
    glow: "shadow-amber-500/10",
  },
  {
    key: "rejected",
    label: "Rejected",
    icon: "cancel",
    accent: "text-error",
    badge: "bg-error/10 text-error",
    border: "border-error/30",
    glow: "shadow-error/10",
  },
  {
    key: "offer",
    label: "Offer",
    icon: "workspace_premium",
    accent: "text-green-500",
    badge: "bg-green-500/10 text-green-500",
    border: "border-green-500/30",
    glow: "shadow-green-500/10",
  },
  {
    key: "withdrawn",
    label: "Withdrawn",
    icon: "remove_circle",
    accent: "text-on-surface-variant",
    badge: "bg-surface-container text-on-surface-variant",
    border: "border-outline-variant/30",
    glow: "shadow-black/0",
  },
  {
    key: "unknown",
    label: "Unknown",
    icon: "help",
    accent: "text-on-surface-variant",
    badge: "bg-surface-container text-on-surface-variant",
    border: "border-outline-variant/30",
    glow: "shadow-black/0",
  },
];
const EMPTY_DISCOVERY_MODAL = {
  open: false,
  item: null,
  payload: null,
};
const EMPTY_DISCOVERY_FEEDBACK = {
  message: "",
  error: "",
};
const TRACKER_SOURCE_FILTERS = [
  { value: "all", label: "All sources" },
  { value: "standard_run", label: "Standard runs" },
  { value: "test_run", label: "Test runs" },
  { value: "external", label: "External applications" },
];

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

function formatDateTime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function triggerDownload(blob, fileName) {
  const objectUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = fileName || "document";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(objectUrl);
}

function StatusDropdown({ current, onSelect, disabled }) {
  const [open, setOpen] = useState(false);
  const currentCol = COLUMNS.find((c) => c.key === current) || COLUMNS[0];

  return (
    <div className="relative">
      <button
        className={[
          "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold transition-all",
          currentCol.badge,
          disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:opacity-80",
        ].join(" ")}
        disabled={disabled}
        onClick={() => !disabled && setOpen((v) => !v)}
        type="button"
      >
        <span className="material-symbols-outlined text-[14px]">{currentCol.icon}</span>
        {currentCol.label}
        <span className="material-symbols-outlined text-[12px]">expand_more</span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-full z-20 mt-1 w-52 overflow-hidden rounded-xl border border-outline-variant/20 bg-surface-container-lowest shadow-xl">
            {COLUMNS.map((col) => (
              <button
                className={[
                  "flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors hover:bg-surface-container-low",
                  col.key === current ? "font-semibold " + col.accent : "text-on-surface",
                ].join(" ")}
                key={col.key}
                onClick={() => {
                  setOpen(false);
                  if (col.key !== current) onSelect(col.key);
                }}
                type="button"
              >
                <span className={["material-symbols-outlined text-[16px]", col.accent].join(" ")}>
                  {col.icon}
                </span>
                {col.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function ApplicationWarnings({ warnings = [], compact = false }) {
  const visibleWarnings = (warnings || []).filter((warning) => warning?.message || warning?.title);
  if (!visibleWarnings.length) return null;
  return (
    <div className={compact ? "space-y-1.5" : "mt-3 space-y-2"}>
      {visibleWarnings.slice(0, compact ? 2 : 3).map((warning, index) => {
        const blocking = String(warning.severity || "") === "blocking";
        return (
          <div
            className={[
              "rounded-xl border px-3 py-2 text-xs leading-5",
              blocking
                ? "border-error/25 bg-error/5 text-error"
                : "border-amber-500/25 bg-amber-500/5 text-amber-700",
            ].join(" ")}
            key={`${warning.code || "application-warning"}-${index}`}
          >
            <div className="flex items-start gap-2">
              <span className="material-symbols-outlined mt-0.5 text-[15px]">
                {blocking ? "priority_high" : "info"}
              </span>
              <div>
                <div className="font-semibold">{warning.title || "Application requirement"}</div>
                <div>{warning.message}</div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TrackerCard({ item, onUpdate, onDelete, updating }) {
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState(item.rejection_note || "");
  const isBusy = updating === item.review_id;
  const currentStatus = item.tracker_status === "email_confirmed" ? "applied" : item.tracker_status || "unknown";
  const isRejected = currentStatus === "rejected";

  async function handleStatusChange(newStatus) {
    await onUpdate(item.review_id, { tracker_status: newStatus });
    if (newStatus === "rejected") setNoteOpen(true);
  }

  async function handleEmailToggle() {
    await onUpdate(item.review_id, { email_confirmed: !item.email_confirmed });
  }

  async function saveNote() {
    await onUpdate(item.review_id, { rejection_note: note });
    setNoteOpen(false);
  }

  const col = COLUMNS.find((c) => c.key === currentStatus) || COLUMNS[COLUMNS.length - 1];

  return (
    <div
      className={[
        "group relative overflow-hidden rounded-2xl border bg-surface-container-lowest p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md",
        col.border,
        col.glow,
      ].join(" ")}
    >
      {/* Loading overlay */}
      {isBusy && (
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-2xl bg-surface-container-lowest/70 backdrop-blur-sm">
          <span className="material-symbols-outlined animate-spin text-2xl text-primary">
            progress_activity
          </span>
        </div>
      )}

      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-on-surface leading-tight">
            {item.title}
          </h3>
          <div className="mt-0.5 flex items-center gap-1.5 text-xs text-on-surface-variant">
            <span className="material-symbols-outlined text-[13px]">business</span>
            <span className="truncate">{item.company || "Unknown Company"}</span>
          </div>
        </div>
        <StatusDropdown
          current={currentStatus}
          disabled={isBusy}
          onSelect={handleStatusChange}
        />
      </div>

      <div className="mb-3 flex flex-wrap gap-2 text-xs text-on-surface-variant">
        {item.workspace_name && (
          <span className="flex items-center gap-1">
            <span className="material-symbols-outlined text-[12px]">workspaces</span>
            {item.workspace_name}
          </span>
        )}
        {item.run_finished_at && (
          <span className="flex items-center gap-1">
            <span className="material-symbols-outlined text-[12px]">event</span>
            {formatDate(item.run_finished_at)}
          </span>
        )}
        {item.location && (
          <span className="flex items-center gap-1">
            <span className="material-symbols-outlined text-[12px]">location_on</span>
            {item.location}
          </span>
        )}
      </div>

      <ApplicationWarnings warnings={item.application_warnings} />

      <div className="flex items-center justify-between gap-2">
        {/* Email confirmed toggle (REQ-10) */}
        <button
          className={[
            "flex items-center gap-1.5 rounded-full px-2 py-1 text-xs font-medium transition-all",
            item.email_confirmed
              ? "bg-teal-500/10 text-teal-600"
              : "bg-surface-container text-on-surface-variant hover:bg-teal-500/10 hover:text-teal-600",
          ].join(" ")}
          disabled={isBusy}
          onClick={handleEmailToggle}
          title={item.email_confirmed ? "Email confirmed — click to unmark" : "Mark email as confirmed"}
          type="button"
        >
          <span className="material-symbols-outlined text-[14px]">
            {item.email_confirmed ? "mark_email_read" : "mail"}
          </span>
          {item.email_confirmed ? "Email confirmed" : "Confirm email"}
        </button>

        <div className="flex items-center gap-1.5">
          {onDelete ? (
            <button
              className="flex h-7 w-7 items-center justify-center rounded-full text-on-surface-variant transition-colors hover:bg-error/10 hover:text-error"
              disabled={isBusy}
              onClick={() => onDelete(item)}
              title="Delete job"
              type="button"
            >
              <span className="material-symbols-outlined text-[16px]">delete</span>
            </button>
          ) : null}
          {isRejected && (
            <button
              className="flex h-7 w-7 items-center justify-center rounded-full text-on-surface-variant transition-colors hover:bg-surface-container hover:text-primary"
              onClick={() => setNoteOpen((v) => !v)}
              title="Add rejection note"
              type="button"
            >
              <span className="material-symbols-outlined text-[16px]">note_add</span>
            </button>
          )}
          {item.apply_link && (
            <a
              className="flex h-7 w-7 items-center justify-center rounded-full text-on-surface-variant transition-colors hover:bg-surface-container hover:text-primary"
              href={item.apply_link}
              rel="noreferrer"
              target="_blank"
              title="Open job posting"
            >
              <span className="material-symbols-outlined text-[16px]">open_in_new</span>
            </a>
          )}
        </div>
      </div>

      {/* Rejection note area */}
      {noteOpen && (
        <div className="mt-3 border-t border-outline-variant/10 pt-3">
          <textarea
            className="w-full rounded-lg border border-outline-variant/20 bg-surface-container p-2 text-xs text-on-surface placeholder-on-surface-variant/50 focus:border-primary/30 focus:outline-none focus:ring-1 focus:ring-primary/20"
            onChange={(e) => setNote(e.target.value)}
            placeholder="Optional rejection note…"
            rows={2}
            value={note}
          />
          <div className="mt-1.5 flex justify-end gap-2">
            <button
              className="rounded px-2 py-1 text-xs text-on-surface-variant hover:text-on-surface"
              onClick={() => setNoteOpen(false)}
              type="button"
            >
              Cancel
            </button>
            <button
              className="rounded bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/20"
              onClick={saveNote}
              type="button"
            >
              Save note
            </button>
          </div>
        </div>
      )}

      {item.rejection_note && !noteOpen && (
        <div className="mt-2 border-t border-outline-variant/10 pt-2 text-xs italic text-on-surface-variant">
          {item.rejection_note}
        </div>
      )}
    </div>
  );
}

function statusKeyFromItem(item) {
  const trackerStatus = item.tracker_status === "email_confirmed" ? "applied" : item.tracker_status;
  return COLUMNS.some((column) => column.key === trackerStatus) ? trackerStatus : "unknown";
}

const TRACKER_RESOURCE_BUTTON_CLASS =
  "inline-flex min-w-[120px] items-center justify-center gap-1 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors";

function TrackerLink({ href, children }) {
  if (!href) {
    return (
      <span
        className={[
          TRACKER_RESOURCE_BUTTON_CLASS,
          "cursor-not-allowed bg-surface-container-low text-on-surface-variant/60",
        ].join(" ")}
      >
        {children}
      </span>
    );
  }
  return (
    <a
      className={[TRACKER_RESOURCE_BUTTON_CLASS, "bg-primary/10 text-primary hover:bg-primary/20"].join(" ")}
      href={href}
      rel="noreferrer"
      target="_blank"
    >
      {children}
      <span className="material-symbols-outlined text-[13px]">open_in_new</span>
    </a>
  );
}

function buildTrackerBundleLabel(item) {
  const base = [item.company, item.title, "application_documents"]
    .map((segment) => String(segment || "").trim())
    .filter(Boolean)
    .join("_")
    .replace(/[^\w.-]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
  return base || "application_documents";
}

function parseTrackerNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function trackerAtsStopReasonLabel(stopReason) {
  const normalized = String(stopReason || "").trim().toLowerCase();
  if (normalized === "target_reached") return "Target reached";
  if (normalized === "max_attempts_reached") return "Pass limit reached";
  if (normalized === "score_stalled") return "Score stalled";
  return normalized ? normalized.replace(/_/g, " ") : "";
}

function normalizeTrackerAtsAttemptHistory(gate = {}) {
  const metadata = gate.metadata && typeof gate.metadata === "object" ? gate.metadata : {};
  return Array.isArray(metadata.attempt_history)
    ? metadata.attempt_history.map((attempt, index) => ({
        attempt: parseTrackerNumber(attempt?.attempt) ?? index + 1,
        score: parseTrackerNumber(attempt?.score),
        changedSections: Array.isArray(attempt?.changed_sections)
          ? attempt.changed_sections.map((section) => String(section || "").trim()).filter(Boolean)
          : [],
        changeSummary: String(attempt?.change_summary || "").trim(),
        missingRequirements: Array.isArray(attempt?.missing_requirements)
          ? attempt.missing_requirements.map((requirement) => String(requirement || "").trim()).filter(Boolean)
          : [],
        improvementActions: Array.isArray(attempt?.improvement_actions)
          ? attempt.improvement_actions.map((action) => String(action || "").trim()).filter(Boolean)
          : [],
        rationale: String(attempt?.rationale || "").trim(),
      }))
    : [];
}

function summarizeTrackerAtsState(documents = []) {
  const atsDocuments = (Array.isArray(documents) ? documents : []).filter((document) => {
    const gate = document?.ats_export_gate;
    const documentType = String(document?.document_type || "").trim().toLowerCase();
    const assetKind = String(document?.asset_kind || "").trim().toLowerCase();
    return (
      Boolean(document?.final_export_blocked) ||
      (gate && typeof gate === "object") ||
      documentType === "tailored cv" ||
      assetKind === "generated_cv"
    );
  });
  if (!atsDocuments.length) {
    return null;
  }

  const pickDocument =
    atsDocuments.find((document) => Boolean(document.final_export_blocked)) ||
    atsDocuments.find((document) => {
      const gateState = String(document?.ats_export_gate?.gate_state || "").trim().toLowerCase();
      return gateState === "blocked";
    }) ||
    atsDocuments.find((document) => {
      const gateState = String(document?.ats_export_gate?.gate_state || "").trim().toLowerCase();
      return gateState === "passed" || gateState === "exported_anyway";
    }) ||
    atsDocuments[0];

  const gate =
    pickDocument?.ats_export_gate && typeof pickDocument.ats_export_gate === "object"
      ? pickDocument.ats_export_gate
      : {};
  const gateState = String(gate.gate_state || "").trim().toLowerCase();
  const bestScore = parseTrackerNumber(gate.best_score ?? pickDocument?.ats_best_score ?? pickDocument?.ats_score);
  const targetScore = parseTrackerNumber(gate.target_score ?? pickDocument?.ats_target_score);
  const attemptCount = parseTrackerNumber(gate.attempt_count ?? pickDocument?.ats_attempt_count);
  const maxAttempts = parseTrackerNumber(gate.max_attempts ?? pickDocument?.ats_max_attempts);
  const metadata = gate.metadata && typeof gate.metadata === "object" ? gate.metadata : {};
  const stopReason = String(metadata.stop_reason || pickDocument?.ats_stop_reason || "").trim();
  const missingRequirements = Array.isArray(gate.missing_requirements)
    ? gate.missing_requirements.map((requirement) => String(requirement || "").trim()).filter(Boolean)
    : [];
  const attemptHistory = normalizeTrackerAtsAttemptHistory(gate);
  const belowTarget = bestScore !== null && targetScore !== null && bestScore < targetScore;

  const summary =
    pickDocument?.final_export_blocked || gateState === "blocked"
      ? {
          badgeClass: "bg-error/10 text-error",
          label: "ATS gate active",
          message:
            "ATS failed: the best scored CV is still below the target, so final CV export stays blocked unless the warning is overridden.",
        }
      : gateState === "passed"
        ? {
            badgeClass: "bg-teal-500/10 text-teal-600",
            label: "ATS cleared",
            message: "ATS passed: the tailored CV reached the target score before export.",
          }
        : gateState === "exported_anyway"
          ? {
              badgeClass: "bg-amber-500/10 text-amber-600",
              label: "ATS override",
              message:
                "ATS warning acknowledged: the CV was exported even though it did not record a clean pass.",
            }
          : {
              badgeClass: "bg-primary/10 text-primary",
              label: "ATS preflight",
              message: "ATS scoring runs before the final tailored CV is released in the application bundle.",
            };

  const metrics = [
    bestScore !== null && targetScore !== null ? `${bestScore}% / ${targetScore}% target` : "",
    attemptCount !== null && maxAttempts !== null ? `Pass ${attemptCount}/${maxAttempts}` : "",
  ].filter(Boolean);

  return {
    ...summary,
    attemptHistory,
    belowTarget,
    lastWarning: String(gate.last_warning || pickDocument?.ats_last_warning || "").trim(),
    metrics,
    missingRequirements,
    stopReasonLabel: trackerAtsStopReasonLabel(stopReason),
    targetScore,
    bestScore,
    maxAttempts,
  };
}

function trackerDocumentExtension(document = {}) {
  const candidates = [
    document.file_extension,
    document.path,
    document.file_name,
    document.label,
    document.download_url,
    document.document_id,
  ];
  for (const candidate of candidates) {
    const text = String(candidate || "").trim().toLowerCase();
    if (!text) continue;
    if (text === "pdf" || text.endsWith(".pdf")) return "pdf";
    if (text === "docx" || text.endsWith(".docx")) return "docx";
    if (text === "txt" || text.endsWith(".txt")) return "txt";
  }
  const contentType = String(document.content_type || "").trim().toLowerCase();
  if (contentType === "application/pdf") return "pdf";
  if (contentType === "application/vnd.openxmlformats-officedocument.wordprocessingml.document") {
    return "docx";
  }
  if (contentType.startsWith("text/")) return "txt";
  return "";
}

function isTrackerApplicationCv(document = {}) {
  const assetKind = String(document.asset_kind || "").trim().toLowerCase();
  const documentType = String(document.document_type || "").trim().toLowerCase();
  return (
    Boolean(String(document.run_id || "").trim()) &&
    Boolean(String(document.job_id || "").trim()) &&
    (assetKind === "generated_cv" ||
      assetKind === "applied_cv" ||
      documentType === "tailored cv" ||
      documentType === "applied cv")
  );
}

function trackerDocumentExportRank(document = {}) {
  if (!isTrackerApplicationCv(document)) return 0;
  const extension = trackerDocumentExtension(document);
  if (extension === "pdf") return 0;
  if (extension === "docx") return 1;
  if (extension === "txt") return 2;
  return 3;
}

function canExportTrackerDocument(document = {}) {
  if (!String(document.document_id || "").trim()) return false;
  if (!document.final_export_blocked) return true;
  const gate = document.ats_export_gate && typeof document.ats_export_gate === "object"
    ? document.ats_export_gate
    : {};
  return Boolean(gate.export_anyway_allowed);
}

function selectTrackerExportDocuments(documents = []) {
  const candidates = (Array.isArray(documents) ? documents : []).filter(canExportTrackerDocument);
  const preferredByKey = new Map();

  candidates.forEach((document) => {
    if (!isTrackerApplicationCv(document)) {
      return;
    }
    const key = [
      document.run_id || "",
      document.job_id || "",
      document.asset_kind || "",
      document.document_type || "",
    ].join("::");
    const current = preferredByKey.get(key);
    if (!current || trackerDocumentExportRank(document) < trackerDocumentExportRank(current)) {
      preferredByKey.set(key, document);
    }
  });

  const preferredIds = new Set(
    Array.from(preferredByKey.values()).map((document) => String(document.document_id || "")),
  );
  const selected = [];
  const emittedKeys = new Set();
  candidates.forEach((document) => {
    if (!isTrackerApplicationCv(document)) {
      selected.push(document);
      return;
    }
    const key = [
      document.run_id || "",
      document.job_id || "",
      document.asset_kind || "",
      document.document_type || "",
    ].join("::");
    if (emittedKeys.has(key)) return;
    if (preferredIds.has(String(document.document_id || ""))) {
      selected.push(document);
      emittedKeys.add(key);
    }
  });
  return selected;
}

function TrackerResourceCell({ item, request }) {
  const navigate = useNavigate();
  const [exporting, setExporting] = useState(false);
  const [descriptionFeedback, setDescriptionFeedback] = useState("");
  const [error, setError] = useState("");
  const atsSummary = summarizeTrackerAtsState(item.documents);
  const exportableDocuments = selectTrackerExportDocuments(item.documents);
  const documentLabels = exportableDocuments.map((document) => String(document.label || document.document_type || "Document").trim()).filter(Boolean);
  const canEditGeneratedCv = Boolean(item.cv_studio_seed?.profile);
  const description = String(item.full_description || item.tracker_table_row?.full_description || "").trim();
  const descriptionUrl = `/tracker/job-descriptions/${encodeURIComponent(item.review_id)}`;

  function openGeneratedCvEditor() {
    if (!canEditGeneratedCv) return;
    stashCvStudioSeed({
      ...item.cv_studio_seed,
      returnTo: "/tracker",
      sourceLabel: [item.title, item.company].filter(Boolean).join(" at ") || "Generated application CV",
    });
    navigate(CV_STUDIO_ROUTE);
  }

  async function downloadBundle() {
    if (!exportableDocuments.length) {
      return;
    }
    setExporting(true);
    setError("");
    try {
      const bundle = await request("/documents/bulk-export", {
        method: "POST",
        body: {
          label: buildTrackerBundleLabel(item),
          document_ids: exportableDocuments.map((document) => document.document_id),
          export_anyway: true,
        },
      });
      const blob = await request(bundle.download_url, { responseType: "blob" });
      triggerDownload(blob, bundle.file_name || "application_documents.zip");
    } catch (exportError) {
      setError(exportError.message || "Unable to export application documents.");
    } finally {
      setExporting(false);
    }
  }

  async function copyDescription() {
    if (!description) return;
    setDescriptionFeedback("");
    setError("");
    try {
      await navigator.clipboard.writeText(description);
      setDescriptionFeedback("Description copied.");
    } catch (copyError) {
      setError(copyError.message || "Unable to copy the job description.");
    }
  }

  return (
    <div className="min-w-56 max-w-72 space-y-2">
      <div className="flex flex-wrap gap-2">
        <TrackerLink href={item.apply_link || item.tracker_table_row?.apply_link}>Apply</TrackerLink>
        <button
          className={[
            TRACKER_RESOURCE_BUTTON_CLASS,
            exportableDocuments.length
              ? "bg-primary/10 text-primary hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-60"
              : "cursor-not-allowed bg-surface-container-low text-on-surface-variant/60",
          ].join(" ")}
          disabled={!exportableDocuments.length || exporting}
          onClick={downloadBundle}
          title={
            documentLabels.length
              ? `Download application documents: ${documentLabels.join(" | ")}`
              : "No exportable application documents available"
          }
          type="button"
        >
          <span className="material-symbols-outlined text-[13px]">
            {exporting ? "progress_activity" : "folder_zip"}
          </span>
          {exporting ? "Preparing..." : "Documents ZIP"}
        </button>
        {canEditGeneratedCv ? (
          <button
            className={`${TRACKER_RESOURCE_BUTTON_CLASS} bg-surface-container-low text-on-surface hover:bg-surface-container-high`}
            onClick={openGeneratedCvEditor}
            title="Edit generated CV in CV Studio"
            type="button"
          >
            <span className="material-symbols-outlined text-[13px]">edit_document</span>
            Edit CV
          </button>
        ) : null}
        <button
          className={[
            TRACKER_RESOURCE_BUTTON_CLASS,
            description
              ? "bg-surface-container-low text-on-surface hover:bg-surface-container-high"
              : "cursor-not-allowed bg-surface-container-low text-on-surface-variant/60",
          ].join(" ")}
          disabled={!description}
          onClick={copyDescription}
          title={description ? "Copy the full job description" : "No job description available"}
          type="button"
        >
          <span className="material-symbols-outlined text-[13px]">content_copy</span>
          Copy description
        </button>
        {description ? (
          <a
            className={`${TRACKER_RESOURCE_BUTTON_CLASS} bg-surface-container-low text-on-surface hover:bg-surface-container-high`}
            href={descriptionUrl}
            rel="noreferrer"
            target="_blank"
            title="Open the full job description in a new Runr tab"
          >
            <span className="material-symbols-outlined text-[13px]">open_in_new</span>
            Open description
          </a>
        ) : (
          <span
            className={`${TRACKER_RESOURCE_BUTTON_CLASS} cursor-not-allowed bg-surface-container-low text-on-surface-variant/60`}
            title="No job description available"
          >
            <span className="material-symbols-outlined text-[13px]">open_in_new</span>
            Open description
          </span>
        )}
      </div>
      <ApplicationWarnings compact warnings={item.application_warnings} />
      {atsSummary ? (
        <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className={["rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide", atsSummary.badgeClass].join(" ")}>
              {atsSummary.label}
            </span>
            {atsSummary.metrics.map((metric) => (
              <span
                className="rounded-full bg-surface-container-lowest px-2.5 py-1 text-[10px] font-medium text-on-surface-variant"
                key={metric}
              >
                {metric}
              </span>
            ))}
          </div>
          <div className="mt-2 text-[11px] leading-5 text-on-surface-variant">
            {atsSummary.message}
          </div>
          {atsSummary.stopReasonLabel ? (
            <div className="mt-2 text-[11px] font-medium text-on-surface">
              Result: {atsSummary.stopReasonLabel}
            </div>
          ) : null}
          {atsSummary.belowTarget && atsSummary.maxAttempts ? (
            <div className="mt-2 text-[11px] leading-5 text-on-surface-variant">
              {atsSummary.maxAttempts} ATS passes are a capped optimization effort, not a guarantee. A CV can still fail when the
              source CV lacks evidence for required job criteria or when later passes stop improving the score.
            </div>
          ) : null}
          {atsSummary.missingRequirements.length ? (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {atsSummary.missingRequirements.slice(0, 4).map((requirement) => (
                <span
                  className="rounded-full bg-surface-container-lowest px-2 py-0.5 text-[10px] font-medium text-on-surface"
                  key={requirement}
                >
                  {requirement}
                </span>
              ))}
            </div>
          ) : null}
          {atsSummary.attemptHistory.length ? (
            <details className="mt-3">
              <summary className="cursor-pointer text-[11px] font-semibold text-primary">
                ATS pass audit
              </summary>
              <div className="mt-2 space-y-2">
                {atsSummary.attemptHistory.map((attempt) => (
                  <div
                    className="rounded-xl border border-outline-variant/15 bg-surface-container-lowest p-2 text-[11px] leading-5"
                    key={`ats-pass-${attempt.attempt}`}
                  >
                    <div className="flex flex-wrap items-center gap-2 font-semibold text-on-surface">
                      <span>Pass {attempt.attempt}</span>
                      {attempt.score !== null ? <span>{attempt.score}%</span> : null}
                    </div>
                    {attempt.changeSummary ? (
                      <div className="mt-1 text-on-surface-variant">{attempt.changeSummary}</div>
                    ) : null}
                    {attempt.improvementActions.length ? (
                      <div className="mt-1 text-on-surface-variant">
                        Next action: {attempt.improvementActions[0]}
                      </div>
                    ) : null}
                    {attempt.rationale ? (
                      <div className="mt-1 text-on-surface-variant">{attempt.rationale}</div>
                    ) : null}
                  </div>
                ))}
              </div>
            </details>
          ) : null}
          {atsSummary.lastWarning ? (
            <div className="mt-2 text-[11px] leading-5 text-on-surface-variant">
              {atsSummary.lastWarning}
            </div>
          ) : null}
        </div>
      ) : null}
      {descriptionFeedback ? <div className="text-xs text-primary">{descriptionFeedback}</div> : null}
      {error ? <div className="text-xs text-error">{error}</div> : null}
    </div>
  );
}

function TrackerNotesCell({ item, onUpdate, updating }) {
  const [note, setNote] = useState(item.notes || "");
  const [editing, setEditing] = useState(false);
  const isDirty = note !== (item.notes || "");
  const isBusy = updating === item.review_id;

  useEffect(() => {
    setNote(item.notes || "");
  }, [item.notes]);

  async function saveNote() {
    if (!isDirty) return;
    await onUpdate(item.review_id, { notes: note });
    setEditing(false);
  }

  if (!editing) {
    return (
      <div className="min-w-44 max-w-64">
        <p className="line-clamp-2 text-xs leading-5 text-on-surface-variant">
          {item.notes || "No notes yet."}
        </p>
        <button
          className="mt-2 rounded-full bg-surface-container-low px-3 py-1 text-xs font-semibold text-primary transition-colors hover:bg-primary/10"
          disabled={isBusy}
          onClick={() => setEditing(true)}
          type="button"
        >
          {item.notes ? "Edit note" : "Add note"}
        </button>
      </div>
    );
  }

  return (
    <div className="min-w-56 space-y-2">
      <textarea
        className="min-h-20 w-full rounded-xl border border-outline-variant/20 bg-surface px-3 py-2 text-xs text-on-surface"
        disabled={isBusy}
        onChange={(event) => setNote(event.target.value)}
        placeholder="Add notes"
        value={note}
      />
      <div className="flex flex-wrap gap-2">
        <button
          className="rounded-full bg-primary/10 px-3 py-1.5 text-xs font-semibold text-primary transition-colors hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!isDirty || isBusy}
          onClick={saveNote}
          type="button"
        >
          {isBusy ? "Saving..." : "Save"}
        </button>
        <button
          className="rounded-full bg-surface-container-low px-3 py-1.5 text-xs font-semibold text-on-surface-variant transition-colors hover:bg-surface-container"
          onClick={() => {
            setNote(item.notes || "");
            setEditing(false);
          }}
          type="button"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function TrackerTable({ items, onUpdate, updating, request }) {
  const [filters, setFilters] = useState({
    query: "",
    status: "all",
    workspace: "all",
    source: "all",
  });
  const workspaceOptions = useMemo(
    () => [...new Set(items.map((item) => item.workspace_name).filter(Boolean))].sort(),
    [items],
  );
  const filteredItems = useMemo(() => {
    const query = filters.query.trim().toLocaleLowerCase();
    return items.filter((item) => {
      const row = item.tracker_table_row || {};
      const sourceType = item.tracker_source_type
        || (item.external_application ? "external" : item.is_test_run ? "test_run" : "standard_run");
      const searchableText = [
        item.title,
        row.title,
        item.company,
        row.company,
        item.location,
        row.location_raw,
        item.workspace_name,
      ]
        .filter(Boolean)
        .join(" ")
        .toLocaleLowerCase();
      return (
        (!query || searchableText.includes(query))
        && (filters.status === "all" || statusKeyFromItem(item) === filters.status)
        && (filters.workspace === "all" || item.workspace_name === filters.workspace)
        && (filters.source === "all" || sourceType === filters.source)
      );
    });
  }, [filters, items]);
  const hasActiveFilters = Object.values(filters).some((value) => value && value !== "all");

  function updateFilter(field, value) {
    setFilters((current) => ({ ...current, [field]: value }));
  }

  function clearFilters() {
    setFilters({ query: "", status: "all", workspace: "all", source: "all" });
  }

  if (!items.length) {
    return (
      <div className="rounded-2xl border border-dashed border-outline-variant/30 bg-surface-container-lowest p-8 text-center">
        <span className="material-symbols-outlined text-3xl text-on-surface-variant">table</span>
        <p className="mt-3 text-sm font-semibold text-on-surface">No tracker rows yet.</p>
        <p className="mt-1 text-xs text-on-surface-variant">
          Applications and imported Gmail matches will appear here.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-outline-variant/20 bg-surface-container-lowest shadow-sm">
      <div className="border-b border-outline-variant/10 bg-surface-container-low px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-on-surface">Tracker table</h2>
            <p className="mt-1 text-xs leading-5 text-on-surface-variant">
              Filter applications without adding more columns to the table.
            </p>
          </div>
          <div className="text-xs font-semibold text-on-surface-variant">
            Showing {filteredItems.length} of {items.length}
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(220px,1.5fr)_repeat(3,minmax(150px,1fr))_auto]">
          <label className="relative">
            <span className="material-symbols-outlined pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-lg text-on-surface-variant">
              search
            </span>
            <input
              aria-label="Search tracker"
              className="w-full rounded-xl border border-outline-variant/20 bg-surface px-10 py-2.5 text-sm text-on-surface"
              onChange={(event) => updateFilter("query", event.target.value)}
              placeholder="Search role, company, location..."
              type="search"
              value={filters.query}
            />
          </label>
          <select
            aria-label="Filter tracker by status"
            className="w-full rounded-xl border border-outline-variant/20 bg-surface px-3 py-2.5 text-sm text-on-surface"
            onChange={(event) => updateFilter("status", event.target.value)}
            value={filters.status}
          >
            <option value="all">All statuses</option>
            {COLUMNS.map((column) => (
              <option key={column.key} value={column.key}>{column.label}</option>
            ))}
          </select>
          <select
            aria-label="Filter tracker by workspace"
            className="w-full rounded-xl border border-outline-variant/20 bg-surface px-3 py-2.5 text-sm text-on-surface"
            onChange={(event) => updateFilter("workspace", event.target.value)}
            value={filters.workspace}
          >
            <option value="all">All workspaces</option>
            {workspaceOptions.map((workspace) => (
              <option key={workspace} value={workspace}>{workspace}</option>
            ))}
          </select>
          <select
            aria-label="Filter tracker by source"
            className="w-full rounded-xl border border-outline-variant/20 bg-surface px-3 py-2.5 text-sm text-on-surface"
            onChange={(event) => updateFilter("source", event.target.value)}
            value={filters.source}
          >
            {TRACKER_SOURCE_FILTERS.map((source) => (
              <option key={source.value} value={source.value}>{source.label}</option>
            ))}
          </select>
          <button
            className="rounded-xl border border-outline-variant/20 bg-surface px-4 py-2.5 text-sm font-semibold text-on-surface-variant transition-colors hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-40"
            disabled={!hasActiveFilters}
            onClick={clearFilters}
            type="button"
          >
            Clear
          </button>
        </div>
      </div>
      {filteredItems.length ? (
        <div className="overflow-x-auto">
          <table className="tracker-table min-w-[1060px] w-full table-fixed border-collapse text-left text-sm">
            <thead className="bg-surface-container-low text-[11px] uppercase tracking-[0.14em] text-on-surface-variant">
              <tr>
                <th className="w-36 px-4 py-3">Status</th>
                <th className="w-48 px-4 py-3">Company</th>
                <th className="w-64 px-4 py-3">Role</th>
                <th className="w-44 px-4 py-3">Location</th>
                <th className="w-36 px-4 py-3">Applied</th>
                <th className="w-56 px-4 py-3">Resource</th>
                <th className="w-28 px-4 py-3">Priority</th>
                <th className="w-64 px-4 py-3">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {filteredItems.map((item) => {
                const row = item.tracker_table_row || {};
                return (
                  <tr
                    className="tracker-table__row align-top transition-colors hover:bg-surface-container-low/70"
                    key={item.review_id}
                  >
                    <td className="px-4 py-4">
                      <StatusDropdown
                        current={statusKeyFromItem(item)}
                        disabled={updating === item.review_id}
                        onSelect={(nextStatus) => onUpdate(item.review_id, { tracker_status: nextStatus })}
                      />
                    </td>
                    <td className="max-w-56 px-4 py-4">
                      <div className="font-semibold text-on-surface">{item.company || row.company || "Unknown company"}</div>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-on-surface-variant">
                        <span>{item.workspace_name || "Tracker"}</span>
                        {item.is_test_run ? (
                          <span className="rounded-full bg-primary/10 px-2 py-0.5 font-semibold text-primary">Test run</span>
                        ) : null}
                      </div>
                    </td>
                    <td className="max-w-72 px-4 py-4">
                      <div className="font-medium text-on-surface">{item.title || row.title || "Untitled role"}</div>
                      {row.keyword ? (
                        <div className="mt-1 text-xs text-on-surface-variant">Keyword: {row.keyword}</div>
                      ) : null}
                    </td>
                    <td className="max-w-52 px-4 py-4 text-on-surface-variant">
                      {item.location || row.location_raw || "Not set"}
                    </td>
                    <td className="px-4 py-4 text-on-surface-variant">
                      {formatDate(item.application_date || row.application_date || item.run_finished_at) || "Not set"}
                    </td>
                    <td className="px-4 py-4">
                      <TrackerResourceCell item={item} request={request} />
                    </td>
                    <td className="px-4 py-4 text-on-surface-variant">
                      {item.priority_rank || row.priority_rank || row.priority_tier || "Not set"}
                    </td>
                    <td className="px-4 py-4">
                      <TrackerNotesCell item={item} onUpdate={onUpdate} updating={updating} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="p-8 text-center">
          <span className="material-symbols-outlined text-3xl text-on-surface-variant">filter_alt_off</span>
          <p className="mt-3 text-sm font-semibold text-on-surface">No tracker rows match these filters.</p>
          <button
            className="mt-3 rounded-full bg-primary/10 px-4 py-2 text-xs font-semibold text-primary transition-colors hover:bg-primary/20"
            onClick={clearFilters}
            type="button"
          >
            Clear filters
          </button>
        </div>
      )}
    </div>
  );
}

function KanbanColumn({ colDef, cards, onDelete, onUpdate, updating }) {
  return (
    <div className="flex min-w-[280px] flex-1 flex-col">
      {/* Column header */}
      <div
        className={[
          "mb-4 flex items-center justify-between rounded-xl border px-4 py-3",
          colDef.border,
        ].join(" ")}
      >
        <div className="flex items-center gap-2">
          <span
            className={["material-symbols-outlined text-xl", colDef.accent].join(" ")}
            style={{ fontVariationSettings: "'FILL' 1" }}
          >
            {colDef.icon}
          </span>
          <span className="font-semibold text-on-surface">{colDef.label}</span>
        </div>
        <span
          className={[
            "min-w-[24px] rounded-full px-2 py-0.5 text-center text-xs font-bold",
            colDef.badge,
          ].join(" ")}
        >
          {cards.length}
        </span>
      </div>

      {/* Cards */}
      <div className="flex flex-col gap-3">
        {cards.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-outline-variant/20 py-10 text-center text-sm text-on-surface-variant/50">
            <span
              className="material-symbols-outlined mb-2 text-3xl opacity-30"
              style={{ fontVariationSettings: "'FILL' 1" }}
            >
              {colDef.icon}
            </span>
            No jobs here yet
          </div>
        ) : (
          cards.map((item) => (
            <TrackerCard
              item={item}
              key={item.review_id}
              onDelete={onDelete}
              onUpdate={onUpdate}
              updating={updating}
            />
          ))
        )}
      </div>
    </div>
  );
}

function buildEmailFormState(integration) {
  const config = integration?.config || {};
  return {
    folder: config.folder || "INBOX",
    max_messages: String(config.max_messages || 40),
    scan_window: config.scan_window || "last_1_month",
  };
}

function EmailIntegrationPanel({
  integration,
  busy,
  onStartGoogle,
  onRefreshIntegration,
  onSaveSettings,
  onSync,
  onApproveDetections,
  onDismissDetections,
  onDelete,
  lastSyncResult,
}) {
  const config = integration?.config || {};
  const [form, setForm] = useState(() => buildEmailFormState(integration));
  const [feedback, setFeedback] = useState({ message: "", error: "" });

  useEffect(() => {
    setForm(buildEmailFormState(integration));
  }, [integration]);

  const syncSummary = lastSyncResult?.summary || config.last_sync_summary || null;
  const reviewDetections = config.pending_detections || [];
  const pendingDetectionCount = Number(config.pending_detection_count || reviewDetections.length || 0);
  const detectionActionBusy = busy === "approve-detections" || busy === "dismiss-detections";

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function handleSaveSettings(event) {
    event.preventDefault();
    setFeedback({ message: "", error: "" });
    try {
      await onSaveSettings({
        provider_id: "gmail",
        auth_strategy: "google_oauth",
        folder: form.folder,
        max_messages: Number(form.max_messages || 40),
        scan_window: form.scan_window,
      });
      setFeedback({ message: "Sync settings updated.", error: "" });
    } catch (saveError) {
      setFeedback({ message: "", error: saveError.message || "Unable to update sync settings." });
    }
  }

  async function handleGoogleConnect() {
    setFeedback({ message: "", error: "" });
    try {
      const startPayload = await onStartGoogle({
        folder: form.folder,
        max_messages: Number(form.max_messages || 40),
        scan_window: form.scan_window,
      });
      const authorizationUrl = startPayload?.authorization_url || "";
      if (!authorizationUrl) {
        throw new Error("Google authorization could not be started.");
      }
      const popup = window.open(
        authorizationUrl,
        "tracker-google-oauth",
        "popup=yes,width=520,height=720",
      );
      if (!popup) {
        window.location.assign(authorizationUrl);
        return;
      }
      setFeedback({
        message: "Finish Google sign-in in the popup. The tracker will refresh automatically once access is granted.",
        error: "",
      });
      const timeoutAt = Date.now() + 90_000;
      while (Date.now() < timeoutAt) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        const refreshed = await onRefreshIntegration();
        const refreshedConfig = refreshed?.config || {};
        if (refreshedConfig.connected) {
          try {
            popup.close();
          } catch {
            // Ignore popup close issues.
          }
          setFeedback({
            message: `${refreshedConfig.email_address || "Your Gmail inbox"} is now connected.`,
            error: "",
          });
          return;
        }
        if (refreshedConfig.last_error) {
          throw new Error(refreshedConfig.last_error);
        }
        if (popup.closed && refreshedConfig.authorization_state !== "authorization_url_created") {
          break;
        }
      }
      setFeedback({
        message: "Waiting for Google authorization to finish. If you already approved access, refresh once.",
        error: "",
      });
    } catch (connectError) {
      setFeedback({
        message: "",
        error: connectError.message || "Unable to start Google authorization.",
      });
    }
  }

  async function handleSync() {
    setFeedback({ message: "", error: "" });
    try {
      const result = await onSync({
        max_messages: Number(form.max_messages || 40),
        scan_window: form.scan_window,
      });
      const summary = result?.result?.summary || {};
      setFeedback({
        message: `Sync complete. ${summary.updated_reviews || 0} tracker card${summary.updated_reviews === 1 ? "" : "s"} updated.`,
        error: "",
      });
    } catch (syncError) {
      setFeedback({ message: "", error: syncError.message || "Unable to sync inbox." });
    }
  }

  async function handleDelete() {
    setFeedback({ message: "", error: "" });
    try {
      await onDelete();
      setForm(buildEmailFormState({}));
      setFeedback({ message: "Inbox connection removed.", error: "" });
    } catch (deleteError) {
      setFeedback({ message: "", error: deleteError.message || "Unable to disconnect inbox." });
    }
  }

  async function approveDetection(detection) {
    setFeedback({ message: "", error: "" });
    try {
      await onApproveDetections([detection]);
      setFeedback({ message: "Gmail detection imported into the tracker.", error: "" });
    } catch (approveError) {
      setFeedback({ message: "", error: approveError.message || "Unable to approve this detection." });
    }
  }

  async function dismissDetection(detection) {
    setFeedback({ message: "", error: "" });
    try {
      await onDismissDetections([detection]);
      setFeedback({ message: "Detection dismissed and removed from review.", error: "" });
    } catch (dismissError) {
      setFeedback({ message: "", error: dismissError.message || "Unable to dismiss this detection." });
    }
  }

  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-sm">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-2xl">
          <h2 className="font-headline text-2xl font-bold tracking-tight text-on-surface">
            Email Inbox Sync
          </h2>
          <p className="mt-2 text-sm leading-7 text-on-surface-variant">
            Connect Gmail with Google authorization so the tracker can pull confirmations,
            interview invites, and rejections into the board when you run inbox sync.
          </p>
          <p className="mt-3 rounded-2xl bg-surface-container px-4 py-3 text-xs leading-6 text-on-surface-variant">
            <span className="font-semibold text-on-surface">Secure access:</span>
            {" "}
            the tracker stores OAuth tokens and reads Gmail in read-only mode. It does not ask
            for your account password.
          </p>
          {config.email_address ? (
            <p className="mt-3 rounded-2xl bg-surface-container px-4 py-3 text-xs leading-6 text-on-surface-variant">
              <span className="font-semibold text-on-surface">Connected account:</span>
              {" "}
              {config.email_address}
            </p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!config.oauth_available || busy === "authorize"}
            onClick={handleGoogleConnect}
            type="button"
          >
            <span className="material-symbols-outlined text-[18px]">
              {busy === "authorize" ? "progress_activity" : "login"}
            </span>
            {busy === "authorize"
              ? "Opening Google..."
              : config.connected
                ? "Reconnect Google"
                : "Connect with Google"}
          </button>
          <button
            className="flex items-center gap-2 rounded-lg bg-primary/10 px-4 py-2.5 text-sm font-medium text-primary transition-colors hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!config.connected || busy === "sync"}
            onClick={handleSync}
            type="button"
          >
            <span className="material-symbols-outlined text-[18px]">
              {busy === "sync" ? "progress_activity" : "mark_email_read"}
            </span>
            {busy === "sync" ? "Syncing..." : "Sync Inbox"}
          </button>
          <button
            className="rounded-lg border border-outline-variant/20 px-4 py-2.5 text-sm font-medium text-on-surface-variant transition-colors hover:bg-surface-container-low disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!config.connected || busy === "delete"}
            onClick={handleDelete}
            type="button"
          >
            Disconnect
          </button>
        </div>
      </div>

      <form className="mt-6 grid gap-4 lg:grid-cols-2" onSubmit={handleSaveSettings}>
        <label className="block">
          <span className="mb-2 block text-sm font-semibold text-on-surface">Scan Depth</span>
          <input
            className="w-full rounded-xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            max="100"
            min="1"
            onChange={(event) => updateField("max_messages", event.target.value)}
            type="number"
            value={form.max_messages}
          />
        </label>

        <label className="block">
          <span className="mb-2 block text-sm font-semibold text-on-surface">Folder</span>
          <input
            className="w-full rounded-xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateField("folder", event.target.value)}
            placeholder="INBOX"
            type="text"
            value={form.folder}
          />
        </label>

        <label className="block lg:col-span-2">
          <span className="mb-2 block text-sm font-semibold text-on-surface">Read emails from</span>
          <select
            className="w-full rounded-xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateField("scan_window", event.target.value)}
            value={form.scan_window}
          >
            <option value="now">Now onward</option>
            <option value="last_1_month">Last 1 month</option>
            <option value="last_2_months">Last 2 months</option>
            <option value="last_3_months">Last 3 months</option>
          </select>
          <span className="mt-2 block text-xs leading-6 text-on-surface-variant">
            Runr only looks for likely application-status emails such as confirmations,
            interviews, rejections, and offers.
          </span>
        </label>

        <div className="lg:col-span-2">
          {feedback.error ? (
            <div className="rounded-2xl border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">
              {feedback.error}
            </div>
          ) : null}
          {feedback.message ? (
            <div className="rounded-2xl border border-primary/20 bg-primary/5 px-4 py-3 text-sm text-primary">
              {feedback.message}
            </div>
          ) : null}
          {config.last_error && !feedback.error ? (
            <div className="rounded-2xl border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">
              Last sync error: {config.last_error}
            </div>
          ) : null}
          {!config.oauth_available ? (
            <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm text-amber-600">
              Google OAuth is not configured on the backend yet. Set the tracker Google client ID and secret first.
            </div>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-3 lg:col-span-2">
          <button
            className="rounded-lg bg-surface-container-high px-5 py-3 text-sm font-medium text-on-surface shadow-sm transition-all hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-60"
            disabled={busy === "save"}
            type="submit"
          >
            {busy === "save" ? "Saving..." : "Save Sync Settings"}
          </button>
          {config.connected_at ? (
            <span className="text-sm text-on-surface-variant">
              Connected {formatDate(config.connected_at)}
            </span>
          ) : null}
          {config.last_sync_at ? (
            <span className="text-sm text-on-surface-variant">
              Last sync {formatDate(config.last_sync_at)}
            </span>
          ) : null}
          {config.authorization_state === "authorization_url_created" && !config.connected ? (
            <span className="text-sm text-primary">Awaiting Google authorization</span>
          ) : null}
        </div>
      </form>

      {syncSummary ? (
        <div className="mt-6 flex gap-3 overflow-x-auto pb-1">
          {[
            { label: "Checked", value: syncSummary.checked_messages || 0 },
            { label: "Processed", value: syncSummary.processed_messages || 0 },
            { label: "Updated", value: syncSummary.updated_reviews || 0 },
            { label: "Unmatched", value: syncSummary.unmatched_messages || 0 },
            { label: "Needs review", value: pendingDetectionCount },
          ].map((item) => (
            <div
              className="flex min-w-[180px] flex-1 items-center justify-between gap-4 rounded-2xl border border-outline-variant/20 bg-surface-container px-4 py-3"
              key={item.label}
            >
              <div className="min-w-0 whitespace-nowrap text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">
                {item.label}
              </div>
              <div className="shrink-0 text-2xl font-bold text-on-surface">{item.value}</div>
            </div>
          ))}
        </div>
      ) : null}

      {lastSyncResult?.matched_updates?.length ? (
        <div className="mt-6 rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4">
          <h3 className="text-sm font-semibold text-on-surface">Automatic Tracker Updates</h3>
          <p className="mt-1 text-xs leading-6 text-on-surface-variant">
            High-confidence Gmail matches update the tracker immediately when the sender and message content look job-related.
          </p>
          <div className="mt-3 space-y-2">
            {lastSyncResult.matched_updates.slice(0, 5).map((match) => (
              <div
                className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-surface px-3 py-2 text-sm"
                key={`${match.review_id}-${match.message_id}`}
              >
                <div>
                  <span className="font-medium text-on-surface">{match.company || "Unknown Company"}</span>
                  {" "}
                  <span className="text-on-surface-variant">- {match.title || "Untitled role"}</span>
                </div>
                <div className="text-on-surface-variant">
                  {match.from_status || "not_applied"} → {match.to_status}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {reviewDetections.length ? (
        <div className="mt-6 rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-on-surface">Needs Review</h3>
              <p className="mt-1 text-xs leading-6 text-on-surface-variant">
                Approve messages that should update the tracker or import an external application. Dismiss anything that is too weak or irrelevant.
              </p>
            </div>
            <span className="rounded-full bg-surface px-3 py-1 text-xs font-semibold text-on-surface-variant">
              {pendingDetectionCount} pending
            </span>
          </div>
          <div className="mt-4 space-y-3">
            {reviewDetections.slice(0, 12).map((detection) => {
              const detectedCompany = detection.detected_application.company || "Company not matched";
              const detectedTitle = detection.detected_application.title || "Title not detected";
              const isMatchedTrackerCard = Boolean(detection.metadata?.review_id);
              return (
                <article
                  className="rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3"
                  key={detection.detection_id}
                >
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-on-surface">
                          {detectedCompany}
                          {detectedTitle ? ` - ${detectedTitle}` : ""}
                        </span>
                        <span className="rounded-full bg-surface-container px-2 py-1 text-xs text-on-surface-variant">
                          {detection.status.suggested_application_status} · {detection.status.confidence}
                        </span>
                        <span className="rounded-full bg-primary/10 px-2 py-1 text-xs font-medium text-primary">
                          {isMatchedTrackerCard ? "Matched tracker card" : "New external application"}
                        </span>
                      </div>
                      <div className="mt-2 text-xs leading-6 text-on-surface-variant">
                        {detection.source_email.subject || "No subject"} · {detection.source_email.from_address || "Unknown sender"}
                      </div>
                      <div className="text-xs leading-6 text-on-surface-variant">
                        {formatDateTime(detection.source_email.sent_at)}
                      </div>
                      {detection.status.evidence?.length ? (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {detection.status.evidence.map((evidence) => (
                            <span
                              className="rounded-full bg-surface-container-high px-2.5 py-1 text-[11px] font-medium text-on-surface-variant"
                              key={`${detection.detection_id}-${evidence}`}
                            >
                              {evidence}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>

                    <div className="flex shrink-0 flex-wrap gap-2">
                      <button
                        className="rounded-lg bg-primary/10 px-3 py-2 text-xs font-semibold text-primary transition hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-60"
                        disabled={detectionActionBusy}
                        onClick={() => approveDetection(detection)}
                        type="button"
                      >
                        Import / approve
                      </button>
                      <button
                        className="rounded-lg bg-surface-container-high px-3 py-2 text-xs font-semibold text-on-surface transition hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-60"
                        disabled={detectionActionBusy}
                        onClick={() => dismissDetection(detection)}
                        type="button"
                      >
                        Dismiss
                      </button>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      ) : syncSummary ? (
        <div className="mt-6 rounded-2xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 text-sm text-on-surface-variant">
          No Gmail detections are waiting for review.
        </div>
      ) : null}
    </section>
  );
}

export default function TrackerPage() {
  const { request } = useSession();
  const [deleteFeedback, setDeleteFeedback] = useState({ message: "", error: "" });
  const [discoveringId, setDiscoveringId] = useState("");
  const [discoveryModal, setDiscoveryModal] = useState(EMPTY_DISCOVERY_MODAL);
  const [discoveryFeedback, setDiscoveryFeedback] = useState(EMPTY_DISCOVERY_FEEDBACK);
  const {
    columns,
    items,
    loading,
    error,
    refresh,
    updating,
    updateCard,
    deleteCard,
    emailIntegration,
    integrationBusy,
    lastSyncResult,
    refreshEmailIntegration,
    startGoogleEmailIntegration,
    updateEmailIntegrationSettings,
    syncEmailIntegration,
    approveEmailDetections,
    dismissEmailDetections,
    deleteEmailIntegration,
  } = useTracker();
  const totalCards = items.length;

  async function handleDeleteCard(item) {
    const confirmed = window.confirm(
      `Delete ${item.title || "this job"}? This removes it from the tracker${item.external_application ? "" : " and linked generated job data"}.`,
    );
    if (!confirmed) {
      return;
    }
    setDeleteFeedback({ message: "", error: "" });
    try {
      await deleteCard(item);
      setDeleteFeedback({ message: "Deleted job.", error: "" });
    } catch (deleteError) {
      setDeleteFeedback({
        message: "",
        error: deleteError.message || "Unable to delete this job.",
      });
    }
  }

  function closeDiscoveryModal() {
    setDiscoveryModal(EMPTY_DISCOVERY_MODAL);
    setDiscoveryFeedback(EMPTY_DISCOVERY_FEEDBACK);
  }

  async function handleDiscoverContacts(item) {
    if (!item?.run_id || !item?.job_id) {
      setDeleteFeedback({
        message: "",
        error: "This tracker row is missing the run or job reference needed for contact discovery.",
      });
      return;
    }
    setDeleteFeedback({ message: "", error: "" });
    setDiscoveringId(item.review_id || item.job_id || `${item.run_id}:${item.job_id}`);
    try {
      const payload = await request("/outreach/target-contact-discovery", {
        method: "POST",
        body: {
          run_id: item.run_id,
          job_id: item.job_id,
        },
      });
      setDiscoveryModal({
        open: true,
        item,
        payload,
      });
      setDiscoveryFeedback(EMPTY_DISCOVERY_FEEDBACK);
    } catch (discoveryError) {
      setDeleteFeedback({
        message: "",
        error: discoveryError.message || "Unable to generate target contact discovery right now.",
      });
    } finally {
      setDiscoveringId("");
    }
  }

  async function copyDiscoveryText(text, successMessage) {
    try {
      await navigator.clipboard.writeText(String(text || ""));
      setDiscoveryFeedback({ message: successMessage, error: "" });
    } catch (copyError) {
      setDiscoveryFeedback({
        message: "",
        error: copyError.message || "Unable to copy this text.",
      });
    }
  }

  return (
    <div className="space-y-8">
      {/* Page header */}
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="font-headline text-[2.25rem] font-extrabold leading-tight tracking-tight text-on-surface">
            Application Tracker
          </h1>
          <p className="mt-1 text-sm text-on-surface-variant">
            {totalCards > 0
              ? `Tracking ${totalCards} application${totalCards === 1 ? "" : "s"} across all stages.`
              : "Track applications here once they are active."}
          </p>
        </div>
        <button
          className="flex items-center gap-2 rounded bg-surface-container-high px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-surface-container-low active:scale-[0.98]"
          onClick={() => refresh().catch(() => undefined)}
          type="button"
        >
          <span className="material-symbols-outlined text-sm">refresh</span>
          Refresh
        </button>
      </header>

      {/* State feedback */}
      {loading && (
        <div className="flex items-center gap-3 rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-6 py-4 text-sm text-on-surface-variant">
          <span className="material-symbols-outlined animate-spin">progress_activity</span>
          Loading tracker...
        </div>
      )}
      {error && !loading && (
        <div className="flex items-center gap-3 rounded-xl border border-error/20 bg-error/5 px-6 py-4 text-sm text-error">
          <span className="material-symbols-outlined">error</span>
          {error}
        </div>
      )}
      {!loading && !error && (deleteFeedback.message || deleteFeedback.error) ? (
        <div
          className={[
            "flex items-center gap-3 rounded-xl border px-6 py-4 text-sm",
            deleteFeedback.error
              ? "border-error/20 bg-error/5 text-error"
              : "border-primary/20 bg-primary/5 text-primary",
          ].join(" ")}
        >
          <span className="material-symbols-outlined">
            {deleteFeedback.error ? "error" : "task_alt"}
          </span>
          {deleteFeedback.error || deleteFeedback.message}
        </div>
      ) : null}

      {!loading && !error ? (
        <EmailIntegrationPanel
          busy={integrationBusy}
          integration={emailIntegration}
          lastSyncResult={lastSyncResult}
          onDelete={deleteEmailIntegration}
          onDismissDetections={dismissEmailDetections}
          onRefreshIntegration={refreshEmailIntegration}
          onSaveSettings={updateEmailIntegrationSettings}
          onApproveDetections={approveEmailDetections}
          onStartGoogle={startGoogleEmailIntegration}
          onSync={syncEmailIntegration}
        />
      ) : null}

      {!loading && !error && (
        <div className="grid gap-3 md:grid-cols-4 xl:grid-cols-7">
          {COLUMNS.map((column) => (
            <div
              className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3"
              key={column.key}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-on-surface-variant">{column.label}</span>
                <span className={["rounded-full px-2 py-0.5 text-xs font-bold", column.badge].join(" ")}>
                  {columns[column.key]?.length || 0}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {!loading && !error ? (
        <TrackerTable
          items={items}
          onUpdate={updateCard}
          request={request}
          updating={updating}
        />
      ) : null}

      {discoveryModal.open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 px-6 py-10 backdrop-blur-sm">
          <div className="w-full max-w-5xl rounded-3xl border border-outline-variant/20 bg-surface-container-lowest shadow-2xl">
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-outline-variant/10 px-6 py-5">
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                  Target Contact Discovery
                </div>
                <h2 className="mt-1 font-headline text-2xl font-bold tracking-tight text-on-surface">
                  {discoveryModal.item?.title || "Application"}{discoveryModal.item?.company ? ` at ${discoveryModal.item.company}` : ""}
                </h2>
                <p className="mt-2 max-w-3xl text-sm text-on-surface-variant">
                  {discoveryModal.payload?.strategy_summary ||
                    "Use this shortlist to find people who are more likely to influence referrals, process visibility, or team context."}
                </p>
              </div>
              <button
                className="rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container-low hover:text-on-surface"
                onClick={closeDiscoveryModal}
                type="button"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>

            <div className="space-y-5 px-6 py-5">
              <div className="grid gap-3 md:grid-cols-4">
                <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4">
                  <div className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">Department</div>
                  <div className="mt-2 text-base font-semibold text-on-surface">
                    {discoveryModal.payload?.department_label || "Hiring Team"}
                  </div>
                </div>
                <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4">
                  <div className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">Location Hint (Optional)</div>
                  <div className="mt-2 text-base font-semibold text-on-surface">
                    {discoveryModal.payload?.location_hint || "Not specified"}
                  </div>
                </div>
                <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4">
                  <div className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">Candidate Lanes</div>
                  <div className="mt-2 text-base font-semibold text-on-surface">
                    {(discoveryModal.payload?.candidates || []).length}
                  </div>
                </div>
                <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4">
                  <div className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">Default Passes</div>
                  <div className="mt-2 text-base font-semibold text-on-surface">
                    {discoveryModal.payload?.default_pass_count || 2}
                  </div>
                </div>
              </div>

              {discoveryFeedback.message || discoveryFeedback.error ? (
                <div
                  className={[
                    "rounded-2xl border px-4 py-3 text-sm",
                    discoveryFeedback.error
                      ? "border-error/20 bg-error/5 text-error"
                      : "border-primary/20 bg-primary/5 text-primary",
                  ].join(" ")}
                >
                  {discoveryFeedback.error || discoveryFeedback.message}
                </div>
              ) : null}

              {discoveryModal.payload?.warnings?.length ? (
                <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm text-amber-700">
                  {discoveryModal.payload.warnings.join(" | ")}
                </div>
              ) : null}

              {(discoveryModal.payload?.passes || []).length ? (
                <div className="grid gap-4 xl:grid-cols-2">
                  {(discoveryModal.payload?.passes || []).map((passItem) => (
                    <section
                      className="rounded-3xl border border-outline-variant/20 bg-surface p-5"
                      key={`pass-${passItem.pass_index}`}
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                            Pass {passItem.pass_index}
                          </div>
                          <div className="mt-2 text-lg font-semibold text-on-surface">
                            {passItem.result_count || 0} public result{passItem.result_count === 1 ? "" : "s"}
                          </div>
                          <p className="mt-2 text-sm leading-6 text-on-surface-variant">
                            {passItem.summary}
                          </p>
                        </div>
                        <div className="rounded-2xl bg-surface-container-low px-4 py-3 text-right">
                          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">
                            Queries
                          </div>
                          <div className="mt-1 text-xl font-semibold text-on-surface">
                            {passItem.query_count || 0}
                          </div>
                        </div>
                      </div>

                      {passItem.top_domains?.length ? (
                        <div className="mt-4 flex flex-wrap gap-2">
                          {passItem.top_domains.map((domain) => (
                            <span
                              className="rounded-full bg-surface-container-low px-2.5 py-1 text-xs font-medium text-on-surface"
                              key={`${passItem.pass_index}-${domain}`}
                            >
                              {domain}
                            </span>
                          ))}
                        </div>
                      ) : null}

                      {passItem.queries?.length ? (
                        <div className="mt-4 space-y-2">
                          {passItem.queries.map((queryPlan, index) => (
                            <div
                              className="rounded-2xl border border-outline-variant/20 bg-surface-container-low p-3"
                              key={`pass-${passItem.pass_index}-query-${index}`}
                            >
                              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">
                                {queryPlan.lane || "general"} query
                              </div>
                              <div className="mt-1 text-sm font-medium text-on-surface">{queryPlan.query}</div>
                              {queryPlan.objective ? (
                                <div className="mt-1 text-xs leading-5 text-on-surface-variant">
                                  {queryPlan.objective}
                                </div>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      ) : null}

                      {passItem.results_preview?.length ? (
                        <div className="mt-4 space-y-2">
                          {passItem.results_preview.map((result, index) => (
                            <a
                              className="block rounded-2xl border border-outline-variant/20 bg-surface-container-low p-3 transition-colors hover:bg-surface-container"
                              href={result.url}
                              key={`pass-${passItem.pass_index}-result-${index}`}
                              rel="noreferrer"
                              target="_blank"
                            >
                              <div className="text-sm font-semibold text-on-surface">{result.title}</div>
                              <div className="mt-1 text-xs text-on-surface-variant">
                                {(result.source_domain || "unknown domain")}
                                {result.lane ? ` | ${result.lane}` : ""}
                              </div>
                              {result.snippet ? (
                                <div className="mt-2 text-xs leading-5 text-on-surface-variant">
                                  {result.snippet}
                                </div>
                              ) : null}
                            </a>
                          ))}
                        </div>
                      ) : null}
                    </section>
                  ))}
                </div>
              ) : null}

              <div className="grid gap-4 xl:grid-cols-2">
                {(discoveryModal.payload?.candidates || []).map((candidate) => (
                  <article
                    className="rounded-3xl border border-outline-variant/20 bg-surface p-5"
                    key={candidate.candidate_id || candidate.role_label}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="text-lg font-semibold text-on-surface">{candidate.role_label}</h3>
                          <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
                            Score {candidate.fit_score || 0}
                          </span>
                          <span className="rounded-full bg-surface-container-low px-2.5 py-1 text-xs font-semibold text-on-surface-variant">
                            {candidate.confidence || "medium"}
                          </span>
                        </div>
                        {candidate.resolved_name ? (
                          <div className="mt-2 text-sm font-medium text-on-surface">
                            {candidate.resolved_name}
                          </div>
                        ) : candidate.guessed_name ? (
                          <div className="mt-2 text-sm font-medium text-on-surface">
                            Named signal: {candidate.guessed_name}
                          </div>
                        ) : (
                          <div className="mt-2 text-sm font-medium text-on-surface-variant">
                            Unresolved lane, keep verifying before outreach.
                          </div>
                        )}
                      </div>
                      <span className="rounded-full bg-surface-container-low px-3 py-1 text-xs font-semibold text-on-surface-variant">
                        {candidate.access_hint || "Hiring signal"}
                      </span>
                    </div>

                    {(candidate.resolved_title || candidate.resolved_company || candidate.resolved_location) ? (
                      <div className="mt-3 grid gap-3 sm:grid-cols-3">
                        <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-low p-3">
                          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">
                            Title
                          </div>
                          <div className="mt-1 text-sm font-medium text-on-surface">
                            {candidate.resolved_title || "Not resolved"}
                          </div>
                        </div>
                        <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-low p-3">
                          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">
                            Company
                          </div>
                          <div className="mt-1 text-sm font-medium text-on-surface">
                            {candidate.resolved_company || "Not resolved"}
                          </div>
                        </div>
                        <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-low p-3">
                          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">
                            Location
                          </div>
                          <div className="mt-1 text-sm font-medium text-on-surface">
                            {candidate.resolved_location || "Not resolved"}
                          </div>
                        </div>
                      </div>
                    ) : null}

                    {candidate.title_variants?.length ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {candidate.title_variants.map((titleVariant) => (
                          <span
                            className="rounded-full bg-surface-container-low px-2.5 py-1 text-xs font-medium text-on-surface"
                            key={`${candidate.candidate_id}-${titleVariant}`}
                          >
                            {titleVariant}
                          </span>
                        ))}
                      </div>
                    ) : null}

                    <p className="mt-4 text-sm leading-6 text-on-surface-variant">
                      {candidate.rationale}
                    </p>

                    {candidate.evidence?.length ? (
                      <div className="mt-4 rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4">
                        <div className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">
                          Evidence
                        </div>
                        <div className="mt-3 space-y-2">
                          {candidate.evidence.map((item, index) => (
                            <div
                              className="rounded-2xl bg-surface px-3 py-2 text-sm leading-6 text-on-surface-variant"
                              key={`${candidate.candidate_id}-evidence-${index}`}
                            >
                              {item}
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {candidate.source_urls?.length ? (
                      <div className="mt-4 rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4">
                        <div className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">
                          Source Links
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {candidate.source_urls.map((url, index) => (
                            <a
                              className="inline-flex items-center gap-1 rounded-full bg-surface-container px-3 py-1.5 text-xs font-semibold text-on-surface hover:bg-surface-container-high"
                              href={url}
                              key={`${candidate.candidate_id}-source-${index}`}
                              rel="noreferrer"
                              target="_blank"
                            >
                              {candidate.source_titles?.[index] || `Source ${index + 1}`}
                              <span className="material-symbols-outlined text-[13px]">open_in_new</span>
                            </a>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {candidate.search_query ? (
                      <div className="mt-4 rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4">
                        <div className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">Verification Query</div>
                        <div className="mt-2 text-sm font-medium text-on-surface">{candidate.search_query}</div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {candidate.linkedin_search_url ? (
                            <a
                              className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/20"
                              href={candidate.linkedin_search_url}
                              rel="noreferrer"
                              target="_blank"
                            >
                              LinkedIn Search
                              <span className="material-symbols-outlined text-[13px]">open_in_new</span>
                            </a>
                          ) : null}
                          {candidate.google_xray_search_url ? (
                            <a
                              className="inline-flex items-center gap-1 rounded-full bg-surface-container px-3 py-1.5 text-xs font-semibold text-on-surface hover:bg-surface-container-high"
                              href={candidate.google_xray_search_url}
                              rel="noreferrer"
                              target="_blank"
                            >
                              X-Ray Search
                              <span className="material-symbols-outlined text-[13px]">open_in_new</span>
                            </a>
                          ) : null}
                        </div>
                        <div className="mt-3 text-xs text-on-surface-variant">
                          {candidate.resolved_in_pass
                            ? `Best evidence surfaced by pass ${candidate.resolved_in_pass}.`
                            : "Keep verifying this lane before outreach."}
                        </div>
                      </div>
                    ) : null}

                    <div className="mt-4 grid gap-4">
                      <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4">
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-sm font-semibold text-on-surface">Quick Connect Note</div>
                          <button
                            className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary hover:bg-primary/20"
                            onClick={() =>
                              copyDiscoveryText(candidate.connection_note, "Connection note copied.")
                            }
                            type="button"
                          >
                            Copy
                          </button>
                        </div>
                        <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-on-surface-variant">
                          {candidate.connection_note}
                        </p>
                      </div>

                      <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4">
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-sm font-semibold text-on-surface">Follow-Up After They Accept</div>
                          <button
                            className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary hover:bg-primary/20"
                            onClick={() =>
                              copyDiscoveryText(candidate.follow_up_message, "Follow-up message copied.")
                            }
                            type="button"
                          >
                            Copy
                          </button>
                        </div>
                        <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-on-surface-variant">
                          {candidate.follow_up_message}
                        </p>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-outline-variant/10 px-6 py-4">
              <div className="text-xs text-on-surface-variant">
                Searches open in LinkedIn or Google so you can verify the real profile before sending anything.
              </div>
              <button
                className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90"
                onClick={closeDiscoveryModal}
                type="button"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
