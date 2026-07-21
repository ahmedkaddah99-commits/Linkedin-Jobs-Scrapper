import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../../context/SessionContext";
import { useApiResource } from "../../hooks/useApiResource";
import {
  buildInitialSelection,
  groupDocumentsBySourceType,
  sourceAssetKindLabel,
} from "../../lib/careerProfileSources";
import { formatDateTime } from "../../lib/formatters";

const CAREER_ASSET_KINDS = new Set([
  "workspace_cv", "certification", "recommendation_letter",
  "uploaded_document", "motivation_letter", "cover_letter",
  "transcript", "grades", "degree_certificate", "master_career_profile",
]);

function toggleInArray(array, item) {
  const id = String(item || "");
  return array.includes(id)
    ? array.filter((existing) => existing !== id)
    : [...array, id];
}

export default function CareerProfileSourceSelector({
  baselineCvAssetId = "",
  manageDocumentsTo = "/documents",
  onCancel,
  onSave,
  profileName = "Career Profile",
  saving = false,
  selectedAssetIds: externalSelectedIds,
}) {
  const { request } = useSession();

  const { data: documentsPayload, loading } = useApiResource(
    () => request("/documents?limit=500", { timeoutMs: 60000 }),
    [request],
    { cacheKey: "documents:all", staleMs: 30000, backgroundRefresh: true },
  );

  const allDocuments = documentsPayload?.documents || [];

  const eligibleDocuments = useMemo(
    () =>
      allDocuments.filter((item) => {
        const assetKind = String(item.asset_kind || "").trim().toLowerCase();
        return (
          CAREER_ASSET_KINDS.has(assetKind) &&
          String(item.source_origin || "") === "upload"
        );
      }),
    [allDocuments],
  );

  const initialSelection = useMemo(
    () =>
      externalSelectedIds && externalSelectedIds.length
        ? [...externalSelectedIds]
        : buildInitialSelection({
            documents: eligibleDocuments,
            baselineCvAssetId,
          }),
    [
      eligibleDocuments.length,
      baselineCvAssetId,
      JSON.stringify(externalSelectedIds),
    ],
  );

  const groupedDocuments = useMemo(
    () => groupDocumentsBySourceType(eligibleDocuments),
    [eligibleDocuments],
  );

  const [selectedIds, setSelectedIds] = useState(initialSelection);

  useEffect(() => {
    if (baselineCvAssetId && !selectedIds.includes(baselineCvAssetId)) {
      setSelectedIds((prev) => [...prev, baselineCvAssetId]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baselineCvAssetId]);

  const selectedCount = selectedIds.length;
  const totalCount = eligibleDocuments.length;

  function handleToggle(assetId) {
    setSelectedIds((prev) => toggleInArray(prev, assetId));
  }

  function handleSelectAll() {
    setSelectedIds(
      eligibleDocuments.map((doc) => String(doc.asset_id || "")),
    );
  }

  function handleDeselectAll() {
    setSelectedIds([]);
  }

  function handleSave() {
    if (onSave) {
      onSave(selectedIds);
    }
  }

  if (loading) {
    return (
      <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        <div className="space-y-4">
          <div className="h-7 w-48 animate-pulse rounded-full bg-surface-container" />
          <div className="h-4 w-96 animate-pulse rounded-full bg-surface-container" />
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="h-20 animate-pulse rounded-2xl bg-surface-container" />
            <div className="h-20 animate-pulse rounded-2xl bg-surface-container" />
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-primary">
            Source Documents
          </div>
          <h2 className="mt-3 font-headline text-xl font-bold text-on-surface">
            Select source documents for {profileName}
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-on-surface-variant">
            These documents will be analysed for career evidence. Runr
            extracts achievements, skills, certifications, projects, and
            experience from the sources you select. The more relevant sources
            you include, the stronger your career profile becomes.
          </p>
        </div>
        <Link
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high shrink-0"
          to={manageDocumentsTo}
        >
          Upload more documents
          <span className="material-symbols-outlined text-[16px]">upload</span>
        </Link>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <span className="rounded-xl border border-outline-variant/15 bg-surface px-4 py-2 text-sm font-semibold text-on-surface">
          {selectedCount} of {totalCount} selected
        </span>
        <button
          className="inline-flex items-center gap-1.5 rounded-xl bg-surface-container-low px-3 py-1.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
          onClick={handleSelectAll}
          type="button"
        >
          <span className="material-symbols-outlined text-[16px]">select_all</span>
          Select all
        </button>
        <button
          className="inline-flex items-center gap-1.5 rounded-xl bg-surface-container-low px-3 py-1.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
          onClick={handleDeselectAll}
          type="button"
        >
          <span className="material-symbols-outlined text-[16px]">deselect</span>
          Deselect all
        </button>
      </div>

      {totalCount === 0 ? (
        <div className="mt-6 rounded-2xl border border-dashed border-outline-variant/20 bg-surface p-8 text-center">
          <span className="material-symbols-outlined text-[2.5rem] text-on-surface-variant">
            cloud_upload
          </span>
          <p className="mt-3 text-sm leading-6 text-on-surface-variant">
            No documents found. Upload a baseline CV or supporting documents
            in the Asset Library first.
          </p>
          <Link
            className="mt-4 inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90"
            to={manageDocumentsTo}
          >
            Go to Asset Library
            <span className="material-symbols-outlined text-[16px]">folder_open</span>
          </Link>
        </div>
      ) : (
        <div className="mt-6 space-y-5">
          {groupedDocuments.map((group) => (
            <SourceGroupSection
              baselineCvAssetId={baselineCvAssetId}
              formatDateTime={formatDateTime}
              group={group}
              key={group.id}
              onToggle={handleToggle}
              selectedIds={selectedIds}
            />
          ))}
        </div>
      )}

      <div className="mt-6 rounded-2xl border border-primary/20 bg-primary/5 p-5">
        <div className="flex items-start gap-3">
          <span className="material-symbols-outlined mt-0.5 text-[20px] text-primary">
            info
          </span>
          <div>
            <div className="text-sm font-semibold text-on-surface">
              Selected sources will be analysed for career evidence
            </div>
            <p className="mt-1 text-sm leading-6 text-on-surface-variant">
              Runr extracts factual evidence such as role titles, employer
              names, date ranges, achievements, skills, certifications, and
              project descriptions from each source you select. You will
              review and confirm extracted evidence in the next step before
              it becomes part of your career profile.
            </p>
          </div>
        </div>
      </div>

      <div className="mt-6 flex flex-wrap gap-3">
        <button
          className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          disabled={saving}
          onClick={handleSave}
          type="button"
        >
          {saving ? "Saving..." : "Save source selection"}
        </button>
        {onCancel ? (
          <button
            className="inline-flex items-center gap-2 rounded-xl bg-surface-container-low px-5 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            disabled={saving}
            onClick={onCancel}
            type="button"
          >
            Cancel
          </button>
        ) : null}
      </div>
    </section>
  );
}

function SourceGroupSection({
  baselineCvAssetId,
  formatDateTime,
  group,
  onToggle,
  selectedIds,
}) {
  const selectedInGroup = group.documents.filter((doc) =>
    selectedIds.includes(String(doc.asset_id || "")),
  );

  return (
    <section className="rounded-2xl border border-outline-variant/15 bg-surface p-5">
      <div className="flex flex-wrap items-center gap-3">
        <span className="material-symbols-outlined text-[20px] text-on-surface-variant">
          {group.icon}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-headline text-base font-bold text-on-surface">
              {group.label}
            </h3>
            <span className="rounded-full bg-surface-container-low px-2.5 py-0.5 text-[11px] font-semibold text-on-surface-variant">
              {selectedInGroup.length}/{group.documents.length} selected
            </span>
          </div>
          <p className="mt-1 text-sm leading-6 text-on-surface-variant">
            {group.description}
          </p>
        </div>
      </div>
      <div className="mt-4 space-y-2">
        {group.documents.map((doc) => {
          const assetId = String(doc.asset_id || "");
          const isSelected = selectedIds.includes(assetId);
          const isBaseline =
            baselineCvAssetId && assetId === String(baselineCvAssetId);
          return (
            <label
              className={[
                "flex cursor-pointer items-start gap-3 rounded-xl border p-3.5 transition-colors",
                isSelected
                  ? "border-primary/30 bg-primary/10"
                  : "border-outline-variant/10 bg-surface-container-lowest hover:bg-surface-container-low",
              ].join(" ")}
              key={doc.document_id}
            >
              <input
                checked={isSelected}
                className="mt-0.5 h-4 w-4 rounded border-outline-variant/40 text-primary focus:ring-primary"
                onChange={() => onToggle(assetId)}
                type="checkbox"
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="font-semibold text-sm text-on-surface">
                    {doc.display_name || doc.file_name || "Unnamed document"}
                  </div>
                  <span className="rounded-full bg-surface-container-low px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-on-surface-variant">
                    {sourceAssetKindLabel(doc.asset_kind)}
                  </span>
                  {isBaseline ? (
                    <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-semibold text-primary">
                      Baseline CV
                    </span>
                  ) : null}
                </div>
                <div className="mt-1 text-xs text-on-surface-variant">
                  {[
                    doc.workspace_name || "Shared",
                    doc.created_at ? formatDateTime(doc.created_at) : "",
                  ]
                    .filter(Boolean)
                    .join(" | ")}
                </div>
              </div>
            </label>
          );
        })}
      </div>
    </section>
  );
}
