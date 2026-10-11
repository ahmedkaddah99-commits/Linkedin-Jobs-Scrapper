const apiResourceCache = new Map();
const apiResourceInFlight = new Map();

export function clearApiResourceCache(cacheKey = "") {
  if (cacheKey) {
    apiResourceCache.delete(cacheKey);
    apiResourceInFlight.delete(cacheKey);
    return;
  }
  apiResourceCache.clear();
  apiResourceInFlight.clear();
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

export function getApiResourceInFlight(cacheKey) {
  return cacheKey ? apiResourceInFlight.get(cacheKey) || null : null;
}

export function setApiResourceInFlight(cacheKey, promise) {
  if (!cacheKey) return promise;
  apiResourceInFlight.set(cacheKey, promise);
  const clearIfCurrent = () => {
    if (apiResourceInFlight.get(cacheKey) === promise) {
      apiResourceInFlight.delete(cacheKey);
    }
  };
  promise.then(clearIfCurrent, clearIfCurrent);
  return promise;
}
