export function labelize(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function formatDateTime(value) {
  if (!value) return "N/A";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return parsed.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function statusTone(status) {
  const normalized = String(status || "").toLowerCase();
  if (["completed", "approved", "active", "running", "artifact_ready", "ready"].includes(normalized)) {
    return "success";
  }
  if (["failed", "rejected", "error", "cancelled", "missing"].includes(normalized)) {
    return "warning";
  }
  return "primary";
}
