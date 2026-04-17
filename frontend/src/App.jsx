import { Route, Routes } from "react-router-dom";
import AdminPage from "./pages/AdminPage";
import AppShell from "./components/AppShell";
import ArtifactsPage from "./pages/ArtifactsPage";
import ConnectionPanel from "./components/ConnectionPanel";
import { useSession } from "./context/SessionContext";
import DashboardPage from "./pages/DashboardPage";
import ReviewQueuePage from "./pages/ReviewQueuePage";
import RunDetailPage from "./pages/RunDetailPage";
import RunsPage from "./pages/RunsPage";
import SettingsPage from "./pages/SettingsPage";
import WorkspacesPage from "./pages/WorkspacesPage";

export default function App() {
  const { isConnected } = useSession();

  return (
    <AppShell>
      {isConnected ? (
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/workspaces" element={<WorkspacesPage />} />
          <Route path="/runs" element={<RunsPage />} />
          <Route path="/runs/:runId" element={<RunDetailPage />} />
          <Route path="/review-queue" element={<ReviewQueuePage />} />
          <Route path="/artifacts" element={<ArtifactsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      ) : (
        <ConnectionPanel />
      )}
    </AppShell>
  );
}
