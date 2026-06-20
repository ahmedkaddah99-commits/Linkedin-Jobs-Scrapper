import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "../context/SessionContext";

export function useApiResource(loader, deps = [], { immediate = true } = {}) {
  const { isConnected } = useSession();
  const [data, setDataState] = useState(null);
  const [loading, setLoading] = useState(Boolean(immediate));
  const [error, setError] = useState("");
  const dataRef = useRef(null);
  const loaderRef = useRef(loader);
  const requestCounterRef = useRef(0);

  useEffect(() => {
    loaderRef.current = loader;
  }, [loader]);

  const setData = useCallback((nextData) => {
    setDataState((currentData) => {
      const resolvedData = typeof nextData === "function" ? nextData(currentData) : nextData;
      dataRef.current = resolvedData;
      return resolvedData;
    });
  }, []);

  const refresh = useCallback(async ({ showLoading } = {}) => {
    const requestId = requestCounterRef.current + 1;
    requestCounterRef.current = requestId;

    if (!isConnected) {
      setLoading(false);
      return null;
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
  }, [isConnected, setData]);

  useEffect(() => {
    if (!immediate || !isConnected) {
      setLoading(false);
      return;
    }
    refresh({ showLoading: true }).catch(() => undefined);
    // Intentionally use the caller-provided deps instead of `refresh` directly.
    // `loader` is often an inline callback, and depending on it here would
    // create a request loop that keeps pages stuck in loading state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [immediate, isConnected, ...deps]);

  return { data, loading, error, refresh, setData };
}
