export const RUNR_ASSISTED_APPLY_EXTENSION_ID = "najcdfohhfgbjpbokhmmekkahghfhegp";

function runtimeError(runtime) {
  return runtime?.lastError?.message || "Runr Assisted Apply did not respond.";
}

/**
 * Ask only the installed, first-party extension to bind an already-launched
 * opaque package to the tab Runr just opened. The web app never receives the
 * package payload or an extension session credential.
 */
export function bindRunrApplicationPackage({
  bindingId,
  applicationUrl,
  runtime = globalThis.chrome?.runtime,
}) {
  if (!runtime || typeof runtime.sendMessage !== "function") {
    return Promise.reject(new Error("Install and connect the Runr browser extension before using Assisted Apply."));
  }
  return new Promise((resolve, reject) => {
    try {
      runtime.sendMessage(
        RUNR_ASSISTED_APPLY_EXTENSION_ID,
        {
          type: "RUNR_WEB_BIND_APPLICATION_PACKAGE",
          bindingId,
          applicationUrl,
        },
        (response) => {
          const error = runtimeError(runtime);
          if (runtime?.lastError) {
            reject(new Error(error));
            return;
          }
          if (!response || response.ok !== true || typeof response.packageId !== "string") {
            reject(new Error(response?.error || "Runr could not bind this application package."));
            return;
          }
          resolve(response);
        },
      );
    } catch (error) {
      reject(error instanceof Error ? error : new Error("Runr could not contact the browser extension."));
    }
  });
}
