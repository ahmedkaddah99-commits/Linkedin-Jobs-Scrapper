const apiResourceCache = new Map();

export function clearApiResourceCache(cacheKey = "") {
  if (cacheKey) {
    apiResourceCache.delete(cacheKey);
    return;
  }
  apiResourceCache.clear();
}

export function getApiResourceCacheEntry(cacheKey) {
  return apiResourceCache.get(cacheKey) || null;
}

export function setApiResourceCacheEntry(cacheKey, data, cachedAt = Date.now()) {
  if (!cacheKey) return;
  apiResourceCache.set(cacheKey, { data, cachedAt });
}

export function isApiResourceCacheFresh(entry, staleMs) {
  if (!entry) return false;
  if (staleMs === Infinity) return true;
  return Date.now() - Number(entry.cachedAt || 0) < Number(staleMs || 0);
}
