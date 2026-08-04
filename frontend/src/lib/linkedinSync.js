export const LINKEDIN_CONNECTIONS_URL =
  "https://www.linkedin.com/mynetwork/invite-connect/connections/";

export const RUNR_ASSISTED_APPLY_EXTENSION_ID = "najcdfohhfgbjpbokhmmekkahghfhegp";

function runtimeError(runtime) {
  return runtime?.lastError?.message || "Runr Assisted Apply did not respond.";
}

function sendExtensionMessage(message, runtime = globalThis.chrome?.runtime) {
  if (!runtime || typeof runtime.sendMessage !== "function") {
    return Promise.reject(new Error("Install the Runr browser extension before syncing LinkedIn connections."));
  }
  return new Promise((resolve, reject) => {
    try {
      runtime.sendMessage(RUNR_ASSISTED_APPLY_EXTENSION_ID, message, (response) => {
        if (runtime.lastError) {
          reject(new Error(runtimeError(runtime)));
          return;
        }
        if (!response || response.ok !== true) {
          reject(new Error(response?.error || "Runr could not complete the LinkedIn sync."));
          return;
        }
        resolve(response);
      });
    } catch (error) {
      reject(error instanceof Error ? error : new Error("Runr could not contact the browser extension."));
    }
  });
}

export function openLinkedInConnections() {
  return Boolean(globalThis.window?.open?.(LINKEDIN_CONNECTIONS_URL, "_blank", "noopener,noreferrer"));
}

export function syncLinkedInConnections({ runtime = globalThis.chrome?.runtime } = {}) {
  return sendExtensionMessage({ type: "RUNR_WEB_SYNC_LINKEDIN_CONNECTIONS" }, runtime);
}
