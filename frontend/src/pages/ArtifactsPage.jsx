import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { formatDateTime, labelize } from "../lib/formatters";

const VIEW_LIBRARY = "library";
const VIEW_REJECTED = "rejected";
const DEFAULT_UPLOAD_KIND = "uploaded_document";
const DEFAULT_REQUEUE_NOTE = "Override from rejected jobs review.";

const UPLOAD_KIND_OPTIONS = [
  { value: "uploaded_document", label: "Supporting Document" },
  { value: "certification", label: "Certification" },
  { value: "recommendation_letter", label: "Recommendation Letter" },
  { value: "motivation_letter", label: "Motivation Letter" },
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

function openBlob(blob) {
  const objectUrl = window.URL.createObjectURL(blob);
  const openedWindow = window.open(objectUrl, "_blank", "noopener,noreferrer");
  if (!openedWindow) {
    window.location.assign(objectUrl);
  }
  window.setTimeout(() => {
    window.URL.revokeObjectURL(objectUrl);
  }, 60000);
}

function FilterSelect({ children, onChange, value }) {
  return (
    <select
      className="rounded-lg border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface"
      onChange={onChange}
      value={value}
    >
      {children}
    </select>
  );
}

export default function DocumentsPage() {
  const { request } = useSession();
  const [activeView, setActiveView] = useState(VIEW_LIBRARY);
  const [documentFilters, setDocumentFilters] = useState({
    search: "",
    workspaceId: "",
    runId: "",
    groupId: "",
  });
  const [rejectedFilters, setRejectedFilters] = useState({
    search: "",
    workspaceId: "",
    reasonCode: "",
  });
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([]);
  const [selectedRejectedIds, setSelectedRejectedIds] = useState([]);
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
  });
  const [requeueState, setRequeueState] = useState({
    loading: false,
    message: "",
    error: "",
  });

  const {
    data: documentsPayload,
    loading: documentsLoading,
    error: documentsError,
    refresh: refreshDocuments,
  } = useApiResource(() => request("/documents?limit=500"), [request]);
  const {
    data: rejectedPayload,
    loading: rejectedLoading,
    error: rejectedError,
    refresh: refreshRejected,
  } = useApiResource(() => request("/rejected-jobs?limit=300"), [request]);
  const { data: workspacesPayload } = useApiResource(() => request("/workspaces?limit=100"), [request]);

  const allDocuments = documentsPayload?.documents || [];
  const documentGroups = documentsPayload?.groups || [];
  const allRejectedItems = rejectedPayload?.items || [];
  const workspaces = workspacesPayload?.workspaces || [];

  const workspaceOptions = useMemo(
    () =>
      workspaces.map((workspace) => ({
        value: workspace.id,
        label: workspace.name || workspace.id,
      })),
    [workspaces],
  );
  const runOptions = useMemo(
    () =>
      Array.from(
        new Map(
          allDocuments
            .filter((item) => item.run_id)
            .map((item) => [item.run_id, item.run_id]),
        ).entries(),
      ).map(([value, label]) => ({ value, label })),
    [allDocuments],
  );
  const rejectedReasonOptions = useMemo(
    () =>
      Array.from(
        new Map(
          allRejectedItems
            .filter((item) => item.reason_code)
            .map((item) => [item.reason_code, item.reason_label || labelize(item.reason_code)]),
        ).entries(),
      ).map(([value, label]) => ({ value, label })),
    [allRejectedItems],
  );

  const filteredDocuments = useMemo(
    () =>
      allDocuments.filter((item) => {
        if (documentFilters.workspaceId && item.workspace_id !== documentFilters.workspaceId) {
          return false;
        }
        if (documentFilters.runId && item.run_id !== documentFilters.runId) {
          return false;
        }
        if (documentFilters.groupId && item.group_id !== documentFilters.groupId) {
          return false;
        }
        return matchesQuery(
          [
            item.display_name,
            item.group_label,
            item.job_title,
            item.company,
            item.workspace_name,
            item.run_id,
            item.relative_path,
            item.asset_kind,
          ],
          documentFilters.search,
        );
      }),
    [allDocuments, documentFilters],
  );

  const filteredRejectedItems = useMemo(
    () =>
      allRejectedItems.filter((item) => {
        if (rejectedFilters.workspaceId && item.workspace_id !== rejectedFilters.workspaceId) {
          return false;
        }
        if (rejectedFilters.reasonCode && item.reason_code !== rejectedFilters.reasonCode) {
          return false;
        }
        return matchesQuery(
          [
            item.title,
            item.company,
            item.reason_label,
            item.reason_summary,
            item.workspace_name,
            item.job_id,
          ],
          rejectedFilters.search,
        );
      }),
    [allRejectedItems, rejectedFilters],
  );

  const selectedDocuments = useMemo(
    () => allDocuments.filter((item) => selectedDocumentIds.includes(item.document_id)),
    [allDocuments, selectedDocumentIds],
  );
  const selectedRejectedItems = useMemo(
    () => allRejectedItems.filter((item) => selectedRejectedIds.includes(item.rejected_id)),
    [allRejectedItems, selectedRejectedIds],
  );
  const selectedRequeueableItems = useMemo(
    () => selectedRejectedItems.filter((item) => item.can_requeue),
    [selectedRejectedItems],
  );
  const selectedUnavailableRequeueCount =
    selectedRejectedItems.length - selectedRequeueableItems.length;

  function toggleSelection(setter, currentIds, id) {
    setter(
      currentIds.includes(id) ? currentIds.filter((item) => item !== id) : [...currentIds, id],
    );
  }

  async function downloadFile(path, fileName) {
    const blob = await request(path, { responseType: "blob" });
    triggerDownload(blob, fileName);
  }

  async function openFile(path) {
    const blob = await request(path, { responseType: "blob" });
    openBlob(blob);
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
      await request(`/documents/upload?${params.toString()}`, {
        method: "POST",
        body: formData,
      });
      await refreshDocuments().catch(() => undefined);
      setUploadState({
        uploading: false,
        message: `Uploaded ${file.name} to the documents library.`,
        error: "",
      });
    } catch (uploadError) {
      setUploadState({
        uploading: false,
        message: "",
        error: uploadError.message || "Unable to upload document.",
      });
    }
  }

  async function exportSelectedDocuments() {
    if (!selectedDocumentIds.length) {
      return;
    }
    setExportState({ exporting: true, message: "", error: "" });
    try {
      const bundle = await request("/documents/bulk-export", {
        method: "POST",
        body: {
          label: "application_documents",
          document_ids: selectedDocumentIds,
        },
      });
      const blob = await request(bundle.download_url, { responseType: "blob" });
      triggerDownload(blob, bundle.file_name || "application_documents.zip");
      setExportState({
        exporting: false,
        message: `Exported ${bundle.document_count} document${bundle.document_count === 1 ? "" : "s"}.`,
        error: "",
      });
    } catch (exportError) {
      setExportState({
        exporting: false,
        message: "",
        error: exportError.message || "Unable to export selected documents.",
      });
    }
  }

  async function queueRejectedItems(items) {
    if (!items.length) {
      return;
    }
    setRequeueState({ loading: true, message: "", error: "" });
    try {
      for (const item of items) {
        await request("/rejected-jobs/requeue", {
          method: "POST",
          body: {
            run_id: item.run_id,
            job_id: item.job_id,
            source_stage: item.source_stage,
            reason_summary: item.reason_summary,
            execution_mode: "queued",
            notes: DEFAULT_REQUEUE_NOTE,
          },
        });
      }
      await refreshRejected().catch(() => undefined);
      setSelectedRejectedIds([]);
      setRequeueState({
        loading: false,
        message: `Queued ${items.length} rejected job${items.length === 1 ? "" : "s"} for regeneration.`,
        error: "",
      });
    } catch (requeueError) {
      setRequeueState({
        loading: false,
        message: "",
        error: requeueError.message || "Unable to send rejected jobs back to the pipeline.",
      });
    }
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div className="space-y-2">
          <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
            Documents
          </h1>
          <p className="max-w-3xl text-sm leading-7 text-on-surface-variant">
            Browse generated CVs and letters, keep supporting application assets in one library,
            and send rejected jobs back into the pipeline when filters were too aggressive.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            className={[
              "rounded-full px-4 py-2 text-sm font-medium transition-colors",
              activeView === VIEW_LIBRARY
                ? "bg-primary text-white"
                : "bg-surface-container-low text-on-surface hover:bg-surface-container-high",
            ].join(" ")}
            onClick={() => setActiveView(VIEW_LIBRARY)}
            type="button"
          >
            Library
          </button>
          <button
            className={[
              "rounded-full px-4 py-2 text-sm font-medium transition-colors",
              activeView === VIEW_REJECTED
                ? "bg-primary text-white"
                : "bg-surface-container-low text-on-surface hover:bg-surface-container-high",
            ].join(" ")}
            onClick={() => setActiveView(VIEW_REJECTED)}
            type="button"
          >
            Rejected Jobs
          </button>
        </div>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
          <div className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
            Documents In Library
          </div>
          <div className="mt-2 font-headline text-3xl font-bold text-on-surface">
            {allDocuments.length}
          </div>
          <div className="mt-1 text-sm text-on-surface-variant">
            Generated files and uploaded assets in one place.
          </div>
        </div>
        <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
          <div className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
            Rejected Jobs
          </div>
          <div className="mt-2 font-headline text-3xl font-bold text-on-surface">
            {allRejectedItems.length}
          </div>
          <div className="mt-1 text-sm text-on-surface-variant">
            Review why jobs were filtered out and override them when needed.
          </div>
        </div>
        <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
          <div className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
            Current Selection
          </div>
          <div className="mt-2 font-headline text-3xl font-bold text-on-surface">
            {activeView === VIEW_LIBRARY ? selectedDocumentIds.length : selectedRejectedIds.length}
          </div>
          <div className="mt-1 text-sm text-on-surface-variant">
            {activeView === VIEW_LIBRARY
              ? "Selected for bulk export."
              : "Selected to send back into the generation flow."}
          </div>
        </div>
      </section>

      {activeView === VIEW_LIBRARY ? (
        <div className="space-y-6">
          <section className="grid gap-6 xl:grid-cols-[1.2fr_2fr]">
            <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
              <div className="space-y-2">
                <h2 className="font-headline text-xl font-bold text-on-surface">
                  Upload Supporting Documents
                </h2>
                <p className="text-sm leading-7 text-on-surface-variant">
                  Add certifications, recommendation letters, motivation letters, or other
                  supporting files to the shared document library.
                </p>
              </div>

              <div className="mt-5 grid gap-4">
                <label className="space-y-2">
                  <span className="block text-sm font-semibold text-on-surface">Document Type</span>
                  <FilterSelect
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

                <label className="space-y-2">
                  <span className="block text-sm font-semibold text-on-surface">
                    Bind To Workspace
                  </span>
                  <FilterSelect
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

                <label className="inline-flex cursor-pointer items-center justify-center rounded bg-gradient-to-br from-primary to-primary-container px-4 py-3 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90">
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
                  {uploadState.uploading ? "Uploading..." : "Upload Document"}
                </label>

                {uploadState.message ? (
                  <p className="text-sm text-primary">{uploadState.message}</p>
                ) : null}
                {uploadState.error ? (
                  <p className="text-sm text-error">{uploadState.error}</p>
                ) : null}
              </div>
            </div>

            <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h2 className="font-headline text-xl font-bold text-on-surface">
                    Documents Library
                  </h2>
                  <p className="mt-1 text-sm text-on-surface-variant">
                    Preview files, download them individually, or export a selected bundle.
                  </p>
                </div>
                <div className="flex flex-wrap gap-3">
                  <button
                    className="rounded bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                    onClick={() => {
                      setSelectedDocumentIds(filteredDocuments.map((item) => item.document_id));
                    }}
                    type="button"
                  >
                    Select Visible
                  </button>
                  <button
                    className="rounded bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                    onClick={() => setSelectedDocumentIds([])}
                    type="button"
                  >
                    Clear Selection
                  </button>
                  <button
                    className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                    disabled={!selectedDocumentIds.length || exportState.exporting}
                    onClick={exportSelectedDocuments}
                    type="button"
                  >
                    {exportState.exporting ? "Exporting..." : "Bulk Export Selected"}
                  </button>
                </div>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-4">
                <input
                  className="rounded-lg border border-outline-variant/20 bg-surface px-4 py-2.5 text-sm text-on-surface"
                  onChange={(event) =>
                    setDocumentFilters((current) => ({ ...current, search: event.target.value }))
                  }
                  placeholder="Search document, job, company, or run"
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
                    setDocumentFilters((current) => ({ ...current, runId: event.target.value }))
                  }
                  value={documentFilters.runId}
                >
                  <option value="">All Runs</option>
                  {runOptions.map((run) => (
                    <option key={run.value} value={run.value}>
                      {run.label}
                    </option>
                  ))}
                </FilterSelect>
                <button
                  className="rounded-lg bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                  onClick={() => refreshDocuments().catch(() => undefined)}
                  type="button"
                >
                  Refresh Library
                </button>
              </div>

              <div className="mt-5 flex flex-wrap gap-3">
                <button
                  className={[
                    "rounded-full px-3 py-1.5 text-sm font-medium transition-colors",
                    !documentFilters.groupId
                      ? "bg-primary text-white"
                      : "bg-surface-container-low text-on-surface hover:bg-surface-container-high",
                  ].join(" ")}
                  onClick={() =>
                    setDocumentFilters((current) => ({ ...current, groupId: "" }))
                  }
                  type="button"
                >
                  All Groups
                </button>
                {documentGroups.map((group) => (
                  <button
                    className={[
                      "rounded-full px-3 py-1.5 text-sm font-medium transition-colors",
                      documentFilters.groupId === group.group_id
                        ? "bg-primary text-white"
                        : "bg-surface-container-low text-on-surface hover:bg-surface-container-high",
                    ].join(" ")}
                    key={group.group_id}
                    onClick={() =>
                      setDocumentFilters((current) => ({ ...current, groupId: group.group_id }))
                    }
                    type="button"
                  >
                    {group.group_label} ({group.count})
                  </button>
                ))}
              </div>

              {exportState.message ? (
                <p className="mt-4 text-sm text-primary">{exportState.message}</p>
              ) : null}
              {exportState.error ? (
                <p className="mt-4 text-sm text-error">{exportState.error}</p>
              ) : null}
            </div>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            {documentsLoading ? (
              <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 text-on-surface-variant shadow-soft lg:col-span-2">
                Loading documents...
              </div>
            ) : documentsError ? (
              <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 text-error shadow-soft lg:col-span-2">
                {documentsError}
              </div>
            ) : filteredDocuments.length ? (
              filteredDocuments.map((document) => {
                const isSelected = selectedDocumentIds.includes(document.document_id);
                return (
                  <article
                    className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft"
                    key={document.document_id}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="font-headline text-xl font-bold text-on-surface">
                            {document.display_name}
                          </h3>
                          <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
                            {document.group_label}
                          </span>
                        </div>
                        <p className="text-sm text-on-surface-variant">
                          {[document.job_title, document.company].filter(Boolean).join(" at ") ||
                            "Shared document"}
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

                    <div className="mt-4 grid gap-3 text-sm text-on-surface-variant md:grid-cols-2">
                      <div>
                        <span className="font-semibold text-on-surface">Workspace:</span>{" "}
                        {document.workspace_name || "Shared"}
                      </div>
                      <div>
                        <span className="font-semibold text-on-surface">Run:</span>{" "}
                        {document.run_id || "Manual upload"}
                      </div>
                      <div>
                        <span className="font-semibold text-on-surface">Created:</span>{" "}
                        {formatDateTime(document.created_at)}
                      </div>
                      <div>
                        <span className="font-semibold text-on-surface">Origin:</span>{" "}
                        {labelize(document.source_origin)}
                      </div>
                    </div>

                    {document.tags?.length ? (
                      <div className="mt-4 flex flex-wrap gap-2">
                        {document.tags.map((tag) => (
                          <span
                            className="rounded-full bg-surface-container-low px-2.5 py-1 text-xs font-medium text-on-surface-variant"
                            key={`${document.document_id}-${tag}`}
                          >
                            {labelize(tag)}
                          </span>
                        ))}
                      </div>
                    ) : null}

                    <div className="mt-5 flex flex-wrap gap-3">
                      <button
                        className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                        onClick={() => openFile(document.preview_url || document.download_url)}
                        type="button"
                      >
                        Preview
                      </button>
                      <button
                        className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                        onClick={() =>
                          downloadFile(document.download_url, document.display_name || "document")
                        }
                        type="button"
                      >
                        Download
                      </button>
                    </div>
                  </article>
                );
              })
            ) : (
              <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft lg:col-span-2">
                <h2 className="font-headline text-xl font-bold text-on-surface">
                  No documents match these filters
                </h2>
                <p className="mt-2 text-sm leading-7 text-on-surface-variant">
                  Upload a supporting document, generate a new CV from a run, or widen the
                  current filters.
                </p>
              </div>
            )}
          </section>
        </div>
      ) : (
        <div className="space-y-6">
          <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h2 className="font-headline text-xl font-bold text-on-surface">
                  Rejected Jobs Review
                </h2>
                <p className="mt-1 text-sm text-on-surface-variant">
                  Use rejection reasons to tune future filtering, then requeue jobs that deserve a
                  second pass.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  className="rounded bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                  onClick={() => {
                    setSelectedRejectedIds(
                      filteredRejectedItems
                        .filter((item) => item.can_requeue)
                        .map((item) => item.rejected_id),
                    );
                  }}
                  type="button"
                >
                  Select Visible
                </button>
                <button
                  className="rounded bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                  onClick={() => setSelectedRejectedIds([])}
                  type="button"
                >
                  Clear Selection
                </button>
                <button
                  className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={!selectedRequeueableItems.length || requeueState.loading}
                  onClick={() => queueRejectedItems(selectedRequeueableItems)}
                  type="button"
                >
                  {requeueState.loading ? "Queueing..." : "Send Selected Back To Queue"}
                </button>
              </div>
            </div>

            <div className="mt-5 grid gap-4 md:grid-cols-4">
              <input
                className="rounded-lg border border-outline-variant/20 bg-surface px-4 py-2.5 text-sm text-on-surface"
                onChange={(event) =>
                  setRejectedFilters((current) => ({ ...current, search: event.target.value }))
                }
                placeholder="Search job, company, reason, or workspace"
                type="text"
                value={rejectedFilters.search}
              />
              <FilterSelect
                onChange={(event) =>
                  setRejectedFilters((current) => ({ ...current, workspaceId: event.target.value }))
                }
                value={rejectedFilters.workspaceId}
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
                  setRejectedFilters((current) => ({ ...current, reasonCode: event.target.value }))
                }
                value={rejectedFilters.reasonCode}
              >
                <option value="">All Reasons</option>
                {rejectedReasonOptions.map((reason) => (
                  <option key={reason.value} value={reason.value}>
                    {reason.label}
                  </option>
                ))}
              </FilterSelect>
              <button
                className="rounded-lg bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                onClick={() => refreshRejected().catch(() => undefined)}
                type="button"
              >
                Refresh Rejections
              </button>
            </div>

            {requeueState.message ? (
              <p className="mt-4 text-sm text-primary">{requeueState.message}</p>
            ) : null}
            {requeueState.error ? (
              <p className="mt-4 text-sm text-error">{requeueState.error}</p>
            ) : null}
            {selectedUnavailableRequeueCount ? (
              <p className="mt-4 text-sm text-on-surface-variant">
                {selectedUnavailableRequeueCount} selected item
                {selectedUnavailableRequeueCount === 1 ? " is" : "s are"} not eligible for
                requeue and will be skipped by the bulk action.
              </p>
            ) : null}
          </section>

          <section className="space-y-4">
            {rejectedLoading ? (
              <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 text-on-surface-variant shadow-soft">
                Loading rejected jobs...
              </div>
            ) : rejectedError ? (
              <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 text-error shadow-soft">
                {rejectedError}
              </div>
            ) : filteredRejectedItems.length ? (
              filteredRejectedItems.map((item) => {
                const isSelected = selectedRejectedIds.includes(item.rejected_id);
                return (
                  <article
                    className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft"
                    key={item.rejected_id}
                  >
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="font-headline text-xl font-bold text-on-surface">
                            {item.title || "Untitled role"}
                          </h3>
                          <span className="rounded-full bg-error/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-error">
                            {item.reason_label || labelize(item.reason_code)}
                          </span>
                          {item.override_state ? (
                            <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
                              {labelize(item.override_state)}
                            </span>
                          ) : null}
                        </div>
                        <p className="text-sm text-on-surface-variant">
                          {[item.company, item.workspace_name].filter(Boolean).join(" | ")}
                        </p>
                        <p className="text-sm leading-7 text-on-surface-variant">
                          {item.reason_summary || "No rejection summary was saved."}
                        </p>
                      </div>

                      <label className="inline-flex items-center gap-2 text-sm text-on-surface">
                        <input
                          checked={isSelected}
                          className="h-4 w-4 rounded border-outline-variant/40 text-primary focus:ring-primary"
                          onChange={() =>
                            toggleSelection(
                              setSelectedRejectedIds,
                              selectedRejectedIds,
                              item.rejected_id,
                            )
                          }
                          type="checkbox"
                        />
                        Select
                      </label>
                    </div>

                    {item.details?.length ? (
                      <div className="mt-4 rounded-lg bg-surface-container-low p-4 text-sm text-on-surface-variant">
                        <div className="font-semibold text-on-surface">Saved rejection details</div>
                        <div className="mt-2 space-y-1">
                          {item.details.map((detail) => (
                            <div key={`${item.rejected_id}-${detail}`}>{detail}</div>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    <div className="mt-4 grid gap-3 text-sm text-on-surface-variant md:grid-cols-2">
                      <div>
                        <span className="font-semibold text-on-surface">Recorded:</span>{" "}
                        {formatDateTime(item.recorded_at)}
                      </div>
                      <div>
                        <span className="font-semibold text-on-surface">Run:</span> {item.run_id}
                      </div>
                      <div>
                        <span className="font-semibold text-on-surface">Source Stage:</span>{" "}
                        {labelize(item.source_stage)}
                      </div>
                      <div>
                        <span className="font-semibold text-on-surface">Override Run:</span>{" "}
                        {item.requeue_run_id || "Not queued yet"}
                      </div>
                    </div>

                    <div className="mt-5 flex flex-wrap gap-3">
                      <Link
                        className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                        to={item.workspace_editor_url}
                      >
                        Adjust Workspace Settings
                      </Link>
                      {item.apply_link ? (
                        <a
                          className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                          href={item.apply_link}
                          rel="noreferrer"
                          target="_blank"
                        >
                          Open Job Listing
                        </a>
                      ) : null}
                      <button
                        className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                        disabled={!item.can_requeue || requeueState.loading}
                        onClick={() => queueRejectedItems([item])}
                        type="button"
                      >
                        {item.can_requeue ? "Send Back To Queue" : "Requeue Unavailable"}
                      </button>
                    </div>
                  </article>
                );
              })
            ) : (
              <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
                <h2 className="font-headline text-xl font-bold text-on-surface">
                  No rejected jobs match these filters
                </h2>
                <p className="mt-2 text-sm leading-7 text-on-surface-variant">
                  When screening rejects a job, it will appear here with a saved reason and a path
                  back to the relevant workspace settings.
                </p>
              </div>
            )}
          </section>
        </div>
      )}

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
