import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { formatDateTime, labelize } from "../lib/formatters";

const DOCUMENTS_REQUEST_TIMEOUT_MS = 60000;
const RESUMES_TAB = "resumes";
const COVER_LETTERS_TAB = "cover_letters";
const MASTER_CV_TAB = "master_cv";
const TEMPLATES_TAB = "templates";

const tabs = [
  { id: RESUMES_TAB, label: "Resumes", icon: "description" },
  { id: COVER_LETTERS_TAB, label: "Motivation Letters", icon: "article" },
  { id: MASTER_CV_TAB, label: "Master CV", icon: "auto_awesome" },
  { id: TEMPLATES_TAB, label: "Templates", icon: "dashboard_customize" },
];

function normalizedDocumentValue(document, key) {
  return String(document?.[key] || "").trim().toLowerCase();
}

function documentTab(document) {
  const assetKind = normalizedDocumentValue(document, "asset_kind");
  const sourceOrigin = normalizedDocumentValue(document, "source_origin");
  if (sourceOrigin !== "upload") return "";
  if (assetKind === "workspace_cv") return RESUMES_TAB;
  if (["cover_letter", "motivation_letter"].includes(assetKind)) {
    return COVER_LETTERS_TAB;
  }
  return "";
}

function documentName(document) {
  return document?.display_name || document?.document_name || document?.file_name || "Untitled document";
}

function documentExtension(document) {
  const value = document?.content_type || document?.file_name || documentName(document);
  const contentType = String(value || "").toLowerCase();
  if (contentType.includes("pdf") || /\.pdf(?:$|\?)/.test(contentType)) return "PDF";
  if (contentType.includes("word") || /\.docx?(?:$|\?)/.test(contentType)) return "DOCX";
  if (contentType.includes("text") || /\.txt(?:$|\?)/.test(contentType)) return "TXT";
  const extension = contentType.match(/\.([a-z0-9]{2,5})(?:$|\?)/)?.[1];
  return extension ? extension.toUpperCase() : "FILE";
}

function documentSource(document) {
  return document?.is_generated || document?.source_origin === "generated_run" ? "Generated" : "Uploaded";
}

function documentStatus(document) {
  const status = String(document?.display_status || document?.status || "ready").trim().toLowerCase();
  if (status === "export_blocked") return "Needs review";
  if (status === "ready" || status === "completed") return "Ready";
  return labelize(status || "ready");
}

function documentDate(document) {
  return document?.updated_at || document?.last_edited_at || document?.created_at || "";
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

function Icon({ children, className = "" }) {
  return <span className={["material-symbols-outlined", className].join(" ")}>{children}</span>;
}

function ActionCard({ description, icon, label, onClick }) {
  return (
    <button className="documents-action-card" onClick={onClick} type="button">
      <span className="documents-action-card__icon"><Icon>{icon}</Icon></span>
      <span className="documents-action-card__copy">
        <strong>{label}</strong>
        <span>{description}</span>
      </span>
      <Icon className="documents-action-card__add">add</Icon>
    </button>
  );
}

function EmptyState({ tab, onCreate }) {
  const copy = tab === COVER_LETTERS_TAB
    ? {
      title: "Create your first motivation letter!",
      body: "Get started with a personalized motivation letter that highlights your qualifications.",
    }
    : tab === TEMPLATES_TAB
      ? {
        title: "Create your first template!",
        body: "Build a reusable document template for your next application.",
      }
      : {
        title: "Create your first resume!",
        body: "Upload a resume or start tailoring one for your next opportunity.",
      };

  return (
    <div className="documents-empty-state">
      <span className="documents-empty-state__icon"><Icon>{tab === TEMPLATES_TAB ? "dashboard_customize" : "note_add"}</Icon></span>
      <strong>{copy.title}</strong>
      <p>{copy.body}</p>
      <button className="documents-link-button" onClick={onCreate} type="button">Get started</button>
    </div>
  );
}

export default function DocumentsPage() {
  const { request, resolvePath } = useSession();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const uploadInputRef = useRef(null);
  const [activeTab, setActiveTab] = useState(() => requestedTab === COVER_LETTERS_TAB ? COVER_LETTERS_TAB : RESUMES_TAB);
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState("All");
  const [selectedIds, setSelectedIds] = useState([]);
  const [openMenuId, setOpenMenuId] = useState("");
  const [previewDocument, setPreviewDocument] = useState(null);
  const [uploadKind, setUploadKind] = useState("workspace_cv");
  const [uploadState, setUploadState] = useState({ uploading: false, message: "", error: "" });
  const [actionState, setActionState] = useState({ message: "", error: "" });

  useEffect(() => {
    if (requestedTab === COVER_LETTERS_TAB) setActiveTab(COVER_LETTERS_TAB);
  }, [requestedTab]);

  const {
    data: documentsPayload,
    loading,
    error,
    refresh,
  } = useApiResource(
    () => request("/documents?limit=500&include_preview_profile=false", { timeoutMs: DOCUMENTS_REQUEST_TIMEOUT_MS }),
    [request],
    { cacheKey: "documents:all", staleMs: 30000, backgroundRefresh: true },
  );

  const allDocuments = documentsPayload?.documents || [];
  const visibleDocuments = useMemo(() => {
    const query = search.trim().toLowerCase();
    return allDocuments.filter((document) => {
      if (documentTab(document) !== activeTab) return false;
      if (sourceFilter !== "All" && documentSource(document) !== sourceFilter) return false;
      if (!query) return true;
      return [
        documentName(document),
        document.document_type,
        document.job_title,
        document.company,
        document.workspace_name,
        documentStatus(document),
      ].filter(Boolean).some((value) => String(value).toLowerCase().includes(query));
    });
  }, [activeTab, allDocuments, search, sourceFilter]);

  const selectedDocuments = useMemo(
    () => allDocuments.filter((document) => selectedIds.includes(document.document_id)),
    [allDocuments, selectedIds],
  );
  const allVisibleSelected = visibleDocuments.length > 0 && visibleDocuments.every((document) => selectedIds.includes(document.document_id));

  useEffect(() => {
    setSelectedIds((current) => current.filter((id) => allDocuments.some((document) => document.document_id === id)));
  }, [allDocuments]);

  useEffect(() => {
    function closeMenu(event) {
      if (!event.target.closest(".documents-row-menu")) setOpenMenuId("");
    }
    document.addEventListener("pointerdown", closeMenu);
    return () => document.removeEventListener("pointerdown", closeMenu);
  }, []);

  useEffect(() => {
    if (!previewDocument) return undefined;
    function closeOnEscape(event) {
      if (event.key === "Escape") setPreviewDocument(null);
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [previewDocument]);

  function openUpload(kind) {
    setUploadKind(kind);
    uploadInputRef.current?.click();
  }

  async function uploadDocument(file) {
    if (!file) return;
    setUploadState({ uploading: true, message: "", error: "" });
    try {
      const params = new URLSearchParams({
        asset_kind: uploadKind,
        display_name: file.name,
        purposes: "extract_career_facts,include_in_applications",
      });
      const formData = new FormData();
      formData.append("document_file", file);
      await request(`/documents/upload?${params.toString()}`, { method: "POST", body: formData });
      await refresh();
      setUploadState({ uploading: false, message: `${file.name} is now in Documents.`, error: "" });
    } catch (uploadError) {
      setUploadState({ uploading: false, message: "", error: uploadError.message || "Unable to upload this document." });
    }
  }

  function toggleSelection(documentId) {
    setSelectedIds((current) => current.includes(documentId)
      ? current.filter((id) => id !== documentId)
      : [...current, documentId]);
  }

  function toggleAllVisible() {
    if (allVisibleSelected) {
      setSelectedIds((current) => current.filter((id) => !visibleDocuments.some((document) => document.document_id === id)));
      return;
    }
    setSelectedIds((current) => [...new Set([...current, ...visibleDocuments.map((document) => document.document_id)])]);
  }

  async function downloadDocument(document) {
    if (!document.download_url) {
      setActionState({ message: "This document is still being prepared.", error: "" });
      return;
    }
    try {
      const blob = await request(document.download_url, { responseType: "blob" });
      triggerDownload(blob, documentName(document));
      setOpenMenuId("");
    } catch (downloadError) {
      setActionState({ message: "", error: downloadError.message || "Unable to download this document." });
    }
  }

  async function deleteDocument(document) {
    const assetId = String(document?.asset_id || "").trim();
    if (!assetId) {
      setActionState({ message: "Generated documents cannot be deleted here.", error: "" });
      setOpenMenuId("");
      return;
    }
    if (!window.confirm(`Delete ${documentName(document)}? This cannot be undone.`)) return;
    try {
      await request(`/documents/assets/${encodeURIComponent(assetId)}`, { method: "DELETE" });
      setSelectedIds((current) => current.filter((id) => id !== document.document_id));
      await refresh();
      setActionState({ message: `${documentName(document)} was deleted.`, error: "" });
      setOpenMenuId("");
    } catch (deleteError) {
      setActionState({ message: "", error: deleteError.message || "Unable to delete this document." });
    }
  }

  async function deleteSelected() {
    const deletable = selectedDocuments.filter((document) => String(document.asset_id || "").trim());
    if (!deletable.length) {
      setActionState({ message: "Only uploaded documents can be deleted here.", error: "" });
      return;
    }
    if (!window.confirm(`Delete ${deletable.length} selected document${deletable.length === 1 ? "" : "s"}? This cannot be undone.`)) return;
    try {
      await Promise.all(deletable.map((document) => request(`/documents/assets/${encodeURIComponent(document.asset_id)}`, { method: "DELETE" })));
      setSelectedIds([]);
      await refresh();
      setActionState({ message: `Deleted ${deletable.length} document${deletable.length === 1 ? "" : "s"}.`, error: "" });
    } catch (deleteError) {
      setActionState({ message: "", error: deleteError.message || "Unable to delete the selected documents." });
    }
  }

  function createCoverLetter() {
    setActiveTab(COVER_LETTERS_TAB);
    openUpload("cover_letter");
  }

  function createResume() {
    setActiveTab(RESUMES_TAB);
    openUpload("workspace_cv");
  }

  function createTemplate() {
    navigate("/cv-studio");
  }

  function editDocument(document) {
    const assetId = String(document?.asset_id || "").trim();
    if (assetId && String(document?.asset_kind || "").trim().toLowerCase() === "workspace_cv") {
      navigate(`/documents/assets/${encodeURIComponent(assetId)}/edit`);
      return;
    }
    setPreviewDocument(document);
  }

  function createMasterCv() {
    navigate("/master-cv");
  }

  function answerQuestions() {
    navigate("/career-evidence");
  }

  return (
    <div className="documents-page">
      <input
        accept=".pdf,.doc,.docx,.txt"
        className="documents-upload-input"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          void uploadDocument(file);
        }}
        ref={uploadInputRef}
        type="file"
      />

      <header className="documents-page__header">
        <h1>My Documents</h1>
        <p>Manage and tailor all of your job search documents here.</p>
      </header>

      <section aria-label="Create a document" className="documents-action-grid">
        <ActionCard description="Craft and tailor to a job description" icon="description" label="New Resume" onClick={createResume} />
        <ActionCard description="Create and customize with AI" icon="article" label="New Motivation Letter" onClick={createCoverLetter} />
        <ActionCard description="Capture the complete record of your career" icon="auto_awesome" label="Master CV" onClick={createMasterCv} />
        <ActionCard description="Create a reusable cover letter template" icon="dashboard_customize" label="New Template" onClick={createTemplate} />
        <ActionCard description="Generate tailored responses to application questions" icon="question_answer" label="Question Response" onClick={answerQuestions} />
      </section>

      <nav aria-label="Document types" className="documents-tabs">
        {tabs.map((tab) => (
          <button
            className={activeTab === tab.id ? "is-active" : ""}
            key={tab.id}
            onClick={() => {
              if (tab.id === MASTER_CV_TAB) {
                navigate("/master-cv");
                return;
              }
              setActiveTab(tab.id);
              setSelectedIds([]);
              setSourceFilter("All");
              setOpenMenuId("");
            }}
            type="button"
          >
            <Icon>{tab.icon}</Icon>
            {tab.label}
          </button>
        ))}
      </nav>

      <section className="documents-library" aria-label={`${tabs.find((tab) => tab.id === activeTab)?.label || "Documents"} library`}>
        <div className="documents-toolbar">
          <div className="documents-toolbar__selection">
            {selectedIds.length ? <button className="documents-selection-clear" onClick={() => setSelectedIds([])} type="button"><Icon>close</Icon>{selectedIds.length} selected</button> : <span>0 selected</span>}
            <span className="documents-toolbar__divider" />
            <button className="documents-delete-button" disabled={!selectedIds.length} onClick={() => void deleteSelected()} type="button"><Icon>delete_outline</Icon>Delete</button>
          </div>
          <div className="documents-toolbar__actions">
            <button className="documents-upload-button" disabled={uploadState.uploading} onClick={() => openUpload(activeTab === COVER_LETTERS_TAB ? "cover_letter" : "workspace_cv")} type="button"><Icon>upload</Icon>{uploadState.uploading ? "Uploading" : "Upload"}</button>
            {activeTab === RESUMES_TAB ? (
              <select aria-label="Filter resumes" className="documents-filter-select" onChange={(event) => setSourceFilter(event.target.value)} value={sourceFilter}>
                <option>All</option>
                <option>Generated</option>
                <option>Uploaded</option>
              </select>
            ) : null}
            <label className="documents-search">
              <Icon>search</Icon>
              <input onChange={(event) => setSearch(event.target.value)} placeholder="Search" type="search" value={search} />
            </label>
          </div>
        </div>

        {uploadState.message ? <p className="documents-feedback documents-feedback--success">{uploadState.message}</p> : null}
        {uploadState.error ? <p className="documents-feedback documents-feedback--error">{uploadState.error}</p> : null}
        {actionState.message ? <p className="documents-feedback documents-feedback--success">{actionState.message}</p> : null}
        {actionState.error ? <p className="documents-feedback documents-feedback--error">{actionState.error}</p> : null}

        {activeTab !== TEMPLATES_TAB ? (
          <div className="documents-table-wrap">
            <div className="documents-table__head">
              <label className="documents-checkbox-cell"><input aria-label="Select all visible documents" checked={allVisibleSelected} onChange={toggleAllVisible} type="checkbox" /><span> {activeTab === COVER_LETTERS_TAB ? "MOTIVATION LETTER NAME" : "RESUME NAME"}</span></label>
              <span>CREATED</span>
              <span>LAST EDITED</span>
              <span>ACTIONS</span>
            </div>
            {loading ? <div className="documents-table-message">Loading documents…</div> : error ? <div className="documents-table-message documents-table-message--error">{error}</div> : visibleDocuments.length ? visibleDocuments.map((document) => {
              const selected = selectedIds.includes(document.document_id);
              return (
                <div className={["documents-table__row", selected ? "is-selected" : ""].join(" ")} key={document.document_id}>
                  <div className="documents-name-cell">
                    <input aria-label={`Select ${documentName(document)}`} checked={selected} onChange={() => toggleSelection(document.document_id)} type="checkbox" />
                    <button className="documents-file-icon" onClick={() => setPreviewDocument(document)} title="Preview document" type="button"><Icon>{documentExtension(document) === "PDF" ? "picture_as_pdf" : "description"}</Icon></button>
                    <button className="documents-name-button" onClick={() => setPreviewDocument(document)} type="button">
                      <strong>{documentName(document)}</strong>
                      <span><em className={documentStatus(document) === "Ready" ? "is-ready" : ""}>{documentSource(document)}</em><em>{documentExtension(document)}</em>{document.asset_kind === "workspace_cv" ? <em>Default</em> : null}</span>
                    </button>
                  </div>
                  <span className="documents-date-cell">{formatDateTime(document.created_at)}</span>
                  <span className="documents-date-cell">{formatDateTime(documentDate(document))}</span>
                  <div className="documents-row-actions">
                    <button className="documents-edit-button" onClick={() => editDocument(document)} type="button"><Icon>edit</Icon>Edit</button>
                    <span className="documents-row-actions__divider" />
                    <div className="documents-row-menu">
                      <button aria-expanded={openMenuId === document.document_id} className="documents-more-button" onClick={() => setOpenMenuId((current) => current === document.document_id ? "" : document.document_id)} type="button">More <Icon>expand_more</Icon></button>
                      {openMenuId === document.document_id ? <div className="documents-row-menu__popup"><button onClick={() => setPreviewDocument(document)} type="button"><Icon>visibility</Icon>Preview</button><button onClick={() => void downloadDocument(document)} type="button"><Icon>download</Icon>Download</button><button onClick={() => void deleteDocument(document)} type="button"><Icon>delete_outline</Icon>Delete</button></div> : null}
                    </div>
                  </div>
                </div>
              );
            }) : <EmptyState onCreate={activeTab === COVER_LETTERS_TAB ? createCoverLetter : createResume} tab={activeTab} />}
          </div>
        ) : (
          <div className="documents-table-wrap"><EmptyState onCreate={createTemplate} tab={TEMPLATES_TAB} /></div>
        )}
      </section>

      {previewDocument ? (
        <div className="documents-preview-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setPreviewDocument(null); }}>
          <section aria-label={`${documentName(previewDocument)} preview`} aria-modal="true" className="documents-preview-modal" role="dialog">
            <header className="documents-preview-modal__header">
              <div className="documents-preview-modal__title"><span className="documents-preview-modal__icon"><Icon>description</Icon></span><div><h2>{documentTab(previewDocument) === COVER_LETTERS_TAB ? "Motivation Letter Preview" : "Resume Preview"}</h2><p>Review your document before using it for an application.</p></div></div>
              <button aria-label="Close preview" className="documents-preview-close" onClick={() => setPreviewDocument(null)} type="button"><Icon>close</Icon></button>
            </header>
            <div className="documents-preview-modal__body">
              {previewDocument.preview_url || previewDocument.download_url ? <iframe title={`Preview of ${documentName(previewDocument)}`} src={resolvePath(previewDocument.preview_url || previewDocument.download_url)} /> : <div className="documents-preview-unavailable"><Icon>description</Icon><strong>Preview unavailable</strong><p>Download the document to open it in your preferred editor.</p></div>}
            </div>
            <footer className="documents-preview-modal__footer"><span>{documentName(previewDocument)}</span><button className="documents-upload-button" onClick={() => void downloadDocument(previewDocument)} type="button"><Icon>download</Icon>Download</button></footer>
          </section>
        </div>
      ) : null}
    </div>
  );
}
