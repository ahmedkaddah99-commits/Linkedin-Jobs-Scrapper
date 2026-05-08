import { Navigate, Route, Routes } from "react-router-dom";
import AdminPage from "./pages/AdminPage";
import AppShell from "./components/AppShell";
import ConnectionPanel from "./components/ConnectionPanel";
import { useSession } from "./context/SessionContext";
import DashboardPage from "./pages/DashboardPage";
import CvStudioPage from "./pages/CvStudioPage";
import DocumentsPage from "./pages/ArtifactsPage";
import ReviewQueuePage from "./pages/ReviewQueuePage";
import ReferralsPage from "./pages/ReferralsPage";
import LinkedInConnectionsGuidePage from "./pages/LinkedInConnectionsGuidePage";
import QuickApplyPage from "./pages/QuickApplyPage";
import RunDetailPage from "./pages/RunDetailPage";
import RunsPage from "./pages/RunsPage";
import SettingsPage from "./pages/SettingsPage";
import TrackerPage from "./pages/TrackerPage";
import WorkspacesPage from "./pages/WorkspacesPage";

export default function App() {
  const { isConnected } = useSession();

  return (
    <AppShell>
      {isConnected ? (
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/dashboard" element={<Navigate replace to="/" />} />
          <Route path="/workspaces" element={<WorkspacesPage />} />
          <Route path="/quick-apply" element={<QuickApplyPage />} />
          <Route path="/runs" element={<RunsPage />} />
          <Route path="/runs/:runId" element={<RunDetailPage />} />
          <Route path="/review-queue" element={<ReviewQueuePage />} />
          <Route path="/tracker" element={<TrackerPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/cv-studio" element={<CvStudioPage />} />
          <Route path="/artifacts" element={<Navigate replace to="/documents" />} />
          <Route path="/referrals" element={<ReferralsPage />} />
          <Route path="/referrals/linkedin-csv-guide" element={<LinkedInConnectionsGuidePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="*" element={<Navigate replace to="/" />} />
        </Routes>
      ) : (
        <ConnectionPanel />
      )}
    </AppShell>
  );
}
