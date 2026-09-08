import { Link } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { getApiErrorMessage } from "../lib/api";
import { formatDateTime, labelize } from "../lib/formatters";
import { AdminBadge, AdminMetric, AdminPanel, AdminSection, AdminState } from "../components/admin/AdminPrimitives";

function value(value, fallback = "Unknown") {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "boolean") return value ? "Enabled" : "Disabled";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function healthTone(status) {
  const normalized = String(status || "").toLowerCase();
  if (["ready", "healthy", "ok", "connected", "enabled"].includes(normalized)) return "success";
  if (["failed", "unhealthy", "error", "blocked"].includes(normalized)) return "danger";
  return "neutral";
}

function HealthDetails({ payload }) {
  const entries = Object.entries(payload || {}).filter(([, item]) => typeof item !== "object" || item === null).slice(0, 16);
  if (!entries.length) return <AdminState description="The endpoint returned no scalar health fields." title="No health detail available" />;
  return <dl className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3">{entries.map(([key, item]) => <div className="rounded-xl border border-outline-variant/10 p-3" key={key}><dt className="text-xs text-on-surface-variant">{labelize(key)}</dt><dd className="mt-1 break-words text-sm font-semibold text-on-surface">{key.includes("_at") ? formatDateTime(item) : value(item)}</dd></div>)}</dl>;
}

export function AdminSystemHealthPage() {
  const { apiBaseUrl, request, status } = useSession();
  const rollout = useApiResource(() => request("/admin/acquisition/rollout/health"), [request], { cacheKey: "admin:rollout-health", staleMs: 15000 });
  const users = useApiResource(() => request("/admin/users/health"), [request], { cacheKey: "admin:user-health", staleMs: 15000 });
  const loading = rollout.loading || users.loading;
  const refresh = () => Promise.allSettled([rollout.refresh({ showLoading: false }), users.refresh({ showLoading: false })]);
  return <AdminSection actions={<button className="admin-button admin-button--secondary" disabled={loading} onClick={() => refresh().catch(() => undefined)} type="button">{loading ? "Refreshing…" : "Refresh health"}</button>} description="Read-only operational checks from existing authenticated health contracts. Unknown fields remain explicit." eyebrow="Platform" title="System health">
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><AdminMetric detail="authenticated browser session" label="API session" tone={healthTone(status)} value={labelize(status || "unknown")} /><AdminMetric detail="configured frontend target" label="API target" value={apiBaseUrl || "Unknown"} /><AdminMetric detail="acquisition rollout contract" label="Acquisition health" tone={healthTone(rollout.data?.status)} value={value(rollout.data?.status)} /><AdminMetric detail="admin user health contract" label="User health" tone={healthTone(users.data?.status)} value={value(users.data?.status)} /></div>
    {rollout.error || users.error ? <AdminState description={[rollout.error && getApiErrorMessage(rollout.error), users.error && getApiErrorMessage(users.error)].filter(Boolean).join(" ")} kind={rollout.data || users.data ? "partial" : "error"} title={rollout.data || users.data ? "Partial health data" : "Health checks unavailable"} /> : null}
    <div className="grid gap-4 xl:grid-cols-2"><AdminPanel description="Provider policy and acquisition readiness; this view never changes rollout state." title="Acquisition rollout"><HealthDetails payload={rollout.data} /></AdminPanel><AdminPanel description="Aggregate account-health fields exposed to authenticated admins." title="User health"><HealthDetails payload={users.data} /></AdminPanel></div>
  </AdminSection>;
}

export function AdminAccessSummary() {
  const { user } = useSession();
  return <AdminSection description="Backend authorization remains authoritative and deny-by-default. This page does not grant roles or infer permissions." eyebrow="Platform" title="Access and permissions">
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><AdminMetric label="Signed-in role" tone={String(user?.role).toLowerCase() === "admin" ? "success" : "danger"} value={value(user?.role)} /><AdminMetric label="User" value={user?.email || user?.user_id || "Unknown"} /><AdminMetric label="Authorization source" value="Backend-enforced" /><AdminMetric label="Default policy" value="Deny unless authorized" /></div>
    <AdminPanel description="These areas make authenticated requests. A 403 remains visible and is never converted into an empty result." title="Admin capability boundaries"><div className="grid gap-3 p-4 md:grid-cols-2">{[
      ["Acquisition reads", "Read models require acquisition permissions."], ["Acquisition mutations", "Plan, confirmation, and operation-specific permission checks remain required."], ["Provider policy", "Admin authentication is required; provider activation is never implied by viewing policy."], ["Publication", "Preview, publish, undo, and restore retain backend confirmation and safety contracts."], ["Promotions", "Creem-backed creation and deletion remain explicit admin actions."], ["General events", "General event access is admin-only and may not include complete acquisition audit history."],
    ].map(([title, description]) => <article className="rounded-xl border border-outline-variant/10 p-4" key={title}><div className="flex items-center justify-between gap-3"><strong className="text-sm">{title}</strong><AdminBadge tone="neutral">Backend verified</AdminBadge></div><p className="mt-2 text-xs leading-5 text-on-surface-variant">{description}</p></article>)}</div></AdminPanel>
    <p className="text-sm text-on-surface-variant">Use <Link className="font-semibold text-primary" to="/admin/events">General events</Link> for platform analytics events and <Link className="font-semibold text-primary" to="/admin/acquisition/audit">Acquisition audit</Link> for acquisition evidence.</p>
  </AdminSection>;
}

export function AdminNotFoundPage() {
  return <AdminSection description="This URL is not part of the Runr admin console." eyebrow="Admin" title="Page not found"><AdminState action={<Link className="admin-button admin-button--primary" to="/admin">Return to overview</Link>} description="Check the address or choose an area from the admin navigation." title="Unknown admin route" /></AdminSection>;
}
