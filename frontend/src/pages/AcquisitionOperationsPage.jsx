import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import AcquisitionShell from "../components/acquisition/AcquisitionShell";
import StatusBadge from "../components/StatusBadge";
import { useApiResource } from "../hooks/useApiResource";
import { useSession } from "../context/SessionContext";
import { getApiErrorMessage } from "../lib/api";
import { formatDateTime, labelize } from "../lib/formatters";
import {
  buildInspectionPath,
  buildJobsPath,
  formatCount,
  getCapabilityKey,
  getResourceViewState,
  getSourceCollectionState,
  getSourceOperationalState,
  parseJobFilters,
} from "../lib/acquisitionOperations";

function toneForValue(value) {
  const normalized = String(value || "").toLowerCase();
  if (["ready", "running", "online", "published", "present"].some((item) => normalized.includes(item))) return "success";
  if (["paused", "unavailable", "missing", "warning", "failed", "error", "unresolved"].some((item) => normalized.includes(item))) return "warning";
  return "neutral";
}

function Status({ value, fallback = "Unavailable" }) {
  const label = value || fallback;
  return <StatusBadge tone={toneForValue(label)}>{labelize(label)}</StatusBadge>;
}

function RefreshButton({ refreshing, onClick }) {
  return (
    <button
      className="inline-flex items-center justify-center gap-2 rounded-xl border border-outline-variant/20 bg-surface-container-low px-3 py-2 text-sm font-semibold text-on-surface transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-60"
      disabled={refreshing}
      onClick={onClick}
      type="button"
    >
      <span className="material-symbols-outlined text-[18px]">refresh</span>
      {refreshing ? "Refreshing…" : "Refresh"}
    </button>
  );
}

function Notice({ children, tone = "neutral", role = "status" }) {
  const classes = tone === "warning"
    ? "border-[#E65100]/20 bg-[#FFF3E0] text-[#8a3b00]"
    : tone === "error"
      ? "border-error/20 bg-error-container text-on-error-container"
      : "border-primary/15 bg-primary/5 text-on-surface-variant";
  return <div className={`rounded-2xl border px-4 py-3 text-sm leading-6 ${classes}`} role={role}>{children}</div>;
}

function LoadingBlock({ label = "Loading acquisition data…" }) {
  return (
    <div aria-label={label} className="space-y-4" role="status">
      <div className="h-24 animate-pulse rounded-2xl bg-surface-container" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[1, 2, 3, 4].map((item) => <div className="h-32 animate-pulse rounded-2xl bg-surface-container" key={item} />)}
      </div>
    </div>
  );
}

function ErrorBlock({ error, onRetry }) {
  return (
    <Notice role="alert" tone="error">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <span>{error || "This acquisition data could not be loaded."}</span>
        <button className="inline-flex w-fit items-center gap-2 rounded-lg border border-current/20 px-3 py-2 text-xs font-bold" onClick={onRetry} type="button">
          <span className="material-symbols-outlined text-[16px]">refresh</span>
          Retry
        </button>
      </div>
    </Notice>
  );
}

function EmptyBlock({ title, description }) {
  return (
    <div className="rounded-2xl border border-dashed border-outline-variant/40 bg-surface-container-lowest p-10 text-center">
      <span className="material-symbols-outlined text-3xl text-on-surface-variant">inbox</span>
      <h2 className="mt-3 font-headline text-lg font-bold text-on-surface">{title}</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-on-surface-variant">{description}</p>
    </div>
  );
}

function MetricCard({ label, value, detail, tone = "neutral" }) {
  const valueClassName = tone === "success" ? "text-primary" : "text-on-surface";
  return (
    <article className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-on-surface-variant">{label}</p>
      <div className="mt-3 flex items-end justify-between gap-3">
        <strong className={`font-headline text-3xl font-extrabold tracking-tight ${valueClassName}`}>{value}</strong>
        <span className="text-right text-xs text-on-surface-variant">{detail}</span>
      </div>
    </article>
  );
}

function OverviewPage() {
  const { request } = useSession();
  const resource = useApiResource(
    () => request("/admin/acquisition/overview"),
    [request],
    { cacheKey: "acquisition:overview", staleMs: 15000 },
  );
  const state = getResourceViewState({
    data: resource.data,
    loading: resource.loading,
    error: resource.error,
    unavailable: resource.data?.unavailable === true,
  });
  const data = resource.data || {};
  const review = data.review || {};
  const imports = data.imports || {};

  return (
    <AcquisitionShell
      description="A read-only view of collection health, review activity, and the current acquisition read model."
      title="Overview"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-on-surface-variant" role="status">
          {resource.refreshing ? "Refreshing the latest read model…" : "No acquisition operation is started from this screen."}
        </p>
        <RefreshButton onClick={() => resource.refresh({ showLoading: false }).catch(() => undefined)} refreshing={resource.refreshing} />
      </div>

      {resource.error && resource.data ? <ErrorBlock error={resource.error} onRetry={() => resource.refresh({ showLoading: false }).catch(() => undefined)} /> : null}
      {state === "loading" ? <LoadingBlock label="Loading acquisition overview" /> : null}
      {state === "error" ? <ErrorBlock error={resource.error} onRetry={() => resource.refresh().catch(() => undefined)} /> : null}
      {state === "unavailable" ? <EmptyBlock description="The acquisition overview is not available from the current backend response." title="Overview unavailable" /> : null}

      {state === "ready" || state === "partial" ? (
        <>
          {imports.paused ? <Notice role="status" tone="warning">Collection is paused. This read-only screen does not change that state.</Notice> : null}
          {(data.warnings || []).length ? <Notice tone="warning">Partial data: {(data.warnings || []).join(" ")}</Notice> : null}

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard detail="backend overview" label="Import status" tone={imports.paused ? "neutral" : "success"} value={imports.status || "Unavailable"} />
            <MetricCard detail="latest plan" label="Jobs found" value={formatCount(data.jobs_found)} />
            <MetricCard detail={`${formatCount(review.approved)} approved`} label="Review queue" value={formatCount(review.needs_review)} />
            <MetricCard detail="current read model" label="Live jobs" tone="success" value={formatCount(data.current_live_jobs)} />
          </div>

          <div className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
            <section className="overflow-hidden rounded-2xl border border-outline-variant/20 bg-surface-container-lowest shadow-soft">
              <div className="border-b border-outline-variant/10 px-5 py-4">
                <h2 className="font-headline text-lg font-bold text-on-surface">Recent imports</h2>
                <p className="mt-1 text-sm text-on-surface-variant">Read-only history returned by the acquisition overview.</p>
              </div>
              {(data.history || []).length ? (
                <div className="divide-y divide-outline-variant/10">
                  {data.history.slice(0, 5).map((item) => (
                    <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4" key={item.import_id || item.created_at}>
                      <div className="min-w-0">
                        <p className="truncate font-mono text-xs text-primary">{item.import_id || "Unknown import"}</p>
                        <p className="mt-1 text-xs text-on-surface-variant">{formatDateTime(item.created_at)} · {formatCount((item.source_ids || []).length)} sources</p>
                      </div>
                      <Status value={item.status} />
                    </div>
                  ))}
                </div>
              ) : <p className="px-5 py-8 text-sm text-on-surface-variant">No import history is available.</p>}
            </section>

            <section className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
              <h2 className="font-headline text-lg font-bold text-on-surface">Read-model status</h2>
              <dl className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                <div className="rounded-xl bg-surface-container-low p-3"><dt className="text-xs text-on-surface-variant">Worker</dt><dd className="mt-1 flex items-center justify-between gap-3 font-semibold text-on-surface"><span>{data.worker?.status || "Unavailable"}</span><Status value={data.worker?.status} /></dd></div>
                <div className="rounded-xl bg-surface-container-low p-3"><dt className="text-xs text-on-surface-variant">Estimated spend</dt><dd className="mt-1 font-semibold text-on-surface">{data.estimated_spend_today?.known ? `${formatCount(data.estimated_spend_today.credits)} ${data.estimated_spend_today.currency || "credits"}` : "Unknown"}</dd></div>
                <div className="rounded-xl bg-surface-container-low p-3"><dt className="text-xs text-on-surface-variant">Last publication reference</dt><dd className="mt-1 break-all font-mono text-xs text-on-surface">{data.last_publication?.publication_id || "Unavailable"}</dd></div>
              </dl>
            </section>
          </div>
        </>
      ) : null}
    </AcquisitionShell>
  );
}

function capabilityMap(rows = []) {
  return new Map(rows.map((item) => {
    const key = `${String(item.connector || "").trim().toLowerCase()}:${String(item.target_id || "").trim().toLowerCase()}`;
    return [key, item];
  }));
}

function SourcesPage() {
  const { request } = useSession();
  const location = useLocation();
  const navigate = useNavigate();
  const sourcesResource = useApiResource(
    () => request("/admin/acquisition/sources"),
    [request],
    { cacheKey: "acquisition:sources", staleMs: 15000 },
  );
  const capabilitiesResource = useApiResource(
    () => request("/admin/acquisition/connectors/capabilities?limit=200"),
    [request],
    { cacheKey: "acquisition:connector-capabilities", staleMs: 15000 },
  );
  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const [search, setSearch] = useState(params.get("source_search") || "");
  const [statusFilter, setStatusFilter] = useState(params.get("source_status") || "");

  useEffect(() => {
    setSearch(params.get("source_search") || "");
    setStatusFilter(params.get("source_status") || "");
  }, [params]);

  function updateSourceFilters(next) {
    const nextParams = new URLSearchParams();
    if (next.search.trim()) nextParams.set("source_search", next.search.trim());
    if (next.status) nextParams.set("source_status", next.status);
    const query = nextParams.toString();
    navigate(`/admin/acquisition/sources${query ? `?${query}` : ""}`);
  }

  const rows = sourcesResource.data?.sources || [];
  const capabilities = capabilityMap(capabilitiesResource.data?.connectors || []);
  const filteredRows = rows.filter((source) => {
    const haystack = [source.name, source.company, source.connector, source.source_type].join(" ").toLowerCase();
    const matchesSearch = !search.trim() || haystack.includes(search.trim().toLowerCase());
    const operational = getSourceOperationalState(source);
    return matchesSearch && (!statusFilter || operational === statusFilter);
  });
  const state = getResourceViewState({
    data: sourcesResource.data,
    loading: sourcesResource.loading,
    error: sourcesResource.error,
    empty: sourcesResource.data && rows.length === 0,
    unavailable: sourcesResource.data?.unavailable === true,
  });

  return (
    <AcquisitionShell
      description="Inspect configured acquisition sources and the limits exposed by the current read models."
      title="Sources"
    >
      <section className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-4 shadow-soft">
        <form className="grid gap-3 md:grid-cols-[minmax(0,1fr)_13rem_auto]" onSubmit={(event) => { event.preventDefault(); updateSourceFilters({ search, status: statusFilter }); }}>
          <label className="sr-only" htmlFor="acquisition-source-search">Search sources</label>
          <input className="min-h-11 rounded-xl border border-outline-variant/20 bg-surface px-3 text-sm text-on-surface outline-none focus:border-primary focus:ring-2 focus:ring-primary/20" id="acquisition-source-search" onChange={(event) => setSearch(event.target.value)} placeholder="Search source, company or connector" value={search} />
          <label className="sr-only" htmlFor="acquisition-source-status">Filter source status</label>
          <select className="min-h-11 rounded-xl border border-outline-variant/20 bg-surface px-3 text-sm text-on-surface outline-none focus:border-primary focus:ring-2 focus:ring-primary/20" id="acquisition-source-status" onChange={(event) => setStatusFilter(event.target.value)} value={statusFilter}>
            <option value="">All source states</option>
            <option value="Ready">Ready</option>
            <option value="Paused">Paused</option>
            <option value="Unavailable">Unavailable</option>
          </select>
          <button className="min-h-11 rounded-xl bg-primary px-4 text-sm font-bold text-white transition-opacity hover:opacity-90" type="submit">Apply filters</button>
        </form>
      </section>

      {capabilitiesResource.error ? <Notice tone="warning">Source data loaded, but capability metadata is unavailable. Completeness badges remain unavailable.</Notice> : null}
      {state === "loading" ? <LoadingBlock label="Loading acquisition sources" /> : null}
      {state === "error" ? <ErrorBlock error={sourcesResource.error} onRetry={() => sourcesResource.refresh().catch(() => undefined)} /> : null}
      {state === "unavailable" ? <EmptyBlock description="The source registry is not available from the current backend response." title="Sources unavailable" /> : null}
      {state === "empty" ? <EmptyBlock description="No acquisition sources were returned by the backend." title="No sources available" /> : null}

      {state === "ready" || state === "partial" ? (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-on-surface-variant">Showing {formatCount(filteredRows.length)} of {formatCount(rows.length)} configured sources.</p>
            <div className="flex items-center gap-3">
              {capabilitiesResource.refreshing ? <span className="text-xs text-on-surface-variant" role="status">Refreshing capability metadata…</span> : null}
              <RefreshButton onClick={() => { sourcesResource.refresh({ showLoading: false }).catch(() => undefined); capabilitiesResource.refresh({ showLoading: false }).catch(() => undefined); }} refreshing={sourcesResource.refreshing || capabilitiesResource.refreshing} />
            </div>
          </div>
          {!filteredRows.length ? <EmptyBlock description="Try a different source search or state filter." title="No matching sources" /> : (
            <div className="grid gap-4 lg:grid-cols-2">
              {filteredRows.map((source) => {
                const capability = capabilities.get(getCapabilityKey(source));
                const operationalState = getSourceOperationalState(source);
                const collectionState = getSourceCollectionState(source, capability);
                return (
                  <article className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft" key={source.id || source.name}>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h2 className="truncate font-headline text-lg font-bold text-on-surface">{source.name || source.id || "Unnamed source"}</h2>
                        <p className="mt-1 text-sm text-on-surface-variant">{source.company || "Company unavailable"} · {source.connector || source.source_type || "Connector unavailable"}</p>
                      </div>
                      <div className="flex flex-wrap justify-end gap-2">
                        <Status value={operationalState} />
                        <StatusBadge tone="neutral">{collectionState}</StatusBadge>
                      </div>
                    </div>
                    <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
                      <div><dt className="text-xs text-on-surface-variant">Method</dt><dd className="mt-1 font-semibold text-on-surface">{source.method || "Unavailable"}</dd></div>
                      <div><dt className="text-xs text-on-surface-variant">Page ceiling</dt><dd className="mt-1 font-semibold text-on-surface">{source.max_pages ? formatCount(source.max_pages) : "Unavailable"}</dd></div>
                      <div><dt className="text-xs text-on-surface-variant">Last import</dt><dd className="mt-1 font-semibold text-on-surface">{formatDateTime(source.last_import)}</dd></div>
                      <div><dt className="text-xs text-on-surface-variant">Jobs found</dt><dd className="mt-1 font-semibold text-on-surface">{formatCount(source.jobs_found)}</dd></div>
                    </dl>
                    {source.reason ? <Notice tone={operationalState === "Unavailable" || operationalState === "Paused" ? "warning" : "neutral"}>{source.reason}</Notice> : null}
                    {capabilitiesResource.error ? <p className="mt-4 text-xs text-on-surface-variant">Completeness unavailable: capability metadata could not be loaded.</p> : null}
                  </article>
                );
              })}
            </div>
          )}
        </>
      ) : null}
    </AcquisitionShell>
  );
}

function FilterInput({ id, label, onChange, placeholder, value }) {
  return (
    <label className="block text-xs font-semibold text-on-surface-variant" htmlFor={id}>
      {label}
      <input className="mt-2 min-h-10 w-full rounded-xl border border-outline-variant/20 bg-surface px-3 text-sm font-normal text-on-surface outline-none focus:border-primary focus:ring-2 focus:ring-primary/20" id={id} onChange={onChange} placeholder={placeholder} value={value} />
    </label>
  );
}

function FilterSelect({ id, label, onChange, options, value }) {
  return (
    <label className="block text-xs font-semibold text-on-surface-variant" htmlFor={id}>
      {label}
      <select className="mt-2 min-h-10 w-full rounded-xl border border-outline-variant/20 bg-surface px-3 text-sm font-normal text-on-surface outline-none focus:border-primary focus:ring-2 focus:ring-primary/20" id={id} onChange={onChange} value={value}>
        {options.map(([optionValue, optionLabel]) => <option key={optionValue} value={optionValue}>{optionLabel}</option>)}
      </select>
    </label>
  );
}

function JobsPage() {
  const { request } = useSession();
  const location = useLocation();
  const navigate = useNavigate();
  const { canonicalJobId } = useParams();
  const filters = useMemo(() => parseJobFilters(location.search), [location.search]);
  const requestPath = useMemo(() => {
    const query = new URLSearchParams(location.search);
    query.set("limit", String(filters.limit));
    query.set("offset", String(filters.offset));
    return `/admin/acquisition/jobs?${query.toString()}`;
  }, [filters.limit, filters.offset, location.search]);
  const resource = useApiResource(
    () => request(requestPath),
    [requestPath],
    { cacheKey: `acquisition:jobs:${requestPath}`, staleMs: 15000 },
  );
  const [draftFilters, setDraftFilters] = useState(filters);

  useEffect(() => setDraftFilters(filters), [filters]);

  function applyFilters(event) {
    event.preventDefault();
    navigate(buildJobsPath({ ...draftFilters, offset: 0 }));
  }

  function clearFilters() {
    navigate(buildJobsPath({ limit: filters.limit, offset: 0 }));
  }

  function openInspection(id) {
    navigate(buildInspectionPath(id, location.search));
  }

  const closeInspection = useCallback(
    () => navigate(`/admin/acquisition/jobs${location.search}`),
    [location.search, navigate],
  );

  function goToPage(page) {
    navigate(buildJobsPath({ ...filters, offset: (page - 1) * filters.limit }));
  }

  const rows = resource.data?.jobs || [];
  const total = Number(resource.data?.total || 0);
  const currentPage = Math.floor(filters.offset / filters.limit) + 1;
  const pageCount = Math.max(1, Math.ceil(total / filters.limit));
  const state = getResourceViewState({
    data: resource.data,
    loading: resource.loading,
    error: resource.error,
    empty: resource.data && rows.length === 0,
    unavailable: resource.data?.unavailable === true,
  });

  return (
    <AcquisitionShell
      description="Search canonical jobs and open a read-only inspection of source, quality, review, and publication evidence."
      title="Jobs"
    >
      <section className="overflow-hidden rounded-2xl border border-outline-variant/20 bg-surface-container-lowest shadow-soft">
        <form className="grid gap-4 border-b border-outline-variant/10 p-5 md:grid-cols-2 xl:grid-cols-4" onSubmit={applyFilters}>
          <div className="md:col-span-2 xl:col-span-4"><FilterInput id="acquisition-job-search" label="Search" onChange={(event) => setDraftFilters((current) => ({ ...current, search: event.target.value }))} placeholder="Title, company, location or job ID" value={draftFilters.search} /></div>
          <FilterInput id="acquisition-job-location" label="Location" onChange={(event) => setDraftFilters((current) => ({ ...current, location: event.target.value }))} placeholder="Raw location text" value={draftFilters.location} />
          <FilterInput id="acquisition-job-function" label="Runr function" onChange={(event) => setDraftFilters((current) => ({ ...current, function: event.target.value }))} placeholder="Function" value={draftFilters.function} />
          <FilterInput id="acquisition-job-warning" label="Warning code" onChange={(event) => setDraftFilters((current) => ({ ...current, warning_type: event.target.value }))} placeholder="Warning type" value={draftFilters.warning_type} />
          <FilterSelect id="acquisition-job-completeness" label="Completeness" onChange={(event) => setDraftFilters((current) => ({ ...current, completeness_state: event.target.value }))} options={[["", "All quality states"], ["complete", "Complete"], ["incomplete", "Incomplete"], ["unknown", "Unknown"]]} value={draftFilters.completeness_state} />
          <FilterSelect id="acquisition-job-publication" label="Publication state" onChange={(event) => setDraftFilters((current) => ({ ...current, publication_state: event.target.value }))} options={[["", "All publication states"], ["published", "Published"], ["unpublished", "Unpublished"]]} value={draftFilters.publication_state} />
          <FilterSelect id="acquisition-job-limit" label="Rows per page" onChange={(event) => setDraftFilters((current) => ({ ...current, limit: Number(event.target.value), offset: 0 }))} options={[[25, "25"], [50, "50"], [100, "100"], [200, "200"]]} value={draftFilters.limit} />
          <div className="flex flex-wrap items-end gap-2 md:col-span-2 xl:col-span-4">
            <button className="min-h-10 rounded-xl bg-primary px-4 text-sm font-bold text-white transition-opacity hover:opacity-90" type="submit">Apply filters</button>
            <button className="min-h-10 rounded-xl border border-outline-variant/20 px-4 text-sm font-semibold text-on-surface transition-colors hover:bg-surface-container-high" onClick={clearFilters} type="button">Clear filters</button>
          </div>
        </form>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-outline-variant/10 px-5 py-3">
          <p className="text-sm text-on-surface-variant">{total ? `Showing ${filters.offset + 1}–${Math.min(filters.offset + rows.length, total)} of ${formatCount(total)} jobs.` : "No jobs match the current filters."}</p>
          <div className="flex items-center gap-3">
            {resource.refreshing ? <span className="text-xs text-on-surface-variant" role="status">Refreshing…</span> : null}
            <RefreshButton onClick={() => resource.refresh({ showLoading: false }).catch(() => undefined)} refreshing={resource.refreshing} />
          </div>
        </div>
      </section>

      {resource.error && resource.data ? <Notice role="alert" tone="warning">The previous job results remain visible. Refresh failed: {resource.error}</Notice> : null}
      {state === "loading" ? <LoadingBlock label="Loading acquisition jobs" /> : null}
      {state === "error" ? <ErrorBlock error={resource.error} onRetry={() => resource.refresh().catch(() => undefined)} /> : null}
      {state === "unavailable" ? <EmptyBlock description="The canonical jobs read model is not available from the current backend response." title="Jobs unavailable" /> : null}
      {state === "empty" ? <EmptyBlock description="Try clearing one or more filters to inspect the available canonical jobs." title="No matching jobs" /> : null}

      {state === "ready" || state === "partial" ? (
        <>
          <div className="overflow-hidden rounded-2xl border border-outline-variant/20 bg-surface-container-lowest shadow-soft md:block">
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full min-w-[860px] text-left text-sm">
                <thead className="bg-surface-container-low text-xs uppercase tracking-[0.12em] text-on-surface-variant"><tr><th className="px-5 py-3 font-bold">Job</th><th className="px-5 py-3 font-bold">Company</th><th className="px-5 py-3 font-bold">Location</th><th className="px-5 py-3 font-bold">Source</th><th className="px-5 py-3 font-bold">State</th><th className="px-5 py-3 font-bold">Apply</th></tr></thead>
                <tbody className="divide-y divide-outline-variant/10">
                  {rows.map((row) => <JobTableRow key={row.canonical_job_id} onOpen={openInspection} row={row} />)}
                </tbody>
              </table>
            </div>
            <div className="divide-y divide-outline-variant/10 md:hidden">
              {rows.map((row) => <JobCard key={row.canonical_job_id} onOpen={openInspection} row={row} />)}
            </div>
          </div>
          <Pagination currentPage={currentPage} goToPage={goToPage} pageCount={pageCount} total={total} />
        </>
      ) : null}

      <InspectionDrawer canonicalJobId={canonicalJobId} onClose={closeInspection} />
    </AcquisitionShell>
  );
}

function JobTableRow({ onOpen, row }) {
  return (
    <tr className="align-top transition-colors hover:bg-surface-container-low">
      <td className="max-w-[24rem] px-5 py-4"><button className="text-left font-semibold text-primary underline-offset-2 hover:underline focus:outline-none focus:ring-2 focus:ring-primary/30" onClick={() => onOpen(row.canonical_job_id)} type="button">{row.title || "Untitled job"}<span className="mt-1 block truncate font-mono text-[11px] font-normal text-on-surface-variant">{row.canonical_job_id}</span></button></td>
      <td className="px-5 py-4 text-on-surface">{row.company || "Company unavailable"}</td>
      <td className="px-5 py-4 text-on-surface-variant">{row.location || "Location unavailable"}</td>
      <td className="px-5 py-4 text-on-surface-variant">{row.source || "Unavailable"}</td>
      <td className="px-5 py-4"><Status value={row.state} /></td>
      <td className="px-5 py-4"><Status value={row.apply_status} /></td>
    </tr>
  );
}

function JobCard({ onOpen, row }) {
  return (
    <button className="block w-full p-4 text-left transition-colors hover:bg-surface-container-low focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary/30" onClick={() => onOpen(row.canonical_job_id)} type="button">
      <div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate font-semibold text-primary">{row.title || "Untitled job"}</p><p className="mt-1 truncate font-mono text-[11px] text-on-surface-variant">{row.canonical_job_id}</p></div><Status value={row.state} /></div>
      <p className="mt-3 text-sm text-on-surface">{row.company || "Company unavailable"}</p>
      <p className="mt-1 text-xs text-on-surface-variant">{row.location || "Location unavailable"} · {row.source || "Source unavailable"}</p>
      <div className="mt-3 flex flex-wrap gap-2"><Status value={row.apply_status} /></div>
    </button>
  );
}

function Pagination({ currentPage, goToPage, pageCount, total }) {
  if (!total) return null;
  return (
    <nav aria-label="Jobs pagination" className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-xs text-on-surface-variant">Page {currentPage} of {pageCount}</p>
      <div className="flex gap-2">
        <button aria-label="Previous page" className="rounded-xl border border-outline-variant/20 px-3 py-2 text-sm font-semibold text-on-surface disabled:cursor-not-allowed disabled:opacity-40" disabled={currentPage <= 1} onClick={() => goToPage(currentPage - 1)} type="button">Previous</button>
        <button aria-label="Next page" className="rounded-xl border border-outline-variant/20 px-3 py-2 text-sm font-semibold text-on-surface disabled:cursor-not-allowed disabled:opacity-40" disabled={currentPage >= pageCount} onClick={() => goToPage(currentPage + 1)} type="button">Next</button>
      </div>
    </nav>
  );
}

function collectionLength(value) {
  if (Array.isArray(value)) return value.length;
  if (value && typeof value === "object") return Object.keys(value).length;
  return 0;
}

function InspectionDrawer({ canonicalJobId, onClose }) {
  const { request } = useSession();
  const path = canonicalJobId ? `/admin/acquisition/jobs/${encodeURIComponent(canonicalJobId)}` : "";
  const resource = useApiResource(
    () => request(path),
    [path],
    { immediate: Boolean(path), cacheKey: path ? `acquisition:inspection:${path}` : "", staleMs: 15000 },
  );
  const closeRef = useRef(null);
  const returnFocusRef = useRef(null);

  useEffect(() => {
    if (!canonicalJobId) return undefined;
    returnFocusRef.current = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusFrame = window.requestAnimationFrame(() => closeRef.current?.focus());
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      returnFocusRef.current?.focus?.();
    };
  }, [canonicalJobId, onClose]);

  if (!canonicalJobId) return null;

  const data = resource.data || {};
  const job = data.job || {};
  const company = data.company || {};
  const admin = data.admin || {};
  const completeness = data.completeness || {};
  const raw = data.raw || {};
  const state = getResourceViewState({ data: resource.data, loading: resource.loading, error: resource.error });

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-end bg-[#07111f]/45" role="presentation">
      <button aria-label="Close job inspection" className="absolute inset-0 cursor-default" onClick={onClose} type="button" />
      <aside aria-labelledby="acquisition-inspection-title" aria-modal="true" className="relative max-h-[94vh] w-full overflow-y-auto rounded-t-[1.5rem] border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-2xl sm:max-w-2xl sm:rounded-l-[1.5rem] sm:rounded-t-none md:p-7" role="dialog">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0"><p className="font-mono text-xs text-primary">{job.canonical_job_id || canonicalJobId}</p><h2 className="mt-1 truncate font-headline text-2xl font-extrabold text-on-surface" id="acquisition-inspection-title">{job.title || "Job inspection"}</h2><p className="mt-1 text-sm text-on-surface-variant">{company.name || job.company || "Company unavailable"} · {job.location_raw || "Location unavailable"}</p></div>
          <button aria-label="Close" className="shrink-0 rounded-xl border border-outline-variant/20 px-3 py-2 text-sm font-semibold text-on-surface hover:bg-surface-container-high" onClick={onClose} ref={closeRef} type="button">Close</button>
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <span className="text-xs text-on-surface-variant" role="status">{resource.refreshing ? "Refreshing inspection…" : "Read-only backend record"}</span>
          <RefreshButton onClick={() => resource.refresh({ showLoading: false }).catch(() => undefined)} refreshing={resource.refreshing} />
        </div>
        {resource.error && resource.data ? <Notice role="alert" tone="warning">The previous inspection remains visible. Refresh failed: {resource.error}</Notice> : null}
        {state === "loading" ? <LoadingBlock label="Loading job inspection" /> : null}
        {state === "error" ? <ErrorBlock error={resource.error} onRetry={() => resource.refresh().catch(() => undefined)} /> : null}
        {state === "ready" || state === "partial" ? (
          <>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl bg-surface-container-low p-4"><span className="text-xs text-on-surface-variant">Apply URL</span><strong className="mt-1 block text-sm text-on-surface">{labelize(data.apply_url?.status || "unavailable")}</strong><p className="mt-1 break-all text-xs text-on-surface-variant">{data.apply_url?.user_facing_url || data.apply_url?.resolved_url || "No application URL in the inspection"}</p></div>
              <div className="rounded-xl bg-surface-container-low p-4"><span className="text-xs text-on-surface-variant">Coverage report</span><strong className="mt-1 block text-sm text-on-surface">{completeness.overall_percent ?? "—"}%</strong><p className="mt-1 text-xs text-on-surface-variant">Report-only quality; not a publication blocker.</p></div>
            </div>

            <section className="mt-5 rounded-xl border border-outline-variant/15 p-4"><h3 className="font-headline text-base font-bold text-on-surface">Record context</h3><dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-xs text-on-surface-variant">Connector</dt><dd className="mt-1 font-semibold text-on-surface">{admin.connector || "Unavailable"}</dd></div><div><dt className="text-xs text-on-surface-variant">Provider</dt><dd className="mt-1 font-semibold text-on-surface">{admin.provider || "Unavailable"}</dd></div><div><dt className="text-xs text-on-surface-variant">Source observations</dt><dd className="mt-1 font-semibold text-on-surface">{formatCount((admin.source_observation_ids || []).length)}</dd></div><div><dt className="text-xs text-on-surface-variant">Posting version</dt><dd className="mt-1 font-semibold text-on-surface">{admin.posting_version_id || job.posting_version || "Unavailable"}</dd></div><div><dt className="text-xs text-on-surface-variant">Review state</dt><dd className="mt-1"><Status value={admin.review_state} /></dd></div><div><dt className="text-xs text-on-surface-variant">Publication state</dt><dd className="mt-1"><Status value={admin.publication_status} /></dd></div></dl></section>

            <section className="mt-5 rounded-xl border border-outline-variant/15 p-4"><h3 className="font-headline text-base font-bold text-on-surface">Evidence retained</h3><div className="mt-3 grid gap-3 sm:grid-cols-3"><div className="rounded-lg bg-surface-container-low p-3"><span className="block text-xs text-on-surface-variant">Observations</span><strong className="mt-1 block text-lg text-on-surface">{formatCount(collectionLength(raw.source_observations))}</strong></div><div className="rounded-lg bg-surface-container-low p-3"><span className="block text-xs text-on-surface-variant">Versions</span><strong className="mt-1 block text-lg text-on-surface">{formatCount(collectionLength(raw.posting_versions))}</strong></div><div className="rounded-lg bg-surface-container-low p-3"><span className="block text-xs text-on-surface-variant">Provenance fields</span><strong className="mt-1 block text-lg text-on-surface">{formatCount(collectionLength(raw.field_provenance_summary))}</strong></div></div></section>

            {(completeness.critical_checks || []).length ? <section className="mt-5 rounded-xl border border-outline-variant/15 p-4"><div className="flex items-center justify-between gap-3"><h3 className="font-headline text-base font-bold text-on-surface">Quality checks</h3><StatusBadge tone="neutral">Report-only</StatusBadge></div><div className="mt-3 space-y-2">{completeness.critical_checks.slice(0, 8).map((check) => <div className="flex items-start justify-between gap-3 rounded-lg bg-surface-container-low p-3 text-sm" key={check.name}><span className="text-on-surface">{check.name}</span><span className="text-right text-xs text-on-surface-variant">{check.detail || labelize(check.status)}</span></div>)}</div></section> : null}
          </>
        ) : null}
      </aside>
    </div>
  );
}

export default function AcquisitionOperationsPage() {
  const { canonicalJobId } = useParams();
  const location = useLocation();
  if (location.pathname === "/admin/acquisition/sources") return <SourcesPage />;
  if (location.pathname === "/admin/acquisition/jobs" || canonicalJobId) return <JobsPage />;
  return <OverviewPage />;
}
