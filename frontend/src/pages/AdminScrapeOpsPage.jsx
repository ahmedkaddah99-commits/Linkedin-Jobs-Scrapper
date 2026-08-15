import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { formatDateTime, labelize } from "../lib/formatters";

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

function formatNumber(value) {
  const normalized = Number(value || 0);
  if (!Number.isFinite(normalized)) {
    return "0";
  }
  return new Intl.NumberFormat().format(normalized);
}

function formatSignedNumber(value) {
  const normalized = Number(value || 0);
  if (!Number.isFinite(normalized)) {
    return "0";
  }
  const prefix = normalized > 0 ? "+" : "";
  return `${prefix}${formatNumber(normalized)}`;
}

function scrapeOpsTone(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "healthy") return "success";
  if (normalized === "out_of_credits") return "warning";
  if (normalized === "unavailable" || normalized === "missing_api_key") return "warning";
  return "primary";
}

function discrepancyTone(value) {
  const normalized = Number(value || 0);
  if (!Number.isFinite(normalized) || normalized === 0) {
    return "success";
  }
  return "warning";
}

function MetricCard({ label, value, hint = "", tone = "primary", badge = "" }) {
  return (
    <article className="rounded-[1.5rem] border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-on-surface-variant">{label}</p>
          <p className="mt-3 font-headline text-3xl font-extrabold tracking-tight text-on-surface">{value}</p>
        </div>
        {badge ? <StatusBadge tone={tone}>{badge}</StatusBadge> : null}
      </div>
      {hint ? <p className="mt-3 text-sm leading-6 text-on-surface-variant">{hint}</p> : null}
    </article>
  );
}

function BreakdownTable({ emptyLabel, rows, title, valueKey = "runner_credits" }) {
  return (
    <section className="overflow-hidden rounded-[1.5rem] border border-outline-variant/20 bg-surface-container-lowest shadow-soft">
      <div className="border-b border-outline-variant/10 px-5 py-4">
        <h2 className="font-headline text-lg font-bold text-on-surface">{title}</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[28rem] text-left text-sm">
          <thead className="bg-surface-container-low text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
            <tr>
              {rows.length
                ? Object.keys(rows[0]).map((column) => (
                  <th className="px-5 py-4" key={column}>
                    {labelize(column)}
                  </th>
                ))
                : (
                  <th className="px-5 py-4">Summary</th>
                )}
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/10">
            {rows.length ? (
              rows.map((row, index) => (
                <tr className="hover:bg-surface-container-low" key={`${title}-${index}`}>
                  {Object.entries(row).map(([column, value]) => (
                    <td className="px-5 py-4 text-on-surface-variant" key={column}>
                      {column === valueKey || column === "native_credits" || column === "requests" || column === "billed_requests"
                        ? formatNumber(value)
                        : String(value || "N/A")}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-5 py-8 text-on-surface-variant">{emptyLabel}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function UsageTrendChart({ rows }) {
  const chartRows = Array.isArray(rows) ? rows : [];
  return (
    <section className="rounded-[1.5rem] border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="font-headline text-lg font-bold text-on-surface">Usage Trend</h2>
          <p className="mt-1 text-sm text-on-surface-variant">Daily runner credits, native credits, and requests.</p>
        </div>
        <StatusBadge tone="primary">{chartRows.length} Days</StatusBadge>
      </div>
      {chartRows.length ? (
        <div className="h-72">
          <ResponsiveContainer height="100%" width="100%">
            <AreaChart data={chartRows} margin={{ bottom: 0, left: 0, right: 12, top: 12 }}>
              <defs>
                <linearGradient id="runnerCreditsGradient" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="5%" stopColor="#0f766e" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#0f766e" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="nativeCreditsGradient" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="5%" stopColor="#2563eb" stopOpacity={0.24} />
                  <stop offset="95%" stopColor="#2563eb" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#d8dee8" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="day" tick={{ fill: "#64748b", fontSize: 12 }} tickLine={false} />
              <YAxis tick={{ fill: "#64748b", fontSize: 12 }} tickLine={false} width={48} />
              <Tooltip formatter={(value) => formatNumber(value)} />
              <Area
                dataKey="runner_credits"
                fill="url(#runnerCreditsGradient)"
                name="Runner credits"
                stroke="#0f766e"
                strokeWidth={2}
                type="monotone"
              />
              <Area
                dataKey="native_credits"
                fill="url(#nativeCreditsGradient)"
                name="Native credits"
                stroke="#2563eb"
                strokeWidth={2}
                type="monotone"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="rounded-2xl bg-surface-container-low p-6 text-sm text-on-surface-variant">
          No usage events are available for the current filters.
        </div>
      )}
    </section>
  );
}

function extractDomainStatsRows(domainStats) {
  if (!domainStats || typeof domainStats !== "object") {
    return [];
  }
  if (Array.isArray(domainStats)) {
    return domainStats.filter((item) => item && typeof item === "object");
  }
  for (const key of ["results", "domains", "stats", "data"]) {
    if (Array.isArray(domainStats[key])) {
      return domainStats[key].filter((item) => item && typeof item === "object");
    }
  }
  return [];
}

export default function AdminScrapeOpsPage() {
  const { request } = useSession();
  const [telemetryRequested, setTelemetryRequested] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const appliedFilters = useMemo(
    () => ({
      userId: searchParams.get("user_id") || "",
      workspaceId: searchParams.get("workspace_id") || "",
      runId: searchParams.get("run_id") || "",
      occurredFrom: searchParams.get("occurred_from") || "",
      occurredTo: searchParams.get("occurred_to") || "",
      reconciliationDate: searchParams.get("date") || "",
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
    if (appliedFilters.userId) {
      params.set("user_id", appliedFilters.userId);
    }
    if (appliedFilters.workspaceId) {
      params.set("workspace_id", appliedFilters.workspaceId);
    }
    if (appliedFilters.runId) {
      params.set("run_id", appliedFilters.runId);
    }
    const occurredFrom = formatUtcDayBoundary(appliedFilters.occurredFrom, 0);
    const occurredTo = formatUtcDayBoundary(appliedFilters.occurredTo, 1);
    if (occurredFrom) {
      params.set("occurred_from", occurredFrom);
    }
    if (occurredTo) {
      params.set("occurred_to", occurredTo);
    }
    if (appliedFilters.reconciliationDate) {
      params.set("date", appliedFilters.reconciliationDate);
    }
    const query = params.toString();
    if (!telemetryRequested) return "/admin/scrapeops/policy";
    return query ? `/admin/scrapeops/usage?${query}` : "/admin/scrapeops/usage";
  }, [appliedFilters, telemetryRequested]);

  const { data, loading, error, refresh } = useApiResource(() => request(requestPath), [request, requestPath]);
  const usage = data?.usage || {};
  const reconciliation = data?.reconciliation || {};
  const policy = telemetryRequested ? data?.policy || {} : data || {};
  const usageSeries = data?.usage_series || [];
  const reconciliationSeries = data?.reconciliation_series || [];
  const alerts = data?.alerts || {};
  const totals = usage.totals || {};
  const accountState = reconciliation.account_state || {};
  const accountUsage = accountState.usage || {};
  const domainStatsRows = extractDomainStatsRows(reconciliation.domain_stats);
  const [policyDraft, setPolicyDraft] = useState("");
  const [policyDirty, setPolicyDirty] = useState(false);
  const [policyStatus, setPolicyStatus] = useState("");
  const [policyError, setPolicyError] = useState("");
  const [reconciliationStatus, setReconciliationStatus] = useState("");

  useEffect(() => {
    if (policyDirty || !policy || !Object.keys(policy).length) {
      return;
    }
    setPolicyDraft(JSON.stringify(policy, null, 2));
  }, [policy, policyDirty]);

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
    if (draftFilters.userId) next.set("user_id", draftFilters.userId);
    if (draftFilters.workspaceId) next.set("workspace_id", draftFilters.workspaceId);
    if (draftFilters.runId) next.set("run_id", draftFilters.runId);
    if (draftFilters.occurredFrom) next.set("occurred_from", draftFilters.occurredFrom);
    if (draftFilters.occurredTo) next.set("occurred_to", draftFilters.occurredTo);
    if (draftFilters.reconciliationDate) next.set("date", draftFilters.reconciliationDate);
    setSearchParams(next);
  }

  function clearFilters() {
    setFilterError("");
    setDraftFilters({
      userId: "",
      workspaceId: "",
      runId: "",
      occurredFrom: "",
      occurredTo: "",
      reconciliationDate: "",
    });
    setSearchParams(new URLSearchParams());
  }

  async function savePolicy() {
    setPolicyError("");
    setPolicyStatus("");
    let parsedPolicy = {};
    try {
      parsedPolicy = JSON.parse(policyDraft || "{}");
    } catch {
      setPolicyStatus("");
      setPolicyError("Policy JSON is not valid.");
      return;
    }
    if (!window.confirm("Save this provider policy? This changes server-enforced limits and alert behavior, but does not activate a provider.")) return;
    setPolicyStatus("Saving policy...");
    try {
      const savedPolicy = await request("/admin/scrapeops/policy", {
        method: "PUT",
        body: parsedPolicy,
      });
      setPolicyDraft(JSON.stringify(savedPolicy, null, 2));
      setPolicyDirty(false);
      setPolicyStatus("Policy saved.");
      await refresh();
    } catch (saveError) {
      setPolicyStatus("");
      setPolicyError(saveError?.message || "Unable to save policy.");
    }
  }

  async function runReconciliationNow() {
    if (!window.confirm("Run provider reconciliation now? This may contact the configured ScrapeOps account and records an immutable reconciliation event.")) return;
    setReconciliationStatus("Running reconciliation...");
    try {
      const result = await request("/admin/scrapeops/reconciliation/run", {
        method: "POST",
        body: {},
      });
      setReconciliationStatus(
        result?.alerts?.length
          ? `Reconciliation recorded with ${formatNumber(result.alerts.length)} alert(s).`
          : "Reconciliation recorded.",
      );
      await refresh();
    } catch (reconciliationError) {
      setReconciliationStatus(reconciliationError?.message || "Unable to run reconciliation.");
    }
  }

  const summaryCards = [
    {
      label: "Account Status",
      value: labelize(accountState.status || "unknown"),
      hint: String(accountState.summary || "ScrapeOps account state is not available."),
      tone: scrapeOpsTone(accountState.status),
      badge: accountState.status ? labelize(accountState.status) : "Unknown",
    },
    {
      label: "Runner Credits",
      value: formatNumber(totals.runner_credits),
      hint: "Internal product-facing credits attributed from ScrapeOps-backed requests.",
    },
    {
      label: "Native Credits",
      value: formatNumber(totals.native_credits),
      hint: "Estimated native ScrapeOps credits from the internal usage ledger.",
    },
    {
      label: "Billed Requests",
      value: formatNumber(totals.billed_requests),
      hint: `${formatNumber(totals.failed_requests)} failed or unbilled requests in the current view.`,
    },
    {
      label: "Remote Credits Remaining",
      value: formatNumber(accountUsage.remaining),
      hint: `Remote account usage: ${formatNumber(accountUsage.used)} used of ${formatNumber(accountUsage.limit)}.`,
    },
    {
      label: "Reconciliation Delta",
      value: formatSignedNumber(reconciliation.discrepancy),
      hint: "Remote used credits minus internal native-credit totals.",
      tone: discrepancyTone(reconciliation.discrepancy),
      badge: Number(reconciliation.discrepancy || 0) === 0 ? "Aligned" : "Review",
    },
  ];

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="space-y-2">
          <Link className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:text-primary-container" to="/admin">
            <span className="material-symbols-outlined text-[18px]">arrow_back</span>
            Operations overview
          </Link>
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
                Provider policy
              </h1>
              <StatusBadge tone="primary">Admin Only</StatusBadge>
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-7 text-on-surface-variant">
              Provider-neutral policy, request usage, runner-credit burn, account health, and reconciliation evidence. Viewing this page never activates a provider.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            className="inline-flex items-center gap-2 rounded-2xl border border-primary/20 bg-primary/10 px-4 py-3 text-sm font-medium text-primary transition-colors hover:bg-primary/15"
            onClick={() => {
              if (telemetryRequested || window.confirm("Load live provider telemetry? This may contact the configured ScrapeOps account but does not change provider policy.")) setTelemetryRequested(true);
            }}
            type="button"
          >
            <span className="material-symbols-outlined text-[18px]">network_check</span>
            {telemetryRequested ? "Provider telemetry loaded" : "Load provider telemetry"}
          </button>
          <button
            className="inline-flex items-center gap-2 rounded-2xl border border-primary/20 bg-primary/10 px-4 py-3 text-sm font-medium text-primary transition-colors hover:bg-primary/15"
            onClick={runReconciliationNow}
            type="button"
          >
            <span className="material-symbols-outlined text-[18px]">sync</span>
            Reconcile
          </button>
          <Link
            className="inline-flex items-center gap-2 rounded-2xl border border-primary/20 bg-primary/10 px-4 py-3 text-sm font-medium text-primary transition-colors hover:bg-primary/15"
            to="/admin/events"
          >
            <span className="material-symbols-outlined text-[18px]">timeline</span>
            Event Explorer
          </Link>
          <button
            className="rounded-2xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            onClick={() => refresh().catch(() => undefined)}
            type="button"
          >
            Refresh
          </button>
        </div>
      </header>
      {!telemetryRequested ? (
        <section className="rounded-[1.25rem] border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-900" role="status">
          Stored provider policy is shown without contacting ScrapeOps. Live account usage and domain telemetry remain unloaded until an administrator explicitly requests them.
        </section>
      ) : null}
      {reconciliationStatus ? (
        <section className="rounded-[1.25rem] border border-primary/15 bg-primary/10 px-5 py-3 text-sm text-primary">
          {reconciliationStatus}
        </section>
      ) : null}

      <section className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
        <form className="grid gap-4 md:grid-cols-2 xl:grid-cols-[1.2fr_1.2fr_1.2fr_0.9fr_0.9fr_0.9fr_auto]" onSubmit={applyFilters}>
          <input
            className="rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateDraftFilter("userId", event.target.value)}
            placeholder="Filter by user id"
            type="text"
            value={draftFilters.userId}
          />
          <input
            className="rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateDraftFilter("workspaceId", event.target.value)}
            placeholder="Filter by workspace id"
            type="text"
            value={draftFilters.workspaceId}
          />
          <input
            className="rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateDraftFilter("runId", event.target.value)}
            placeholder="Filter by run id"
            type="text"
            value={draftFilters.runId}
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
          <input
            className="rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateDraftFilter("reconciliationDate", event.target.value)}
            title="Optional ScrapeOps domain-stats day"
            type="date"
            value={draftFilters.reconciliationDate}
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

      {loading ? (
        <section className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-8 text-sm text-on-surface-variant shadow-soft">
          Loading ScrapeOps dashboard...
        </section>
      ) : error ? (
        <section className="rounded-[1.75rem] border border-error/30 bg-error-container px-6 py-5 text-sm text-on-error-container shadow-soft">
          {error}
        </section>
      ) : (
        <>
          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {summaryCards.map((card) => (
              <MetricCard
                badge={card.badge}
                hint={card.hint}
                key={card.label}
                label={card.label}
                tone={card.tone}
                value={card.value}
              />
            ))}
          </section>

          <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
            <UsageTrendChart rows={usageSeries} />
            <section className="rounded-[1.5rem] border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <h2 className="font-headline text-lg font-bold text-on-surface">Alerts</h2>
                  <p className="mt-1 text-sm text-on-surface-variant">Latest automated ScrapeOps reconciliation alerts.</p>
                </div>
                <StatusBadge tone={(alerts.latest || []).length ? "warning" : "success"}>
                  {formatNumber((alerts.latest || []).length)}
                </StatusBadge>
              </div>
              {(alerts.latest || []).length ? (
                <div className="space-y-3">
                  {(alerts.latest || []).slice(0, 6).map((alert, index) => (
                    <article className="rounded-2xl bg-surface-container-low p-4" key={`${alert.occurred_at}-${index}`}>
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-on-surface">{labelize(alert.alert_type || "alert")}</p>
                        <StatusBadge tone={alert.severity === "critical" ? "warning" : "primary"}>
                          {labelize(alert.severity || "warning")}
                        </StatusBadge>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-on-surface-variant">{alert.message || "No alert message."}</p>
                      <p className="mt-2 text-xs text-on-surface-variant">{formatDateTime(alert.occurred_at)}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="rounded-2xl bg-surface-container-low p-6 text-sm text-on-surface-variant">
                  No ScrapeOps alerts are recorded in the current history window.
                </div>
              )}
            </section>
          </section>

          <section className="rounded-[1.5rem] border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
            <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <h2 className="font-headline text-lg font-bold text-on-surface">Policy Editor</h2>
                <p className="mt-1 text-sm text-on-surface-variant">
                  Admin-only plan limits, per-user overrides, domain policies, and reconciliation alert settings.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  className="rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-low"
                  onClick={() => {
                    setPolicyDraft(JSON.stringify(policy || {}, null, 2));
                    setPolicyDirty(false);
                    setPolicyError("");
                    setPolicyStatus("");
                  }}
                  type="button"
                >
                  Reset
                </button>
                <button
                  className="rounded-2xl bg-gradient-to-br from-primary to-primary-container px-4 py-3 text-sm font-semibold text-white shadow-sm"
                  onClick={savePolicy}
                  type="button"
                >
                  Save Policy
                </button>
              </div>
            </div>
            <textarea
              className="min-h-[24rem] w-full rounded-2xl border border-outline-variant/20 bg-surface p-4 font-mono text-xs leading-6 text-on-surface outline-none focus:border-primary"
              onChange={(event) => {
                setPolicyDraft(event.target.value);
                setPolicyDirty(true);
                setPolicyStatus("");
                setPolicyError("");
              }}
              spellCheck="false"
              value={policyDraft}
            />
            {policyStatus ? <p className="mt-3 text-sm text-primary">{policyStatus}</p> : null}
            {policyError ? <p className="mt-3 text-sm text-error">{policyError}</p> : null}
          </section>

          <section className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
            <article className="rounded-[1.5rem] border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="font-headline text-xl font-bold text-on-surface">Usage Scope</h2>
                  <p className="mt-1 text-sm text-on-surface-variant">
                    Current dashboard filters and aggregate request totals.
                  </p>
                </div>
                <StatusBadge tone={scrapeOpsTone(accountState.status)}>
                  {labelize(accountState.status || "unknown")}
                </StatusBadge>
              </div>

              <dl className="mt-5 grid gap-4 md:grid-cols-2">
                <div className="rounded-2xl bg-surface-container-low p-4">
                  <dt className="text-xs font-semibold uppercase tracking-[0.24em] text-on-surface-variant">User Filter</dt>
                  <dd className="mt-2 font-mono text-sm text-on-surface">{usage.filters?.user_id || "All users"}</dd>
                </div>
                <div className="rounded-2xl bg-surface-container-low p-4">
                  <dt className="text-xs font-semibold uppercase tracking-[0.24em] text-on-surface-variant">Workspace Filter</dt>
                  <dd className="mt-2 font-mono text-sm text-on-surface">{usage.filters?.workspace_id || "All workspaces"}</dd>
                </div>
                <div className="rounded-2xl bg-surface-container-low p-4">
                  <dt className="text-xs font-semibold uppercase tracking-[0.24em] text-on-surface-variant">Run Filter</dt>
                  <dd className="mt-2 font-mono text-sm text-on-surface">{usage.filters?.run_id || "All runs"}</dd>
                </div>
                <div className="rounded-2xl bg-surface-container-low p-4">
                  <dt className="text-xs font-semibold uppercase tracking-[0.24em] text-on-surface-variant">Generated At</dt>
                  <dd className="mt-2 text-sm text-on-surface">{formatDateTime(reconciliation.generated_at)}</dd>
                </div>
              </dl>
            </article>

            <article className="rounded-[1.5rem] border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
              <h2 className="font-headline text-xl font-bold text-on-surface">Remote Account</h2>
              <p className="mt-1 text-sm text-on-surface-variant">
                Shared ScrapeOps account state returned by the backend reconciliation probe.
              </p>
              <dl className="mt-5 space-y-4">
                <div className="flex items-center justify-between gap-4">
                  <dt className="text-sm text-on-surface-variant">Used Credits</dt>
                  <dd className="font-semibold text-on-surface">{formatNumber(accountUsage.used)}</dd>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <dt className="text-sm text-on-surface-variant">Credit Limit</dt>
                  <dd className="font-semibold text-on-surface">{formatNumber(accountUsage.limit)}</dd>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <dt className="text-sm text-on-surface-variant">Remaining</dt>
                  <dd className="font-semibold text-on-surface">{formatNumber(accountUsage.remaining)}</dd>
                </div>
                <div className="rounded-2xl bg-surface-container-low p-4 text-sm leading-6 text-on-surface-variant">
                  {accountState.summary || "No remote account summary returned."}
                </div>
              </dl>
            </article>
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <BreakdownTable
              emptyLabel="No request-mode usage matches the current filters."
              rows={usage.by_request_mode || []}
              title="By Request Mode"
            />
            <BreakdownTable
              emptyLabel="No domain usage matches the current filters."
              rows={usage.by_domain || []}
              title="By Domain"
            />
          </section>

          <BreakdownTable
            emptyLabel="No run-level usage matches the current filters."
            rows={usage.by_run || []}
            title="By Run"
          />

          <section className="grid gap-4 xl:grid-cols-2">
            <BreakdownTable
              emptyLabel="No reconciliation snapshots have been recorded yet."
              rows={reconciliationSeries || []}
              title="Reconciliation History"
              valueKey="remote_used_credits"
            />
            <BreakdownTable
              emptyLabel="No alert trend rows have been recorded yet."
              rows={alerts.series || []}
              title="Alert Trend"
              valueKey="alerts"
            />
          </section>

          <section className="rounded-[1.5rem] border border-outline-variant/20 bg-surface-container-lowest shadow-soft">
            <div className="border-b border-outline-variant/10 px-5 py-4">
              <h2 className="font-headline text-lg font-bold text-on-surface">ScrapeOps Domain Stats</h2>
              <p className="mt-1 text-sm text-on-surface-variant">
                Remote domain-level stats from ScrapeOps for the selected reconciliation day.
              </p>
            </div>
            {domainStatsRows.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[42rem] text-left text-sm">
                  <thead className="bg-surface-container-low text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
                    <tr>
                      {Object.keys(domainStatsRows[0]).map((column) => (
                        <th className="px-5 py-4" key={column}>
                          {labelize(column)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-outline-variant/10">
                    {domainStatsRows.map((row, index) => (
                      <tr className="hover:bg-surface-container-low" key={`domain-stat-${index}`}>
                        {Object.entries(row).map(([column, value]) => (
                          <td className="px-5 py-4 text-on-surface-variant" key={column}>
                            {typeof value === "number" ? formatNumber(value) : String(value ?? "N/A")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="space-y-4 p-5">
                <p className="text-sm text-on-surface-variant">
                  No structured domain-stat rows were returned for the selected day. Raw response is shown below for inspection.
                </p>
                <pre className="overflow-x-auto rounded-2xl bg-surface-container-low p-4 text-xs leading-6 text-on-surface-variant">
                  {JSON.stringify(reconciliation.domain_stats || {}, null, 2)}
                </pre>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
