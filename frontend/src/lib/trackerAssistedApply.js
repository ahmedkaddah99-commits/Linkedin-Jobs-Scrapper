import { isSupportedAssistedApplyUrl } from "./supportedAssistedApplyUrl.js";

function trackerStatus(item) {
  const status = item?.tracker_status === "email_confirmed"
    ? "applied"
    : item?.tracker_status;
  return String(status || "unknown").trim();
}

/**
 * Returns the immutable-package launch input for a Tracker row, or null when
 * the job must remain on the ordinary employer-application path.
 */
export function assistedApplyTrackerRow(item) {
  const trackerRow = item?.tracker_table_row || {};
  const applicationUrl = String(item?.apply_link || trackerRow.apply_link || "").trim();
  const runId = String(item?.run_id || "").trim();
  const jobId = String(item?.job_id || "").trim();

  if (
    trackerStatus(item) !== "not_applied"
    || !runId
    || !jobId
    || !isSupportedAssistedApplyUrl(applicationUrl)
  ) {
    return null;
  }

  return {
    ...item,
    run_id: runId,
    job_id: jobId,
    apply_link: applicationUrl,
    title: item.title || trackerRow.title || "",
    company: item.company || trackerRow.company || "",
    location: item.location || trackerRow.location_raw || "",
  };
}
