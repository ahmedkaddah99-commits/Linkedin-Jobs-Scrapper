export const TRACKER_REQUEST_TIMEOUT_MS = 60000;
export const TRACKER_INTEGRATION_REQUEST_TIMEOUT_MS = 30000;

export async function loadTrackerShell(request) {
  return {
    tracker: await request("/tracker?view=board", { timeoutMs: TRACKER_REQUEST_TIMEOUT_MS }),
    integration: null,
  };
}

export async function loadTrackerIntegration(request) {
  return request("/tracker/email-integration", { timeoutMs: TRACKER_INTEGRATION_REQUEST_TIMEOUT_MS });
}
