// CP-039R: Bounded polling with exponential backoff for source processing.
// Used by the Career Evidence guided flow to poll processing state
// until completion, timeout, or failure.

const DEFAULT_POLL_TIMEOUT_MS = 120000;
const INITIAL_DELAY_MS = 1000;
const MAX_DELAY_MS = 8000;
const BACKOFF_FACTOR = 2.0;

/**
 * Poll a status-checking function with exponential backoff.
 *
 * @param {() => Promise<object>} checkFn - returns { status, extracted_count?, error? }
 * @param {object} options
 * @param {number} [options.timeoutMs=120000]
 * @param {number} [options.initialDelayMs=1000]
 * @param {number} [options.maxDelayMs=8000]
 * @param {number} [options.backoffFactor=2.0]
 * @param {(state: object) => void} [options.onTick] - called after each poll
 * @returns {Promise<object>} the terminal state
 */
export async function pollProcessingState(
  checkFn,
  {
    timeoutMs = DEFAULT_POLL_TIMEOUT_MS,
    initialDelayMs = INITIAL_DELAY_MS,
    maxDelayMs = MAX_DELAY_MS,
    backoffFactor = BACKOFF_FACTOR,
    onTick,
  } = {},
) {
  const deadline = Date.now() + timeoutMs;
  let delay = initialDelayMs;

  while (Date.now() < deadline) {
    let state;
    try {
      state = await checkFn();
    } catch (err) {
      // Treat network errors as transient; retry after backoff
      await new Promise((r) => setTimeout(r, delay));
      delay = Math.min(delay * backoffFactor, maxDelayMs);
      continue;
    }

    if (onTick) {
      onTick(state);
    }

    const status = state?.state || state?.status || "";
    if (status === "completed" || status === "failed" || status === "timeout" || status === "empty") {
      return state;
    }

    await new Promise((r) => setTimeout(r, delay));
    delay = Math.min(delay * backoffFactor, maxDelayMs);
  }

  return {
    state: "timeout",
    extracted_count: 0,
    total_sources: 0,
    error: "Processing timed out.",
    retry_allowed: true,
  };
}

/**
 * Read a file as base64-encoded data URL.
 *
 * @param {File} file
 * @returns {Promise<string>} base64-encoded file data
 */
export async function readFileAsBase64(file) {
  if (typeof FileReader === "undefined") {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    }
    return btoa(binary);
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result;
      // Strip the data:...;base64, prefix
      const base64 = dataUrl.split(",")[1] || "";
      resolve(base64);
    };
    reader.onerror = () => reject(new Error("Failed to read file."));
    reader.readAsDataURL(file);
  });
}
