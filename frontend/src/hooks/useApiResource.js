import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "../context/SessionContext";
import {
  getApiResourceCacheEntry,
  isApiResourceCacheFresh,
  setApiResourceCacheEntry,
} from "./apiResourceCache";

export {
  clearApiResourceCache,
  getApiResourceCacheEntry,
  setApiResourceCacheEntry,
} from "./apiResourceCache";

export function useApiResource(
  loader,
  deps = [],
  {
    immediate = true,
    cacheKey = "",
    staleMs = 0,
    backgroundRefresh = true,
  } = {},
) {
  const { isConnected } = useSession();
  const cachedEntry = cacheKey ? getApiResourceCacheEntry(cacheKey) : null;
  const [data, setDataState] = useState(cachedEntry?.data ?? null);
  const [loading, setLoading] = useState(Boolean(immediate && !cachedEntry));
  const [error, setError] = useState("");
  const dataRef = useRef(cachedEntry?.data ?? null);
  const loaderRef = useRef(loader);
  const requestCounterRef = useRef(0);

  useEffect(() => {
    loaderRef.current = loader;
  }, [loader]);

  const setData = useCallback((nextData) => {
    setDataState((currentData) => {
      const resolvedData = typeof nextData === "function" ? nextData(currentData) : nextData;
      dataRef.current = resolvedData;
      if (cacheKey) {
        setApiResourceCacheEntry(cacheKey, resolvedData);
      }
      return resolvedData;
    });
  }, [cacheKey]);

  const refresh = useCallback(async ({ showLoading, force = true } = {}) => {
    const requestId = requestCounterRef.current + 1;
    requestCounterRef.current = requestId;

    if (!isConnected) {
      setLoading(false);
      return null;
    }

    if (!force && cacheKey && isApiResourceCacheFresh(getApiResourceCacheEntry(cacheKey), staleMs)) {
      return dataRef.current;
    }

    const shouldShowLoading = showLoading ?? dataRef.current === null;
    if (shouldShowLoading) {
      setLoading(true);
    }
    setError("");
    try {
      const payload = await loaderRef.current();
      if (requestCounterRef.current === requestId) {
        setData(payload);
      }
      return payload;
    } catch (requestError) {
      if (requestCounterRef.current === requestId) {
        setError(requestError.message || "Request failed.");
      }
      throw requestError;
    } finally {
      if (requestCounterRef.current === requestId) {
        setLoading(false);
      }
    }
  }, [cacheKey, isConnected, setData, staleMs]);

  useEffect(() => {
    if (!immediate || !isConnected) {
      setLoading(false);
      return;
    }
    const cached = cacheKey ? getApiResourceCacheEntry(cacheKey) : null;
    if (cached && dataRef.current !== cached.data) {
      setData(cached.data);
    }
    if (cached && !backgroundRefresh) {
      setLoading(false);
      return;
    }
    refresh({
      showLoading: !cached,
      force: !cached || !isApiResourceCacheFresh(cached, staleMs),
    }).catch(() => undefined);
    // Intentionally use the caller-provided deps instead of `refresh` directly.
    // `loader` is often an inline callback, and depending on it here would
    // create a request loop that keeps pages stuck in loading state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [immediate, isConnected, cacheKey, backgroundRefresh, staleMs, ...deps]);

  return { data, loading, error, refresh, setData };
}
