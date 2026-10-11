const runtimeEnv = import.meta.env || {};
const firebaseConfig = {
  apiKey: String(runtimeEnv.VITE_FIREBASE_API_KEY || "").trim(),
  authDomain: String(runtimeEnv.VITE_FIREBASE_AUTH_DOMAIN || "").trim(),
  projectId: String(runtimeEnv.VITE_FIREBASE_PROJECT_ID || "").trim(),
  storageBucket: String(runtimeEnv.VITE_FIREBASE_STORAGE_BUCKET || "").trim(),
  messagingSenderId: String(runtimeEnv.VITE_FIREBASE_MESSAGING_SENDER_ID || "").trim(),
  appId: String(runtimeEnv.VITE_FIREBASE_APP_ID || "").trim(),
  measurementId: String(runtimeEnv.VITE_FIREBASE_MEASUREMENT_ID || "").trim(),
};

const hasFirebaseConfig = [
  firebaseConfig.apiKey,
  firebaseConfig.projectId,
  firebaseConfig.appId,
  firebaseConfig.measurementId,
].every(Boolean);

let analyticsInstancePromise;
let firstPartyEventSink = null;

const FIRST_PARTY_ALLOWED_KEYS = new Set([
  "auth_provider",
  "route",
  "page",
  "feature_key",
  "job_id",
  "job_preview_id",
  "filter_name",
  "filter_count",
  "job_count",
  "feedback_reason_code",
  "onboarding_step",
  "data_mode",
  "scene_key",
  "progression",
  "extraction_status",
  "showcase_skipped",
  "notification_mode",
  "selected_plan_id",
  "offer_source",
  "ready_to_notification_ms",
  "notification_to_modal_ms",
  "reduced_motion",
  "offer_outcome",
  "quota_type",
  "plan_id",
  "source",
  "portal",
  "status",
  "outcome",
  "app_version",
  "release_version",
  "worker_version",
  "duration_ms",
  "duration_seconds",
  "latency_ms",
  "error_code",
  "failure_code",
  "failure_stage",
  "method",
  "status_code",
  "request_path",
]);

async function loadAnalyticsBundle() {
  const [appModule, analyticsModule] = await Promise.all([
    import("firebase/app"),
    import("firebase/analytics"),
  ]);

  return {
    getAnalytics: analyticsModule.getAnalytics,
    getApp: appModule.getApp,
    getApps: appModule.getApps,
    initializeApp: appModule.initializeApp,
    isSupported: analyticsModule.isSupported,
    logEvent: analyticsModule.logEvent,
    setUserId: analyticsModule.setUserId,
    setUserProperties: analyticsModule.setUserProperties,
  };
}

function buildRuntimeConfig() {
  return Object.fromEntries(Object.entries(firebaseConfig).filter(([, value]) => value));
}

function sanitizeProperties(properties = {}) {
  return Object.fromEntries(
    Object.entries(properties).filter(([, value]) => value !== undefined && value !== null && value !== ""),
  );
}

export function sanitizeFirstPartyProperties(properties = {}) {
  return Object.fromEntries(
    Object.entries(properties).flatMap(([key, value]) => {
      if (!FIRST_PARTY_ALLOWED_KEYS.has(key) || value === undefined || value === null || value === "") {
        return [];
      }
      if (typeof value === "number" && !Number.isFinite(value)) {
        return [];
      }
      if (!["string", "number", "boolean"].includes(typeof value)) {
        return [];
      }
      const safeValue = typeof value === "string" ? value.trim().slice(0, 160) : value;
      return safeValue === "" ? [] : [[key, safeValue]];
    }),
  );
}

export function configureFirstPartyEventSink(request) {
  if (typeof request !== "function") {
    firstPartyEventSink = null;
    return undefined;
  }
  const sink = (eventName, properties) => {
    const payload = {
      event_name: eventName,
      source: "frontend_first_party",
      route: properties.route || properties.page || "",
      payload: sanitizeFirstPartyProperties(properties),
    };
    // Analytics must never delay or fail the user action that produced it.
    Promise.resolve(request("/analytics/events", { method: "POST", body: payload })).catch(() => undefined);
  };
  firstPartyEventSink = sink;
  return () => {
    if (firstPartyEventSink === sink) {
      firstPartyEventSink = null;
    }
  };
}

function debugFallback(action, payload) {
  if (runtimeEnv.DEV) {
    console.debug(`[analytics:${action}]`, payload);
  }
}

function ensureAnalytics() {
  if (analyticsInstancePromise !== undefined) {
    return analyticsInstancePromise;
  }
  if (!hasFirebaseConfig || typeof window === "undefined") {
    analyticsInstancePromise = Promise.resolve(null);
    return analyticsInstancePromise;
  }

  analyticsInstancePromise = loadAnalyticsBundle()
    .then((bundle) => bundle.isSupported().then((supported) => ({ bundle, supported })))
    .then(({ bundle, supported }) => {
      if (!supported) {
        return null;
      }
      const app = bundle.getApps().length
        ? bundle.getApp()
        : bundle.initializeApp(buildRuntimeConfig());
      return {
        analytics: bundle.getAnalytics(app),
        logEvent: bundle.logEvent,
        setUserId: bundle.setUserId,
        setUserProperties: bundle.setUserProperties,
      };
    })
    .catch(() => null);

  return analyticsInstancePromise;
}

export function logEvent(eventName, properties = {}) {
  const normalizedEventName = String(eventName || "").trim();
  if (!normalizedEventName) {
    return;
  }

  const sanitizedProperties = sanitizeProperties(properties);
  if (firstPartyEventSink) {
    firstPartyEventSink(normalizedEventName, sanitizedProperties);
  }
  ensureAnalytics().then((bundle) => {
    if (!bundle) {
      debugFallback("event", {
        eventName: normalizedEventName,
        properties: sanitizedProperties,
      });
      return;
    }
    bundle.logEvent(bundle.analytics, normalizedEventName, sanitizedProperties);
  });
}

export function identify(userId) {
  const normalizedUserId = String(userId || "").trim() || null;
  ensureAnalytics().then((bundle) => {
    if (!bundle) {
      debugFallback("identify", { userId: normalizedUserId });
      return;
    }
    bundle.setUserId(bundle.analytics, normalizedUserId);
    if (normalizedUserId) {
      bundle.setUserProperties(bundle.analytics, { user_id: normalizedUserId });
    }
  });
}
