export const TRACKER_REQUEST_TIMEOUT_MS = 60000;
export const TRACKER_INTEGRATION_REQUEST_TIMEOUT_MS = 30000;

export async function loadTrackerShell(request) {
  const [tracker, integration] = await Promise.all([
    request("/tracker", { timeoutMs: TRACKER_REQUEST_TIMEOUT_MS }),
    request("/tracker/email-integration", { timeoutMs: TRACKER_INTEGRATION_REQUEST_TIMEOUT_MS }),
  ]);
  return { tracker, integration };
}
