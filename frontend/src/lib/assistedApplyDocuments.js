const SUPPORTED_MIME_TYPES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

const SUPPORTED_ASSET_KINDS = new Set([
  "workspace_cv",
  "cover_letter",
  "motivation_letter",
  "uploaded_document",
  "certification",
  "recommendation_letter",
  "degree_diploma",
  "academic_transcript",
  "language_certificate",
  "employment_certificate",
  "portfolio_work_sample",
  "other_supporting_document",
]);

const ROLE_DOCUMENT_KINDS = new Set([
  "generated_cv", "applied_cv", "cover_letter", "motivation_letter",
  "academic_transcript", "certification", "language_certificate",
  "employment_certificate", "supporting_document",
]);

function normalizedPurposes(document) {
  const metadata = document?.metadata && typeof document.metadata === "object"
    ? document.metadata
    : {};
  const applicationMetadata = document?.application_document?.metadata && typeof document.application_document.metadata === "object"
    ? document.application_document.metadata
    : {};
  const purposes = metadata.purposes || applicationMetadata.purposes || [];
  return new Set(Array.isArray(purposes) ? purposes.map((item) => String(item).trim().toLowerCase()) : []);
}

function inferredMimeType(document) {
  const explicit = String(document?.content_type || document?.mime_type || "").trim().toLowerCase();
  const name = String(document?.file_name || document?.path || document?.display_name || "").trim().toLowerCase();
  if (explicit && SUPPORTED_MIME_TYPES.has(explicit)) return explicit;
  const assetKind = String(document?.asset_kind || "").trim().toLowerCase();
  const status = String(document?.status || "").trim().toLowerCase();
  const canNormalizeLegacyDocx = assetKind === "workspace_cv"
    && (!status || status === "ready")
    && (!explicit || explicit === "application/octet-stream")
    && name.endsWith(".docx");
  if (explicit && !canNormalizeLegacyDocx) return "";
  if (name.endsWith(".pdf")) return "application/pdf";
  if (name.endsWith(".docx")) return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  return "";
}

export function isApplicationDocument(document, role = {}) {
  const assetKind = String(document?.asset_kind || "").trim().toLowerCase();
  const purposes = normalizedPurposes(document);
  const status = String(document?.status || "").trim().toLowerCase();
  const isLegacyReadyWorkspaceCv = assetKind === "workspace_cv"
    && purposes.size === 0
    && (!status || status === "ready");
  const documentId = String(document?.document_id || "").trim();
  const roleRunId = String(role?.run_id || "").trim();
  const roleJobId = String(role?.job_id || "").trim();
  const roleArtifact = Boolean(roleRunId && roleJobId) && documentId.startsWith("artifact::") &&
    String(document?.run_id || "").trim() === roleRunId &&
    String(document?.job_id || "").trim() === roleJobId &&
    ROLE_DOCUMENT_KINDS.has(assetKind) && !document?.final_export_blocked;
  return Boolean(
    (roleArtifact || (documentId.startsWith("asset::")
      && SUPPORTED_ASSET_KINDS.has(assetKind)
      && (purposes.has("include_in_applications") || isLegacyReadyWorkspaceCv)
      && !purposes.has("private_never_attach")))
      && inferredMimeType(document),
  );
}

export function candidateDocuments(documents, role = {}) {
  const seen = new Set();
  return (Array.isArray(documents) ? documents : []).filter((document) => {
    const documentId = String(document?.document_id || "").trim();
    if (!isApplicationDocument(document, role) || seen.has(documentId)) return false;
    seen.add(documentId);
    return true;
  });
}

export function applicationRoleDocuments(documents, role = {}) {
  const runId = String(role?.run_id || "").trim();
  const jobId = String(role?.job_id || "").trim();
  if (!runId || !jobId) return [];
  return candidateDocuments(documents, role).filter((document) =>
    String(document?.document_id || "").startsWith("artifact::")
      && String(document?.run_id || "").trim() === runId
      && String(document?.job_id || "").trim() === jobId,
  );
}

function documentKind(document) {
  const kind = String(document?.asset_kind || "").trim().toLowerCase();
  if (["workspace_cv", "generated_cv", "applied_cv"].includes(kind)) return "cv";
  if (["cover_letter", "motivation_letter"].includes(kind)) return "cover_letter";
  return "supporting_document";
}

function extensionRank(document) {
  const name = String(document?.file_name || document?.path || document?.display_name || "").toLowerCase();
  return name.endsWith(".pdf") || String(document?.content_type || "").toLowerCase() === "application/pdf" ? 0 : 1;
}

export function defaultSelectedDocumentIds(documents, role = {}) {
  const candidates = candidateDocuments(documents, role);
  if (candidates.length === 1) return [candidates[0].document_id];
  const roleCvs = candidates.filter((document) => documentKind(document) === "cv" && String(document.document_id).startsWith("artifact::"));
  const primaryCv = (roleCvs.length ? roleCvs : candidates.filter((document) => documentKind(document) === "cv"))
    .sort((left, right) => extensionRank(left) - extensionRank(right))[0];
  return [
    ...(primaryCv ? [primaryCv.document_id] : []),
    ...candidates.filter((document) => documentKind(document) !== "cv").map((document) => document.document_id),
  ];
}
