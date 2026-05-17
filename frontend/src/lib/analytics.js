const firebaseConfig = {
  apiKey: String(import.meta.env.VITE_FIREBASE_API_KEY || "").trim(),
  authDomain: String(import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "").trim(),
  projectId: String(import.meta.env.VITE_FIREBASE_PROJECT_ID || "").trim(),
  storageBucket: String(import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || "").trim(),
  messagingSenderId: String(import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || "").trim(),
  appId: String(import.meta.env.VITE_FIREBASE_APP_ID || "").trim(),
  measurementId: String(import.meta.env.VITE_FIREBASE_MEASUREMENT_ID || "").trim(),
};

const hasFirebaseConfig = [
  firebaseConfig.apiKey,
  firebaseConfig.projectId,
  firebaseConfig.appId,
  firebaseConfig.measurementId,
].every(Boolean);

let analyticsInstancePromise;

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

function debugFallback(action, payload) {
  if (import.meta.env.DEV) {
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
