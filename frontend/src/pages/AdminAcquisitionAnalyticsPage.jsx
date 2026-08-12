import { useMemo } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import AcquisitionShell from "../components/acquisition/AcquisitionShell";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { getApiErrorMessage } from "../lib/api";
import { formatDateTime, labelize } from "../lib/formatters";

const RANGE_OPTIONS = [
  ["24h", "Last 24 hours"],
  ["7d", "Last 7 days"],
  ["30d", "Last 30 days"],
];

function count(value) {
  return value === null || value === undefined ? "Unknown" : Number(value).toLocaleString();
}

function text(value, fallback = "Unknown") {
  const normalized = String(value ?? "").trim();
  return normalized || fallback;
}

function statusTone(value) {
  const normalized = String(value || "").toLowerCase();
  if (["completed", "successful", "ready", "valid", "matched", "published", "complete"].some((item) => normalized.includes(item))) return "success";
  if (["failed", "blocked", "paused", "partial", "unknown", "unavailable", "ambiguous", "retryable", "permanent"].some((item) => normalized.includes(item))) return "warning";
  return "neutral";
}

function Status({ value }) {
  const label = text(value);
  return <StatusBadge tone={statusTone(label)}>{labelize(label)}</StatusBadge>;
}

function Panel({ title, description, children }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-outline-variant/20 bg-surface-container-lowest shadow-soft">
      <div className="flex flex-col gap-2 border-b border-outline-variant/10 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="font-headline text-lg font-bold text-on-surface">{title}</h2>
          {description ? <p className="mt-1 text-sm leading-6 text-on-surface-variant">{description}</p> : null}
        </div>
      </div>
      {children}
    </section>
  );
}

function MetricCard({ label, value, detail, href }) {
  const content = (
    <article className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-on-surface-variant">{label}</p>
      <strong className="mt-3 block break-words font-headline text-3xl font-extrabold tracking-tight text-on-surface">{count(value)}</strong>
      <p className="mt-2 text-xs leading-5 text-on-surface-variant">{detail}</p>
    </article>
  );
  return href ? <Link className="block rounded-2xl focus:outline-none focus:ring-2 focus:ring-primary/40" to={href}>{content}</Link> : content;
}

function Table({ headers, rows, empty = "No authoritative rows are available for this period." }) {
  if (!rows.length) return <p className="px-5 py-8 text-sm text-on-surface-variant">{empty}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[48rem] text-left text-sm">
        <thead className="bg-surface-container-low text-xs uppercase tracking-[0.1em] text-on-surface-variant">
          <tr>{headers.map(([key, label]) => <th className="px-5 py-3 font-bold" key={key}>{label}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-outline-variant/10">
          {rows.map((row, index) => (
            <tr className="align-top" key={row.key || row.id || `${index}`}>
              {headers.map(([key, , render]) => <td className="px-5 py-4 text-on-surface-variant" key={key}>{render ? render(row) : text(row[key])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ErrorBlock({ error, onRetry }) {
  return <div className="rounded-2xl border border-error/20 bg-error-container px-4 py-3 text-sm text-on-error-container" role="alert"><div className="flex flex-wrap items-center justify-between gap-3"><span>{error || "Analytics could not be loaded."}</span><button className="rounded-lg border border-current/20 px-3 py-2 text-xs font-bold" onClick={onRetry} type="button">Retry</button></div></div>;
}

function Funnel({ data }) {
  const rows = (data?.stages || []).map((stage) => ({ ...stage, key: stage.key }));
  return <Panel title="Acquisition funnel" description="Counts use one event window and evaluate snapshot stages at period end. Each row is a distinct canonical job ID; versions do not inflate the canonical stage."><Table headers={[["label", "Stage"], ["count", "Count"], ["definition", "What is counted"]]} rows={rows} /></Panel>;
}

function OperationCounts({ data }) {
  const rows = Object.entries(data || {}).flatMap(([group, values]) => Object.entries(values || {}).map(([status, value]) => ({ key: `${group}-${status}`, group: labelize(group), status, count: value })));
  return <Panel title="Run outcomes" description="Status buckets are normalized from durable collection cycles and admin import records. Pending and queued states are running work; unsupported states are not guessed."><Table headers={[["group", "Operation kind"], ["status", "Outcome", (row) => <Status value={row.status} />], ["count", "Runs", (row) => count(row.count)]]} rows={rows} empty="No collection or import runs were recorded in this period." /></Panel>;
}

function Sources({ rows }) {
  return <Panel title="Source performance" description="Rates and request usage are calculated from durable acquisition attempts and requests. Bounded collection is reported as state, never as an invented completeness score."><Table headers={[["name", "Source"], ["runs", "Runs", (row) => count(row.runs)], ["success_rate", "Success / partial / failure", (row) => <span className="inline-flex flex-col gap-1"><span>{row.success_rate === null ? "Unknown" : `${Math.round(row.success_rate * 100)}%`} success</span><span>{row.partial_rate === null ? "Unknown" : `${Math.round(row.partial_rate * 100)}%`} partial</span><span>{row.failure_rate === null ? "Unknown" : `${Math.round(row.failure_rate * 100)}%`} failure</span></span>], ["observations", "Observations", (row) => count(row.observations)], ["new_canonical_jobs", "New canonical", (row) => count(row.new_canonical_jobs)], ["updated_jobs", "Updated", (row) => count(row.updated_jobs)], ["readiness", "Readiness", (row) => <span className="inline-flex flex-col gap-1"><Status value={row.readiness} /><span className="text-xs">Bounded: {text(row.bounded_collection?.state)}</span></span>], ["last_attempted_collection", "Last attempted", (row) => formatDateTime(row.last_attempted_collection)]]} rows={rows.map((row) => ({ ...row, key: row.source_id }))} /></Panel>;
}

function Quality({ data }) {
  const rows = (data?.by_rule || []).map((row) => ({ ...row, key: `${row.rule}-${row.severity}` }));
  const fields = (data?.by_field || []).map((row) => ({ ...row, key: row.field }));
  return <Panel title="Data quality" description="Findings are report and review information only. The current contract does not persist reviewed or resolved states, so those values remain explicitly unknown."><div className="grid gap-4 p-5 sm:grid-cols-3"><MetricCard label="Created" value={data?.findings_created} detail="quality events in period" /><MetricCard label="Reviewed" value={data?.reviewed_count} detail="not persisted by current contract" /><MetricCard label="Resolved" value={data?.resolved_count} detail="not persisted by current contract" /></div><Table headers={[["rule", "Rule / category"], ["severity", "Severity"], ["count", "Findings", (row) => count(row.count)], ["navigate", "Inspect"]]} rows={rows.map((row) => ({ ...row, navigate: <Link className="font-semibold text-primary underline-offset-2 hover:underline" to={`/admin/acquisition/jobs?warning_type=${encodeURIComponent(row.rule)}`}>Open filtered jobs</Link> }))} empty="No quality findings were created in this period." /><div className="border-t border-outline-variant/10"><Table headers={[["field", "Most affected field"], ["count", "Findings", (row) => count(row.count)]]} rows={fields} empty="Affected fields are unavailable for these findings." /></div><div className="flex flex-wrap gap-3 border-t border-outline-variant/10 px-5 py-4 text-sm"><Link className="font-semibold text-primary underline-offset-2 hover:underline" to="/admin/acquisition/jobs">Inspect filtered Jobs</Link><Link className="font-semibold text-primary underline-offset-2 hover:underline" to="/admin/acquisition/companies">Inspect Companies</Link><Link className="font-semibold text-primary underline-offset-2 hover:underline" to="/admin/acquisition/data-quality">Open Data Quality</Link><span className="text-on-surface-variant">{text(data?.resolution_note, "Resolution state is unavailable.")}</span></div></Panel>;
}

function Enrichment({ data }) {
  const totals = Object.entries(data?.state_totals || {}).map(([state, value]) => ({ key: state, state, value }));
  const rows = (data?.by_state || []).map((row, index) => ({ ...row, key: `${row.provider}-${row.target_type}-${row.field_path}-${row.state}-${index}` }));
  return <Panel title="Enrichment analytics" description="These are durable report-only operation items. Providers are not activated and analytics never issue a live provider request."><div className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-4">{totals.length ? totals.map((item) => <div className="rounded-xl bg-surface-container-low p-4" key={item.key}><span className="text-xs text-on-surface-variant">{labelize(item.state)}</span><strong className="mt-1 block text-xl text-on-surface">{count(item.value)}</strong></div>) : <p className="text-sm text-on-surface-variant">No enrichment results are available for this period.</p>}</div><Table headers={[["provider", "Provider"], ["target_type", "Boundary"], ["field_path", "Field"], ["state", "State"], ["count", "Results", (row) => count(row.count)]]} rows={rows} /><div className="border-t border-outline-variant/10"><Table headers={[["action", "Proposal decision"], ["count", "Actions", (row) => count(row.count)]]} rows={(data?.proposal_actions || []).map((row) => ({ ...row, key: row.action }))} empty="No proposal decisions are available for this period." /></div><div className="border-t border-outline-variant/10 px-5 py-4 text-sm text-on-surface-variant">Cache hit and miss telemetry is {data?.cache?.available ? "available" : "unavailable"}; request and cost usage is shown only where durable provider-operation usage exists. Provider activation: {data?.provider_activation ? "enabled" : "disabled"}.</div></Panel>;
}

function Publication({ data }) {
  const head = data?.current_head || {};
  const metrics = [["publication_count", "Publications", "in selected period"], ["preview_count", "Previews", "staging records"], ["added_count", "Added", "preflight count"], ["removed_count", "Removed", "preflight count"], ["retained_count", "Retained", "same IDs in next snapshot"], ["changed_count", "Changed", "preflight count"]];
  return <Panel title="Publication and live catalog" description="Analytics never mutate publication. Live count and age use the latest valid publication snapshot at period end."><div className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-3">{metrics.map(([key, label, detail]) => <MetricCard detail={detail} key={key} label={label} value={data?.[key]} />)}</div><div className="mx-5 mb-5 rounded-xl border border-primary/15 bg-primary/5 p-4"><div className="flex flex-wrap items-center gap-3"><strong className="font-mono text-sm text-on-surface">{text(head.publication_id, "No valid publication head")}</strong><Status value={head.publication_id ? "valid" : "unavailable"} /></div><p className="mt-2 text-sm text-on-surface-variant">{count(head.job_count)} live jobs - publication age {head.age_seconds === null || head.age_seconds === undefined ? "Unknown" : `${Math.floor(head.age_seconds / 3600)}h`} - {formatDateTime(head.published_at)}</p><Link className="mt-3 inline-flex font-semibold text-primary underline-offset-2 hover:underline" to="/admin/acquisition/live-catalog">Open live catalog</Link></div><Table headers={[["publication_id", "Publication"], ["status", "Status"], ["published_at", "Created"], ["origin", "Origin"], ["added", "Added", (row) => count(row.added)], ["removed", "Removed", (row) => count(row.removed)], ["changed", "Changed", (row) => count(row.changed)]]} rows={(data?.history || []).map((row) => ({ ...row, key: row.publication_id, published_at: formatDateTime(row.published_at) }))} empty="No publication previews or publications were created in this period." /></Panel>;
}

function Operations({ rows }) {
  const tableRows = rows.map((row) => ({ ...row, key: `${row.kind}-${row.id}`, kind: `${labelize(row.kind)} - ${row.id}`, failure_code: row.failure_code || "None" }));
  return <Panel title="Operational status" description="Active and recent asynchronous work from durable operation state. Progress is shown only when the owning contract exposes exact item and task counts."><Table headers={[["kind", "Operation"], ["status", "Status", (row) => <Status value={row.status} />], ["created_at", "Created", (row) => formatDateTime(row.created_at)], ["progress", "Progress", (row) => row.progress?.percentage === null || row.progress?.percentage === undefined ? "Not available" : `${row.progress.percentage}%`], ["failure_code", "Failure"], ["href", "Owner", (row) => <Link className="font-semibold text-primary underline-offset-2 hover:underline" to={row.href}>Open screen</Link>]]} rows={tableRows} empty="No active or recent asynchronous operations are available." /></Panel>;
}

export default function AdminAcquisitionAnalyticsPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { request } = useSession();
  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const range = RANGE_OPTIONS.some(([value]) => value === params.get("range")) ? params.get("range") : "7d";
  const timezone = params.get("timezone") || "UTC";
  const requestPath = `/admin/acquisition/analytics?range=${encodeURIComponent(range)}&timezone=${encodeURIComponent(timezone)}`;
  const resource = useApiResource(() => request(requestPath), [requestPath, request], { cacheKey: `acquisition:analytics:${requestPath}`, staleMs: 15000 });
  const data = resource.data || {};

  function updateQuery(nextRange) {
    const next = new URLSearchParams(location.search);
    next.set("range", nextRange);
    if (!next.get("timezone")) next.set("timezone", timezone);
    next.delete("start");
    next.delete("end");
    navigate(`/admin/acquisition/analytics?${next.toString()}`);
  }

  return <AcquisitionShell description="Read-only operational analytics for the bounded acquisition pipeline. Every count comes from a durable backend contract or is shown as unknown." title="Analytics"><div className="flex flex-col gap-3 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-4 shadow-soft sm:flex-row sm:items-end sm:justify-between"><div><label className="block text-xs font-semibold text-on-surface-variant" htmlFor="acquisition-analytics-range">Period</label><select className="mt-2 min-h-11 rounded-xl border border-outline-variant/20 bg-surface px-3 text-sm text-on-surface outline-none focus:border-primary focus:ring-2 focus:ring-primary/20" id="acquisition-analytics-range" onChange={(event) => updateQuery(event.target.value)} value={range}>{RANGE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div><div className="text-sm text-on-surface-variant"><p>Timezone: <span className="font-semibold text-on-surface">{text(data.window?.timezone, timezone)}</span></p><p className="mt-1">{formatDateTime(data.window?.start)} to {formatDateTime(data.window?.end)} - {data.window?.boundary || "start inclusive, end exclusive"}</p></div><button className="min-h-11 rounded-xl border border-outline-variant/20 px-4 py-2 text-sm font-semibold text-on-surface hover:bg-surface-container-high disabled:opacity-60" disabled={resource.refreshing} onClick={() => resource.refresh({ showLoading: false }).catch(() => undefined)} type="button">{resource.refreshing ? "Refreshing..." : "Refresh"}</button></div>{resource.error && resource.data ? <ErrorBlock error={getApiErrorMessage(resource.error, "Previous analytics remain visible; refresh failed.")} onRetry={() => resource.refresh({ showLoading: false }).catch(() => undefined)} /> : null}{resource.loading && !resource.data ? <div aria-label="Loading acquisition analytics" className="rounded-2xl bg-surface-container p-8 text-sm text-on-surface-variant" role="status">Loading analytics...</div> : null}{resource.error && !resource.data ? <ErrorBlock error={getApiErrorMessage(resource.error, "Analytics could not be loaded.")} onRetry={() => resource.refresh().catch(() => undefined)} /> : null}{!resource.loading && !resource.error ? <><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[["Collection runs", data.summary?.collection_runs, "acquisition cycles in period", "/admin/acquisition/imports"], ["Observations", data.summary?.observations_received, "immutable observations received", "/admin/acquisition/jobs"], ["New canonical jobs", data.summary?.new_canonical_jobs, "canonical rows created", "/admin/acquisition/jobs"], ["Live jobs", data.publication?.current_head?.job_count, "latest valid snapshot", "/admin/acquisition/live-catalog"], ["Updated / versioned", data.summary?.updated_jobs, "existing jobs with new versions", "/admin/acquisition/jobs"], ["Quality findings", data.summary?.quality_findings_created, "report-only findings", "/admin/acquisition/data-quality"], ["Duplicate clusters", data.summary?.duplicate_clusters_created, "clusters created", "/admin/acquisition/duplicates"], ["Reprocessing runs", data.summary?.reprocessing_runs, "runs created", "/admin/acquisition/reprocessing"]].map(([label, value, detail, href]) => <MetricCard detail={detail} href={href} key={label} label={label} value={value} />)}</div><OperationCounts data={data.summary?.operations} /><Funnel data={data.funnel} /><Sources rows={data.sources || []} /><div className="grid gap-5 xl:grid-cols-2"><Quality data={data.quality} /><Enrichment data={data.enrichment} /></div><Publication data={data.publication} /><Operations rows={data.operations || []} /></> : null}</AcquisitionShell>;
}
