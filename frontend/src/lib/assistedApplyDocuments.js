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
  if (explicit) return SUPPORTED_MIME_TYPES.has(explicit) ? explicit : "";
  const name = String(document?.file_name || document?.path || document?.display_name || "").trim().toLowerCase();
  if (name.endsWith(".pdf")) return "application/pdf";
  if (name.endsWith(".docx")) return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  return "";
}

export function isApplicationDocument(document) {
  const assetKind = String(document?.asset_kind || "").trim().toLowerCase();
  const purposes = normalizedPurposes(document);
  const status = String(document?.status || "").trim().toLowerCase();
  const isLegacyReadyWorkspaceCv = assetKind === "workspace_cv"
    && purposes.size === 0
    && (!status || status === "ready");
  return Boolean(
    String(document?.document_id || "").startsWith("asset::")
      && SUPPORTED_ASSET_KINDS.has(assetKind)
      && (purposes.has("include_in_applications") || isLegacyReadyWorkspaceCv)
      && !purposes.has("private_never_attach")
      && inferredMimeType(document),
  );
}

export function candidateDocuments(documents) {
  const seen = new Set();
  return (Array.isArray(documents) ? documents : []).filter((document) => {
    const documentId = String(document?.document_id || "").trim();
    if (!isApplicationDocument(document) || seen.has(documentId)) return false;
    seen.add(documentId);
    return true;
  });
}

export function defaultSelectedDocumentIds(documents) {
  const candidates = candidateDocuments(documents);
  if (candidates.length === 1) return [candidates[0].document_id];
  const primaryCv = candidates.find((document) => String(document.asset_kind || "").trim().toLowerCase() === "workspace_cv");
  return primaryCv ? [primaryCv.document_id] : [];
}
