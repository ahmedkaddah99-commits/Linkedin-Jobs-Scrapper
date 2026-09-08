export function shouldFocusRunProgress({ hash = "", runStatus = "" } = {}) {
  const status = String(runStatus || "").trim().toLowerCase();
  return hash === "#run-progress"
    || ["planned", "queued", "running", "cancel_requested"].includes(status);
}

export function claimRunProgressFocus(
  focusedRunIds,
  { hash = "", runId = "", runStatus = "" } = {},
) {
  const normalizedRunId = String(runId || "").trim();
  if (
    !(focusedRunIds instanceof Set)
    || !normalizedRunId
    || focusedRunIds.has(normalizedRunId)
    || !shouldFocusRunProgress({ hash, runStatus })
  ) {
    return false;
  }
  focusedRunIds.add(normalizedRunId);
  return true;
}

export function runProgressScrollBehavior(reducedMotion) {
  return reducedMotion ? "auto" : "smooth";
}
