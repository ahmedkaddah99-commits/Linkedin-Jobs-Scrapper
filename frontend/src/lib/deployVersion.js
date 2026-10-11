const ENTRY_ASSET_PATH_RE = /^\/assets\/index-[A-Za-z0-9_-]+\.js$/;

export function entryAssetPathFromUrl(src, baseUrl = "https://app.userunr.com/") {
  const rawSrc = String(src || "").trim();
  if (!rawSrc) return "";
  try {
    const url = new URL(rawSrc, baseUrl);
    return ENTRY_ASSET_PATH_RE.test(url.pathname) ? url.pathname : "";
  } catch {
    return "";
  }
}

export function extractEntryAssetPathFromHtml(html, baseUrl = "https://app.userunr.com/") {
  const source = String(html || "");
  const scriptTags = source.match(/<script\b[^>]*>/gi) || [];
  for (const tag of scriptTags) {
    if (!/\btype=["']module["']/i.test(tag)) {
      continue;
    }
    const srcMatch = tag.match(/\bsrc=["']([^"']+)["']/i);
    const entryPath = entryAssetPathFromUrl(srcMatch?.[1], baseUrl);
    if (entryPath) {
      return entryPath;
    }
  }
  return "";
}

export function currentEntryAssetPath(documentRef = typeof document === "undefined" ? null : document) {
  if (!documentRef?.querySelectorAll) return "";
  const scripts = Array.from(documentRef.querySelectorAll('script[type="module"][src]'));
  for (const script of scripts) {
    const entryPath = entryAssetPathFromUrl(
      script.getAttribute?.("src") || script.src,
      documentRef.location?.href || "https://app.userunr.com/",
    );
    if (entryPath) {
      return entryPath;
    }
  }
  return "";
}

export async function fetchLatestEntryAssetPath({
  baseUrl = typeof window === "undefined" ? "https://app.userunr.com/" : window.location.href,
  fetchImpl = typeof fetch === "undefined" ? null : fetch,
  now = Date.now,
} = {}) {
  if (!fetchImpl) return "";
  const versionUrl = new URL("/", baseUrl);
  versionUrl.searchParams.set("__runr_version_check", String(now()));
  const response = await fetchImpl(versionUrl.toString(), {
    cache: "no-store",
    headers: { Accept: "text/html" },
  });
  if (!response?.ok) {
    return "";
  }
  return extractEntryAssetPathFromHtml(await response.text(), versionUrl.href);
}
