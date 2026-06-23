import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import CareerMemoryBuilderPage from "../components/careerMemoryBuilder/CareerMemoryBuilderPage";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import {
  buildCareerMemoryDraft,
  buildCareerMemoryPayload,
} from "../lib/careerMemoryWorkspace";
import { CV_STUDIO_ROUTE } from "../lib/cvStudio";
import { formatDateTime, labelize, statusTone } from "../lib/formatters";

const VIEW_LIBRARY = "library";
const VIEW_MEMORY = "memory";
const LEGACY_VIEW_CANVAS = "canvas";
const DEFAULT_UPLOAD_KIND = "uploaded_document";
const MASTER_CAREER_PROFILE_KIND = "master_career_profile";
const LEGACY_GENERAL_ASSET_KINDS = new Set([
  MASTER_CAREER_PROFILE_KIND,
  "motivation_letter",
]);
const CAREER_ASSET_KINDS = new Set([
  "workspace_cv",
  MASTER_CAREER_PROFILE_KIND,
  "uploaded_document",
  "certification",
  "recommendation_letter",
  "motivation_letter",
]);
const MEMORY_DEFAULTS = buildCareerMemoryDraft({});

function normalizeViewParam(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === VIEW_MEMORY || normalized === LEGACY_VIEW_CANVAS) {
    return VIEW_MEMORY;
  }
  return VIEW_LIBRARY;
}

const UPLOAD_KIND_OPTIONS = [
  { value: "workspace_cv", label: "Baseline CV" },
  { value: "uploaded_document", label: "Supporting Document" },
  { value: "certification", label: "Certification" },
  { value: "recommendation_letter", label: "Recommendation Letter" },
];

function matchesQuery(values, search) {
  const query = String(search || "").trim().toLowerCase();
  if (!query) {
    return true;
  }
  return values
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(query));
}

function triggerDownload(blob, fileName) {
  const objectUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(objectUrl);
}

function FilterSelect({ children, className = "", onChange, value }) {
  return (
    <select
      className={[
        "rounded-lg border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface",
        className,
      ].join(" ")}
      onChange={onChange}
      value={value}
    >
      {children}
    </select>
  );
}

function documentStatusValue(document) {
  return (
    String(
      document?.display_status ||
        (document?.final_export_blocked
          ? "export_blocked"
          : document?.status || document?.application_document?.status || "ready"),
    ).trim() || "ready"
  );
}

function documentStatusLabel(document) {
  const value = documentStatusValue(document);
  return value === "export_blocked" ? "Export Blocked" : labelize(value);
}

function assetKindLabel(assetKind) {
  const normalized = String(assetKind || "").trim().toLowerCase();
  if (normalized === "workspace_cv") return "Baseline CV";
  if (normalized === MASTER_CAREER_PROFILE_KIND) return "Legacy Master Career Profile";
  if (normalized === "uploaded_document") return "Supporting Document";
  if (normalized === "recommendation_letter") return "Recommendation Letter";
  if (normalized === "motivation_letter") return "Legacy Motivation Letter";
  return labelize(assetKind);
}

function buildDocumentGroupDescription(group) {
  if (group.group_kind === "application") {
    return [group.workspace_name, group.run_id].filter(Boolean).join(" | ");
  }
  if (group.group_kind === "run") {
    return [group.workspace_name, group.run_id].filter(Boolean).join(" | ");
  }
  return group.workspace_name || "Reusable candidate assets available across applications.";
}

export default function DocumentsPage() {
  const { request } = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeView, setActiveView] = useState(() => normalizeViewParam(searchParams.get("view")));
  const [documentFilters, setDocumentFilters] = useState({
    search: "",
    workspaceId: "",
    assetKind: "",
  });
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([]);
  const [uploadState, setUploadState] = useState({
    uploading: false,
    message: "",
    error: "",
  });
  const [uploadForm, setUploadForm] = useState({
    assetKind: DEFAULT_UPLOAD_KIND,
    workspaceId: "",
  });
  const [exportState, setExportState] = useState({
    exporting: false,
    message: "",
    error: "",
    gate: null,
  });
  const [requirementsReviewOpen, setRequirementsReviewOpen] = useState(false);
  const [memoryDraft, setMemoryDraft] = useState(MEMORY_DEFAULTS);
  const [memorySaveState, setMemorySaveState] = useState({
    saving: false,
    message: "",
    error: "",
  });
  const [memoryDirty, setMemoryDirty] = useState(false);

  const {
    data: documentsPayload,
    loading: documentsLoading,
    error: documentsError,
    refresh: refreshDocuments,
  } = useApiResource(() => request("/documents?limit=500", { timeoutMs: 10000 }), [request], {
    cacheKey: "documents:all",
    staleMs: 30000,
    backgroundRefresh: true,
  });
  const {
    data: settingsPayload,
    refresh: refreshSettings,
  } = useApiResource(() => request("/settings", { timeoutMs: 10000 }), [request], {
    cacheKey: "settings",
    staleMs: Infinity,
    backgroundRefresh: false,
  });
  const { data: workspacesPayload } = useApiResource(() => request("/workspaces?limit=100", { timeoutMs: 10000 }), [request], {
    cacheKey: "workspaces:list",
    staleMs: Infinity,
    backgroundRefresh: false,
  });

  const allDocuments = documentsPayload?.documents || [];
  const documentGroups = documentsPayload?.groups || [];
  const workspaces = workspacesPayload?.workspaces || [];

  useEffect(() => {
    if (!settingsPayload?.documents) {
      return;
    }
    setMemoryDraft(buildCareerMemoryDraft(settingsPayload.documents));
    setMemoryDirty(false);
  }, [settingsPayload?.documents]);

  useEffect(() => {
    if (!memoryDirty || activeView !== VIEW_MEMORY) return undefined;
    function confirmNavigation(event) {
      if (!window.confirm("You have unsaved Career Memory changes. Leave without saving them?")) {
        event.preventDefault();
      }
    }
    function confirmUnload(event) {
      event.preventDefault();
      event.returnValue = "";
    }
    window.addEventListener("runr:before-navigation", confirmNavigation);
    window.addEventListener("beforeunload", confirmUnload);
    return () => {
      window.removeEventListener("runr:before-navigation", confirmNavigation);
      window.removeEventListener("beforeunload", confirmUnload);
    };
  }, [activeView, memoryDirty]);

  useEffect(() => {
    const rawView = String(searchParams.get("view") || "").trim().toLowerCase();
    const requestedView = normalizeViewParam(rawView);
    setActiveView((current) => (current === requestedView ? current : requestedView));
    if (rawView === LEGACY_VIEW_CANVAS) {
      const next = new URLSearchParams(searchParams);
      next.set("view", VIEW_MEMORY);
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const workspaceOptions = useMemo(
    () =>
      workspaces.map((workspace) => ({
        value: workspace.id,
        label: workspace.name || workspace.id,
      })),
    [workspaces],
  );
  const assetDocuments = useMemo(
    () =>
      allDocuments.filter((item) => {
        const assetKind = String(item.asset_kind || "").trim().toLowerCase();
        return CAREER_ASSET_KINDS.has(assetKind) && String(item.source_origin || "") === "upload";
      }),
    [allDocuments],
  );
  const cvLikeAssets = useMemo(
    () =>
      assetDocuments.filter((item) => {
        const assetKind = String(item.asset_kind || "").trim().toLowerCase();
        return (
          assetKind === "workspace_cv" ||
          assetKind === "uploaded_document" ||
          assetKind === MASTER_CAREER_PROFILE_KIND
        );
      }),
    [assetDocuments],
  );
  const documentKindOptions = useMemo(
    () =>
      Array.from(
        new Map(
          assetDocuments
            .filter((item) => !LEGACY_GENERAL_ASSET_KINDS.has(String(item.asset_kind || "").trim().toLowerCase()))
            .map((item) => [
              String(item.asset_kind || ""),
              assetKindLabel(item.asset_kind || item.document_type),
            ]),
        ).entries(),
      ).map(([value, label]) => ({ value, label })),
    [assetDocuments],
  );
  const filteredDocuments = useMemo(
    () =>
      assetDocuments.filter((item) => {
        if (documentFilters.workspaceId && item.workspace_id !== documentFilters.workspaceId) {
          return false;
        }
        if (documentFilters.assetKind && item.asset_kind !== documentFilters.assetKind) {
          return false;
        }
        return matchesQuery(
          [
            item.display_name,
            item.group_label,
            item.kind_group_label,
            item.document_type,
            item.job_title,
            item.company,
            item.workspace_name,
            item.run_id,
            item.relative_path,
            item.asset_kind,
            documentStatusLabel(item),
          ],
          documentFilters.search,
        );
      }),
    [assetDocuments, documentFilters],
  );

  const selectedDocuments = useMemo(
    () => assetDocuments.filter((item) => selectedDocumentIds.includes(item.document_id)),
    [assetDocuments, selectedDocumentIds],
  );
  const selectedBlockedDocuments = useMemo(
    () => selectedDocuments.filter((item) => item.final_export_blocked),
    [selectedDocuments],
  );
  const remediationRequirements = useMemo(
    () =>
      Array.from(
        new Set(
          [
            ...(exportState.gate?.missing_requirements || []),
            ...selectedBlockedDocuments.flatMap(
              (document) => document.ats_export_gate?.missing_requirements || [],
            ),
          ].filter(Boolean),
        ),
      ),
    [exportState.gate?.missing_requirements, selectedBlockedDocuments],
  );
  const masterCareerProfileAsset = useMemo(
    () =>
      assetDocuments.find(
        (item) => String(item.asset_id || "") === String(memoryDraft.masterProfileAssetId || ""),
      ) || null,
    [assetDocuments, memoryDraft.masterProfileAssetId],
  );
  const visibleDocumentSections = useMemo(() => {
    const groupMetaById = new Map(
      documentGroups.map((group, index) => [group.group_id, { ...group, sortIndex: index }]),
    );
    const groupedDocuments = new Map();
    filteredDocuments.forEach((item) => {
      const groupId = item.group_id || item.document_id;
      const groupMeta = groupMetaById.get(groupId) || {};
      const existing = groupedDocuments.get(groupId);
      if (existing) {
        existing.documents.push(item);
        if ((item.created_at || "") > (existing.latest_created_at || "")) {
          existing.latest_created_at = item.created_at || "";
        }
        return;
      }
      groupedDocuments.set(groupId, {
        group_id: groupId,
        group_label: item.group_label || groupMeta.group_label || "Documents",
        group_kind: item.group_kind || groupMeta.group_kind || "shared_library",
        workspace_id: item.workspace_id || groupMeta.workspace_id || "",
        workspace_name: item.workspace_name || groupMeta.workspace_name || "",
        run_id: item.run_id || groupMeta.run_id || "",
        job_id: item.job_id || groupMeta.job_id || "",
        job_title: item.job_title || groupMeta.job_title || "",
        company: item.company || groupMeta.company || "",
        latest_created_at: item.created_at || groupMeta.latest_created_at || "",
        documents: [item],
        sortIndex: groupMeta.sortIndex ?? Number.MAX_SAFE_INTEGER,
      });
    });
    const priority = {
      application: 0,
      run: 1,
      workspace_library: 2,
      shared_library: 3,
    };
    return Array.from(groupedDocuments.values()).sort((left, right) => {
      const leftPriority = priority[left.group_kind] ?? 9;
      const rightPriority = priority[right.group_kind] ?? 9;
      if (leftPriority !== rightPriority) {
        return leftPriority - rightPriority;
      }
      if ((left.sortIndex ?? Number.MAX_SAFE_INTEGER) !== (right.sortIndex ?? Number.MAX_SAFE_INTEGER)) {
        return (left.sortIndex ?? Number.MAX_SAFE_INTEGER) - (right.sortIndex ?? Number.MAX_SAFE_INTEGER);
      }
      if ((left.latest_created_at || "") !== (right.latest_created_at || "")) {
        return String(right.latest_created_at || "").localeCompare(String(left.latest_created_at || ""));
      }
      return String(left.group_label || "").localeCompare(String(right.group_label || ""));
    });
  }, [documentGroups, filteredDocuments]);

  useEffect(() => {
    if (!exportState.gate) {
      setRequirementsReviewOpen(false);
    }
  }, [exportState.gate]);

  function toggleSelection(setter, currentIds, id) {
    setter(
      currentIds.includes(id) ? currentIds.filter((item) => item !== id) : [...currentIds, id],
    );
  }

  async function downloadFile(path, fileName) {
    const blob = await request(path, { responseType: "blob" });
    triggerDownload(blob, fileName);
  }

  async function downloadDocument(document) {
    try {
      await downloadFile(document.download_url, document.display_name || "document");
    } catch (downloadError) {
      if (downloadError.code === "ats_export_blocked") {
        setSelectedDocumentIds([document.document_id]);
        setExportState({
          exporting: false,
          message: "",
          error: downloadError.message,
          gate: downloadError.details?.gate || null,
        });
        return;
      }
      throw downloadError;
    }
  }

  async function uploadDocument(file) {
    setUploadState({ uploading: true, message: "", error: "" });
    try {
      const formData = new FormData();
      formData.append("document_file", file);
      const params = new URLSearchParams();
      params.set("asset_kind", uploadForm.assetKind);
      params.set("display_name", file.name);
      if (uploadForm.workspaceId) {
        params.set("workspace_id", uploadForm.workspaceId);
      }
      const response = await request(`/documents/upload?${params.toString()}`, {
        method: "POST",
        body: formData,
      });
      if (response?.status_url) {
        let extractionReady = false;
        setUploadState({
          uploading: true,
          message: `Uploaded ${file.name}. Extracting searchable text...`,
          error: "",
        });
        for (let attempt = 0; attempt < 80; attempt += 1) {
          await new Promise((resolve) => window.setTimeout(resolve, 1500));
          const processing = await request(response.status_url);
          if (processing.status === "ready") {
            extractionReady = true;
            break;
          }
          if (processing.status === "failed") {
            throw new Error(processing.error || "Text extraction failed.");
          }
        }
        if (!extractionReady) {
          throw new Error("Text extraction is still processing. Refresh Career Assets in a moment.");
        }
      }
      await refreshDocuments().catch(() => undefined);
      setUploadState({
        uploading: false,
        message: `Uploaded ${file.name} to Career Assets.`,
        error: "",
      });
      return response?.asset || null;
    } catch (uploadError) {
      await refreshDocuments().catch(() => undefined);
      setUploadState({
        uploading: false,
        message: "",
        error: uploadError.message || "Unable to upload document.",
      });
      return null;
    }
  }

  function updateMemoryField(field, value) {
    setMemoryDraft((current) => ({ ...current, [field]: value }));
    setMemoryDirty(true);
    setMemorySaveState((current) => ({ ...current, message: "", error: "" }));
  }

  async function saveCareerMemory() {
    setMemorySaveState({ saving: true, message: "", error: "" });
    try {
      await request("/settings", {
        method: "PUT",
        body: {
          documents: buildCareerMemoryPayload(memoryDraft),
        },
      });
      await refreshSettings().catch(() => undefined);
      setMemorySaveState({
        saving: false,
        message: "Career Memory Builder saved.",
        error: "",
      });
      setMemoryDirty(false);
    } catch (saveError) {
      setMemorySaveState({
        saving: false,
        message: "",
        error: saveError.message || "Unable to save the Career Memory Builder.",
      });
    }
  }

  async function exportSelectedDocuments({ exportAnyway = false } = {}) {
    if (!selectedDocumentIds.length) {
      return;
    }
    setExportState({ exporting: true, message: "", error: "", gate: null });
    try {
      const bundle = await request("/documents/bulk-export", {
        method: "POST",
        body: {
          label: "application_documents",
          document_ids: selectedDocumentIds,
          export_anyway: exportAnyway,
        },
      });
      const blob = await request(bundle.download_url, { responseType: "blob" });
      triggerDownload(blob, bundle.file_name || "application_documents.zip");
      setExportState({
        exporting: false,
        message: `Exported ${bundle.document_count} document${bundle.document_count === 1 ? "" : "s"}.`,
        error: "",
        gate: null,
      });
    } catch (exportError) {
      setExportState({
        exporting: false,
        message: "",
        error: exportError.message || "Unable to export selected documents.",
        gate: exportError.code === "ats_export_blocked" ? exportError.details?.gate || null : null,
      });
    }
  }

  function handleViewChange(nextViewId) {
    const normalizedView = normalizeViewParam(nextViewId);
    setActiveView(normalizedView);
    const next = new URLSearchParams(searchParams);
    if (normalizedView === VIEW_LIBRARY) {
      next.delete("view");
    } else {
      next.set("view", normalizedView);
    }
    setSearchParams(next);
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div className="space-y-2">
          <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
            Career Assets
          </h1>
          <p className="max-w-3xl text-sm leading-7 text-on-surface-variant">
            Keep uploaded CVs, certifications, letters, and supporting career evidence in one
            place, then use Career Memory Builder to add the context your documents do not fully
            say yet.
          </p>
        </div>
      </header>

      <section
        aria-label="Career asset tools"
        className="grid gap-2 rounded-xl bg-surface-container-low p-2 lg:grid-cols-3"
      >
        {[
          {
            description: "Upload and manage the source files Runr can use.",
            id: VIEW_LIBRARY,
            label: "Asset Library",
          },
          {
            description: "Capture reusable stories, metrics, and career context.",
            id: VIEW_MEMORY,
            label: "Career Memory",
          },
        ].map((view) => (
          <button
            key={view.id}
            className={[
              "rounded-lg px-4 py-3 text-left transition-colors",
              activeView === view.id
                ? "bg-surface-container-lowest text-on-surface shadow-soft"
                : "text-on-surface-variant hover:bg-surface-container-high",
            ].join(" ")}
            onClick={() => handleViewChange(view.id)}
            type="button"
          >
            <span className="block text-sm font-semibold">{view.label}</span>
            <span className="mt-1 block text-xs leading-5 text-on-surface-variant">
              {view.description}
            </span>
          </button>
        ))}
        <Link
          className="rounded-lg px-4 py-3 text-left text-on-surface-variant transition-colors hover:bg-surface-container-high"
          to={CV_STUDIO_ROUTE}
        >
          <span className="block text-sm font-semibold text-on-surface">CV Studio</span>
          <span className="mt-1 block text-xs leading-5 text-on-surface-variant">
            Edit the latest browser draft. Use Tracker's Edit CV action for a generated job CV.
          </span>
        </Link>
      </section>

      {activeView === VIEW_LIBRARY ? (
        <div className="space-y-6">
          <section className="grid gap-6 xl:grid-cols-[1.2fr_2fr]">
            <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
              <div className="space-y-2">
                <h2 className="font-headline text-xl font-bold text-on-surface">
                  Upload Career Assets
                </h2>
                <p className="text-sm leading-7 text-on-surface-variant">
                  Add baseline CVs, certifications, recommendation letters, or other supporting
                  files to the shared asset library.
                </p>
              </div>

              <div className="mt-5 grid gap-4 lg:grid-cols-2">
                <label className="grid gap-2 lg:grid-cols-[max-content_minmax(0,1fr)] lg:items-center lg:gap-4">
                  <span className="text-sm font-semibold text-on-surface">
                    Asset Type
                  </span>
                  <FilterSelect
                    className="min-w-0 w-full"
                    onChange={(event) =>
                      setUploadForm((current) => ({ ...current, assetKind: event.target.value }))
                    }
                    value={uploadForm.assetKind}
                  >
                    {UPLOAD_KIND_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </FilterSelect>
                </label>

                <label className="grid gap-2 lg:grid-cols-[max-content_minmax(0,1fr)] lg:items-center lg:gap-4">
                  <span className="text-sm font-semibold text-on-surface">
                    Bind To Workspace
                  </span>
                  <FilterSelect
                    className="min-w-0 w-full"
                    onChange={(event) =>
                      setUploadForm((current) => ({ ...current, workspaceId: event.target.value }))
                    }
                    value={uploadForm.workspaceId}
                  >
                    <option value="">Shared across workspaces</option>
                    {workspaceOptions.map((workspace) => (
                      <option key={workspace.value} value={workspace.value}>
                        {workspace.label}
                      </option>
                    ))}
                  </FilterSelect>
                </label>

                <label className="inline-flex cursor-pointer items-center justify-center rounded bg-gradient-to-br from-primary to-primary-container px-4 py-3 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 lg:col-span-2">
                  <input
                    className="hidden"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) {
                        uploadDocument(file);
                        event.target.value = "";
                      }
                    }}
                    type="file"
                  />
                  {uploadState.uploading ? "Uploading..." : "Upload Asset"}
                </label>

                {uploadState.message ? (
                  <p className="text-sm text-primary lg:col-span-2">{uploadState.message}</p>
                ) : null}
                {uploadState.error ? (
                  <p className="text-sm text-error lg:col-span-2">{uploadState.error}</p>
                ) : null}
              </div>
            </div>

            <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h2 className="font-headline text-xl font-bold text-on-surface">
                    Asset Library
                  </h2>
                  <p className="mt-1 text-sm text-on-surface-variant">
                    Download uploaded assets individually or export a selected bundle.
                  </p>
                </div>
                <div className="flex gap-3">
                  <button
                    className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                    disabled={!selectedDocumentIds.length || exportState.exporting}
                    onClick={exportSelectedDocuments}
                    type="button"
                  >
                    {exportState.exporting ? "Exporting..." : "Export"}
                  </button>
                  <button
                    className="rounded bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                    onClick={() => setSelectedDocumentIds([])}
                    type="button"
                  >
                    Clear
                  </button>
                </div>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-5">
                <input
                  className="rounded-lg border border-outline-variant/20 bg-surface px-4 py-2.5 text-sm text-on-surface"
                  onChange={(event) =>
                    setDocumentFilters((current) => ({ ...current, search: event.target.value }))
                  }
                  placeholder="Search asset, type, workspace, or filename"
                  type="text"
                  value={documentFilters.search}
                />
                <FilterSelect
                  onChange={(event) =>
                    setDocumentFilters((current) => ({ ...current, workspaceId: event.target.value }))
                  }
                  value={documentFilters.workspaceId}
                >
                  <option value="">All Workspaces</option>
                  {workspaceOptions.map((workspace) => (
                    <option key={workspace.value} value={workspace.value}>
                      {workspace.label}
                    </option>
                  ))}
                </FilterSelect>
                <FilterSelect
                  onChange={(event) =>
                    setDocumentFilters((current) => ({ ...current, assetKind: event.target.value }))
                  }
                  value={documentFilters.assetKind}
                >
                  <option value="">All Asset Types</option>
                  {documentKindOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </FilterSelect>
                <button
                  className="rounded-lg bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                  onClick={() => refreshDocuments().catch(() => undefined)}
                  type="button"
                >
                  Refresh Assets
                </button>
              </div>

              {exportState.message ? (
                <p className="mt-4 text-sm text-primary">{exportState.message}</p>
              ) : null}
              {exportState.error ? (
                <p className="mt-4 text-sm text-error">{exportState.error}</p>
              ) : null}
              {exportState.gate ? (
                <div className="mt-4 rounded-2xl border border-amber-500/20 bg-amber-500/5 p-4">
                  <div className="text-sm font-semibold text-on-surface">
                    ATS score gate blocked final CV export
                  </div>
                  <p className="mt-1 text-sm leading-6 text-on-surface-variant">
                    Best score reached: {exportState.gate.best_score}%. Target:{" "}
                    {exportState.gate.target_score}%.
                  </p>
                  {exportState.gate.missing_requirements?.length ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {exportState.gate.missing_requirements.map((requirement) => (
                        <span
                          className="rounded-full bg-surface-container-low px-2.5 py-1 text-xs text-on-surface"
                          key={requirement}
                        >
                          {requirement}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <div className="mt-4 flex flex-wrap gap-3">
                    <button
                      className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface hover:bg-surface-container-high"
                      onClick={() => setRequirementsReviewOpen(true)}
                      type="button"
                    >
                      Review missing requirements
                    </button>
                    <Link
                      className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface hover:bg-surface-container-high"
                      to="/settings"
                    >
                      Edit CV/profile inputs
                    </Link>
                    <button
                      className="rounded bg-primary/10 px-4 py-2 text-sm font-medium text-primary hover:bg-primary/20"
                      onClick={() => exportSelectedDocuments({ exportAnyway: true })}
                      type="button"
                    >
                      Export anyway
                    </button>
                    <button
                      className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface hover:bg-surface-container-high"
                      onClick={() => exportSelectedDocuments()}
                      type="button"
                    >
                      Try again
                    </button>
                  </div>
                </div>
              ) : null}
              {exportState.gate && requirementsReviewOpen ? (
                <div className="mt-4 rounded-2xl border border-outline-variant/20 bg-surface p-5">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <h3 className="font-headline text-lg font-bold text-on-surface">
                        Missing Requirements Review
                      </h3>
                      <p className="mt-1 text-sm leading-6 text-on-surface-variant">
                        Compare the blocked document set with the missing ATS requirements, then
                        review the related run details or profile inputs before trying again.
                      </p>
                    </div>
                    <button
                      className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface hover:bg-surface-container-high"
                      onClick={() => setRequirementsReviewOpen(false)}
                      type="button"
                    >
                      Close
                    </button>
                  </div>

                  {remediationRequirements.length ? (
                    <div className="mt-4 flex flex-wrap gap-2">
                      {remediationRequirements.map((requirement) => (
                        <span
                          className="rounded-full bg-surface-container-low px-2.5 py-1 text-xs font-medium text-on-surface"
                          key={requirement}
                        >
                          {requirement}
                        </span>
                      ))}
                    </div>
                  ) : null}

                  {selectedBlockedDocuments.length ? (
                    <div className="mt-4 grid gap-3 lg:grid-cols-2">
                      {selectedBlockedDocuments.map((document) => (
                        <div
                          className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-4"
                          key={`blocked-${document.document_id}`}
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <div className="font-semibold text-on-surface">{document.display_name}</div>
                            <StatusBadge tone={statusTone(documentStatusValue(document))}>
                              {documentStatusLabel(document)}
                            </StatusBadge>
                          </div>
                          <p className="mt-2 text-sm text-on-surface-variant">
                            {document.group_label}
                          </p>
                          <p className="mt-2 text-sm text-on-surface-variant">
                            Best score: {document.ats_export_gate?.best_score ?? exportState.gate.best_score}%.
                            Target: {document.ats_export_gate?.target_score ?? exportState.gate.target_score}%.
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : null}

                  <div className="mt-5 flex flex-wrap gap-3">
                    <Link
                      className="rounded bg-primary/10 px-4 py-2 text-sm font-medium text-primary hover:bg-primary/20"
                      to="/tracker"
                    >
                      Open Tracker
                    </Link>
                    <Link
                      className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface hover:bg-surface-container-high"
                      to="/settings"
                    >
                      Edit CV/profile inputs
                    </Link>
                    {selectedBlockedDocuments.length === 1 && selectedBlockedDocuments[0].run_id ? (
                      <Link
                        className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface hover:bg-surface-container-high"
                        to={`/runs/${selectedBlockedDocuments[0].run_id}`}
                      >
                        Open Related Run
                      </Link>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>
          </section>

          <section className="space-y-4">
            {documentsLoading ? (
              <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 text-on-surface-variant shadow-soft">
                Loading career assets...
              </div>
            ) : documentsError ? (
              <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 text-error shadow-soft">
                {documentsError}
              </div>
            ) : visibleDocumentSections.length ? (
              visibleDocumentSections.map((group) => (
                <section
                  className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft"
                  key={group.group_id}
                >
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="font-headline text-2xl font-bold text-on-surface">
                          {group.group_label}
                        </h2>
                        <span className="rounded-full bg-surface-container-low px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-on-surface-variant">
                          {labelize(group.group_kind)}
                        </span>
                      </div>
                      <p className="mt-1 text-sm text-on-surface-variant">
                        {buildDocumentGroupDescription(group) || "Assets linked to this workspace."}
                      </p>
                    </div>
                    <div className="text-sm text-on-surface-variant">
                      {group.documents.length} asset{group.documents.length === 1 ? "" : "s"}
                    </div>
                  </div>

                  <div className="mt-5 grid gap-4 lg:grid-cols-2">
                    {group.documents.map((document) => {
                      const isSelected = selectedDocumentIds.includes(document.document_id);
                      return (
                        <article
                          className="flex h-full flex-col gap-4 rounded-xl border border-outline-variant/20 bg-surface p-5"
                          key={document.document_id}
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="min-w-0 space-y-2">
                              <div className="flex flex-wrap items-center gap-2">
                                <h3 className="font-headline text-xl font-bold text-on-surface">
                                  {document.display_name}
                                </h3>
                                <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
                                  {assetKindLabel(document.asset_kind || document.document_type)}
                                </span>
                                <StatusBadge tone={statusTone(documentStatusValue(document))}>
                                  {documentStatusLabel(document)}
                                </StatusBadge>
                              </div>
                              <p className="text-sm text-on-surface-variant">
                                {[document.job_title, document.company].filter(Boolean).join(" at ") ||
                                  "Reusable career asset"}
                              </p>
                            </div>
                            <label className="inline-flex items-center gap-2 text-sm text-on-surface">
                              <input
                                checked={isSelected}
                                className="h-4 w-4 rounded border-outline-variant/40 text-primary focus:ring-primary"
                                onChange={() =>
                                  toggleSelection(
                                    setSelectedDocumentIds,
                                    selectedDocumentIds,
                                    document.document_id,
                                  )
                                }
                                type="checkbox"
                              />
                              Select
                            </label>
                          </div>
                          {document.metadata?.text_extraction ? (
                            <div className="rounded-lg bg-surface-container-low px-3 py-2 text-xs leading-5 text-on-surface-variant">
                              <div>
                                Text extraction: {labelize(document.metadata.text_extraction.method || "pending")}
                                {Number(document.metadata.text_extraction.confidence) > 0
                                  ? ` · ${Math.round(Number(document.metadata.text_extraction.confidence) * 100)}% confidence`
                                  : ""}
                              </div>
                              {(document.metadata.text_extraction.warnings || []).map((warning) => (
                                <div className="mt-1 text-error" key={warning}>{warning}</div>
                              ))}
                            </div>
                          ) : null}
                          <div className="flex flex-wrap gap-3">
                            <button
                              className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                              onClick={() => downloadDocument(document).catch(() => undefined)}
                              type="button"
                            >
                              Download
                            </button>
                          </div>
                        </article>
                      );
                    })}
                  </div>
                </section>
              ))
            ) : (
              <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
                <h2 className="font-headline text-xl font-bold text-on-surface">
                  No assets match these filters
                </h2>
                <p className="mt-2 text-sm leading-7 text-on-surface-variant">
                  Upload a CV or supporting asset, or widen the current filters.
                </p>
              </div>
            )}
          </section>
        </div>
      ) : activeView === VIEW_MEMORY ? (
        <CareerMemoryBuilderPage
          assetDocuments={assetDocuments}
          assetKindLabel={assetKindLabel}
          cvLikeAssets={cvLikeAssets}
          draft={memoryDraft}
          formatDateTime={formatDateTime}
          masterCareerProfileAsset={masterCareerProfileAsset}
          onChangeField={updateMemoryField}
          onSave={saveCareerMemory}
          saveState={memorySaveState}
        />
      ) : null}

      {selectedDocuments.length && activeView === VIEW_LIBRARY ? (
        <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
          <h2 className="font-headline text-lg font-bold text-on-surface">
            Selected For Export
          </h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {selectedDocuments.map((document) => (
              <span
                className="rounded-full bg-surface-container-low px-3 py-1.5 text-sm text-on-surface"
                key={document.document_id}
              >
                {document.display_name}
              </span>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
