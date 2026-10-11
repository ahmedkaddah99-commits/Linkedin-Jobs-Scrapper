export interface AssistedApplyRuntimeConfig {
  apiBaseUrl: string;
  frontendOrigin: string;
  allowedWebOrigins: string[];
  chromeWebStoreUrl: string;
}

const PRODUCTION_CONFIG: AssistedApplyRuntimeConfig = {
  apiBaseUrl: "https://runr-api.onrender.com/v1",
  frontendOrigin: "https://app.userunr.com",
  allowedWebOrigins: ["https://app.userunr.com", "https://runr-frontend.onrender.com"],
  chromeWebStoreUrl: "https://chromewebstore.google.com/detail/runr-assisted-apply/najcdfohhfgbjpbokhmmekkahghfhegp",
};

const TESTING_CONFIG: AssistedApplyRuntimeConfig = {
  apiBaseUrl: "http://127.0.0.1:4174",
  frontendOrigin: "http://127.0.0.1:4174",
  allowedWebOrigins: ["http://127.0.0.1:4174"],
  chromeWebStoreUrl: "http://127.0.0.1:4174/assisted-apply",
};

export function assistedApplyRuntimeConfig(
  mode: string = import.meta.env.MODE,
): AssistedApplyRuntimeConfig {
  return mode === "testing" ? { ...TESTING_CONFIG } : { ...PRODUCTION_CONFIG };
}
