export const ACQUISITION_GET_ENDPOINTS = Object.freeze([
  "/admin/acquisition/overview",
  "/admin/acquisition/sources",
  "/admin/acquisition/jobs",
  "/admin/acquisition/connectors/capabilities",
]);

export const JOB_FILTER_KEYS = Object.freeze([
  "search",
  "function",
  "subfunction",
  "employment_type",
  "workplace",
  "location",
  "language",
  "seniority",
  "freshness",
  "completeness_state",
  "warning_type",
  "duplicate_state",
  "application_method",
  "publication_state",
]);

export const DEFAULT_JOB_LIMIT = 25;
export const MAX_JOB_LIMIT = 200;

function integerOrDefault(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizeLimit(value) {
  return Math.min(MAX_JOB_LIMIT, Math.max(1, integerOrDefault(value, DEFAULT_JOB_LIMIT)));
}

function normalizeOffset(value) {
  return Math.max(0, integerOrDefault(value, 0));
}

export function parseJobFilters(search = "") {
  const params = new URLSearchParams(search);
  const filters = Object.fromEntries(
    JOB_FILTER_KEYS.map((key) => [key, params.get(key) || ""]),
  );
  return {
    ...filters,
    limit: normalizeLimit(params.get("limit")),
    offset: normalizeOffset(params.get("offset")),
  };
}

export function buildJobsQuery(filters = {}) {
  const params = new URLSearchParams();
  JOB_FILTER_KEYS.forEach((key) => {
    const value = String(filters[key] || "").trim();
    if (value) params.set(key, value);
  });
  params.set("limit", String(normalizeLimit(filters.limit)));
  params.set("offset", String(normalizeOffset(filters.offset)));
  return params.toString();
}

export function buildJobsPath(filters = {}) {
  return `/admin/acquisition/jobs?${buildJobsQuery(filters)}`;
}

export function buildInspectionPath(canonicalJobId, search = "") {
  const encodedId = encodeURIComponent(String(canonicalJobId || "").trim());
  const normalizedSearch = String(search || "").trim();
  return `/admin/acquisition/jobs/${encodedId}${normalizedSearch || ""}`;
}

export function getJobsRangeLabel({ offset = 0, rows = 0, total = 0 } = {}) {
  const normalizedOffset = Math.max(0, Number(offset) || 0);
  const normalizedRows = Math.max(0, Number(rows) || 0);
  const normalizedTotal = Math.max(0, Number(total) || 0);
  if (!normalizedTotal) return "No jobs match the current filters.";
  if (!normalizedRows || normalizedOffset >= normalizedTotal) {
    return `No jobs on this page. ${formatCount(normalizedTotal)} jobs match the current filters.`;
  }
  return `Showing ${normalizedOffset + 1}–${Math.min(normalizedOffset + normalizedRows, normalizedTotal)} of ${formatCount(normalizedTotal)} jobs.`;
}

export function getSourceOperationalState(source = {}) {
  const status = String(source.status || "").trim().toLowerCase();
  if (status === "ready") return "Ready";
  if (status === "paused" || status === "source_paused") return "Paused";
  if (source.available === false || status) return "Unavailable";
  return "Unavailable";
}

function capabilityMetadata(capability = {}) {
  const nested = capability.capabilities;
  return nested && typeof nested === "object"
    ? { ...capability, ...nested }
    : capability;
}

function hasPositiveLimit(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0;
}

export function getSourceCollectionState(source = {}, capability = {}) {
  const metadata = capabilityMetadata(capability);
  const explicitState = String(
    source.completeness_state || metadata.completeness_state || "",
  ).trim().toLowerCase();

  if (explicitState === "bounded") return "Bounded collection";

  const requestLimits = metadata.request_limits;
  const hasBound = [
    source.max_pages,
    source.max_requests,
    source.max_credits,
    requestLimits?.max_pages,
    requestLimits?.max_requests,
    requestLimits?.max_credits,
  ].some(hasPositiveLimit);

  return hasBound ? "Bounded collection" : "Completeness unavailable";
}

export function getCapabilityKey(source = {}) {
  const connector = String(source.connector || "").trim().toLowerCase();
  const targetId = String(source.id || source.target_id || "").trim().toLowerCase();
  return `${connector}:${targetId}`;
}

export function getResourceViewState({
  data = null,
  loading = false,
  error = "",
  empty = false,
  unavailable = false,
} = {}) {
  if (loading && data === null) return "loading";
  if (unavailable) return "unavailable";
  if (error && data === null) return "error";
  if (empty) return "empty";
  if (error) return "partial";
  return "ready";
}

export function formatCount(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toLocaleString() : "—";
}
