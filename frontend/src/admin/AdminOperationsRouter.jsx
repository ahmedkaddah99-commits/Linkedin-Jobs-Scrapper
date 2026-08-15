import { Suspense, lazy } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import AdminOperationsShell from "../components/admin/AdminOperationsShell";
import { AdminState } from "../components/admin/AdminPrimitives";
import { compatibilityTarget } from "./adminRoutes";
import { AdminNotFoundPage, AdminSystemHealthPage } from "./AdminPlatformPages";

const AcquisitionOperationsPage = lazy(() => import("../pages/AcquisitionOperationsPage"));
const AdminAcquisitionPage = lazy(() => import("../pages/AdminAcquisitionPage"));
const AdminAcquisitionAnalyticsPage = lazy(() => import("../pages/AdminAcquisitionAnalyticsPage"));
const AdminEventsPage = lazy(() => import("../pages/AdminEventsPage"));
const AdminPage = lazy(() => import("../pages/AdminPage"));
const AdminScrapeOpsPage = lazy(() => import("../pages/AdminScrapeOpsPage"));

function CompatibilityRedirect() {
  const location = useLocation();
  const target = compatibilityTarget(location.pathname, location.search);
  return target ? <Navigate replace to={target} /> : <AdminNotFoundPage />;
}

export default function AdminOperationsRouter() {
  return <AdminOperationsShell><Suspense fallback={<AdminState description="The protected admin module is loading." kind="loading" title="Loading admin area" />}><Routes>
    <Route path="/admin" element={<AcquisitionOperationsPage />} />
    <Route path="/admin/analytics" element={<AdminAcquisitionAnalyticsPage />} />
    <Route path="/admin/acquisition/sources" element={<AcquisitionOperationsPage />} />
    <Route path="/admin/acquisition/imports" element={<AdminAcquisitionPage section="imports" />} />
    <Route path="/admin/acquisition/imports/:importId" element={<AdminAcquisitionPage section="imports" />} />
    <Route path="/admin/acquisition/jobs" element={<AcquisitionOperationsPage />} />
    <Route path="/admin/acquisition/jobs/:canonicalJobId" element={<AcquisitionOperationsPage />} />
    <Route path="/admin/acquisition/companies" element={<AdminAcquisitionPage section="companies" />} />
    <Route path="/admin/acquisition/companies/:canonicalCompanyId" element={<AdminAcquisitionPage section="companies" />} />
    <Route path="/admin/acquisition/enrichment" element={<AdminAcquisitionPage section="enrichment" />} />
    <Route path="/admin/acquisition/data-quality" element={<AdminAcquisitionPage section="data-quality" />} />
    <Route path="/admin/acquisition/rules" element={<AdminAcquisitionPage section="rules" />} />
    <Route path="/admin/acquisition/reprocessing" element={<AdminAcquisitionPage section="reprocessing" />} />
    <Route path="/admin/acquisition/duplicates" element={<AdminAcquisitionPage section="duplicates" />} />
    <Route path="/admin/acquisition/publication" element={<AdminAcquisitionPage section="publication" />} />
    <Route path="/admin/acquisition/live-catalog" element={<AdminAcquisitionPage section="live-catalog" />} />
    <Route path="/admin/acquisition/audit" element={<AdminAcquisitionPage section="audit" />} />
    <Route path="/admin/system" element={<AdminSystemHealthPage />} />
    <Route path="/admin/provider-policy" element={<AdminScrapeOpsPage />} />
    <Route path="/admin/events" element={<AdminEventsPage />} />
    <Route path="/admin/promotions" element={<AdminPage deferExternalLoad initialTab="promoCodes" key="promotions" pageTitle="Promotions" showTabs={false} />} />
    <Route path="/admin/access" element={<AdminPage includePromotions={false} initialTab="users" key="access" pageTitle="Access and permissions" />} />
    <Route path="/admin/acquisition" element={<CompatibilityRedirect />} />
    <Route path="/admin/acquisition/analytics" element={<CompatibilityRedirect />} />
    <Route path="/admin/job-import" element={<CompatibilityRedirect />} />
    <Route path="/admin/scrapeops" element={<CompatibilityRedirect />} />
    <Route path="/admin/*" element={<AdminNotFoundPage />} />
  </Routes></Suspense></AdminOperationsShell>;
}
