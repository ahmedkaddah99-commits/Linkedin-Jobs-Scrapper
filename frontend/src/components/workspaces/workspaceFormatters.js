export function formatDateTime(value) {
  if (!value) {
    return "Unknown";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return parsed.toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function workspaceRunSchedule(workspace) {
  const rawSchedule =
    workspace?.schedule && typeof workspace.schedule === "object"
      ? workspace.schedule
      : workspace?.metadata?.run_schedule || {};
  const parsedInterval = Number.parseInt(rawSchedule.interval_days, 10);
  const intervalDays = Number.isInteger(parsedInterval) && parsedInterval > 0 ? parsedInterval : 0;
  const enabled = Boolean(rawSchedule.enabled) && intervalDays > 0;
  return {
    enabled,
    intervalDays: enabled ? intervalDays : 0,
    nextRunAt: String(rawSchedule.next_run_at || ""),
    lastEnqueuedAt: String(rawSchedule.last_enqueued_at || ""),
    lastRunId: String(rawSchedule.last_run_id || ""),
    lastError: String(rawSchedule.last_error || ""),
    lastErrorAt: String(rawSchedule.last_error_at || ""),
  };
}

export function scheduleIntervalLabel(intervalDays) {
  return `Every ${intervalDays} day${intervalDays === 1 ? "" : "s"}`;
}
