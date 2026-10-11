export function normalizeTrackerDescription(value) {
  const text = String(value || "");
  if (!text.trim()) {
    return "";
  }

  const withRealLineBreaks = /[\r\n]/.test(text)
    ? text
    : text.replace(/\\r\\n|\\n|\\r/g, "\n");

  return withRealLineBreaks
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((line) => line.replace(/[ \t]+$/g, ""))
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function trackerDescriptionForItem(item) {
  return normalizeTrackerDescription(
    item?.full_description || item?.tracker_table_row?.full_description || "",
  );
}
