import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { formatDateTime, labelize, statusTone } from "../lib/formatters";

const VIEW_LIBRARY = "library";
const VIEW_CANVAS = "canvas";
const VIEW_REJECTED = "rejected";
const DEFAULT_UPLOAD_KIND = "uploaded_document";
const DEFAULT_REQUEUE_NOTE = "Override from rejected jobs review.";
const MASTER_CAREER_PROFILE_KIND = "master_career_profile";
const CAREER_ASSET_KINDS = new Set([
  "workspace_cv",
  MASTER_CAREER_PROFILE_KIND,
  "uploaded_document",
  "certification",
  "recommendation_letter",
  "motivation_letter",
]);
const CANVAS_DEFAULTS = {
  master_career_profile_asset_id: "",
  master_career_profile_text: "",
  career_highlights_text: "",
  bullet_bank_text: "",
  professional_hurdles_text: "",
  motivation_letter_notes: "",
  ai_canvas_source_asset_ids: [],
};

const UPLOAD_KIND_OPTIONS = [
  { value: "workspace_cv", label: "Baseline CV" },
  { value: MASTER_CAREER_PROFILE_KIND, label: "Master Career Profile" },
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
  if (normalized === MASTER_CAREER_PROFILE_KIND) return "Master Career Profile";
  if (normalized === "uploaded_document") return "Supporting Document";
  if (normalized === "recommendation_letter") return "Recommendation Letter";
  if (normalized === "motivation_letter") return "Motivation Letter";
  return labelize(assetKind);
}

function normalizeCanvasDraft(documents = {}) {
  const sourceAssetIds = Array.isArray(documents.ai_canvas_source_asset_ids)
    ? documents.ai_canvas_source_asset_ids
    : [];
  return {
    master_career_profile_asset_id: String(documents.master_career_profile_asset_id || ""),
    master_career_profile_text: String(documents.master_career_profile_text || ""),
    career_highlights_text: String(documents.career_highlights_text || ""),
    bullet_bank_text: String(documents.bullet_bank_text || ""),
    professional_hurdles_text: String(documents.professional_hurdles_text || ""),
    motivation_letter_notes: String(documents.motivation_letter_notes || ""),
    ai_canvas_source_asset_ids: Array.from(
      new Set(sourceAssetIds.map((item) => String(item || "").trim()).filter(Boolean)),
    ),
  };
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
  const [activeView, setActiveView] = useState(VIEW_LIBRARY);
  const [documentFilters, setDocumentFilters] = useState({
    search: "",
    workspaceId: "",
    assetKind: "",
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
    gate: null,
  });
  const [requeueState, setRequeueState] = useState({
    loading: false,
    message: "",
    error: "",
  });
  const [requirementsReviewOpen, setRequirementsReviewOpen] = useState(false);
  const [canvasDraft, setCanvasDraft] = useState(CANVAS_DEFAULTS);
  const [canvasSaveState, setCanvasSaveState] = useState({
    saving: false,
    message: "",
    error: "",
  });
  const [masterProfileUploadState, setMasterProfileUploadState] = useState({
    uploading: false,
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
  } = useApiResource(() => request("/rejected-jobs?limit=500"), [request]);
  const {
    data: settingsPayload,
    refresh: refreshSettings,
  } = useApiResource(() => request("/settings"), [request]);
  const { data: workspacesPayload } = useApiResource(() => request("/workspaces?limit=100"), [request]);

  const allDocuments = documentsPayload?.documents || [];
  const documentGroups = documentsPayload?.groups || [];
  const allRejectedItems = rejectedPayload?.items || [];
  const workspaces = workspacesPayload?.workspaces || [];

  useEffect(() => {
    if (!settingsPayload?.documents) {
      return;
    }
    setCanvasDraft(normalizeCanvasDraft(settingsPayload.documents));
  }, [settingsPayload?.documents]);

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
        return assetKind === "workspace_cv" || assetKind === MASTER_CAREER_PROFILE_KIND;
      }),
    [assetDocuments],
  );
  const documentKindOptions = useMemo(
    () =>
      Array.from(
        new Map(
          assetDocuments.map((item) => [
            String(item.asset_kind || ""),
            assetKindLabel(item.asset_kind || item.document_type),
          ]),
        ).entries(),
      ).map(([value, label]) => ({ value, label })),
    [assetDocuments],
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
    () => assetDocuments.filter((item) => selectedDocumentIds.includes(item.document_id)),
    [assetDocuments, selectedDocumentIds],
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
  const requeueableRejectedCount = useMemo(
    () => allRejectedItems.filter((item) => item.can_requeue).length,
    [allRejectedItems],
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
        (item) => String(item.asset_id || "") === String(canvasDraft.master_career_profile_asset_id || ""),
      ) || null,
    [assetDocuments, canvasDraft.master_career_profile_asset_id],
  );
  const selectedCanvasAssets = useMemo(
    () =>
      assetDocuments.filter((item) =>
        canvasDraft.ai_canvas_source_asset_ids.includes(String(item.asset_id || "")),
      ),
    [assetDocuments, canvasDraft.ai_canvas_source_asset_ids],
  );
  const canvasCoverage = useMemo(() => {
    const countForKind = (assetKind) =>
      assetDocuments.filter((item) => String(item.asset_kind || "") === assetKind).length;
    return [
      {
        label: "Baseline CVs",
        present: countForKind("workspace_cv") > 0,
        detail: `${countForKind("workspace_cv")} uploaded`,
      },
      {
        label: "Master Career Profile",
        present: Boolean(canvasDraft.master_career_profile_asset_id),
        detail: canvasDraft.master_career_profile_asset_id ? "Configured for AI canvas" : "Not linked yet",
      },
      {
        label: "Certifications",
        present: countForKind("certification") > 0,
        detail: `${countForKind("certification")} uploaded`,
      },
      {
        label: "Recommendation Letters",
        present: countForKind("recommendation_letter") > 0,
        detail: `${countForKind("recommendation_letter")} uploaded`,
      },
      {
        label: "Motivation-Letter Source Notes",
        present: Boolean(canvasDraft.motivation_letter_notes.trim()) || countForKind("motivation_letter") > 0,
        detail:
          countForKind("motivation_letter") > 0
            ? `${countForKind("motivation_letter")} uploaded`
            : "Add notes or upload examples",
      },
    ];
  }, [assetDocuments, canvasDraft.master_career_profile_asset_id, canvasDraft.motivation_letter_notes]);
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

  const summaryCards =
    activeView === VIEW_LIBRARY
      ? [
          {
            label: "Career Assets",
            value: assetDocuments.length,
            description: "Uploaded CVs, certifications, letters, and supporting documents.",
          },
          {
            label: "Visible Groups",
            value: visibleDocumentSections.length,
            description: "Shared and workspace-linked asset collections currently in view.",
          },
          {
            label: "Current Selection",
            value: selectedDocumentIds.length,
            description: "Selected for bulk export.",
          },
        ]
      : activeView === VIEW_CANVAS
        ? [
            {
              label: "Selected Source Assets",
              value: selectedCanvasAssets.length,
              description: "Assets the canvas can draw from when building personalized documents.",
            },
            {
              label: "Master Profile",
              value: masterCareerProfileAsset ? "Ready" : "Missing",
              description: "Detailed career source file for deeper bullet and letter personalization.",
            },
            {
              label: "Coverage Checks",
              value: canvasCoverage.filter((item) => item.present).length,
              description: "Recommended source categories already represented in your asset base.",
            },
          ]
        : [
            {
              label: "Rejected Jobs",
              value: allRejectedItems.length,
              description: "Saved screening rejects available for review and requeue.",
            },
            {
              label: "Can Requeue",
              value: requeueableRejectedCount,
              description: "Rejected jobs that can be sent back through the pipeline.",
            },
            {
              label: "Current Selection",
              value: selectedRejectedIds.length,
              description: "Selected for bulk requeue.",
            },
          ];

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

  async function openDocument(document) {
    try {
      await openFile(document.preview_url || document.download_url);
    } catch (openError) {
      if (openError.code === "ats_export_blocked") {
        setSelectedDocumentIds([document.document_id]);
        setExportState({
          exporting: false,
          message: "",
          error: openError.message,
          gate: openError.details?.gate || null,
        });
        return;
      }
      throw openError;
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
      await refreshDocuments().catch(() => undefined);
      setUploadState({
        uploading: false,
        message: `Uploaded ${file.name} to Career Assets.`,
        error: "",
      });
      return response?.asset || null;
    } catch (uploadError) {
      setUploadState({
        uploading: false,
        message: "",
        error: uploadError.message || "Unable to upload document.",
      });
      return null;
    }
  }

  function updateCanvasField(field, value) {
    setCanvasDraft((current) => ({ ...current, [field]: value }));
    setCanvasSaveState((current) => ({ ...current, message: "", error: "" }));
  }

  function toggleCanvasSourceAsset(assetId) {
    const normalizedAssetId = String(assetId || "");
    setCanvasDraft((current) => {
      const selectedIds = current.ai_canvas_source_asset_ids.includes(normalizedAssetId)
        ? current.ai_canvas_source_asset_ids.filter((item) => item !== normalizedAssetId)
        : [...current.ai_canvas_source_asset_ids, normalizedAssetId];
      return {
        ...current,
        ai_canvas_source_asset_ids: selectedIds,
      };
    });
    setCanvasSaveState((current) => ({ ...current, message: "", error: "" }));
  }

  async function saveCanvas() {
    setCanvasSaveState({ saving: true, message: "", error: "" });
    try {
      await request("/settings", {
        method: "PUT",
        body: {
          documents: canvasDraft,
        },
      });
      await refreshSettings().catch(() => undefined);
      setCanvasSaveState({
        saving: false,
        message: "Document AI canvas saved.",
        error: "",
      });
    } catch (saveError) {
      setCanvasSaveState({
        saving: false,
        message: "",
        error: saveError.message || "Unable to save the AI canvas.",
      });
    }
  }

  async function uploadMasterCareerProfile(file) {
    if (!file) {
      return;
    }
    setMasterProfileUploadState({ uploading: true, message: "", error: "" });
    try {
      const formData = new FormData();
      formData.append("document_file", file);
      const params = new URLSearchParams();
      params.set("asset_kind", MASTER_CAREER_PROFILE_KIND);
      params.set("display_name", file.name);
      const response = await request(`/documents/upload?${params.toString()}`, {
        method: "POST",
        body: formData,
      });
      const uploadedAsset = response?.asset || null;
      await refreshDocuments().catch(() => undefined);
      if (uploadedAsset?.asset_id) {
        setCanvasDraft((current) => ({
          ...current,
          master_career_profile_asset_id: String(uploadedAsset.asset_id || ""),
          master_career_profile_text:
            String(uploadedAsset?.metadata?.source_text || "").trim() || current.master_career_profile_text,
        }));
      }
      setMasterProfileUploadState({
        uploading: false,
        message: `Uploaded ${file.name}. Review the imported text, then save the AI canvas.`,
        error: "",
      });
      setCanvasSaveState((current) => ({ ...current, message: "", error: "" }));
    } catch (uploadError) {
      setMasterProfileUploadState({
        uploading: false,
        message: "",
        error: uploadError.message || "Unable to upload the master career profile.",
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
            Career Assets
          </h1>
          <p className="max-w-3xl text-sm leading-7 text-on-surface-variant">
            Keep uploaded CVs, certifications, letters, and supporting career evidence in one
            place, then use the AI canvas to turn that source material into stronger applications.
          </p>
        </div>
      </header>

      <section className="flex flex-wrap gap-2 rounded-xl bg-surface-container-low p-2">
        {[
          { id: VIEW_LIBRARY, label: "Asset Library" },
          { id: VIEW_CANVAS, label: "Document AI Canvas" },
          { id: VIEW_REJECTED, label: "Rejected Jobs Review" },
        ].map((view) => (
          <button
            key={view.id}
            className={[
              "rounded-lg px-4 py-2.5 text-sm font-medium transition-colors",
              activeView === view.id
                ? "bg-surface-container-lowest text-on-surface shadow-soft"
                : "text-on-surface-variant hover:bg-surface-container-high",
            ].join(" ")}
            onClick={() => setActiveView(view.id)}
            type="button"
          >
            {view.label}
          </button>
        ))}
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {summaryCards.map((card) => (
          <div
            key={card.label}
            className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft"
          >
            <div className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
              {card.label}
            </div>
            <div className="mt-2 font-headline text-3xl font-bold text-on-surface">
              {card.value}
            </div>
            <div className="mt-1 text-sm text-on-surface-variant">{card.description}</div>
          </div>
        ))}
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
                  Add baseline CVs, a master career profile, certifications, recommendation
                  letters, motivation-letter examples, or other supporting files to the shared
                  asset library.
                </p>
              </div>

              <div className="mt-5 grid gap-4">
                <label className="space-y-2">
                  <span className="block text-sm font-semibold text-on-surface">Asset Type</span>
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
                  {uploadState.uploading ? "Uploading..." : "Upload Asset"}
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
                    Asset Library
                  </h2>
                  <p className="mt-1 text-sm text-on-surface-variant">
                    Preview uploaded assets, download them individually, or export a selected bundle.
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

              <div className="mt-5 flex flex-wrap items-center gap-3 text-sm text-on-surface-variant">
                <span>
                  {visibleDocumentSections.length} visible shared or workspace asset group
                  {visibleDocumentSections.length === 1 ? "" : "s"}.
                </span>
                <span>
                  {filteredDocuments.length} matching asset{filteredDocuments.length === 1 ? "" : "s"}.
                </span>
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
                          className="rounded-xl border border-outline-variant/20 bg-surface p-5"
                          key={document.document_id}
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="space-y-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <h3 className="font-headline text-xl font-bold text-on-surface">
                                  {document.display_name}
                                </h3>
                                <StatusBadge tone={statusTone(documentStatusValue(document))}>
                                  {documentStatusLabel(document)}
                                </StatusBadge>
                                <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
                                  {document.document_type}
                                </span>
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

                          <div className="mt-4 grid gap-3 text-sm text-on-surface-variant md:grid-cols-2">
                            <div>
                              <span className="font-semibold text-on-surface">Status:</span>{" "}
                              {documentStatusLabel(document)}
                            </div>
                            <div>
                              <span className="font-semibold text-on-surface">Category:</span>{" "}
                              {assetKindLabel(document.asset_kind)}
                            </div>
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

                          {document.final_export_blocked ? (
                            <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 text-sm text-on-surface-variant">
                              <div className="font-semibold text-on-surface">
                                Final export blocked at {document.ats_export_gate?.best_score ?? 0}% /{" "}
                                {document.ats_export_gate?.target_score ?? 90}%
                              </div>
                              {document.ats_export_gate?.missing_requirements?.length ? (
                                <div className="mt-3 flex flex-wrap gap-2">
                                  {document.ats_export_gate.missing_requirements.map((requirement) => (
                                    <span
                                      className="rounded-full bg-surface-container-low px-2.5 py-1 text-xs text-on-surface"
                                      key={`${document.document_id}-${requirement}`}
                                    >
                                      {requirement}
                                    </span>
                                  ))}
                                </div>
                              ) : null}
                            </div>
                          ) : null}

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
                              onClick={() => openDocument(document).catch(() => undefined)}
                              type="button"
                            >
                              Preview
                            </button>
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
      ) : activeView === VIEW_CANVAS ? (
        <div className="space-y-6">
          <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h2 className="font-headline text-xl font-bold text-on-surface">
                  Document AI Canvas
                </h2>
                <p className="mt-1 max-w-3xl text-sm leading-7 text-on-surface-variant">
                  Build a personal document knowledge base from your detailed CV, certifications,
                  recommendation letters, and other uploaded evidence. Workspaces can then choose
                  whether to tailor from only the baseline CV, selected source assets, or the full
                  career profile.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <Link
                  className="rounded bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                  to="/workspaces"
                >
                  Review Workspace Scope
                </Link>
                <button
                  className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={canvasSaveState.saving}
                  onClick={saveCanvas}
                  type="button"
                >
                  {canvasSaveState.saving ? "Saving..." : "Save AI Canvas"}
                </button>
              </div>
            </div>
            {canvasSaveState.message ? (
              <p className="mt-4 text-sm text-primary">{canvasSaveState.message}</p>
            ) : null}
            {canvasSaveState.error ? (
              <p className="mt-4 text-sm text-error">{canvasSaveState.error}</p>
            ) : null}
          </section>

          <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <h3 className="font-headline text-lg font-bold text-on-surface">
                    Master Career Profile
                  </h3>
                  <p className="mt-1 text-sm leading-6 text-on-surface-variant">
                    Link the detailed CV or long-form career document that contains the extra
                    bullets, context, and achievements you do not want to lose.
                  </p>
                </div>
                <label className="inline-flex cursor-pointer items-center rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high">
                  <input
                    className="hidden"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) {
                        uploadMasterCareerProfile(file);
                        event.target.value = "";
                      }
                    }}
                    type="file"
                  />
                  {masterProfileUploadState.uploading ? "Uploading..." : "Upload Detailed CV"}
                </label>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-[minmax(0,1fr)_auto]">
                <label className="space-y-2">
                  <span className="block text-sm font-semibold text-on-surface">
                    Linked Source File
                  </span>
                  <FilterSelect
                    onChange={(event) =>
                      updateCanvasField("master_career_profile_asset_id", event.target.value)
                    }
                    value={canvasDraft.master_career_profile_asset_id}
                  >
                    <option value="">Choose an uploaded detailed CV or master profile</option>
                    {cvLikeAssets.map((item) => (
                      <option key={item.asset_id || item.document_id} value={String(item.asset_id || "")}>
                        {item.display_name} ({assetKindLabel(item.asset_kind)})
                      </option>
                    ))}
                  </FilterSelect>
                </label>
                <div className="rounded-lg border border-outline-variant/10 bg-surface p-4 text-sm text-on-surface-variant">
                  This source is used only when a workspace enables broader personalization.
                </div>
              </div>

              {masterProfileUploadState.message ? (
                <p className="mt-4 text-sm text-primary">{masterProfileUploadState.message}</p>
              ) : null}
              {masterProfileUploadState.error ? (
                <p className="mt-4 text-sm text-error">{masterProfileUploadState.error}</p>
              ) : null}

              {masterCareerProfileAsset ? (
                <div className="mt-5 rounded-xl border border-outline-variant/20 bg-surface p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="font-semibold text-on-surface">
                      {masterCareerProfileAsset.display_name}
                    </div>
                    <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
                      {masterCareerProfileAsset.document_type}
                    </span>
                  </div>
                  <div className="mt-3 grid gap-3 text-sm text-on-surface-variant md:grid-cols-3">
                    <div>
                      <span className="font-semibold text-on-surface">Workspace:</span>{" "}
                      {masterCareerProfileAsset.workspace_name || "Shared"}
                    </div>
                    <div>
                      <span className="font-semibold text-on-surface">Created:</span>{" "}
                      {formatDateTime(masterCareerProfileAsset.created_at)}
                    </div>
                    <div>
                      <span className="font-semibold text-on-surface">Imported Text:</span>{" "}
                      {masterCareerProfileAsset.metadata?.source_char_count
                        ? `${masterCareerProfileAsset.metadata.source_char_count} chars`
                        : "Not extracted"}
                    </div>
                  </div>
                </div>
              ) : null}

              <label className="mt-5 block space-y-2">
                <span className="block text-sm font-semibold text-on-surface">
                  Imported Career Context
                </span>
                <textarea
                  className="min-h-56 w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
                  onChange={(event) =>
                    updateCanvasField("master_career_profile_text", event.target.value)
                  }
                  placeholder="Paste or refine the detailed CV text here. This is the long-form career source that AI can consult when a job calls for different bullet points than the baseline CV."
                  value={canvasDraft.master_career_profile_text}
                />
              </label>
            </div>

            <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
              <h3 className="font-headline text-lg font-bold text-on-surface">
                Coverage Checklist
              </h3>
              <p className="mt-1 text-sm leading-6 text-on-surface-variant">
                These sources help the AI move beyond a thin baseline CV and still stay grounded in
                your real history.
              </p>
              <div className="mt-5 space-y-3">
                {canvasCoverage.map((item) => (
                  <div
                    className="rounded-xl border border-outline-variant/15 bg-surface p-4"
                    key={item.label}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-sm font-semibold text-on-surface">{item.label}</div>
                      <span
                        className={[
                          "rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide",
                          item.present
                            ? "bg-primary/10 text-primary"
                            : "bg-surface-container-low text-on-surface-variant",
                        ].join(" ")}
                      >
                        {item.present ? "Ready" : "Missing"}
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-on-surface-variant">{item.detail}</p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
            <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
              <h3 className="font-headline text-lg font-bold text-on-surface">
                Source Asset Selector
              </h3>
              <p className="mt-1 text-sm leading-6 text-on-surface-variant">
                Mark the uploaded assets AI may consult when a workspace uses
                <span className="font-semibold text-on-surface"> Baseline + selected assets</span>.
              </p>
              <div className="mt-5 space-y-3">
                {assetDocuments.length ? (
                  assetDocuments.map((document) => {
                    const isSelected = canvasDraft.ai_canvas_source_asset_ids.includes(
                      String(document.asset_id || ""),
                    );
                    return (
                      <label
                        className="flex cursor-pointer items-start gap-3 rounded-xl border border-outline-variant/15 bg-surface p-4"
                        key={document.document_id}
                      >
                        <input
                          checked={isSelected}
                          className="mt-1 h-4 w-4 rounded border-outline-variant/40 text-primary focus:ring-primary"
                          onChange={() => toggleCanvasSourceAsset(document.asset_id)}
                          type="checkbox"
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <div className="font-semibold text-on-surface">{document.display_name}</div>
                            <span className="rounded-full bg-surface-container-low px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-on-surface-variant">
                              {assetKindLabel(document.asset_kind)}
                            </span>
                          </div>
                          <p className="mt-1 text-sm text-on-surface-variant">
                            {document.workspace_name || "Shared across workspaces"} |{" "}
                            {formatDateTime(document.created_at)}
                          </p>
                        </div>
                      </label>
                    );
                  })
                ) : (
                  <div className="rounded-xl border border-dashed border-outline-variant/20 bg-surface p-6 text-sm text-on-surface-variant">
                    Upload baseline CVs, certifications, or letters in the Asset Library first.
                  </div>
                )}
              </div>
            </div>

            <div className="space-y-6">
              <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
                <h3 className="font-headline text-lg font-bold text-on-surface">
                  Achievement Bank
                </h3>
                <p className="mt-1 text-sm leading-6 text-on-surface-variant">
                  Capture the bullet points and quantified wins that may not fit into the shorter
                  baseline CV but should still be available for job-specific tailoring.
                </p>
                <div className="mt-5 grid gap-4">
                  <label className="space-y-2">
                    <span className="block text-sm font-semibold text-on-surface">
                      Career Highlights
                    </span>
                    <textarea
                      className="min-h-32 w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
                      onChange={(event) =>
                        updateCanvasField("career_highlights_text", event.target.value)
                      }
                      placeholder="Major wins, high-impact projects, quantified outcomes, and patterns you want AI to recognize."
                      value={canvasDraft.career_highlights_text}
                    />
                  </label>
                  <label className="space-y-2">
                    <span className="block text-sm font-semibold text-on-surface">
                      Additional Bullet Bank
                    </span>
                    <textarea
                      className="min-h-40 w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
                      onChange={(event) =>
                        updateCanvasField("bullet_bank_text", event.target.value)
                      }
                      placeholder="Store extra bullets by company, role, or theme. Example: Allianz Technology | led X | automated Y | reduced Z."
                      value={canvasDraft.bullet_bank_text}
                    />
                  </label>
                </div>
              </section>

              <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
                <h3 className="font-headline text-lg font-bold text-on-surface">
                  Story & Letter Notes
                </h3>
                <p className="mt-1 text-sm leading-6 text-on-surface-variant">
                  Save narrative material that helps the AI explain your fit, how you overcome
                  professional hurdles, and what belongs in a motivation letter.
                </p>
                <div className="mt-5 grid gap-4">
                  <label className="space-y-2">
                    <span className="block text-sm font-semibold text-on-surface">
                      Professional Hurdles And Context
                    </span>
                    <textarea
                      className="min-h-32 w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
                      onChange={(event) =>
                        updateCanvasField("professional_hurdles_text", event.target.value)
                      }
                      placeholder="Challenges you solved, difficult transitions, stakeholder situations, and context that makes your achievements more meaningful."
                      value={canvasDraft.professional_hurdles_text}
                    />
                  </label>
                  <label className="space-y-2">
                    <span className="block text-sm font-semibold text-on-surface">
                      Motivation-Letter Notes
                    </span>
                    <textarea
                      className="min-h-32 w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
                      onChange={(event) =>
                        updateCanvasField("motivation_letter_notes", event.target.value)
                      }
                      placeholder="Why you care about certain industries, company types, missions, or problem spaces. Keep this factual and reusable."
                      value={canvasDraft.motivation_letter_notes}
                    />
                  </label>
                </div>
              </section>
            </div>
          </section>

          {selectedCanvasAssets.length ? (
            <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
              <h3 className="font-headline text-lg font-bold text-on-surface">
                Selected Asset Sources
              </h3>
              <div className="mt-4 flex flex-wrap gap-2">
                {selectedCanvasAssets.map((document) => (
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
