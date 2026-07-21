const ASSET_KIND_GROUPS = {
  cv: {
    label: "CVs & Resumes",
    icon: "description",
    description: "Your baseline CV and any alternate versions you have uploaded.",
    kinds: ["workspace_cv"],
  },
  certification: {
    label: "Certificates & Licenses",
    icon: "verified",
    description: "Professional certifications, licenses, training certificates, and degrees.",
    kinds: ["certification", "degree_certificate"],
  },
  recommendation: {
    label: "Recommendations & References",
    icon: "reviews",
    description: "Recommendation letters, reference letters, and testimonials.",
    kinds: ["recommendation_letter"],
  },
  letter: {
    label: "Cover & Motivation Letters",
    icon: "mail",
    description: "Cover letters, motivation letters, and application statements.",
    kinds: ["motivation_letter", "cover_letter"],
  },
  supporting: {
    label: "Supporting Documents",
    icon: "upload_file",
    description: "Uploaded documents, project docs, portfolios, reviews, screenshots, scans, and images.",
    kinds: ["uploaded_document", "transcript", "grades"],
  },
  master_profile: {
    label: "Master Career Profiles",
    icon: "person_book",
    description: "Previously saved master career profiles that contain compiled evidence.",
    kinds: ["master_career_profile"],
  },
};

const ASSET_KIND_TO_GROUP = {};
Object.entries(ASSET_KIND_GROUPS).forEach(([groupId, group]) => {
  group.kinds.forEach((kind) => {
    ASSET_KIND_TO_GROUP[kind] = groupId;
  });
});

function normalizeString(value) {
  return String(value || "").trim();
}

function normalizeStringList(values) {
  return (Array.isArray(values) ? values : [])
    .map((item) => normalizeString(item))
    .filter(Boolean);
}

/**
 * Group an asset document into its suggested source type group.
 * Falls back to checking display_name and file extension.
 */
export function suggestSourceGroup(document) {
  const assetKind = normalizeString(document?.asset_kind).toLowerCase();
  if (ASSET_KIND_TO_GROUP[assetKind]) {
    return ASSET_KIND_TO_GROUP[assetKind];
  }

  const displayName = normalizeString(document?.display_name || document?.file_name || "").toLowerCase();
  const extension = normalizeString(document?.file_extension || document?.extension || "").toLowerCase();

  // Heuristic: check display name
  if (/\b(cv|resume|lebenslauf|curriculum)\b/.test(displayName)) return "cv";
  if (/\b(certif|license|licence|diploma|degree|zeugnis|zertifikat)\b/.test(displayName)) return "certification";
  if (/\b(recommend|reference|referenz|empfehlung|testimonial)\b/.test(displayName)) return "recommendation";
  if (/\b(cover|motivation|anschreiben|bewerbung|statement)\b/.test(displayName)) return "letter";
  if (/\b(screenshot|scan|photo|image|bild|screencap)\b/.test(displayName)) return "supporting";
  if (/\b(portfolio|project|review|report)\b/.test(displayName)) return "supporting";

  // Heuristic: check extension (image files likely screenshots/scans)
  if (["png", "jpg", "jpeg", "gif", "webp", "bmp", "tiff"].includes(extension)) return "supporting";

  return "supporting";
}

/**
 * Group a list of asset documents by suggested source type.
 * Returns an ordered array of group objects with their documents.
 */
export function groupDocumentsBySourceType(documents = []) {
  const groupOrder = ["cv", "certification", "recommendation", "letter", "supporting", "master_profile"];
  const groups = new Map();

  documents.forEach((doc) => {
    const groupId = suggestSourceGroup(doc);
    if (!groups.has(groupId)) {
      groups.set(groupId, []);
    }
    groups.get(groupId).push(doc);
  });

  return groupOrder
    .filter((groupId) => groups.has(groupId))
    .map((groupId) => ({
      id: groupId,
      ...ASSET_KIND_GROUPS[groupId],
      documents: groups.get(groupId),
    }));
}

/**
 * Build the initial set of selected asset IDs, preselecting the baseline CV.
 */
export function buildInitialSelection({ documents = [], baselineCvAssetId = "" } = {}) {
  const ids = new Set();
  const baselineId = normalizeString(baselineCvAssetId);
  if (baselineId) {
    ids.add(baselineId);
  }
  // Also preselect any workspace_cv documents if no baseline is set
  if (!baselineId) {
    documents.forEach((doc) => {
      const kind = normalizeString(doc?.asset_kind).toLowerCase();
      if (kind === "workspace_cv") {
        ids.add(normalizeString(doc.asset_id));
      }
    });
  }
  return Array.from(ids);
}

/**
 * Human-readable label for an asset kind.
 */
export function sourceAssetKindLabel(assetKind) {
  const normalized = normalizeString(assetKind).toLowerCase();
  if (normalized === "workspace_cv") return "Baseline CV";
  if (normalized === "certification") return "Certification";
  if (normalized === "degree_certificate") return "Degree Certificate";
  if (normalized === "recommendation_letter") return "Recommendation Letter";
  if (normalized === "motivation_letter") return "Motivation Letter";
  if (normalized === "cover_letter") return "Cover Letter";
  if (normalized === "uploaded_document") return "Supporting Document";
  if (normalized === "master_career_profile") return "Master Career Profile";
  if (normalized === "transcript") return "Transcript";
  if (normalized === "grades") return "Grade Report";
  // Labelize fallback
  return normalized
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * Get the group metadata for a given group ID.
 */
export function getSourceGroupMeta(groupId) {
  return ASSET_KIND_GROUPS[groupId] || null;
}

export { ASSET_KIND_GROUPS };
