const DEFAULT_POLL_INTERVAL_MS = 1500;
const DEFAULT_TIMEOUT_MS = 120000;

function sleep(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function normalizeStatus(payload) {
  return String(payload?.status || "").trim().toLowerCase();
}

function statusMessage(status, fileName) {
  if (status === "ready") return `Processed ${fileName} and selected it.`;
  if (status === "failed") return `Could not process ${fileName}.`;
  if (status === "processing") return `Processing ${fileName}...`;
  if (status === "queued") return `Queued ${fileName} for processing...`;
  return `Uploaded ${fileName}; waiting for processing...`;
}

export async function uploadAndPollCv({
  request,
  file,
  onStatus,
  refreshAssets,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  pollIntervalMs = DEFAULT_POLL_INTERVAL_MS,
}) {
  const formData = new FormData();
  formData.append("cv_file", file, file.name);
  const uploadPayload = await request("/cv-upload", {
    method: "POST",
    body: formData,
    timeoutMs: 30000,
  });
  let statusUrl = String(uploadPayload?.status_url || "").trim();
  const jobId = String(uploadPayload?.job_id || "").trim();
  if (!statusUrl && jobId) {
    statusUrl = `/cv-upload/${encodeURIComponent(jobId)}`;
  }
  let latestPayload = uploadPayload;
  let status = normalizeStatus(latestPayload);
  onStatus?.({
    ...latestPayload,
    status,
    message: statusMessage(status, file.name),
  });
  await refreshAssets?.();

  const deadline = Date.now() + timeoutMs;
  while (status && status !== "ready" && status !== "failed" && Date.now() < deadline) {
    await sleep(pollIntervalMs);
    latestPayload = await request(statusUrl);
    status = normalizeStatus(latestPayload);
    onStatus?.({
      ...latestPayload,
      status,
      message: statusMessage(status, file.name),
    });
    await refreshAssets?.();
  }

  if (status !== "ready") {
    const errorMessage =
      status === "failed"
        ? String(latestPayload?.error || `Could not process ${file.name}.`)
        : `CV processing did not finish within ${Math.round(timeoutMs / 1000)} seconds.`;
    const error = new Error(errorMessage);
    error.payload = latestPayload;
    throw error;
  }
  return latestPayload;
}
