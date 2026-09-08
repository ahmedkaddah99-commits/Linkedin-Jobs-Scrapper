import { RedirectToSignIn, Show } from "@clerk/react";
import { Component, Suspense, lazy, useEffect, useRef, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import AppShell from "./components/AppShell";
import ConnectionPanel from "./components/ConnectionPanel";
import UpgradeModal from "./components/UpgradeModal";
import { SessionProvider, useSession } from "./context/SessionContext";
import MarketingSite from "./pages/MarketingSite";
import { QUOTA_EXCEEDED_EVENT } from "./lib/api";
import { logEvent } from "./lib/analytics";
import { isAdminUser } from "./lib/auth";
import { personalizedJobsDataMode, personalizedJobsExperienceEnabled } from "./lib/personalizedJobsConfig";
import { hasAuthenticatedSession } from "./lib/sessionState";

const AdminOperationsRouter = lazy(() => import("./admin/AdminOperationsRouter"));
const AssistedApplyConnectionPage = lazy(() => import("./pages/AssistedApplyConnectionPage"));
const ApplyExtensionSetupPage = lazy(() => import("./pages/ApplyExtensionSetupPage"));
const CareerProfilesPage = lazy(() => import("./pages/CareerProfilesPage"));

const appSubdomain = typeof window !== "undefined" && window.location.hostname === "app.userunr.com";

const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const HomePage = lazy(() => import("./pages/HomePage"));
const CareerEvidencePage = lazy(() => import("./pages/CareerEvidencePage"));
const CvStudioPage = lazy(() => import("./pages/CvStudioPage"));
const DocumentsPage = lazy(() => import("./pages/DocumentsPage"));
const CvEditorPage = lazy(() => import("./pages/CvEditorPage"));
const MasterCvPage = lazy(() => import("./pages/MasterCvPage"));
const CareerAssetsPage = lazy(() => import("./pages/ArtifactsPage"));
const JobDescriptionPage = lazy(() => import("./pages/JobDescriptionPage"));
const JobWorkspacePage = lazy(() => import("./pages/JobWorkspacePage"));
const PricingPage = lazy(() => import("./pages/PricingPage"));
const ReferralsPage = lazy(() => import("./pages/ReferralsPage"));
const LinkedInConnectionsGuidePage = lazy(() => import("./pages/LinkedInConnectionsGuidePage"));
const QuickApplyPage = lazy(() => import("./pages/QuickApplyPage"));
const RunDetailPage = lazy(() => import("./pages/RunDetailPage"));
const RunsPage = lazy(() => import("./pages/RunsPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const TrackerPage = lazy(() => import("./pages/TrackerPage"));
const TrackerAtsPage = lazy(() => import("./pages/TrackerAtsPage"));
const WorkspacesPage = lazy(() => import("./pages/WorkspacesPage"));
const PersonalizedJobsPage = lazy(() => import("./pages/PersonalizedJobsPage"));
const HiddenJobsPage = lazy(() => import("./pages/HiddenJobsPage"));
const PersonalizedJobDetailPage = lazy(() => import("./pages/PersonalizedJobDetailPage"));
const PersonalizedOnboardingPage = lazy(() => import("./pages/PersonalizedOnboardingPage"));
const browserTestMode = import.meta.env.VITE_E2E_AUTH === "1";

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
  const { error, refreshSession, status } = useSession();
  const isChecking = status === "connecting";

  function handleRetry() {
    refreshSession().catch(() => undefined);
  }

  if (isChecking) {
    return <RouteLoadingFallback />;
  }

  return (
    <section className="mx-auto max-w-3xl rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">
            Service status
          </p>
          <h1 className="mt-3 font-headline text-2xl font-bold tracking-tight text-on-surface">
            Runr is temporarily unavailable
          </h1>
          <p className="mt-3 text-sm leading-7 text-on-surface-variant">
            {error || "We could not load your account. Retry in a moment."}
          </p>
        </div>
        <span className="material-symbols-outlined rounded-full bg-error-container p-3 text-2xl text-on-error-container">
          cloud_off
        </span>
      </div>

      <div className="mt-6 flex flex-wrap gap-3">
        <button
          className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          onClick={handleRetry}
          type="button"
        >
          <span className="material-symbols-outlined text-[18px]">refresh</span>
          Retry
        </button>
      </div>
    </section>
  );
}

function AuthenticatedApp() {
  const location = useLocation();
  const { status, user } = useSession();
  const hasSession = hasAuthenticatedSession(status, user);
  const lastTrackedPageRef = useRef("");
  const userId = String(user?.user_id || user?.email || "").trim();

  useEffect(() => {
    if (!personalizedJobsExperienceEnabled || !location.pathname.startsWith("/jobs")) return undefined;
    const preload = () => {
      if (personalizedJobsDataMode !== "real") {
        void import("./pages/PersonalizedOnboardingPage");
      }
      void import("./pages/PersonalizedJobsPage");
      void import("./pages/HiddenJobsPage");
      void import("./pages/PersonalizedJobDetailPage");
    };
    const idleId = window.requestIdleCallback?.(preload, { timeout: 2000 });
    const timeoutId = idleId === undefined ? window.setTimeout(preload, 1200) : undefined;
    return () => {
      if (idleId !== undefined) window.cancelIdleCallback?.(idleId);
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };
  }, [location.pathname]);

  useEffect(() => {
    if (!hasSession) {
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
  }, [hasSession, location.hash, location.pathname, location.search, userId]);

  if (location.pathname === "/admin" || location.pathname.startsWith("/admin/")) {
    return (
      <RouteErrorBoundary>
        <Suspense fallback={<RouteLoadingFallback />}>
          {hasSession ? (
            <RequireAdminRoute>
              <AdminOperationsRouter />
            </RequireAdminRoute>
          ) : <BackendConnectionPanel />}
        </Suspense>
      </RouteErrorBoundary>
    );
  }

  return (
    <AppShell muteSidebar={!hasSession}>
      <UpgradeModalHost />
      {hasSession ? (
        <RouteErrorBoundary key={`${location.pathname}${location.search}`}>
          <Suspense fallback={<RouteLoadingFallback />}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/home" element={<Navigate replace to="/" />} />
              <Route path="/onboarding" element={personalizedJobsExperienceEnabled && personalizedJobsDataMode !== "real" ? <PersonalizedOnboardingPage /> : <Navigate replace to="/jobs" />} />
              <Route path="/jobs" element={personalizedJobsExperienceEnabled ? <PersonalizedJobsPage /> : <Navigate replace to="/" />} />
              <Route path="/matches" element={<Navigate replace to="/jobs" />} />
              <Route path="/jobs/hidden" element={personalizedJobsExperienceEnabled ? <HiddenJobsPage /> : <Navigate replace to="/" />} />
              <Route path="/jobs/:jobId" element={personalizedJobsExperienceEnabled ? <PersonalizedJobDetailPage /> : <Navigate replace to="/" />} />
              <Route path="/career-profiles" element={<Navigate replace to="/career-evidence" />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/workspaces" element={<WorkspacesPage />} />
              <Route path="/quick-apply" element={<QuickApplyPage />} />
              <Route path="/runs" element={<RunsPage />} />
              <Route path="/runs/:runId" element={<RunDetailPage />} />
              <Route path="/job-workspaces/:runId/:jobId" element={<JobWorkspacePage />} />
              <Route path="/review-queue" element={<Navigate replace to="/tracker" />} />
              <Route path="/tracker" element={<TrackerPage />} />
              <Route path="/tracker/:reviewId/ats" element={<TrackerAtsPage />} />
              <Route path="/tracker/job-descriptions/:reviewId" element={<JobDescriptionPage />} />
              <Route path="/documents/assets/:assetId/edit" element={<CvEditorPage />} />
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/master-cv" element={<MasterCvPage />} />
              <Route path="/career-assets" element={<CareerAssetsPage />} />
              <Route path="/career-evidence" element={<CareerProfilesPage />} />
              <Route path="/career-evidence/:profileId" element={<CareerEvidencePage />} />
              <Route path="/career-memory" element={<Navigate replace to="/career-evidence" />} />
              <Route path="/career-memory/guide" element={<Navigate replace to="/career-evidence" />} />
              <Route path="/documents/ai-canvas-guide" element={<Navigate replace to="/career-evidence" />} />
              <Route path="/cv-studio" element={<CvStudioPage />} />
              <Route path="/artifacts" element={<Navigate replace to="/career-assets" />} />
              <Route path="/referrals" element={<ReferralsPage />} />
              <Route path="/services" element={<Navigate replace to="/refer" />} />
              <Route path="/refer" element={<ReferralsPage />} />
              <Route path="/referrals/linkedin-csv-guide" element={<LinkedInConnectionsGuidePage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/profile" element={<ProfilePage />} />
              <Route path="/settings/assisted-apply" element={<AssistedApplyConnectionPage />} />
              <Route path="/apply-extension" element={<ApplyExtensionSetupPage />} />
              <Route path="/pricing" element={<PricingPage />} />
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
  if (browserTestMode) return <AuthenticatedApp />;
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
      {appSubdomain ? (
        <Route path="/" element={<ProtectedAppRoute />} />
      ) : (
        <>
          <Route path="/" element={<MarketingSite page="home" />} />
          <Route path="/how-it-works" element={<Navigate replace to="/#how-it-works" />} />
          <Route path="/pricing" element={<Navigate replace to="/#pricing" />} />
          <Route path="/security" element={<MarketingSite page="security" />} />
          <Route path="/terms" element={<MarketingSite page="terms" />} />
          <Route path="/terms-and-conditions" element={<MarketingSite page="terms" />} />
          <Route path="/user-agreement" element={<MarketingSite page="privacy" />} />
          <Route path="/privacy" element={<MarketingSite page="privacy" />} />
        </>
      )}
      <Route path="/sign-in/*" element={<PublicAuthRoute mode="sign-in" />} />
      <Route path="/sign-up/*" element={<PublicAuthRoute mode="sign-up" />} />
      <Route path="*" element={<ProtectedAppRoute />} />
    </Routes>
  );
}

export default function App() {
  if (browserTestMode) return <AppRoutes />;
  return (
    <SessionProvider>
      <AppRoutes />
    </SessionProvider>
  );
}
