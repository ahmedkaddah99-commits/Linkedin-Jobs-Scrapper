export function isSupportedAssistedApplyUrl(value) {
  try {
    const url = new URL(String(value || ""));
    const hostname = url.hostname.toLowerCase();
    return url.protocol === "https:" && (
      hostname === "boards.greenhouse.io" || hostname.endsWith(".lever.co")
    );
  } catch {
    return false;
  }
}
