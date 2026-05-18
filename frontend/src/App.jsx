import { RedirectToSignIn, Show } from "@clerk/react";
import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import AppShell from "./components/AppShell";
import ConnectionPanel from "./components/ConnectionPanel";
import UpgradeModal from "./components/UpgradeModal";
import { SessionProvider, useSession } from "./context/SessionContext";
import { QUOTA_EXCEEDED_EVENT } from "./lib/api";
import { logEvent } from "./lib/analytics";
import { isAdminUser } from "./lib/auth";

const AdminPage = lazy(() => import("./pages/AdminPage"));
const AdminEventsPage = lazy(() => import("./pages/AdminEventsPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const CvStudioPage = lazy(() => import("./pages/CvStudioPage"));
const DocumentsPage = lazy(() => import("./pages/ArtifactsPage"));
const DocumentAICanvasGuidePage = lazy(() => import("./pages/DocumentAICanvasGuidePage"));
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
    <AppShell>
      <UpgradeModalHost />
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
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/documents/ai-canvas-guide" element={<DocumentAICanvasGuidePage />} />
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
          <Route path="*" element={<Navigate replace to="/" />} />
        </Routes>
      </Suspense>
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
      <AppShell>
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
