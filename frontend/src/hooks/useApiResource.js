import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "../context/SessionContext";

export function useApiResource(loader, deps = [], { immediate = true } = {}) {
  const { isConnected } = useSession();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(Boolean(immediate));
  const [error, setError] = useState("");
  const requestCounterRef = useRef(0);

  const refresh = useCallback(async () => {
    const requestId = requestCounterRef.current + 1;
    requestCounterRef.current = requestId;

    if (!isConnected) {
      setLoading(false);
      return null;
    }

    setLoading(true);
    setError("");
    try {
      const payload = await loader();
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
  }, [isConnected, loader]);

  useEffect(() => {
    if (!immediate || !isConnected) {
      setLoading(false);
      return;
    }
    refresh().catch(() => undefined);
    // Intentionally use the caller-provided deps instead of `refresh` directly.
    // `loader` is often an inline callback, and depending on it here would
    // create a request loop that keeps pages stuck in loading state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [immediate, isConnected, ...deps]);

  return { data, loading, error, refresh, setData };
}
