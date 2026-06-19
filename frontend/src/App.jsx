import { RedirectToSignIn, Show } from "@clerk/react";
import { Component, Suspense, lazy, useEffect, useRef, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import AppShell from "./components/AppShell";
import ConnectionPanel from "./components/ConnectionPanel";
import UpgradeModal from "./components/UpgradeModal";
import { SessionProvider, useSession } from "./context/SessionContext";
import { QUOTA_EXCEEDED_EVENT, getDefaultApiBaseUrl } from "./lib/api";
import { logEvent } from "./lib/analytics";
import { isAdminUser } from "./lib/auth";

const AdminPage = lazy(() => import("./pages/AdminPage"));
const AdminEventsPage = lazy(() => import("./pages/AdminEventsPage"));
const AdminScrapeOpsPage = lazy(() => import("./pages/AdminScrapeOpsPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const CvStudioPage = lazy(() => import("./pages/CvStudioPage"));
const DocumentsPage = lazy(() => import("./pages/ArtifactsPage"));
const DocumentAICanvasGuidePage = lazy(() => import("./pages/DocumentAICanvasGuidePage"));
const JobDescriptionPage = lazy(() => import("./pages/JobDescriptionPage"));
const JobWorkspacePage = lazy(() => import("./pages/JobWorkspacePage"));
const PricingPage = lazy(() => import("./pages/PricingPage"));
const ReferralsPage = lazy(() => import("./pages/ReferralsPage"));
const LinkedInConnectionsGuidePage = lazy(() => import("./pages/LinkedInConnectionsGuidePage"));
const QuickApplyPage = lazy(() => import("./pages/QuickApplyPage"));
const RunDetailPage = lazy(() => import("./pages/RunDetailPage"));
const RunsPage = lazy(() => import("./pages/RunsPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const TrackerPage = lazy(() => import("./pages/TrackerPage"));
const WorkspacesPage = lazy(() => import("./pages/WorkspacesPage"));

function RouteLoadingFallback() {
  return (
    <div className="space-y-4">
      <div className="h-5 w-36 animate-pulse rounded-full bg-surface-container" />
      <div className="h-32 animate-pulse rounded-[1.75rem] bg-surface-container" />
      <div className="grid gap-4 md:grid-cols-2">
        <div className="h-40 animate-pulse rounded-[1.75rem] bg-surface-container" />
        <div className="h-40 animate-pulse rounded-[1.75rem] bg-surface-container" />
      </div>
    </div>
  );
}

class RouteErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Route render failed", error, info);
  }

  render() {
    if (!this.state.error) {
      return this.props.children;
    }
    return (
      <section className="rounded-2xl border border-error/20 bg-surface-container-lowest p-8 shadow-soft">
        <h1 className="font-headline text-2xl font-bold text-on-surface">
          This page could not be displayed
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-on-surface-variant">
          Runr hit an unexpected page error. Reload the page to retry without losing saved data.
        </p>
        <button
          className="mt-5 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:opacity-90"
          onClick={() => window.location.reload()}
          type="button"
        >
          Reload page
        </button>
      </section>
    );
  }
}

function RequireAdminRoute({ children }) {
  const { user } = useSession();
  if (!isAdminUser(user)) {
    return <Navigate replace to="/" />;
  }
  return children;
}

function UpgradeModalHost() {
  const location = useLocation();
  const [quotaEvent, setQuotaEvent] = useState(null);
  const currentPage = `${location.pathname}${location.search}${location.hash}`;

  useEffect(() => {
    function handleQuotaExceeded(event) {
      setQuotaEvent({
        ...(event.detail || {}),
        page: currentPage,
      });
    }
    window.addEventListener(QUOTA_EXCEEDED_EVENT, handleQuotaExceeded);
    return () => window.removeEventListener(QUOTA_EXCEEDED_EVENT, handleQuotaExceeded);
  }, [currentPage]);

  return (
    <UpgradeModal
      currentPage={currentPage}
      onClose={() => setQuotaEvent(null)}
      quotaEvent={quotaEvent}
    />
  );
}

function BackendConnectionPanel() {
  const { apiBaseUrl, connect, error, refreshSession, status } = useSession();
  const [isResetting, setIsResetting] = useState(false);
  const isChecking = status === "connecting";
  const defaultApiBaseUrl = getDefaultApiBaseUrl();
  const isUsingDefaultApi = String(apiBaseUrl || "").trim() === defaultApiBaseUrl;

  function handleRetry() {
    refreshSession().catch(() => undefined);
  }

  function handleResetApiBaseUrl() {
    setIsResetting(true);
    connect({ baseUrl: defaultApiBaseUrl })
      .catch(() => undefined)
      .finally(() => setIsResetting(false));
  }

  return (
    <section className="mx-auto max-w-3xl rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">
            Backend connection
          </p>
          <h1 className="mt-3 font-headline text-2xl font-bold tracking-tight text-on-surface">
            {isChecking ? "Connecting to Runr API" : "Runr API is not reachable"}
          </h1>
          <p className="mt-3 text-sm leading-7 text-on-surface-variant">
            {isChecking
              ? "The app is waiting for the authenticated backend session to finish."
              : error || "The frontend could not authenticate with the backend API."}
          </p>
        </div>
        <span
          className={[
            "material-symbols-outlined rounded-full p-3 text-2xl",
            isChecking
              ? "bg-primary/10 text-primary"
              : "bg-error-container text-on-error-container",
          ].join(" ")}
        >
          {isChecking ? "sync" : "cloud_off"}
        </span>
      </div>

      <div className="mt-6 rounded-lg border border-outline-variant/15 bg-surface p-4 text-sm text-on-surface-variant">
        <span className="font-semibold text-on-surface">API target:</span>
        {" "}
        <span className="break-all">{apiBaseUrl || defaultApiBaseUrl}</span>
      </div>

      <div className="mt-6 flex flex-wrap gap-3">
        <button
          className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          disabled={isChecking}
          onClick={handleRetry}
          type="button"
        >
          <span className="material-symbols-outlined text-[18px]">refresh</span>
          Retry
        </button>
        {!isUsingDefaultApi ? (
          <button
            className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/20 bg-surface-container-low px-4 py-2.5 text-sm font-semibold text-on-surface transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isResetting}
            onClick={handleResetApiBaseUrl}
            type="button"
          >
            <span className="material-symbols-outlined text-[18px]">settings_backup_restore</span>
            {isResetting ? "Resetting..." : "Use default API"}
          </button>
        ) : null}
      </div>
    </section>
  );
}

function AuthenticatedApp() {
  const location = useLocation();
  const { isConnected, user } = useSession();
  const lastTrackedPageRef = useRef("");
  const userId = String(user?.user_id || user?.email || "").trim();

  useEffect(() => {
    if (!isConnected) {
      lastTrackedPageRef.current = "";
      return;
    }
    const page = `${location.pathname}${location.search}${location.hash}`;
    if (lastTrackedPageRef.current === page) {
      return;
    }
    lastTrackedPageRef.current = page;
    logEvent("page_view", {
      page,
      user_id: userId,
    });
  }, [isConnected, location.hash, location.pathname, location.search, userId]);

  return (
    <AppShell muteSidebar={!isConnected}>
      <UpgradeModalHost />
      {isConnected ? (
        <RouteErrorBoundary key={`${location.pathname}${location.search}`}>
          <Suspense fallback={<RouteLoadingFallback />}>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/dashboard" element={<Navigate replace to="/" />} />
              <Route path="/workspaces" element={<WorkspacesPage />} />
              <Route path="/quick-apply" element={<QuickApplyPage />} />
              <Route path="/runs" element={<RunsPage />} />
              <Route path="/runs/:runId" element={<RunDetailPage />} />
              <Route path="/job-workspaces/:runId/:jobId" element={<JobWorkspacePage />} />
              <Route path="/review-queue" element={<Navigate replace to="/tracker" />} />
              <Route path="/tracker" element={<TrackerPage />} />
              <Route path="/tracker/job-descriptions/:reviewId" element={<JobDescriptionPage />} />
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/career-memory" element={<Navigate replace to="/documents?view=memory" />} />
              <Route path="/career-memory/guide" element={<DocumentAICanvasGuidePage />} />
              <Route path="/documents/ai-canvas-guide" element={<Navigate replace to="/career-memory/guide" />} />
              <Route path="/cv-studio" element={<CvStudioPage />} />
              <Route path="/artifacts" element={<Navigate replace to="/documents" />} />
              <Route path="/referrals" element={<ReferralsPage />} />
              <Route path="/referrals/linkedin-csv-guide" element={<LinkedInConnectionsGuidePage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/pricing" element={<PricingPage />} />
              <Route
                path="/admin"
                element={(
                  <RequireAdminRoute>
                    <AdminPage />
                  </RequireAdminRoute>
                )}
              />
              <Route
                path="/admin/events"
                element={(
                  <RequireAdminRoute>
                    <AdminEventsPage />
                  </RequireAdminRoute>
                )}
              />
              <Route
                path="/admin/scrapeops"
                element={(
                  <RequireAdminRoute>
                    <AdminScrapeOpsPage />
                  </RequireAdminRoute>
                )}
              />
              <Route path="*" element={<Navigate replace to="/" />} />
            </Routes>
          </Suspense>
        </RouteErrorBoundary>
      ) : (
        <BackendConnectionPanel />
      )}
    </AppShell>
  );
}

function ProtectedAppRoute() {
  return (
    <Show fallback={<RedirectToSignIn />} when="signed-in">
      <AuthenticatedApp />
    </Show>
  );
}

function PublicAuthRoute({ mode }) {
  return (
    <Show fallback={<Navigate replace to="/" />} when="signed-out">
      <AppShell muteSidebar>
        <ConnectionPanel mode={mode} />
      </AppShell>
    </Show>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/sign-in/*" element={<PublicAuthRoute mode="sign-in" />} />
      <Route path="/sign-up/*" element={<PublicAuthRoute mode="sign-up" />} />
      <Route path="*" element={<ProtectedAppRoute />} />
    </Routes>
  );
}

export default function App() {
  return (
    <SessionProvider>
      <AppRoutes />
    </SessionProvider>
  );
}
