import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  apiRequest,
  clearStoredConnection,
  getDefaultApiBaseUrl,
  loadStoredConnection,
  persistConnection,
  resolveApiUrl,
} from "../lib/api";

const SessionContext = createContext(null);

export function SessionProvider({ children }) {
  const storedConnection = useMemo(() => loadStoredConnection(), []);
  const [apiBaseUrl, setApiBaseUrl] = useState(storedConnection.baseUrl || getDefaultApiBaseUrl());
  const [accessToken, setAccessToken] = useState(storedConnection.accessToken || "");
  const [status, setStatus] = useState(storedConnection.accessToken ? "connecting" : "disconnected");
  const [user, setUser] = useState(null);
  const [tokenInfo, setTokenInfo] = useState(null);
  const [error, setError] = useState("");

  const request = useCallback(
    (path, options = {}) => apiRequest(apiBaseUrl, accessToken, path, options),
    [accessToken, apiBaseUrl],
  );

  const refreshSession = useCallback(async () => {
    if (!accessToken) {
      setStatus("disconnected");
      setUser(null);
      setTokenInfo(null);
      setError("");
      return null;
    }
    setStatus("connecting");
    try {
      const payload = await apiRequest(apiBaseUrl, accessToken, "/auth/me");
      setUser(payload.user);
      setTokenInfo(payload.token);
      setStatus("connected");
      setError("");
      return payload;
    } catch (sessionError) {
      setUser(null);
      setTokenInfo(null);
      setStatus("error");
      setError(sessionError.message || "Unable to authenticate with the backend API.");
      throw sessionError;
    }
  }, [accessToken, apiBaseUrl]);

  useEffect(() => {
    if (!accessToken) {
      setStatus("disconnected");
      return;
    }
    refreshSession().catch(() => undefined);
  }, [accessToken, apiBaseUrl, refreshSession]);

  const connect = useCallback(
    async ({ baseUrl, token }) => {
      const normalizedBaseUrl = String(baseUrl || getDefaultApiBaseUrl()).trim() || getDefaultApiBaseUrl();
      const normalizedToken = String(token || "").trim();
      persistConnection({ baseUrl: normalizedBaseUrl, accessToken: normalizedToken });
      setApiBaseUrl(normalizedBaseUrl);
      setAccessToken(normalizedToken);
      return apiRequest(normalizedBaseUrl, normalizedToken, "/auth/me").then((payload) => {
        setUser(payload.user);
        setTokenInfo(payload.token);
        setStatus("connected");
        setError("");
        return payload;
      }).catch((sessionError) => {
        setStatus("error");
        setUser(null);
        setTokenInfo(null);
        setError(sessionError.message || "Unable to authenticate with the backend API.");
        throw sessionError;
      });
    },
    [],
  );

  const disconnect = useCallback(() => {
    clearStoredConnection();
    setApiBaseUrl(getDefaultApiBaseUrl());
    setAccessToken("");
    setUser(null);
    setTokenInfo(null);
    setStatus("disconnected");
    setError("");
  }, []);

  const value = useMemo(
    () => ({
      apiBaseUrl,
      accessToken,
      user,
      tokenInfo,
      status,
      error,
      isConnected: status === "connected",
      connect,
      disconnect,
      refreshSession,
      request,
      resolvePath: (path) => resolveApiUrl(apiBaseUrl, path),
    }),
    [accessToken, apiBaseUrl, connect, disconnect, error, refreshSession, request, status, tokenInfo, user],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used inside SessionProvider.");
  }
  return context;
}
