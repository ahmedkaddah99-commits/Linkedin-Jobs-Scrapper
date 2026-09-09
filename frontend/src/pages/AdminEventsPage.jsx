import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { formatDateTime } from "../lib/formatters";

const PAGE_SIZE = 50;

function parsePageParam(value) {
  const parsed = Number.parseInt(String(value || "1"), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function formatUtcDayBoundary(value, dayOffset = 0) {
  const parts = String(value || "").split("-").map((item) => Number.parseInt(item, 10));
  if (parts.length !== 3 || parts.some((part) => Number.isNaN(part))) {
    return "";
  }
  const [year, month, day] = parts;
  return new Date(Date.UTC(year, month - 1, day + dayOffset, 0, 0, 0))
    .toISOString()
    .replace(".000Z", "+00:00");
}

function payloadSummary(payload) {
  if (Array.isArray(payload)) {
    return `View JSON (${payload.length} items)`;
  }
  if (payload && typeof payload === "object") {
    return `View JSON (${Object.keys(payload).length} keys)`;
  }
  return "View JSON";
}

function formatPayload(payload) {
  try {
    return JSON.stringify(payload ?? {}, null, 2);
  } catch {
    return String(payload ?? "");
  }
}

function metric(value, suffix = "") {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${numeric}${suffix}` : "Unknown";
}

function ProductAnalyticsPanel({ data, loading, error }) {
  if (loading) {
    return <section className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">Loading product analytics...</section>;
  }
  if (error) {
    return <section className="rounded-[1.75rem] border border-error/30 bg-error-container p-6 text-sm text-on-error-container">Product analytics unavailable: {error}</section>;
  }
  if (!data) {
    return <section className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-6 text-sm text-on-surface-variant">No product analytics projection is available yet.</section>;
  }

  const stages = Array.isArray(data.funnel?.stages) ? data.funnel.stages : [];
  const cohorts = Array.isArray(data.retention?.cohorts) ? data.retention.cohorts : [];
  const featureUsage = Array.isArray(data.feature_usage) ? data.feature_usage : [];
  const latencyBands = Array.isArray(data.latency_bands) ? data.latency_bands : [];
  const failures = Array.isArray(data.failure_categories) ? data.failure_categories : [];
  const environments = Array.isArray(data.by_environment) ? data.by_environment : [];

  return (
    <section className="space-y-5 rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft" aria-label="Product analytics">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.22em] text-primary">RC-030 product analytics</p>
          <h2 className="mt-2 font-headline text-2xl font-bold text-on-surface">Customer outcomes</h2>
          <p className="mt-1 text-sm leading-6 text-on-surface-variant">
            {data.environment} traffic · {data.window?.days || 90}-day window · signup denominator {metric(data.funnel?.denominator?.unique_users)}
          </p>
        </div>
        <p className="text-xs text-on-surface-variant">Unparseable events: {metric(data.exclusions?.unparseable_events)} · Excluded: {metric(data.exclusions?.excluded_events)}</p>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <article className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4">
          <h3 className="font-semibold text-on-surface">Funnel</h3>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[34rem] text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-on-surface-variant"><tr><th className="py-2 pr-3">Stage</th><th className="py-2 pr-3">Users</th><th className="py-2 pr-3">Conversion</th><th className="py-2">Evidence</th></tr></thead>
              <tbody className="divide-y divide-outline-variant/10">
                {stages.map((stage) => <tr key={stage.stage}><td className="py-2 pr-3 font-medium text-on-surface">{stage.stage}</td><td className="py-2 pr-3 text-on-surface-variant">{metric(stage.unique_users)}</td><td className="py-2 pr-3 text-on-surface-variant">{metric(stage.conversion_pct, "%")}</td><td className="py-2 text-on-surface-variant">{stage.backend_confirmed ? "Backend confirmed" : "Interaction"}</td></tr>)}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs leading-5 text-on-surface-variant">Saved means the save API completed. Prepared and confirmed outcomes require backend events; opening an employer page and marking a job applied are not confirmed submission.</p>
        </article>

        <article className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4">
          <h3 className="font-semibold text-on-surface">Return retention by signup week</h3>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[30rem] text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-on-surface-variant"><tr><th className="py-2 pr-3">Cohort</th><th className="py-2 pr-3">Signups</th><th className="py-2 pr-3">D7</th><th className="py-2">D30</th></tr></thead>
              <tbody className="divide-y divide-outline-variant/10">
                {cohorts.length ? cohorts.map((cohort) => <tr key={cohort.cohort_week}><td className="py-2 pr-3 font-medium text-on-surface">{cohort.cohort_week}</td><td className="py-2 pr-3 text-on-surface-variant">{metric(cohort.signups)}</td><td className="py-2 pr-3 text-on-surface-variant">{metric(cohort.returned_d7)} / {metric(cohort.eligible_d7)} ({metric(cohort.return_d7_pct, "%")})</td><td className="py-2 text-on-surface-variant">{metric(cohort.returned_d30)} / {metric(cohort.eligible_d30)} ({metric(cohort.return_d30_pct, "%")})</td></tr>) : <tr><td className="py-3 text-on-surface-variant" colSpan={4}>No mature signup cohorts yet.</td></tr>}
              </tbody>
            </table>
          </div>
        </article>

        <article className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4">
          <h3 className="font-semibold text-on-surface">Feature usage and return signals</h3>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[34rem] text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-on-surface-variant"><tr><th className="py-2 pr-3">Feature event</th><th className="py-2 pr-3">Users</th><th className="py-2 pr-3">Events</th><th className="py-2">Jobs / runs</th></tr></thead>
              <tbody className="divide-y divide-outline-variant/10">
                {featureUsage.length ? featureUsage.map((feature) => <tr key={feature.event_name}><td className="py-2 pr-3 font-medium text-on-surface">{feature.event_name}</td><td className="py-2 pr-3 text-on-surface-variant">{metric(feature.unique_users)}</td><td className="py-2 pr-3 text-on-surface-variant">{metric(feature.events)}</td><td className="py-2 text-on-surface-variant">{metric(feature.distinct_jobs)} / {metric(feature.distinct_runs)}</td></tr>) : <tr><td className="py-3 text-on-surface-variant" colSpan={4}>No value events yet.</td></tr>}
              </tbody>
            </table>
          </div>
        </article>

        <article className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4">
          <h3 className="font-semibold text-on-surface">Latency and failure context</h3>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <div><h4 className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Latency bands</h4><ul className="mt-2 space-y-1 text-sm text-on-surface-variant">{latencyBands.length ? latencyBands.map((band) => <li key={band.band}>{band.band}: {metric(band.events)} events · {metric(band.confirmed_outcome_users_after)} later confirmed</li>) : <li>No latency observations.</li>}</ul></div>
            <div><h4 className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Failure categories</h4><ul className="mt-2 space-y-1 text-sm text-on-surface-variant">{failures.length ? failures.map((failure) => <li key={failure.category}>{failure.category}: {metric(failure.events)} events · {metric(failure.later_value_users)} later value users</li>) : <li>No failure observations.</li>}</ul></div>
          </div>
          <p className="mt-3 text-xs leading-5 text-on-surface-variant">These are associations, not causal claims. User report reason codes are the feedback path for relevance reasons analytics cannot infer.</p>
        </article>
      </div>

      <div className="flex flex-wrap gap-2 text-xs text-on-surface-variant">{environments.map((item) => <span className="rounded-full border border-outline-variant/20 bg-surface px-3 py-1.5" key={item.environment}>{item.environment}: {metric(item.unique_users)} users · {metric(item.events)} events</span>)}</div>
    </section>
  );
}

export default function AdminEventsPage() {
  const { request } = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const currentPage = parsePageParam(searchParams.get("page"));
  const appliedFilters = useMemo(
    () => ({
      eventName: searchParams.get("event_name") || "",
      userId: searchParams.get("user_id") || "",
      occurredFrom: searchParams.get("occurred_from") || "",
      occurredTo: searchParams.get("occurred_to") || "",
    }),
    [searchParams],
  );
  const [draftFilters, setDraftFilters] = useState(appliedFilters);
  const [filterError, setFilterError] = useState("");

  useEffect(() => {
    setDraftFilters(appliedFilters);
  }, [appliedFilters]);

  const requestPath = useMemo(() => {
    const params = new URLSearchParams();
    params.set("limit", String(PAGE_SIZE));
    params.set("offset", String((currentPage - 1) * PAGE_SIZE));
    if (appliedFilters.eventName) {
      params.set("event_name", appliedFilters.eventName);
    }
    if (appliedFilters.userId) {
      params.set("user_id", appliedFilters.userId);
    }
    const occurredFrom = formatUtcDayBoundary(appliedFilters.occurredFrom, 0);
    const occurredTo = formatUtcDayBoundary(appliedFilters.occurredTo, 1);
    if (occurredFrom) {
      params.set("occurred_from", occurredFrom);
    }
    if (occurredTo) {
      params.set("occurred_to", occurredTo);
    }
    return `/admin/events?${params.toString()}`;
  }, [appliedFilters, currentPage]);

  const { data, loading, error, refresh } = useApiResource(() => request(requestPath), [request, requestPath]);
  const { data: overviewData, loading: overviewLoading, error: overviewError, refresh: refreshOverview } = useApiResource(
    () => request("/analytics/overview"),
    [request],
  );
  const events = data?.events || [];
  const meta = data?.meta || { limit: PAGE_SIZE, offset: (currentPage - 1) * PAGE_SIZE, returned: events.length, total: 0 };
  const total = Number(meta.total || 0);
  const offset = Number(meta.offset || 0);
  const returned = Number(meta.returned || events.length);
  const hasPreviousPage = currentPage > 1;
  const hasNextPage = offset + returned < total;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function updateDraftFilter(key, value) {
    setDraftFilters((currentValue) => ({ ...currentValue, [key]: value }));
  }

  function applyFilters(event) {
    event.preventDefault();
    if (draftFilters.occurredFrom && draftFilters.occurredTo && draftFilters.occurredFrom > draftFilters.occurredTo) {
      setFilterError("The start date must be earlier than or equal to the end date.");
      return;
    }
    setFilterError("");
    const next = new URLSearchParams();
    if (draftFilters.eventName) {
      next.set("event_name", draftFilters.eventName);
    }
    if (draftFilters.userId) {
      next.set("user_id", draftFilters.userId);
    }
    if (draftFilters.occurredFrom) {
      next.set("occurred_from", draftFilters.occurredFrom);
    }
    if (draftFilters.occurredTo) {
      next.set("occurred_to", draftFilters.occurredTo);
    }
    setSearchParams(next);
  }

  function clearFilters() {
    setFilterError("");
    setDraftFilters({
      eventName: "",
      userId: "",
      occurredFrom: "",
      occurredTo: "",
    });
    setSearchParams(new URLSearchParams());
  }

  function goToPage(pageNumber) {
    const next = new URLSearchParams(searchParams);
    if (pageNumber <= 1) {
      next.delete("page");
    } else {
      next.set("page", String(pageNumber));
    }
    setSearchParams(next);
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div className="space-y-2">
          <Link className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:text-primary-container" to="/admin">
            <span className="material-symbols-outlined text-[18px]">arrow_back</span>
            Operations overview
          </Link>
          <div>
            <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
              General events
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-7 text-on-surface-variant">
              General admin events — acquisition scope may be incomplete. Results are ordered newest first and include the raw payload for each event.
            </p>
          </div>
        </div>
        <button
          className="rounded-2xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
          onClick={() => Promise.allSettled([refresh(), refreshOverview()])}
          type="button"
        >
          Refresh
        </button>
      </header>

      <ProductAnalyticsPanel data={overviewData?.product_analytics} error={overviewError} loading={overviewLoading} />

      <section className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
        <form className="grid gap-4 md:grid-cols-[1.4fr_1.1fr_0.9fr_0.9fr_auto]" onSubmit={applyFilters}>
          <input
            className="rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateDraftFilter("eventName", event.target.value)}
            placeholder="Filter by event name"
            type="text"
            value={draftFilters.eventName}
          />
          <input
            className="rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateDraftFilter("userId", event.target.value)}
            placeholder="Filter by user id"
            type="text"
            value={draftFilters.userId}
          />
          <input
            className="rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateDraftFilter("occurredFrom", event.target.value)}
            type="date"
            value={draftFilters.occurredFrom}
          />
          <input
            className="rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateDraftFilter("occurredTo", event.target.value)}
            type="date"
            value={draftFilters.occurredTo}
          />
          <div className="flex gap-3">
            <button
              className="rounded-2xl bg-gradient-to-br from-primary to-primary-container px-4 py-3 text-sm font-semibold text-white shadow-sm"
              type="submit"
            >
              Apply
            </button>
            <button
              className="rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-low"
              onClick={clearFilters}
              type="button"
            >
              Clear
            </button>
          </div>
        </form>
        {filterError ? <p className="mt-3 text-sm text-error">{filterError}</p> : null}
      </section>

      <section className="overflow-hidden rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest shadow-soft">
        <div className="flex flex-col gap-3 border-b border-outline-variant/10 px-6 py-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="font-headline text-xl font-bold text-on-surface">Event Log</h2>
            <p className="mt-1 text-sm text-on-surface-variant">
              {total
                ? `Showing ${offset + 1}-${Math.min(offset + returned, total)} of ${total} events.`
                : "No events match the current filters."}
            </p>
          </div>
          <div className="text-sm text-on-surface-variant">
            Page {currentPage} of {pageCount}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[68rem] text-left text-sm">
            <thead className="bg-surface-container-low text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
              <tr>
                <th className="px-6 py-4">Event Name</th>
                <th className="px-6 py-4">Occurred At</th>
                <th className="px-6 py-4">User ID</th>
                <th className="px-6 py-4">Payload</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <tr>
                  <td className="px-6 py-10 text-on-surface-variant" colSpan={4}>
                    Loading analytics events...
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td className="px-6 py-10 text-error" colSpan={4}>
                    {error}
                  </td>
                </tr>
              ) : events.length ? (
                events.map((event) => (
                  <tr className="align-top hover:bg-surface-container-low" key={event.event_id || `${event.event_name}-${event.occurred_at}`}>
                    <td className="px-6 py-4 font-medium text-on-surface">{event.event_name || "Unknown event"}</td>
                    <td className="px-6 py-4 text-on-surface-variant">{formatDateTime(event.occurred_at)}</td>
                    <td className="px-6 py-4 font-mono text-xs text-on-surface-variant">
                      {event.user_id || "N/A"}
                    </td>
                    <td className="px-6 py-4">
                      <details className="group max-w-[34rem]">
                        <summary className="cursor-pointer list-none rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm font-medium text-primary transition-colors hover:bg-surface-container-low">
                          <span className="inline-flex items-center gap-2">
                            <span className="material-symbols-outlined text-[18px]">data_object</span>
                            {payloadSummary(event.payload)}
                          </span>
                        </summary>
                        <pre className="mt-3 overflow-x-auto rounded-2xl bg-[#08111d] p-4 text-xs leading-6 text-slate-100">
                          {formatPayload(event.payload)}
                        </pre>
                      </details>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-6 py-10 text-on-surface-variant" colSpan={4}>
                    No analytics events found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex flex-col gap-3 border-t border-outline-variant/10 px-6 py-4 md:flex-row md:items-center md:justify-between">
          <div className="text-sm text-on-surface-variant">
            {total ? `Newest events are shown first. ${PAGE_SIZE} events per page.` : "Apply filters or refresh to inspect captured events."}
          </div>
          <div className="flex gap-3">
            <button
              className="rounded-2xl border border-outline-variant/20 bg-surface px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-low disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!hasPreviousPage}
              onClick={() => goToPage(currentPage - 1)}
              type="button"
            >
              Previous
            </button>
            <button
              className="rounded-2xl border border-outline-variant/20 bg-surface px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-low disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!hasNextPage}
              onClick={() => goToPage(currentPage + 1)}
              type="button"
            >
              Next
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
