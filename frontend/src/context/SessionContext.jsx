import { useAuth, useUser } from "@clerk/react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  apiRequest,
  CLERK_JWT_TEMPLATE_NAME,
  getDefaultApiBaseUrl,
  loadStoredConnection,
  persistConnection,
  resolveApiUrl,
} from "../lib/api";
import { identify, logEvent } from "../lib/analytics";

const SessionContext = createContext(null);

function resolveAnalyticsUserId(user) {
  return String(user?.user_id || user?.clerk_user_id || user?.email || "").trim();
}

function mergeSessionUser(backendUser, clerkUser) {
  const normalizedBackendUser = backendUser && typeof backendUser === "object" ? backendUser : {};
  const clerkEmail = String(clerkUser?.primaryEmailAddress?.emailAddress || "").trim();
  const publicMetadata = {
    ...(normalizedBackendUser.publicMetadata || {}),
    ...(clerkUser?.publicMetadata || {}),
  };
  const normalizedPlanId = String(
    publicMetadata.plan_id || normalizedBackendUser.plan_id || "none",
  ).trim() || "none";
  const normalizedRole = String(
    publicMetadata.role || normalizedBackendUser.role || "user",
  ).trim() || "user";
  return {
    ...normalizedBackendUser,
    user_id: String(normalizedBackendUser.user_id || clerkUser?.id || "").trim(),
    clerk_user_id: String(clerkUser?.id || normalizedBackendUser.clerk_user_id || "").trim(),
    email: clerkEmail || String(normalizedBackendUser.email || "").trim(),
    display_name:
      String(clerkUser?.fullName || clerkUser?.username || normalizedBackendUser.display_name || "").trim(),
    image_url: String(clerkUser?.imageUrl || normalizedBackendUser.image_url || "").trim(),
    role: normalizedRole,
    plan_id: normalizedPlanId,
    publicMetadata: {
      ...publicMetadata,
      role: normalizedRole,
      plan_id: normalizedPlanId,
    },
  };
}

export function SessionProvider({ children }) {
  const storedConnection = useMemo(() => loadStoredConnection(), []);
  const { getToken, isLoaded, isSignedIn, sessionId, signOut } = useAuth();
  const { user: clerkUser } = useUser();
  const [apiBaseUrl, setApiBaseUrl] = useState(storedConnection.baseUrl || getDefaultApiBaseUrl());
  const [status, setStatus] = useState("connecting");
  const [user, setUser] = useState(null);
  const [tokenInfo, setTokenInfo] = useState(null);
  const [error, setError] = useState("");
  const trackedSessionKeyRef = useRef("");

  const getAccessToken = useCallback(async () => {
    if (!isSignedIn) {
      return "";
    }
    return String(await getToken({ template: CLERK_JWT_TEMPLATE_NAME }) || "").trim();
  }, [getToken, isSignedIn]);

  const trackSessionStart = useCallback((baseUrl, nextUser, nextSessionId) => {
    const userId = resolveAnalyticsUserId(nextUser);
    if (!userId) {
      return;
    }
    const sessionKey = `${String(baseUrl || "").trim()}::${String(nextSessionId || userId).trim()}`;
    if (trackedSessionKeyRef.current === sessionKey) {
      return;
    }
    trackedSessionKeyRef.current = sessionKey;
    logEvent("session_started", {
      auth_provider: "clerk",
      user_id: userId,
    });
  }, []);

  const request = useCallback(
    (path, options = {}) => apiRequest(apiBaseUrl, getAccessToken, path, options),
    [apiBaseUrl, getAccessToken],
  );

  const refreshSession = useCallback(async () => {
    if (!isLoaded) {
      setStatus("connecting");
      return null;
    }
    if (!isSignedIn) {
      setStatus("disconnected");
      setUser(null);
      setTokenInfo(null);
      setError("");
      trackedSessionKeyRef.current = "";
      identify(null);
      return null;
    }
    setStatus("connecting");
    try {
      const payload = await apiRequest(apiBaseUrl, getAccessToken, "/auth/me");
      const nextUser = mergeSessionUser(payload.user, clerkUser);
      setUser(nextUser);
      setTokenInfo(payload.token);
      setStatus("connected");
      setError("");
      identify(resolveAnalyticsUserId(nextUser) || null);
      trackSessionStart(apiBaseUrl, nextUser, sessionId);
      return payload;
    } catch (sessionError) {
      setUser(null);
      setTokenInfo(null);
      setStatus("error");
      setError(sessionError.message || "Unable to authenticate with the backend API.");
      trackedSessionKeyRef.current = "";
      identify(null);
      throw sessionError;
    }
  }, [apiBaseUrl, clerkUser, getAccessToken, isLoaded, isSignedIn, sessionId, trackSessionStart]);

  useEffect(() => {
    if (!isLoaded) {
      setStatus("connecting");
      return;
    }
    refreshSession().catch(() => undefined);
  }, [apiBaseUrl, isLoaded, isSignedIn, refreshSession]);

  const connect = useCallback(
    async ({ baseUrl }) => {
      const normalizedBaseUrl = String(baseUrl || getDefaultApiBaseUrl()).trim() || getDefaultApiBaseUrl();
      persistConnection({ baseUrl: normalizedBaseUrl });
      setApiBaseUrl(normalizedBaseUrl);
      return apiRequest(normalizedBaseUrl, getAccessToken, "/auth/me").then((payload) => {
        const nextUser = mergeSessionUser(payload.user, clerkUser);
        setUser(nextUser);
        setTokenInfo(payload.token);
        setStatus("connected");
        setError("");
        identify(resolveAnalyticsUserId(nextUser) || null);
        trackSessionStart(normalizedBaseUrl, nextUser, sessionId);
        return payload;
      }).catch((sessionError) => {
        setStatus("error");
        setUser(null);
        setTokenInfo(null);
        setError(sessionError.message || "Unable to authenticate with the backend API.");
        trackedSessionKeyRef.current = "";
        identify(null);
        throw sessionError;
      });
    },
    [clerkUser, getAccessToken, sessionId, trackSessionStart],
  );

  const disconnect = useCallback(async () => {
    setUser(null);
    setTokenInfo(null);
    setStatus("disconnected");
    setError("");
    trackedSessionKeyRef.current = "";
    identify(null);
    await signOut({ redirectUrl: "/sign-in" });
  }, [signOut]);

  const value = useMemo(
    () => ({
      apiBaseUrl,
      user,
      tokenInfo,
      status,
      error,
      isLoaded,
      isSignedIn: Boolean(isSignedIn),
      isConnected: status === "connected",
      connect,
      disconnect,
      refreshSession,
      request,
      getAccessToken,
      resolvePath: (path) => resolveApiUrl(apiBaseUrl, path),
    }),
    [
      apiBaseUrl,
      connect,
      disconnect,
      error,
      getAccessToken,
      isLoaded,
      isSignedIn,
      refreshSession,
      request,
      status,
      tokenInfo,
      user,
    ],
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
