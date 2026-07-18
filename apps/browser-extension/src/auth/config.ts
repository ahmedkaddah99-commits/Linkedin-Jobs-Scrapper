export interface AssistedApplyRuntimeConfig {
  apiBaseUrl: string;
  frontendOrigin: string;
}

const PRODUCTION_CONFIG: AssistedApplyRuntimeConfig = {
  apiBaseUrl: "https://runr-api.onrender.com/v1",
  frontendOrigin: "https://app.userunr.com",
};

const TESTING_CONFIG: AssistedApplyRuntimeConfig = {
  apiBaseUrl: "http://127.0.0.1:4174",
  frontendOrigin: "http://127.0.0.1:4174",
};

export function assistedApplyRuntimeConfig(
  mode: string = import.meta.env.MODE,
): AssistedApplyRuntimeConfig {
  return mode === "testing" ? { ...TESTING_CONFIG } : { ...PRODUCTION_CONFIG };
}
