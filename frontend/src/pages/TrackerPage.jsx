import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useTracker } from "../hooks/useTracker";
import { useApiResource } from "../hooks/useApiResource";
import AssistedApplyLaunchDialog from "../components/AssistedApplyLaunchDialog";
import { trackerDescriptionForItem } from "../lib/trackerDescription";
import { assistedApplyTrackerRow } from "../lib/trackerAssistedApply";
import { CV_STUDIO_ROUTE, stashCvStudioSeed } from "../lib/cvStudio";

const COLUMNS = [
  { key: "not_applied", label: "Not Applied", icon: "radio_button_unchecked", accent: "text-on-surface-variant", badge: "bg-surface-container text-on-surface-variant", border: "border-outline-variant/30", glow: "shadow-black/0" },
  { key: "applied", label: "Applied", icon: "send", accent: "text-primary", badge: "bg-primary/10 text-primary", border: "border-primary/30", glow: "shadow-primary/10" },
  { key: "interview_invited", label: "Interviewing", icon: "calendar_month", accent: "text-amber-500", badge: "bg-amber-500/10 text-amber-500", border: "border-amber-500/30", glow: "shadow-amber-500/10" },
  { key: "rejected", label: "Rejected", icon: "cancel", accent: "text-error", badge: "bg-error/10 text-error", border: "border-error/30", glow: "shadow-error/10" },
  { key: "offer", label: "Offer", icon: "workspace_premium", accent: "text-green-500", badge: "bg-green-500/10 text-green-500", border: "border-green-500/30", glow: "shadow-green-500/10" },
  { key: "withdrawn", label: "Withdrawn", icon: "remove_circle", accent: "text-on-surface-variant", badge: "bg-surface-container text-on-surface-variant", border: "border-outline-variant/30", glow: "shadow-black/0" },
  { key: "unknown", label: "Unknown", icon: "help", accent: "text-on-surface-variant", badge: "bg-surface-container text-on-surface-variant", border: "border-outline-variant/30", glow: "shadow-black/0" },
];
const EMPTY_DISCOVERY_MODAL = { open: false, item: null, payload: null };
const EMPTY_DISCOVERY_FEEDBACK = { message: "", error: "" };
const TRACKER_SOURCE_FILTERS = [
  { value: "all", label: "All sources" },
  { value: "standard_run", label: "Standard runs" },
  { value: "test_run", label: "Test runs" },
  { value: "external", label: "External applications" },
];
const EMPTY_TRACKER_FILTERS = { query: "", status: "all", workspace: "all", source: "all" };
const BULK_DELETE_MODES = [
  { value: "all", label: "All matching" },
  { value: "date", label: "Added date" },
  { value: "company", label: "Company" },
];

function trackerFiltersFromSearchParams(searchParams) {
  return {
    query: searchParams.get("query") || "",
    status: searchParams.get("status") || "all",
    workspace: searchParams.get("workspace") || "all",
    source: searchParams.get("source") || "all",
  };
}

function formatDate(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }); }
  catch { return iso.slice(0, 10); }
}

function dateKeyFromIso(iso) {
  const text = String(iso || "").trim();
  return text ? text.slice(0, 10) : "";
}

function trackerAddedDateKey(item) {
  return dateKeyFromIso(item.placed_in_tracker_at || item.created_at || item.updated_at || item.run_finished_at);
}

function normalizeCompanyName(value) {
  return String(value || "").trim().toLocaleLowerCase();
}

function formatDateTime(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); }
  catch { return iso; }
}

function triggerDownload(blob, fileName) {
  const objectUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl; anchor.download = fileName || "document";
  document.body.appendChild(anchor); anchor.click(); anchor.remove();
  window.URL.revokeObjectURL(objectUrl);
}

function StatusDropdown({ current, onSelect, disabled }) {
  const [open, setOpen] = useState(false);
  const currentCol = COLUMNS.find((c) => c.key === current) || COLUMNS[0];
  return (
    <div className="relative">
      <button className={["flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold transition-all", currentCol.badge, disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:opacity-80"].join(" ")} disabled={disabled} onClick={() => !disabled && setOpen((v) => !v)} type="button">
        <span className="material-symbols-outlined text-[14px]">{currentCol.icon}</span>{currentCol.label}<span className="material-symbols-outlined text-[12px]">expand_more</span>
      </button>
      {open && (<><div className="fixed inset-0 z-10" onClick={() => setOpen(false)} /><div className="absolute left-0 top-full z-20 mt-1 w-52 overflow-hidden rounded-xl border border-outline-variant/20 bg-surface-container-lowest shadow-xl">{COLUMNS.map((col) => (<button className={["flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors hover:bg-surface-container-low", col.key === current ? "font-semibold " + col.accent : "text-on-surface"].join(" ")} key={col.key} onClick={() => { setOpen(false); if (col.key !== current) onSelect(col.key); }} type="button"><span className={["material-symbols-outlined text-[16px]", col.accent].join(" ")}>{col.icon}</span>{col.label}</button>))}</div></>)}
    </div>
  );
}

function ApplicationWarnings({ warnings = [], compact = false }) {
  const visibleWarnings = (warnings || []).filter((warning) => warning?.message || warning?.title);
  if (!visibleWarnings.length) return null;
  return (<div className={compact ? "space-y-1.5" : "mt-3 space-y-2"}>{visibleWarnings.slice(0, compact ? 2 : 3).map((warning, index) => { const blocking = String(warning.severity || "") === "blocking"; return (<div className={["rounded-xl border px-3 py-2 text-xs leading-5", blocking ? "border-error/25 bg-error/5 text-error" : "border-amber-500/25 bg-amber-500/5 text-amber-700"].join(" ")} key={`${warning.code || "application-warning"}-${index}`}><div className="flex items-start gap-2"><span className="material-symbols-outlined mt-0.5 text-[15px]">{blocking ? "priority_high" : "info"}</span><div><div className="font-semibold">{warning.title || "Application requirement"}</div><div>{warning.message}</div></div></div></div>); })}</div>);
}

function TrackerCard({ item, onAssistedApply, onUpdate, onDelete, updating }) {
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState(item.rejection_note || "");
  const isBusy = updating === item.review_id;
  const currentStatus = item.tracker_status === "email_confirmed" ? "applied" : item.tracker_status || "unknown";
  const isRejected = currentStatus === "rejected";
  const assistedApplyRow = assistedApplyTrackerRow(item);
  async function handleStatusChange(newStatus) { await onUpdate(item.review_id, { tracker_status: newStatus }); if (newStatus === "rejected") setNoteOpen(true); }
  async function handleEmailToggle() { await onUpdate(item.review_id, { email_confirmed: !item.email_confirmed }); }
  async function saveNote() { await onUpdate(item.review_id, { rejection_note: note }); setNoteOpen(false); }
  const col = COLUMNS.find((c) => c.key === currentStatus) || COLUMNS[COLUMNS.length - 1];
  return (
    <div className={["group relative overflow-hidden rounded-2xl border bg-surface-container-lowest p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md", col.border, col.glow].join(" ")}>
      {isBusy && (<div className="absolute inset-0 z-10 flex items-center justify-center rounded-2xl bg-surface-container-lowest/70 backdrop-blur-sm"><span className="material-symbols-outlined animate-spin text-2xl text-primary">progress_activity</span></div>)}
      <div className="mb-3 flex items-start justify-between gap-2"><div className="min-w-0 flex-1"><h3 className="truncate text-sm font-semibold text-on-surface leading-tight">{item.title}</h3><div className="mt-0.5 flex items-center gap-1.5 text-xs text-on-surface-variant"><span className="material-symbols-outlined text-[13px]">business</span><span className="truncate">{item.company || "Unknown Company"}</span></div></div><StatusDropdown current={currentStatus} disabled={isBusy} onSelect={handleStatusChange} /></div>
      <div className="mb-3 flex flex-wrap gap-2 text-xs text-on-surface-variant">{item.workspace_name && (<span className="flex items-center gap-1"><span className="material-symbols-outlined text-[12px]">workspaces</span>{item.workspace_name}</span>)}{item.run_finished_at && (<span className="flex items-center gap-1"><span className="material-symbols-outlined text-[12px]">event</span>{formatDate(item.run_finished_at)}</span>)}{item.location && (<span className="flex items-center gap-1"><span className="material-symbols-outlined text-[12px]">location_on</span>{item.location}</span>)}</div>
      <ApplicationWarnings warnings={item.application_warnings} />
      <div className="flex items-center justify-between gap-2">
        <button className={["flex items-center gap-1.5 rounded-full px-2 py-1 text-xs font-medium transition-all", item.email_confirmed ? "bg-teal-500/10 text-teal-600" : "bg-surface-container text-on-surface-variant hover:bg-teal-500/10 hover:text-teal-600"].join(" ")} disabled={isBusy} onClick={handleEmailToggle} title={item.email_confirmed ? "Email confirmed — click to unmark" : "Mark email as confirmed"} type="button"><span className="material-symbols-outlined text-[14px]">{item.email_confirmed ? "mark_email_read" : "mail"}</span>{item.email_confirmed ? "Email confirmed" : "Confirm email"}</button>
        <div className="flex items-center gap-1.5">
          {onDelete ? (<button className="flex h-7 w-7 items-center justify-center rounded-full text-on-surface-variant transition-colors hover:bg-error/10 hover:text-error" disabled={isBusy} onClick={() => onDelete(item)} title="Delete job" type="button"><span className="material-symbols-outlined text-[16px]">delete</span></button>) : null}
          {isRejected && (<button className="flex h-7 w-7 items-center justify-center rounded-full text-on-surface-variant transition-colors hover:bg-surface-container hover:text-primary" onClick={() => setNoteOpen((v) => !v)} title="Add rejection note" type="button"><span className="material-symbols-outlined text-[16px]">note_add</span></button>)}
          {assistedApplyRow ? (<button className="flex h-7 items-center gap-1 rounded-full bg-primary/10 px-2 text-xs font-semibold text-primary transition-colors hover:bg-primary/20" onClick={() => onAssistedApply(assistedApplyRow)} title="Prepare a reviewed Assisted Apply package" type="button"><span className="material-symbols-outlined text-[15px]">auto_awesome</span>Review &amp; Apply</button>) : null}
          {item.apply_link && (<a className="flex h-7 w-7 items-center justify-center rounded-full text-on-surface-variant transition-colors hover:bg-surface-container hover:text-primary" href={item.apply_link} rel="noreferrer" target="_blank" title="Open job posting"><span className="material-symbols-outlined text-[16px]">open_in_new</span></a>)}
        </div>
      </div>
      {noteOpen && (<div className="mt-3 border-t border-outline-variant/10 pt-3"><textarea className="w-full rounded-lg border border-outline-variant/20 bg-surface-container p-2 text-xs text-on-surface placeholder-on-surface-variant/50 focus:border-primary/30 focus:outline-none focus:ring-1 focus:ring-primary/20" onChange={(e) => setNote(e.target.value)} placeholder="Optional rejection note…" rows={2} value={note} /><div className="mt-1.5 flex justify-end gap-2"><button className="rounded px-2 py-1 text-xs text-on-surface-variant hover:text-on-surface" onClick={() => setNoteOpen(false)} type="button">Cancel</button><button className="rounded bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/20" onClick={saveNote} type="button">Save note</button></div></div>)}
      {item.rejection_note && !noteOpen && (<div className="mt-2 border-t border-outline-variant/10 pt-2 text-xs italic text-on-surface-variant">{item.rejection_note}</div>)}
    </div>
  );
}

function statusKeyFromItem(item) {
  const trackerStatus = item.tracker_status === "email_confirmed" ? "applied" : item.tracker_status;
  return COLUMNS.some((c) => c.key === trackerStatus) ? trackerStatus : "unknown";
}

function trackerItemMatchesFilters(item, filters, { ignoreStatus = false } = {}) {
  const row = item.tracker_table_row || {};
  const query = filters.query.trim().toLocaleLowerCase();
  const sourceType = item.tracker_source_type || (item.external_application ? "external" : item.is_test_run ? "test_run" : "standard_run");
  const searchableText = [item.title, row.title, item.company, row.company, item.location, row.location_raw, item.workspace_name].filter(Boolean).join(" ").toLocaleLowerCase();
  return (!query || searchableText.includes(query)) && (ignoreStatus || filters.status === "all" || statusKeyFromItem(item) === filters.status) && (filters.workspace === "all" || item.workspace_name === filters.workspace) && (filters.source === "all" || sourceType === filters.source);
}

const TRACKER_RESOURCE_BUTTON_CLASS = "inline-flex min-w-[120px] items-center justify-center gap-1 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors";

function TrackerLink({ href, children }) {
  if (!href) return (<span className={[TRACKER_RESOURCE_BUTTON_CLASS, "cursor-not-allowed bg-surface-container-low text-on-surface-variant/60"].join(" ")}>{children}</span>);
  return (<a className={[TRACKER_RESOURCE_BUTTON_CLASS, "bg-primary/10 text-primary hover:bg-primary/20"].join(" ")} href={href} rel="noreferrer" target="_blank">{children}<span className="material-symbols-outlined text-[13px]">open_in_new</span></a>);
}

function buildTrackerBundleLabel(item) {
  const base = [item.company, item.title, "application_documents"].map((s) => String(s || "").trim()).filter(Boolean).join("_").replace(/[^\w.-]+/g, "_").replace(/_+/g, "_").replace(/^_+|_+$/g, "");
  return base || "application_documents";
}

function parseTrackerNumber(value) { const p = Number(value); return Number.isFinite(p) ? p : null; }
function trackerAtsStopReasonLabel(stopReason) { const n = String(stopReason || "").trim().toLowerCase(); if (n === "target_reached") return "Target reached"; if (n === "max_attempts_reached") return "Pass limit reached"; if (n === "score_stalled") return "Score stalled"; return n ? n.replace(/_/g, " ") : ""; }
function normalizeTrackerAtsAttemptHistory(gate = {}) { const m = gate.metadata && typeof gate.metadata === "object" ? gate.metadata : {}; return Array.isArray(m.attempt_history) ? m.attempt_history.map((a, i) => ({ attempt: parseTrackerNumber(a?.attempt) ?? i + 1, score: parseTrackerNumber(a?.score), changedSections: Array.isArray(a?.changed_sections) ? a.changed_sections.map((s) => String(s || "").trim()).filter(Boolean) : [], changeSummary: String(a?.change_summary || "").trim(), missingRequirements: Array.isArray(a?.missing_requirements) ? a.missing_requirements.map((r) => String(r || "").trim()).filter(Boolean) : [], improvementActions: Array.isArray(a?.improvement_actions) ? a.improvement_actions.map((r) => String(r || "").trim()).filter(Boolean) : [], rationale: String(a?.rationale || "").trim() })) : []; }
function summarizeTrackerAtsState(documents = []) {
  const document = (Array.isArray(documents) ? documents : []).find((entry) => {
    const gate = entry?.ats_export_gate;
    return entry?.final_export_blocked || (gate && typeof gate === "object");
  });
  if (!document) return null;
  const gate = document.ats_export_gate && typeof document.ats_export_gate === "object" ? document.ats_export_gate : {};
  const gateState = String(gate.gate_state || "").trim().toLowerCase();
  const bestScore = parseTrackerNumber(gate.best_score ?? document.ats_best_score ?? document.ats_score);
  const targetScore = parseTrackerNumber(gate.target_score ?? document.ats_target_score);
  const stopReason = trackerAtsStopReasonLabel(gate.metadata?.stop_reason || document.ats_stop_reason);
  const attemptHistory = normalizeTrackerAtsAttemptHistory(gate);
  if (document.final_export_blocked || gateState === "blocked") {
    return { label: "ATS blocked", badgeClass: "bg-error/10 text-error", bestScore, targetScore, stopReason, attemptHistory };
  }
  if (gateState === "passed") {
    return { label: "ATS cleared", badgeClass: "bg-teal-500/10 text-teal-600", bestScore, targetScore, stopReason, attemptHistory };
  }
  if (gateState === "exported_anyway") {
    return { label: "ATS override", badgeClass: "bg-amber-500/10 text-amber-600", bestScore, targetScore, stopReason, attemptHistory };
  }
  return { label: "ATS checked", badgeClass: "bg-primary/10 text-primary", bestScore, targetScore, stopReason, attemptHistory };
}
function trackerAtsGateLabel(gateState) { const n = String(gateState || "").trim().toLowerCase(); if (n === "blocked") return "Blocked"; if (n === "passed") return "Cleared"; if (n === "exported_anyway") return "Override"; return "Preflight"; }
function trackerDocumentExtension(document = {}) {
  const candidates = [document.file_extension, document.path, document.file_name, document.label, document.download_url, document.document_id];
  for (const candidate of candidates) {
    const text = String(candidate || "").trim().toLowerCase();
    if (text === "pdf" || text.endsWith(".pdf")) return "pdf";
    if (text === "docx" || text.endsWith(".docx")) return "docx";
    if (text === "txt" || text.endsWith(".txt")) return "txt";
  }
  const contentType = String(document.content_type || "").trim().toLowerCase();
  if (contentType === "application/pdf") return "pdf";
  if (contentType.includes("wordprocessingml")) return "docx";
  if (contentType.startsWith("text/")) return "txt";
  return "";
}
function isTrackerApplicationCv(document = {}) {
  const assetKind = String(document.asset_kind || "").trim().toLowerCase();
  const documentType = String(document.document_type || "").trim().toLowerCase();
  const hasJobReference = Boolean(String(document.run_id || "").trim() && String(document.job_id || "").trim());
  return hasJobReference && (["generated_cv", "applied_cv"].includes(assetKind) || ["tailored cv", "applied cv"].includes(documentType));
}
function trackerDocumentExportRank(document = {}) {
  const extension = trackerDocumentExtension(document);
  if (extension === "pdf") return 0;
  if (extension === "docx") return 1;
  if (extension === "txt") return 2;
  return 3;
}
function canExportTrackerDocument(document = {}) {
  if (!String(document.document_id || "").trim()) return false;
  if (!document.final_export_blocked) return true;
  const gate = document.ats_export_gate && typeof document.ats_export_gate === "object" ? document.ats_export_gate : {};
  return Boolean(gate.export_anyway_allowed);
}
function selectTrackerExportDocuments(documents = []) {
  const candidates = (Array.isArray(documents) ? documents : []).filter(canExportTrackerDocument);
  const preferred = new Map();
  for (const document of candidates) {
    if (!isTrackerApplicationCv(document)) continue;
    const key = [document.run_id || "", document.job_id || "", document.asset_kind || "", document.document_type || ""].join("::");
    const current = preferred.get(key);
    if (!current || trackerDocumentExportRank(document) < trackerDocumentExportRank(current)) preferred.set(key, document);
  }
  const selected = [];
  const emitted = new Set();
  for (const document of candidates) {
    if (!isTrackerApplicationCv(document)) {
      selected.push(document);
      continue;
    }
    const key = [document.run_id || "", document.job_id || "", document.asset_kind || "", document.document_type || ""].join("::");
    if (emitted.has(key)) continue;
    if (preferred.get(key)?.document_id === document.document_id) {
      selected.push(document);
      emitted.add(key);
    }
  }
  return selected;
}
function sourceTypeForItem(item) {
  return item.tracker_source_type || (item.external_application ? "external" : item.is_test_run ? "test_run" : "standard_run");
}
function sourceLabelForItem(item) {
  const sourceType = sourceTypeForItem(item);
  const match = TRACKER_SOURCE_FILTERS.find((entry) => entry.value === sourceType);
  return match?.label || "Standard run";
}
function TrackerResourceCell({ item, onAssistedApply, request }) {
  const navigate = useNavigate();
  const [exporting, setExporting] = useState(false);
  const [feedback, setFeedback] = useState({ message: "", error: "" });
  const description = trackerDescriptionForItem(item);
  const atsSummary = summarizeTrackerAtsState(item.documents);
  const exportableDocuments = selectTrackerExportDocuments(item.documents);
  const canEditGeneratedCv = Boolean(item.has_generated_cv);
  const assistedApplyRow = assistedApplyTrackerRow(item);

  async function openGeneratedCvEditor() {
    if (!canEditGeneratedCv) return;
    try {
      const payload = await request(`/tracker/${encodeURIComponent(item.review_id)}/cv-studio-seed`);
      const seed = payload?.cv_studio_seed || {};
      if (!seed.profile) throw new Error("The generated CV source is unavailable.");
      stashCvStudioSeed({
        ...seed,
        returnTo: "/tracker",
        sourceLabel: [item.title, item.company].filter(Boolean).join(" at ") || "Generated application CV",
      });
      navigate(CV_STUDIO_ROUTE);
    } catch (error) {
      setFeedback({ message: "", error: error.message || "Unable to load the generated CV." });
    }
  }

  async function downloadBundle() {
    if (!exportableDocuments.length) return;
    setExporting(true);
    setFeedback({ message: "", error: "" });
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
      setFeedback({ message: "Documents ready.", error: "" });
    } catch (error) {
      setFeedback({ message: "", error: error.message || "Unable to export application documents." });
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="min-w-60 max-w-80 space-y-2">
      <div className="flex flex-wrap gap-2">
        <TrackerLink href={item.apply_link || item.tracker_table_row?.apply_link}>Apply</TrackerLink>
        {assistedApplyRow ? (
          <button className={`${TRACKER_RESOURCE_BUTTON_CLASS} bg-primary text-white hover:bg-primary/90`} onClick={() => onAssistedApply(assistedApplyRow)} type="button">
            <span className="material-symbols-outlined text-[13px]">auto_awesome</span>
            Review &amp; Apply
          </button>
        ) : null}
        {description ? (
          <Link className={`${TRACKER_RESOURCE_BUTTON_CLASS} bg-surface-container-low text-on-surface hover:bg-surface-container-high`} to={`/tracker/job-descriptions/${encodeURIComponent(item.review_id)}`}>
            <span className="material-symbols-outlined text-[13px]">article</span>
            Read post
          </Link>
        ) : (
          <span className={`${TRACKER_RESOURCE_BUTTON_CLASS} cursor-not-allowed bg-surface-container-low text-on-surface-variant/60`}>
            <span className="material-symbols-outlined text-[13px]">article</span>
            No post text
          </span>
        )}
        <button
          className={[TRACKER_RESOURCE_BUTTON_CLASS, exportableDocuments.length ? "bg-primary/10 text-primary hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-60" : "cursor-not-allowed bg-surface-container-low text-on-surface-variant/60"].join(" ")}
          disabled={!exportableDocuments.length || exporting}
          onClick={downloadBundle}
          type="button"
        >
          <span className="material-symbols-outlined text-[13px]">{exporting ? "progress_activity" : "folder_zip"}</span>
          {exporting ? "Preparing..." : "Documents ZIP"}
        </button>
        {canEditGeneratedCv ? (
          <button className={`${TRACKER_RESOURCE_BUTTON_CLASS} bg-surface-container-low text-on-surface hover:bg-surface-container-high`} onClick={openGeneratedCvEditor} type="button">
            <span className="material-symbols-outlined text-[13px]">edit_document</span>
            Edit CV
          </button>
        ) : null}
        {item.review_id ? (
          <Link className={`${TRACKER_RESOURCE_BUTTON_CLASS} bg-surface-container-low text-on-surface hover:bg-surface-container-high`} to={`/tracker/${encodeURIComponent(item.review_id)}/ats?return=${encodeURIComponent("/tracker")}`}>
            <span className="material-symbols-outlined text-[13px]">fact_check</span>
            ATS
          </Link>
        ) : null}
      </div>
      {atsSummary ? (
        <div className="rounded-xl border border-outline-variant/15 bg-surface-container-low px-3 py-2 text-[11px] leading-5 text-on-surface-variant">
          <div className="flex flex-wrap items-center gap-2">
            <span className={["rounded-full px-2.5 py-0.5 font-semibold", atsSummary.badgeClass].join(" ")}>{atsSummary.label}</span>
            {atsSummary.bestScore !== null && atsSummary.targetScore !== null ? <span>{atsSummary.bestScore}% / {atsSummary.targetScore}%</span> : null}
          </div>
          {atsSummary.stopReason ? <div className="mt-1">Result: {atsSummary.stopReason}</div> : null}
        </div>
      ) : null}
      <ApplicationWarnings compact warnings={item.application_warnings} />
      {feedback.message ? <div className="text-xs text-primary">{feedback.message}</div> : null}
      {feedback.error ? <div className="text-xs text-error">{feedback.error}</div> : null}
    </div>
  );
}
function TrackerNotesCell({ item, onUpdate, updating }) {
  const [note, setNote] = useState(item.notes || "");
  const [editing, setEditing] = useState(false);
  const isBusy = updating === item.review_id;
  const isDirty = note !== (item.notes || "");

  useEffect(() => { setNote(item.notes || ""); }, [item.notes]);

  async function saveNote() {
    if (!isDirty) return;
    await onUpdate(item.review_id, { notes: note });
    setEditing(false);
  }

  if (!editing) {
    return (
      <div className="min-w-44 max-w-64">
        <p className="line-clamp-2 text-xs leading-5 text-on-surface-variant">{item.notes || "No notes yet."}</p>
        <button className="mt-2 rounded-full bg-surface-container-low px-3 py-1 text-xs font-semibold text-primary transition-colors hover:bg-primary/10" disabled={isBusy} onClick={() => setEditing(true)} type="button">
          {item.notes ? "Edit note" : "Add note"}
        </button>
      </div>
    );
  }

  return (
    <div className="min-w-56 space-y-2">
      <textarea className="min-h-20 w-full rounded-xl border border-outline-variant/20 bg-surface px-3 py-2 text-xs text-on-surface" disabled={isBusy} onChange={(event) => setNote(event.target.value)} placeholder="Add notes" value={note} />
      <div className="flex flex-wrap gap-2">
        <button className="rounded-full bg-primary/10 px-3 py-1.5 text-xs font-semibold text-primary transition-colors hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-50" disabled={!isDirty || isBusy} onClick={saveNote} type="button">
          {isBusy ? "Saving..." : "Save"}
        </button>
        <button className="rounded-full bg-surface-container-low px-3 py-1.5 text-xs font-semibold text-on-surface-variant transition-colors hover:bg-surface-container" onClick={() => { setNote(item.notes || ""); setEditing(false); }} type="button">
          Cancel
        </button>
      </div>
    </div>
  );
}
function TrackerTable({ filters, items, allItems, workspaceOptions, onAssistedApply, onFiltersChange, onUpdate, onDelete, onBulkDelete, updating, request }) {
  const [bulkMode, setBulkMode] = useState("all");
  const [bulkDate, setBulkDate] = useState("");
  const [bulkCompany, setBulkCompany] = useState("");
  const hasActiveFilters = Object.values(filters).some((value) => value && value !== "all");
  const bulkBusy = updating === "bulk-delete";
  const notAppliedItems = useMemo(() => items.filter((item) => statusKeyFromItem(item) === "not_applied"), [items]);
  const bulkDateOptions = useMemo(() => [...new Set(notAppliedItems.map(trackerAddedDateKey).filter(Boolean))].sort().reverse(), [notAppliedItems]);
  const bulkCompanyOptions = useMemo(() => [...new Set(notAppliedItems.map((item) => item.company || item.tracker_table_row?.company || "").filter(Boolean))].sort((a, b) => a.localeCompare(b)), [notAppliedItems]);
  const bulkCandidates = useMemo(() => {
    if (bulkMode === "date") {
      return bulkDate ? notAppliedItems.filter((item) => trackerAddedDateKey(item) === bulkDate) : [];
    }
    if (bulkMode === "company") {
      const company = normalizeCompanyName(bulkCompany);
      return company
        ? notAppliedItems.filter((item) => normalizeCompanyName(item.company || item.tracker_table_row?.company) === company)
        : [];
    }
    return notAppliedItems;
  }, [bulkCompany, bulkDate, bulkMode, notAppliedItems]);
  function updateFilter(field, value) { onFiltersChange((current) => ({ ...current, [field]: value })); }
  function clearFilters() { onFiltersChange(EMPTY_TRACKER_FILTERS); }
  async function deleteBulkCandidates() {
    if (!bulkCandidates.length || bulkBusy) return;
    const scopeLabel = bulkMode === "date" && bulkDate
      ? `added on ${formatDate(bulkDate)}`
      : bulkMode === "company" && bulkCompany.trim()
        ? `at ${bulkCompany.trim()}`
        : "matching the current filters";
    const confirmed = window.confirm(`Delete ${bulkCandidates.length} Not Applied job${bulkCandidates.length === 1 ? "" : "s"} ${scopeLabel}? This removes linked generated job data and cannot be undone.`);
    if (!confirmed) return;
    await onBulkDelete(bulkCandidates);
  }

  if (!allItems.length) {
    return (
      <div className="rounded-2xl border border-dashed border-outline-variant/30 bg-surface-container-lowest p-8 text-center">
        <span className="material-symbols-outlined text-3xl text-on-surface-variant">table</span>
        <p className="mt-3 text-sm font-semibold text-on-surface">No tracker rows yet.</p>
        <p className="mt-1 text-xs text-on-surface-variant">Applications and imported Gmail matches will appear here.</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-outline-variant/20 bg-surface-container-lowest shadow-sm">
      <div className="border-b border-outline-variant/10 bg-surface-container-low px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-on-surface">Tracker table</h2>
            <p className="mt-1 text-xs leading-5 text-on-surface-variant">Filter applications without hiding the underlying tracker rows.</p>
          </div>
          <div className="text-xs font-semibold text-on-surface-variant">Showing {items.length} of {allItems.length}</div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(220px,1.5fr)_repeat(3,minmax(150px,1fr))_auto]">
          <label className="relative">
            <span className="material-symbols-outlined pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-lg text-on-surface-variant">search</span>
            <input aria-label="Search tracker" className="w-full rounded-xl border border-outline-variant/20 bg-surface px-10 py-2.5 text-sm text-on-surface" onChange={(event) => updateFilter("query", event.target.value)} placeholder="Search role, company, location..." type="search" value={filters.query} />
          </label>
          <select aria-label="Filter tracker by status" className="w-full rounded-xl border border-outline-variant/20 bg-surface px-3 py-2.5 text-sm text-on-surface" onChange={(event) => updateFilter("status", event.target.value)} value={filters.status}>
            <option value="all">All statuses</option>
            {COLUMNS.map((column) => <option key={column.key} value={column.key}>{column.label}</option>)}
          </select>
          <select aria-label="Filter tracker by workspace" className="w-full rounded-xl border border-outline-variant/20 bg-surface px-3 py-2.5 text-sm text-on-surface" onChange={(event) => updateFilter("workspace", event.target.value)} value={filters.workspace}>
            <option value="all">All workspaces</option>
            {workspaceOptions.map((workspace) => <option key={workspace} value={workspace}>{workspace}</option>)}
          </select>
          <select aria-label="Filter tracker by source" className="w-full rounded-xl border border-outline-variant/20 bg-surface px-3 py-2.5 text-sm text-on-surface" onChange={(event) => updateFilter("source", event.target.value)} value={filters.source}>
            {TRACKER_SOURCE_FILTERS.map((source) => <option key={source.value} value={source.value}>{source.label}</option>)}
          </select>
          <button className="rounded-xl border border-outline-variant/20 bg-surface px-4 py-2.5 text-sm font-semibold text-on-surface-variant transition-colors hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-40" disabled={!hasActiveFilters} onClick={clearFilters} type="button">
            Clear
          </button>
        </div>
        {notAppliedItems.length ? (
          <div className="mt-4 flex flex-col gap-3 rounded-xl border border-error/15 bg-error/5 p-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:items-center">
              <span className="text-xs font-bold uppercase tracking-[0.14em] text-error">Bulk delete</span>
              <select aria-label="Bulk delete scope" className="rounded-lg border border-outline-variant/20 bg-surface px-3 py-2 text-sm text-on-surface" disabled={bulkBusy} onChange={(event) => setBulkMode(event.target.value)} value={bulkMode}>
                {BULK_DELETE_MODES.map((mode) => <option key={mode.value} value={mode.value}>{mode.label}</option>)}
              </select>
              {bulkMode === "date" ? (
                <select aria-label="Bulk delete added date" className="rounded-lg border border-outline-variant/20 bg-surface px-3 py-2 text-sm text-on-surface" disabled={bulkBusy} onChange={(event) => setBulkDate(event.target.value)} value={bulkDate}>
                  <option value="">Select date</option>
                  {bulkDateOptions.map((date) => <option key={date} value={date}>{formatDate(date)}</option>)}
                </select>
              ) : null}
              {bulkMode === "company" ? (
                <>
                  <input aria-label="Bulk delete company name" className="min-w-0 rounded-lg border border-outline-variant/20 bg-surface px-3 py-2 text-sm text-on-surface sm:w-64" disabled={bulkBusy} list="tracker-bulk-company-options" onChange={(event) => setBulkCompany(event.target.value)} placeholder="Exact company name" type="text" value={bulkCompany} />
                  <datalist id="tracker-bulk-company-options">
                    {bulkCompanyOptions.map((company) => <option key={company} value={company} />)}
                  </datalist>
                </>
              ) : null}
            </div>
            <button className="inline-flex items-center justify-center gap-2 rounded-lg bg-error px-4 py-2 text-sm font-semibold text-on-error transition-colors hover:bg-error/90 disabled:cursor-not-allowed disabled:opacity-50" disabled={!bulkCandidates.length || bulkBusy} onClick={deleteBulkCandidates} type="button">
              <span className="material-symbols-outlined text-base">{bulkBusy ? "progress_activity" : "delete"}</span>
              {bulkBusy ? "Deleting..." : `Delete ${bulkCandidates.length}`}
            </button>
          </div>
        ) : null}
      </div>
      {items.length ? (
        <div className="overflow-x-auto">
          <table className="tracker-table min-w-[1180px] w-full table-fixed border-collapse text-left text-sm">
            <thead className="bg-surface-container-low text-[11px] uppercase tracking-[0.14em] text-on-surface-variant">
              <tr>
                <th className="w-36 px-4 py-3">Status</th>
                <th className="w-56 px-4 py-3">Company</th>
                <th className="w-72 px-4 py-3">Role</th>
                <th className="w-44 px-4 py-3">Location</th>
                <th className="w-36 px-4 py-3">Applied</th>
                <th className="w-72 px-4 py-3">Resources</th>
                <th className="w-28 px-4 py-3">Priority</th>
                <th className="w-64 px-4 py-3">Notes</th>
                <th className="w-24 px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {items.map((item) => {
                const row = item.tracker_table_row || {};
                return (
                  <tr className="tracker-table__row align-top transition-colors hover:bg-surface-container-low/70" id={`review-${item.review_id}`} key={item.review_id}>
                    <td className="px-4 py-4"><StatusDropdown current={statusKeyFromItem(item)} disabled={updating === item.review_id} onSelect={(nextStatus) => onUpdate(item.review_id, { tracker_status: nextStatus })} /></td>
                    <td className="max-w-56 px-4 py-4">
                      <div className="font-semibold text-on-surface">{item.company || row.company || "Unknown company"}</div>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-on-surface-variant">
                        <span>{item.workspace_name || "Tracker"}</span>
                        <span className="rounded-full bg-surface-container px-2 py-0.5 font-semibold">{sourceLabelForItem(item)}</span>
                      </div>
                    </td>
                    <td className="max-w-72 px-4 py-4">
                      <div className="font-medium text-on-surface">{item.title || row.title || "Untitled role"}</div>
                      {row.keyword ? <div className="mt-1 text-xs text-on-surface-variant">Keyword: {row.keyword}</div> : null}
                    </td>
                    <td className="max-w-52 px-4 py-4 text-on-surface-variant">{item.location || row.location_raw || "Not set"}</td>
                    <td className="px-4 py-4 text-on-surface-variant">{formatDate(item.application_date || row.application_date || item.run_finished_at) || "Not set"}</td>
                    <td className="px-4 py-4"><TrackerResourceCell item={item} onAssistedApply={onAssistedApply} request={request} /></td>
                    <td className="px-4 py-4 text-on-surface-variant">{item.priority_rank || row.priority_rank || row.priority_tier || "Not set"}</td>
                    <td className="px-4 py-4"><TrackerNotesCell item={item} onUpdate={onUpdate} updating={updating} /></td>
                    <td className="px-4 py-4">
                      <button className="rounded-full bg-error/10 px-3 py-1.5 text-xs font-semibold text-error transition-colors hover:bg-error/20 disabled:cursor-not-allowed disabled:opacity-50" disabled={updating === item.review_id} onClick={() => onDelete(item)} type="button">
                        Delete
                      </button>
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
          <button className="mt-3 rounded-full bg-primary/10 px-4 py-2 text-xs font-semibold text-primary transition-colors hover:bg-primary/20" onClick={clearFilters} type="button">Clear filters</button>
        </div>
      )}
    </div>
  );
}
function KanbanColumn({ colDef, cards, onAssistedApply, onDelete, onUpdate, updating }) {
  return (
    <div className="flex min-w-[280px] flex-1 flex-col">
      <div className={["mb-4 flex items-center justify-between rounded-xl border px-4 py-3", colDef.border].join(" ")}>
        <div className="flex items-center gap-2"><span className={["material-symbols-outlined text-xl", colDef.accent].join(" ")}>{colDef.icon}</span><span className="font-semibold text-on-surface">{colDef.label}</span></div>
        <span className={["min-w-[24px] rounded-full px-2 py-0.5 text-center text-xs font-bold", colDef.badge].join(" ")}>{cards.length}</span>
      </div>
      <div className="flex flex-col gap-3">
        {cards.length === 0 ? <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-outline-variant/20 py-10 text-center text-sm text-on-surface-variant/50"><span className="material-symbols-outlined mb-2 text-3xl opacity-30">{colDef.icon}</span>No jobs here yet</div> : cards.map((item) => <TrackerCard item={item} key={item.review_id} onAssistedApply={onAssistedApply} onDelete={onDelete} onUpdate={onUpdate} updating={updating} />)}
      </div>
    </div>
  );
}

function buildEmailFormState(integration) {
  const config = integration?.config || {};
  return {
    folder: config.folder || "INBOX",
    emailSyncStartDate: config.email_sync_start_date || config.emailSyncStartDate || "",
  };
}

function EmailIntegrationPanel({
  integration, busy, onStartGoogle, onRefreshIntegration, onSaveSettings, onSync,
  onApproveDetections, onDismissDetections, onDelete, lastSyncResult,
}) {
  const config = integration?.config || {};
  const [form, setForm] = useState(() => buildEmailFormState(integration));
  const [feedback, setFeedback] = useState({ message: "", error: "" });

  useEffect(() => { setForm(buildEmailFormState(integration)); }, [integration]);

  const syncSummary = lastSyncResult?.summary || config.last_sync_summary || null;
  const reviewDetections = config.pending_detections || [];
  const pendingDetectionCount = Number(config.pending_detection_count || reviewDetections.length || 0);
  const detectionActionBusy = busy === "approve-detections" || busy === "dismiss-detections";
  const syncStatusLabel = config.email_sync_status === "syncing" ? "Syncing…" : config.email_sync_status === "success" ? "Sync complete" : config.email_sync_status === "error" ? "Sync failed" : "";

  function updateField(field, value) { setForm((c) => ({ ...c, [field]: value })); }

  async function handleSaveSettings(event) {
    event.preventDefault();
    setFeedback({ message: "", error: "" });
    if (!form.emailSyncStartDate) { setFeedback({ message: "", error: "Please select a start date before saving." }); return; }
    const today = new Date().toISOString().slice(0, 10);
    if (form.emailSyncStartDate > today) { setFeedback({ message: "", error: "Start date must not be in the future." }); return; }
    try {
      await onSaveSettings({ provider_id: "gmail", auth_strategy: "google_oauth", folder: form.folder, email_sync_start_date: form.emailSyncStartDate, email_sync_enabled: true });
      setFeedback({ message: "Sync settings updated. Inbox sync is now enabled.", error: "" });
    } catch (saveError) { setFeedback({ message: "", error: saveError.message || "Unable to update sync settings." }); }
  }

  async function handleGoogleConnect() {
    setFeedback({ message: "", error: "" });
    try {
      const startPayload = await onStartGoogle({ folder: form.folder, email_sync_start_date: form.emailSyncStartDate });
      const authorizationUrl = startPayload?.authorization_url || "";
      if (!authorizationUrl) throw new Error("Google authorization could not be started.");
      const popup = window.open(authorizationUrl, "tracker-google-oauth", "popup=yes,width=520,height=720");
      if (!popup) { window.location.assign(authorizationUrl); return; }
      setFeedback({ message: "Finish Google sign-in in the popup. The tracker will refresh automatically once access is granted.", error: "" });
      const timeoutAt = Date.now() + 90_000;
      while (Date.now() < timeoutAt) {
        await new Promise((r) => window.setTimeout(r, 1500));
        const refreshed = await onRefreshIntegration();
        const refreshedConfig = refreshed?.config || {};
        if (refreshedConfig.connected) { try { popup.close(); } catch {} setFeedback({ message: `${refreshedConfig.email_address || "Your Gmail inbox"} is now connected.`, error: "" }); return; }
        if (refreshedConfig.last_error) throw new Error(refreshedConfig.last_error);
        if (popup.closed && refreshedConfig.authorization_state !== "authorization_url_created") break;
      }
      setFeedback({ message: "Waiting for Google authorization to finish. If you already approved access, refresh once.", error: "" });
    } catch (connectError) { setFeedback({ message: "", error: connectError.message || "Unable to start Google authorization." }); }
  }

  async function handleSync() {
    setFeedback({ message: "", error: "" });
    try {
      const result = await onSync();
      const summary = result?.result?.summary || {};
      setFeedback({ message: `Sync complete. ${summary.updated_reviews || 0} tracker card${summary.updated_reviews === 1 ? "" : "s"} updated.`, error: "" });
    } catch (syncError) { setFeedback({ message: "", error: syncError.message || "Unable to sync inbox." }); }
  }

  async function handleDelete() {
    setFeedback({ message: "", error: "" });
    try { await onDelete(); setForm(buildEmailFormState({})); setFeedback({ message: "Inbox connection removed.", error: "" }); }
    catch (deleteError) { setFeedback({ message: "", error: deleteError.message || "Unable to disconnect inbox." }); }
  }

  async function approveDetection(detection) {
    setFeedback({ message: "", error: "" });
    try { await onApproveDetections([detection]); setFeedback({ message: "Gmail detection imported into the tracker.", error: "" }); }
    catch (approveError) { setFeedback({ message: "", error: approveError.message || "Unable to approve this detection." }); }
  }

  async function dismissDetection(detection) {
    setFeedback({ message: "", error: "" });
    try { await onDismissDetections([detection]); setFeedback({ message: "Detection dismissed and removed from review.", error: "" }); }
    catch (dismissError) { setFeedback({ message: "", error: dismissError.message || "Unable to dismiss this detection." }); }
  }

  const lastSyncedDisplay = config.last_email_sync_at || config.last_sync_at;

  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-sm">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-2xl">
          <h2 className="font-headline text-2xl font-bold tracking-tight text-on-surface">Email Inbox Sync</h2>
          <p className="mt-2 text-sm leading-7 text-on-surface-variant">Connect Gmail with Google authorization so the tracker can pull confirmations, interview invites, and rejections into the board when you run inbox sync.</p>
          <p className="mt-3 rounded-2xl bg-surface-container px-4 py-3 text-xs leading-6 text-on-surface-variant"><span className="font-semibold text-on-surface">Secure access:</span> the tracker stores OAuth tokens and reads Gmail in read-only mode. It does not ask for your account password.</p>
          {config.email_address && (<p className="mt-3 rounded-2xl bg-surface-container px-4 py-3 text-xs leading-6 text-on-surface-variant"><span className="font-semibold text-on-surface">Connected account:</span> {config.email_address}</p>)}
          {syncStatusLabel && (<p className="mt-3 rounded-2xl bg-primary/5 px-4 py-3 text-xs leading-6 text-primary font-semibold">{syncStatusLabel}</p>)}
          {lastSyncedDisplay && config.connected && (<p className="mt-2 rounded-2xl bg-surface-container px-4 py-3 text-xs leading-6 text-on-surface-variant">Last synced: {formatDateTime(lastSyncedDisplay)}</p>)}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60" disabled={!config.oauth_available || busy === "authorize"} onClick={handleGoogleConnect} type="button">
            <span className="material-symbols-outlined text-[18px]">{busy === "authorize" ? "progress_activity" : "login"}</span>
            {busy === "authorize" ? "Opening Google..." : config.connected ? "Reconnect Google" : "Connect with Google"}
          </button>
          <button className="flex items-center gap-2 rounded-lg bg-primary/10 px-4 py-2.5 text-sm font-medium text-primary transition-colors hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-60" disabled={!config.connected || busy === "sync"} onClick={handleSync} type="button">
            <span className="material-symbols-outlined text-[18px]">{busy === "sync" ? "progress_activity" : "mark_email_read"}</span>
            {busy === "sync" ? "Syncing..." : syncStatusLabel === "Syncing…" ? "Syncing…" : "Sync Inbox"}
          </button>
          <button className="rounded-lg border border-outline-variant/20 px-4 py-2.5 text-sm font-medium text-on-surface-variant transition-colors hover:bg-surface-container-low disabled:cursor-not-allowed disabled:opacity-60" disabled={!config.connected || busy === "delete"} onClick={handleDelete} type="button">Disconnect</button>
        </div>
      </div>

      <form className="mt-6 grid gap-4 lg:grid-cols-2" onSubmit={handleSaveSettings}>
        <label className="block">
          <span className="mb-2 block text-sm font-semibold text-on-surface">Read emails starting from</span>
          <input className="w-full rounded-xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface" onChange={(event) => updateField("emailSyncStartDate", event.target.value)} type="date" value={form.emailSyncStartDate} max={new Date().toISOString().slice(0, 10)} />
          <span className="mt-2 block text-xs leading-6 text-on-surface-variant">Runr will scan matching emails received on or after this date.</span>
        </label>

        <label className="block">
          <span className="mb-2 block text-sm font-semibold text-on-surface">Folder</span>
          <input className="w-full rounded-xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface" onChange={(event) => updateField("folder", event.target.value)} placeholder="INBOX" type="text" value={form.folder} disabled={!config.connected} />
        </label>

        <div className="lg:col-span-2 rounded-2xl bg-surface-container px-4 py-3 text-xs leading-6 text-on-surface-variant">
          <span className="font-semibold text-on-surface">Automatic syncing:</span> Runr checks your connected inbox daily and after you log in.
        </div>

        <div className="lg:col-span-2">
          {feedback.error && (<div className="rounded-2xl border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">{feedback.error}</div>)}
          {feedback.message && (<div className="rounded-2xl border border-primary/20 bg-primary/5 px-4 py-3 text-sm text-primary">{feedback.message}</div>)}
          {config.last_error && !feedback.error && (<div className="rounded-2xl border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">Last sync error: {config.last_error}</div>)}
          {!config.oauth_available && (<div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm text-amber-600">Google OAuth is not configured on the backend yet. Set the tracker Google client ID and secret first.</div>)}
        </div>

        <div className="flex flex-wrap items-center gap-3 lg:col-span-2">
          <button className="rounded-lg bg-surface-container-high px-5 py-3 text-sm font-medium text-on-surface shadow-sm transition-all hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-60" disabled={busy === "save"} type="submit">{busy === "save" ? "Saving..." : "Save Sync Settings"}</button>
          {config.connected_at && (<span className="text-sm text-on-surface-variant">Connected {formatDate(config.connected_at)}</span>)}
          {lastSyncedDisplay && (<span className="text-sm text-on-surface-variant">Last synced {formatDateTime(lastSyncedDisplay)}</span>)}
          {config.authorization_state === "authorization_url_created" && !config.connected && (<span className="text-sm text-primary">Awaiting Google authorization</span>)}
        </div>
      </form>

      {syncSummary && (<div className="mt-6 flex gap-3 overflow-x-auto pb-1">{[{ label: "Checked", value: syncSummary.checked_messages || 0 }, { label: "Processed", value: syncSummary.processed_messages || 0 }, { label: "Updated", value: syncSummary.updated_reviews || 0 }, { label: "Unmatched", value: syncSummary.unmatched_messages || 0 }, { label: "Needs review", value: pendingDetectionCount }].map((item) => (<div className="flex min-w-[180px] flex-1 items-center justify-between gap-4 rounded-2xl border border-outline-variant/20 bg-surface-container px-4 py-3" key={item.label}><div className="min-w-0 whitespace-nowrap text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">{item.label}</div><div className="shrink-0 text-2xl font-bold text-on-surface">{item.value}</div></div>))}</div>)}

      {lastSyncResult?.matched_updates?.length && (<div className="mt-6 rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4"><h3 className="text-sm font-semibold text-on-surface">Automatic Tracker Updates</h3><p className="mt-1 text-xs leading-6 text-on-surface-variant">High-confidence Gmail matches update the tracker immediately when the sender and message content look job-related.</p><div className="mt-3 space-y-2">{lastSyncResult.matched_updates.slice(0, 5).map((match) => (<div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-surface px-3 py-2 text-sm" key={`${match.review_id}-${match.message_id}`}><div><span className="font-medium text-on-surface">{match.company || "Unknown Company"}</span> <span className="text-on-surface-variant">- {match.title || "Untitled role"}</span></div><div className="text-on-surface-variant">{match.from_status || "not_applied"} → {match.to_status}</div></div>))}</div></div>)}

      {reviewDetections.length ? (<div className="mt-6 rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-sm font-semibold text-on-surface">Needs Review</h3><p className="mt-1 text-xs leading-6 text-on-surface-variant">Approve messages that should update the tracker or import an external application. Dismiss anything that is too weak or irrelevant.</p></div><span className="rounded-full bg-surface px-3 py-1 text-xs font-semibold text-on-surface-variant">{pendingDetectionCount} pending</span></div><div className="mt-4 space-y-3">{reviewDetections.slice(0, 12).map((detection) => { const detectedCompany = detection.detected_application.company || "Company not matched"; const detectedTitle = detection.detected_application.title || "Title not detected"; const isMatchedTrackerCard = Boolean(detection.metadata?.review_id); return (<article className="rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3" key={detection.detection_id}><div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between"><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><span className="font-medium text-on-surface">{detectedCompany}{detectedTitle ? ` - ${detectedTitle}` : ""}</span><span className="rounded-full bg-surface-container px-2 py-1 text-xs text-on-surface-variant">{detection.status.suggested_application_status} · {detection.status.confidence}</span><span className="rounded-full bg-primary/10 px-2 py-1 text-xs font-medium text-primary">{isMatchedTrackerCard ? "Matched tracker card" : "New external application"}</span></div><div className="mt-2 text-xs leading-6 text-on-surface-variant">{detection.source_email.subject || "No subject"} · {detection.source_email.from_address || "Unknown sender"}</div><div className="text-xs leading-6 text-on-surface-variant">{formatDateTime(detection.source_email.sent_at)}</div>{detection.status.evidence?.length ? (<div className="mt-3 flex flex-wrap gap-2">{detection.status.evidence.map((e) => (<span className="rounded-full bg-surface-container-high px-2.5 py-1 text-[11px] font-medium text-on-surface-variant" key={`${detection.detection_id}-${e}`}>{e}</span>))}</div>) : null}</div><div className="flex shrink-0 flex-wrap gap-2"><button className="rounded-lg bg-primary/10 px-3 py-2 text-xs font-semibold text-primary transition hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-60" disabled={detectionActionBusy} onClick={() => approveDetection(detection)} type="button">Import / approve</button><button className="rounded-lg bg-surface-container-high px-3 py-2 text-xs font-semibold text-on-surface transition hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-60" disabled={detectionActionBusy} onClick={() => dismissDetection(detection)} type="button">Dismiss</button></div></div></article>); })}</div></div>) : syncSummary ? (<div className="mt-6 rounded-2xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 text-sm text-on-surface-variant">No Gmail detections are waiting for review.</div>) : null}
    </section>
  );
}

function InboxSyncControl(props) {
  const [expanded, setExpanded] = useState(false);
  const config = props.integration?.config || {};
  const pendingCount = Number(config.pending_detection_count || config.pending_detections?.length || 0);
  const statusLabel = config.connected ? `Connected${config.email_address ? ` as ${config.email_address}` : ""}` : "Not connected";

  return (
    <section className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className={["material-symbols-outlined rounded-full p-2", config.connected ? "bg-primary/10 text-primary" : "bg-surface-container text-on-surface-variant"].join(" ")}>mark_email_read</span>
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-on-surface">Inbox Sync</h2>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-on-surface-variant">
              <span>{statusLabel}</span>
              {(config.last_email_sync_at || config.last_sync_at) && <span>Last sync {formatDateTime(config.last_email_sync_at || config.last_sync_at)}</span>}
              {pendingCount ? <span>{pendingCount} awaiting review</span> : null}
            </div>
          </div>
        </div>
        <button aria-expanded={expanded} className="inline-flex items-center gap-2 rounded-xl bg-surface-container-low px-4 py-2 text-sm font-semibold text-primary transition-colors hover:bg-surface-container-high" onClick={() => setExpanded((c) => !c)} type="button">
          {expanded ? "Close" : config.connected ? "Configure" : "Connect"}<span className="material-symbols-outlined text-[18px]">{expanded ? "expand_less" : "expand_more"}</span>
        </button>
      </div>
      {expanded && (<div className="border-t border-outline-variant/10 p-4"><EmailIntegrationPanel {...props} /></div>)}
    </section>
  );
}

export default function TrackerPage() {
  const { request } = useSession();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [deleteFeedback, setDeleteFeedback] = useState({ message: "", error: "" });
  const [discoveringId, setDiscoveringId] = useState("");
  const [discoveryModal, setDiscoveryModal] = useState(EMPTY_DISCOVERY_MODAL);
  const [discoveryFeedback, setDiscoveryFeedback] = useState(EMPTY_DISCOVERY_FEEDBACK);
  const [assistedApplyRow, setAssistedApplyRow] = useState(null);
  const [trackerFilters, setTrackerFilters] = useState(() => trackerFiltersFromSearchParams(searchParams));
  const { items, loading, error, refresh, updating, updateCard, deleteCard, bulkDeleteCards, emailIntegration, integrationBusy, lastSyncResult, refreshEmailIntegration, startGoogleEmailIntegration, updateEmailIntegrationSettings, syncEmailIntegration, approveEmailDetections, dismissEmailDetections, deleteEmailIntegration } = useTracker();
  const { data: settingsData } = useApiResource(() => request("/settings"), [request]);
  const totalCards = items.length;
  const filteredTrackerItems = useMemo(() => items.filter((item) => trackerItemMatchesFilters(item, trackerFilters)), [items, trackerFilters]);
  const workspaceOptions = useMemo(() => [...new Set(items.map((item) => item.workspace_name).filter(Boolean))].sort(), [items]);
  const statusCounts = useMemo(() => { const visible = items.filter((i) => trackerItemMatchesFilters(i, trackerFilters, { ignoreStatus: true })); return Object.fromEntries(COLUMNS.map((c) => [c.key, visible.filter((i) => statusKeyFromItem(i) === c.key).length])); }, [items, trackerFilters]);

  useEffect(() => { const next = new URLSearchParams(); Object.entries(trackerFilters).forEach(([k, v]) => { if (v && v !== "all") next.set(k, v); }); if (next.toString() !== searchParams.toString()) setSearchParams(next, { replace: true }); }, [searchParams, setSearchParams, trackerFilters]);
  useEffect(() => { if (loading || !location.hash) return; const target = document.getElementById(decodeURIComponent(location.hash.slice(1))); target?.scrollIntoView({ block: "center" }); }, [items, loading, location.hash]);

  async function handleDeleteCard(item) { const confirmed = window.confirm(`Delete ${item.title || "this job"}? This removes it from the tracker${item.external_application ? "" : " and linked generated job data"}.`); if (!confirmed) return; setDeleteFeedback({ message: "", error: "" }); try { await deleteCard(item); setDeleteFeedback({ message: "Deleted job.", error: "" }); } catch (e) { setDeleteFeedback({ message: "", error: e.message || "Unable to delete this job." }); } }
  async function handleBulkDeleteCards(itemsToDelete) { setDeleteFeedback({ message: "", error: "" }); try { const result = await bulkDeleteCards(itemsToDelete); setDeleteFeedback({ message: `Deleted ${result.deleted_count || 0} job${result.deleted_count === 1 ? "" : "s"}.`, error: "" }); } catch (e) { setDeleteFeedback({ message: "", error: e.message || "Unable to delete these jobs." }); } }
  function closeDiscoveryModal() { setDiscoveryModal(EMPTY_DISCOVERY_MODAL); setDiscoveryFeedback(EMPTY_DISCOVERY_FEEDBACK); }
  async function handleDiscoverContacts(item) { if (!item?.run_id || !item?.job_id) { setDeleteFeedback({ message: "", error: "This tracker row is missing the run or job reference needed for contact discovery." }); return; } setDeleteFeedback({ message: "", error: "" }); setDiscoveringId(item.review_id || item.job_id || `${item.run_id}:${item.job_id}`); try { const payload = await request("/outreach/target-contact-discovery", { method: "POST", body: { run_id: item.run_id, job_id: item.job_id } }); setDiscoveryModal({ open: true, item, payload }); setDiscoveryFeedback(EMPTY_DISCOVERY_FEEDBACK); } catch (e) { setDeleteFeedback({ message: "", error: e.message || "Unable to generate target contact discovery right now." }); } finally { setDiscoveringId(""); } }
  async function copyDiscoveryText(text, successMessage) { try { await navigator.clipboard.writeText(String(text || "")); setDiscoveryFeedback({ message: successMessage, error: "" }); } catch (e) { setDiscoveryFeedback({ message: "", error: e.message || "Unable to copy this text." }); } }

  return (
    <div className="space-y-8">
      <header className="flex items-end justify-between gap-4"><div><h1 className="font-headline text-[2.25rem] font-extrabold leading-tight tracking-tight text-on-surface">Application Tracker</h1><p className="mt-1 text-sm text-on-surface-variant">{totalCards > 0 ? `Tracking ${totalCards} application${totalCards === 1 ? "" : "s"} across all stages.` : "Track applications here once they are active."}</p></div><button className="flex items-center gap-2 rounded bg-surface-container-high px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-surface-container-low active:scale-[0.98]" onClick={() => refresh().catch(() => undefined)} type="button"><span className="material-symbols-outlined text-sm">refresh</span>Refresh</button></header>
      {loading && (<div className="flex items-center gap-3 rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-6 py-4 text-sm text-on-surface-variant"><span className="material-symbols-outlined animate-spin">progress_activity</span>Loading tracker...</div>)}
      {error && !loading && (<div className="flex items-center gap-3 rounded-xl border border-error/20 bg-error/5 px-6 py-4 text-sm text-error"><span className="material-symbols-outlined">error</span>{error}</div>)}
      {!loading && !error && (deleteFeedback.message || deleteFeedback.error) && (<div className={["flex items-center gap-3 rounded-xl border px-6 py-4 text-sm", deleteFeedback.error ? "border-error/20 bg-error/5 text-error" : "border-primary/20 bg-primary/5 text-primary"].join(" ")}><span className="material-symbols-outlined">{deleteFeedback.error ? "error" : "task_alt"}</span>{deleteFeedback.error || deleteFeedback.message}</div>)}
      {!loading && !error && (<InboxSyncControl busy={integrationBusy} integration={emailIntegration} lastSyncResult={lastSyncResult} onDelete={deleteEmailIntegration} onDismissDetections={dismissEmailDetections} onRefreshIntegration={refreshEmailIntegration} onSaveSettings={updateEmailIntegrationSettings} onApproveDetections={approveEmailDetections} onStartGoogle={startGoogleEmailIntegration} onSync={syncEmailIntegration} />)}
      {!loading && !error && (<div className="grid gap-3 md:grid-cols-4 xl:grid-cols-7">{COLUMNS.map((column) => { const selected = trackerFilters.status === column.key; return (<button aria-pressed={selected} className={["rounded-2xl border px-4 py-3 text-left transition-colors", selected ? `${column.border} bg-surface-container-low shadow-sm` : "border-outline-variant/20 bg-surface-container-lowest hover:bg-surface-container-low"].join(" ")} key={column.key} onClick={() => { setTrackerFilters((current) => ({ ...current, status: current.status === column.key ? "all" : column.key })); }} type="button"><div className="flex items-center justify-between gap-2"><span className="text-xs font-semibold text-on-surface-variant">{column.label}</span><span className={["rounded-full px-2 py-0.5 text-xs font-bold", column.badge].join(" ")}>{statusCounts[column.key] || 0}</span></div></button>); })}</div>)}

      {!loading && !error && (<TrackerTable allItems={items} filters={trackerFilters} items={filteredTrackerItems} onAssistedApply={setAssistedApplyRow} onBulkDelete={handleBulkDeleteCards} onDelete={handleDeleteCard} onFiltersChange={setTrackerFilters} onUpdate={updateCard} request={request} updating={updating} workspaceOptions={workspaceOptions} />)}
      {assistedApplyRow ? (
        <AssistedApplyLaunchDialog
          onClose={() => setAssistedApplyRow(null)}
          onLaunched={() => setDeleteFeedback({ message: "Assisted Apply package prepared. Review it in the employer tab before submitting.", error: "" })}
          profile={settingsData?.profile}
          request={request}
          row={assistedApplyRow}
        />
      ) : null}
    </div>
  );
}
