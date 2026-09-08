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
          onClick={() => refresh().catch(() => undefined)}
          type="button"
        >
          Refresh
        </button>
      </header>

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
