import { useEffect } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { formatDateTime, labelize } from "../lib/formatters";

const APPLICATION_OUTCOME_SEGMENTS = [
  { label: "Applied", color: "#38bdf8" },
  { label: "Interviewing", color: "#f59e0b" },
  { label: "Offer", color: "#22c55e" },
  { label: "Rejected", color: "#f97316" },
  { label: "Withdrawn", color: "#94a3b8" },
];

const SOURCE_KIND_COLORS = ["#0f766e", "#14b8a6", "#38bdf8", "#f59e0b", "#f97316"];
const ACTIVE_RUN_STATUSES = new Set(["planned", "queued", "running", "cancel_requested"]);
const TERMINAL_RUN_STATUSES = new Set(["completed", "failed", "cancelled"]);
const REFERRAL_STAGE_INDEX = {
  "Not contacted": 0,
  Contacted: 1,
  Replied: 2,
  "Referral offered": 3,
  "No referral": 2,
};

function buildApiPath(path, params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }
    query.set(key, String(value));
  });
  const queryString = query.toString();
  return queryString ? `${path}?${queryString}` : path;
}

async function loadPaginatedCollection(request, path, collectionKey, { limit = 500, params = {} } = {}) {
  const items = [];
  let offset = 0;

  while (true) {
    const payload = await request(buildApiPath(path, { ...params, limit, offset }));
    const page = Array.isArray(payload?.[collectionKey]) ? payload[collectionKey] : [];
    const returned = Number(payload?.meta?.returned ?? page.length);

    items.push(...page);

    if (!page.length || returned < limit) {
      break;
    }
    offset += returned;
  }

  return items;
}

async function loadDashboardPayload(request) {
  return request("/dashboard");
}

function getNumericValue(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(Number(value || 0));
}

function formatPercent(ratio, digits = 0) {
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(Number.isFinite(ratio) ? ratio : 0);
}

function formatDuration(durationMs) {
  if (!Number.isFinite(durationMs) || durationMs <= 0) {
    return "N/A";
  }
  const totalMinutes = Math.round(durationMs / 60000);
  if (totalMinutes < 1) {
    return `${Math.max(1, Math.round(durationMs / 1000))}s`;
  }
  if (totalMinutes < 60) {
    return `${totalMinutes}m`;
  }
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
}

function formatChartTooltipValue(value) {
  return formatNumber(value);
}

function parseTimestamp(value) {
  const timestamp = Date.parse(String(value || ""));
  return Number.isFinite(timestamp) ? timestamp : null;
}

function average(values) {
  if (!values.length) {
    return 0;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function getRunDurationMs(run) {
  const start =
    parseTimestamp(run?.started_at)
    ?? parseTimestamp(run?.queued_at)
    ?? parseTimestamp(run?.created_at);
  const end = parseTimestamp(run?.finished_at);
  if (start === null || end === null || end <= start) {
    return null;
  }
  return end - start;
}

function getFailedStageResult(run) {
  const stageResults = Array.isArray(run?.stage_results) ? run.stage_results : [];
  return [...stageResults].reverse().find((result) => String(result?.status || "").trim().toLowerCase() === "failed") || null;
}

function getFailureStageKey(run) {
  const failedStage = getFailedStageResult(run);
  return String(failedStage?.stage_id || run?.current_stage_id || "unknown").trim() || "unknown";
}

function getFailureMessage(run) {
  const failedStage = getFailedStageResult(run);
  return (
    String(failedStage?.error || run?.last_error || "").trim()
    || "Run failed without a saved error message."
  );
}

function isSourceStage(stageId) {
  return stageId.startsWith("source_") || stageId === "source_search";
}

function isMergeStage(stageId) {
  return stageId.includes("merge");
}

function isScreenStage(stageId) {
  return stageId.includes("screen");
}

function isApprovalStage(stageId) {
  return stageId.includes("prioritize");
}

function isApplyStage(stageId) {
  return stageId.includes("generate") || stageId.includes("package");
}

function deriveRunPipeline(run) {
  const stageResults = Array.isArray(run?.stage_results) ? run.stage_results : [];
  let discoveredFromSources = 0;
  let discoveredFromMerge = 0;
  let screened = 0;
  let screenApproved = 0;
  let approved = 0;
  let applied = 0;

  stageResults.forEach((result) => {
    const stageId = String(result?.stage_id || "").trim();
    const metrics = result?.metrics || {};
    const jobsFound = getNumericValue(metrics.jobs_found);
    const jobsIngested = getNumericValue(metrics.jobs_ingested);
    const mergedJobs = getNumericValue(metrics.merged_jobs);
    const approvedJobs = getNumericValue(metrics.approved);
    const rejectedJobs = getNumericValue(metrics.rejected);
    const generatedJobs = getNumericValue(metrics.generated_jobs);
    const packagedJobs = getNumericValue(metrics.packaged_jobs);

    if (isSourceStage(stageId)) {
      discoveredFromSources += jobsFound + jobsIngested;
    }
    if (isMergeStage(stageId)) {
      discoveredFromMerge = Math.max(discoveredFromMerge, mergedJobs);
    }
    if (isScreenStage(stageId)) {
      screenApproved += approvedJobs;
      screened += approvedJobs + rejectedJobs || approvedJobs;
    }
    if (isApprovalStage(stageId)) {
      approved += approvedJobs;
    }
    if (isApplyStage(stageId)) {
      applied += generatedJobs + packagedJobs;
    }
  });

  return {
    discovered: discoveredFromMerge || discoveredFromSources,
    screened,
    approved: approved || screenApproved,
    applied,
  };
}

function buildDashboardViewModel({ runs, trackerItems, contacts, outreachItems, recentFailedRuns }) {
  const terminalRuns = runs.filter((run) => TERMINAL_RUN_STATUSES.has(String(run?.status || "").trim()));
  const completedRuns = terminalRuns.filter((run) => String(run?.status || "").trim() === "completed");
  const failedRuns = runs.filter((run) => String(run?.status || "").trim() === "failed");
  const activeRuns = runs.filter((run) => ACTIVE_RUN_STATUSES.has(String(run?.status || "").trim()));
  const runDurations = terminalRuns.map(getRunDurationMs).filter((value) => value !== null);

  const failureBreakdownMap = new Map();
  failedRuns.forEach((run) => {
    const key = labelize(getFailureStageKey(run));
    failureBreakdownMap.set(key, (failureBreakdownMap.get(key) || 0) + 1);
  });
  const failureBreakdown = Array.from(failureBreakdownMap.entries())
    .map(([stage, count]) => ({ stage, count }))
    .sort((left, right) => right.count - left.count);

  const aggregatedPipeline = runs.reduce(
    (summary, run) => {
      const pipeline = deriveRunPipeline(run);
      return {
        discovered: summary.discovered + pipeline.discovered,
        screened: summary.screened + pipeline.screened,
        approved: summary.approved + pipeline.approved,
        applied: summary.applied + pipeline.applied,
      };
    },
    { discovered: 0, screened: 0, approved: 0, applied: 0 },
  );
  const pipelineData = [
    { label: "Discovered", value: aggregatedPipeline.discovered, color: "#0f766e" },
    { label: "Screened", value: aggregatedPipeline.screened, color: "#14b8a6" },
    { label: "Approved", value: aggregatedPipeline.approved, color: "#38bdf8" },
    { label: "Applied", value: aggregatedPipeline.applied, color: "#f59e0b" },
  ];

  const applicationStatusMap = new Map();
  trackerItems.forEach((item) => {
    const status = String(item?.application_status || "").trim() || "Unknown";
    applicationStatusMap.set(status, (applicationStatusMap.get(status) || 0) + 1);
  });
  const applicationOutcomes = APPLICATION_OUTCOME_SEGMENTS.map((segment) => ({
    ...segment,
    value: applicationStatusMap.get(segment.label) || 0,
  }));

  const sourceKindMap = new Map();
  contacts.forEach((contact) => {
    const sourceKind = labelize(String(contact?.source_kind || "manual").trim() || "manual");
    sourceKindMap.set(sourceKind, (sourceKindMap.get(sourceKind) || 0) + 1);
  });
  const contactSources = Array.from(sourceKindMap.entries())
    .map(([label, value], index) => ({
      label,
      value,
      color: SOURCE_KIND_COLORS[index % SOURCE_KIND_COLORS.length],
    }))
    .sort((left, right) => right.value - left.value);

  const highestReferralStageByContact = new Map();
  const noReferralContacts = new Set();
  contacts.forEach((contact) => {
    highestReferralStageByContact.set(String(contact?.contact_id || "").trim(), 0);
  });
  outreachItems.forEach((item) => {
    const contactId = String(item?.contact_id || "").trim();
    if (!contactId || !highestReferralStageByContact.has(contactId)) {
      return;
    }
    const stageIndex = REFERRAL_STAGE_INDEX[String(item?.outreach_status || "").trim()] ?? 0;
    if (String(item?.outreach_status || "").trim() === "No referral") {
      noReferralContacts.add(contactId);
    }
    const currentStage = highestReferralStageByContact.get(contactId) || 0;
    if (stageIndex > currentStage) {
      highestReferralStageByContact.set(contactId, stageIndex);
    }
  });

  const contactStageIndexes = Array.from(highestReferralStageByContact.values());
  const noReferralCount = noReferralContacts.size;
  const outreachFunnel = [
    {
      label: "Not contacted",
      value: contactStageIndexes.filter((stageIndex) => stageIndex === 0).length,
      color: "#94a3b8",
    },
    {
      label: "Contacted",
      value: contactStageIndexes.filter((stageIndex) => stageIndex >= 1).length,
      color: "#38bdf8",
    },
    {
      label: "Replied",
      value: contactStageIndexes.filter((stageIndex) => stageIndex >= 2).length,
      color: "#14b8a6",
    },
    {
      label: "Referral offered",
      value: contactStageIndexes.filter((stageIndex) => stageIndex >= 3).length,
      color: "#22c55e",
    },
  ];

  return {
    automation: {
      totalRuns: runs.length,
      terminalRuns: terminalRuns.length,
      completedRuns: completedRuns.length,
      failedRuns: failedRuns.length,
      activeRuns: activeRuns.length,
      successRate: terminalRuns.length ? completedRuns.length / terminalRuns.length : 0,
      averageDurationMs: average(runDurations),
      failureBreakdown,
    },
    pipeline: {
      data: pipelineData,
    },
    outcomes: {
      total: applicationOutcomes.reduce((sum, segment) => sum + segment.value, 0),
      unknown: applicationStatusMap.get("Unknown") || 0,
      segments: applicationOutcomes,
    },
    referrals: {
      totalContacts: contacts.length,
      noReferralCount,
      trackedOutreachItems: outreachItems.length,
      contactSources,
      outreachFunnel,
    },
    recentFailures: recentFailedRuns.map((run) => ({
      id: run.id,
      workspaceName: run.workspace_name || run.workspace_id || "Unknown workspace",
      timestamp: run.finished_at || run.updated_at || run.created_at || "",
      stage: labelize(getFailureStageKey(run)),
      errorText: getFailureMessage(run),
    })),
  };
}

function DashboardPanel({ children, className = "" }) {
  return (
    <section
      className={[
        "rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft",
        className,
      ].join(" ")}
    >
      {children}
    </section>
  );
}

function PanelHeader({ eyebrow, title, description, action }) {
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-on-surface-variant">{eyebrow}</p>
        <h2 className="mt-2 font-headline text-2xl font-bold tracking-tight text-on-surface">{title}</h2>
        <p className="mt-2 max-w-3xl text-sm leading-7 text-on-surface-variant">{description}</p>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

function StatTile({ label, value, detail, accentClass = "text-on-surface" }) {
  return (
    <div className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">{label}</p>
      <p className={["mt-3 text-3xl font-black tracking-tight", accentClass].join(" ")}>{value}</p>
      <p className="mt-2 text-sm text-on-surface-variant">{detail}</p>
    </div>
  );
}

function EmptyChartState({ message }) {
  return (
    <div className="flex h-full min-h-48 items-center justify-center rounded-[1.35rem] border border-dashed border-outline-variant/20 bg-surface text-sm text-on-surface-variant">
      {message}
    </div>
  );
}

function SkeletonBlock({ className = "" }) {
  return <div className={["animate-pulse rounded-2xl bg-surface-container", className].join(" ")} />;
}

function DashboardSkeleton() {
  return (
    <div className="space-y-8">
      <section className="rounded-[2rem] bg-slate-950 px-6 py-8 sm:px-8">
        <SkeletonBlock className="h-5 w-40 bg-white/10" />
        <SkeletonBlock className="mt-4 h-12 w-64 bg-white/10" />
        <SkeletonBlock className="mt-4 h-5 w-full max-w-2xl bg-white/10" />
        <SkeletonBlock className="mt-2 h-5 w-full max-w-xl bg-white/10" />
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          <SkeletonBlock className="h-28 bg-white/10" />
          <SkeletonBlock className="h-28 bg-white/10" />
          <SkeletonBlock className="h-28 bg-white/10" />
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <DashboardPanel>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <SkeletonBlock className="h-28" />
            <SkeletonBlock className="h-28" />
            <SkeletonBlock className="h-28" />
            <SkeletonBlock className="h-28" />
          </div>
          <SkeletonBlock className="mt-6 h-72" />
        </DashboardPanel>
        <DashboardPanel>
          <SkeletonBlock className="h-72" />
        </DashboardPanel>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <DashboardPanel>
          <SkeletonBlock className="h-80" />
        </DashboardPanel>
        <DashboardPanel>
          <SkeletonBlock className="h-80" />
        </DashboardPanel>
      </div>

      <DashboardPanel>
        <SkeletonBlock className="h-96" />
      </DashboardPanel>
    </div>
  );
}

function DashboardError({ error, onRetry }) {
  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-3">
        <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">Dashboard</h1>
        <p className="max-w-3xl text-sm leading-7 text-on-surface-variant">
          Live analytics for run health, application outcomes, and referral outreach.
        </p>
      </header>

      <section className="rounded-[1.75rem] border border-error/20 bg-error/5 px-6 py-6 text-error shadow-soft">
        <p className="font-semibold">Unable to load dashboard data.</p>
        <p className="mt-2 text-sm">{error || "Request failed."}</p>
        <button
          className="mt-4 rounded-full bg-error/10 px-4 py-2 text-sm font-semibold text-error transition-colors hover:bg-error/15"
          onClick={() => onRetry().catch(() => undefined)}
          type="button"
        >
          Retry
        </button>
      </section>
    </div>
  );
}

function DashboardHeader({ model, onRefresh, refreshing }) {
  return (
    <section className="relative overflow-hidden rounded-[2rem] bg-slate-950 px-6 py-8 text-white shadow-[0_28px_80px_rgba(15,23,42,0.28)] sm:px-8">
      <div
        aria-hidden="true"
        className="absolute inset-0 opacity-90"
        style={{
          background:
            "radial-gradient(circle at top left, rgba(20,184,166,0.34), transparent 35%), radial-gradient(circle at 80% 20%, rgba(56,189,248,0.26), transparent 30%), linear-gradient(135deg, rgba(15,23,42,1), rgba(8,47,73,0.94) 55%, rgba(17,24,39,1))",
        }}
      />

      <div className="relative z-10 space-y-8">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="max-w-3xl">
            <div className="mb-4 flex flex-wrap gap-3">
              <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/8 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-white/80">
                <span aria-hidden="true" className="h-2 w-2 rounded-full bg-emerald-300" />
                Live dashboard
              </span>
              <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/8 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-white/70">
                Existing API data only
              </span>
            </div>

            <h1 className="font-headline text-4xl font-black tracking-[-0.05em] text-white sm:text-5xl">
              Dashboard
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-7 text-white/72 sm:text-lg">
              Run automation health, sourcing throughput, application outcomes, and referral outreach
              in one live view powered by the current backend endpoints.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              className="inline-flex items-center justify-center rounded-full border border-white/12 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={refreshing}
              onClick={() => onRefresh().catch(() => undefined)}
              type="button"
            >
              {refreshing ? "Refreshing..." : "Refresh"}
            </button>
            <Link
              className="inline-flex items-center justify-center rounded-full border border-white/65 bg-slate-50 px-5 py-3 text-sm font-semibold text-slate-950 shadow-[0_12px_30px_rgba(2,6,23,0.2)] transition-all hover:-translate-y-0.5 hover:bg-white"
              to="/runs"
            >
              Open Runs
            </Link>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-[1.5rem] border border-white/10 bg-white/8 p-5 backdrop-blur-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-white/60">Total Runs</p>
            <p className="mt-3 text-4xl font-black tracking-[-0.05em] text-white">
              {formatNumber(model.automation.totalRuns)}
            </p>
            <p className="mt-2 text-sm text-white/68">
              {formatNumber(model.automation.activeRuns)} active and {formatNumber(model.automation.failedRuns)} failed
            </p>
          </div>

          <div className="rounded-[1.5rem] border border-white/10 bg-white/8 p-5 backdrop-blur-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-white/60">Tracked Applications</p>
            <p className="mt-3 text-4xl font-black tracking-[-0.05em] text-white">
              {formatNumber(model.outcomes.total)}
            </p>
            <p className="mt-2 text-sm text-white/68">
              {formatNumber(model.pipeline.data[3].value)} applied in run-stage metrics
            </p>
          </div>

          <div className="rounded-[1.5rem] border border-white/10 bg-white/8 p-5 backdrop-blur-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-white/60">Referral Contacts</p>
            <p className="mt-3 text-4xl font-black tracking-[-0.05em] text-white">
              {formatNumber(model.referrals.totalContacts)}
            </p>
            <p className="mt-2 text-sm text-white/68">
              {formatNumber(model.referrals.outreachFunnel[3].value)} reached referral offered
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function AutomationHealthPanel({ automation }) {
  return (
    <DashboardPanel>
      <PanelHeader
        action={
          <span className="rounded-full bg-surface-container-low px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">
            {formatNumber(automation.terminalRuns)} finished runs
          </span>
        }
        description="Success rate is based on terminal runs only. Average duration uses completed, failed, and cancelled runs with valid start and finish timestamps."
        eyebrow="Panel 1"
        title="Automation Health"
      />

      <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatTile
          detail="All runs visible to the current user."
          label="Total Runs"
          value={formatNumber(automation.totalRuns)}
        />
        <StatTile
          accentClass="text-emerald-600"
          detail={`${formatNumber(automation.completedRuns)} completed`}
          label="Success Rate"
          value={formatPercent(automation.successRate)}
        />
        <StatTile
          detail="Average terminal run duration."
          label="Avg Duration"
          value={formatDuration(automation.averageDurationMs)}
        />
        <StatTile
          accentClass="text-rose-600"
          detail={`${formatNumber(automation.activeRuns)} still active`}
          label="Failed Runs"
          value={formatNumber(automation.failedRuns)}
        />
      </div>

      <div className="mt-8">
        {automation.failureBreakdown.length ? (
          <div className="h-72 rounded-[1.35rem] border border-outline-variant/15 bg-surface p-4">
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={automation.failureBreakdown} layout="vertical" margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                <XAxis allowDecimals={false} stroke="#94a3b8" type="number" />
                <YAxis dataKey="stage" stroke="#64748b" type="category" width={112} />
                <Tooltip
                  contentStyle={{ borderRadius: "1rem", borderColor: "rgba(148,163,184,0.2)" }}
                  cursor={{ fill: "rgba(15, 23, 42, 0.04)" }}
                  formatter={(value) => [formatChartTooltipValue(value), "Failed runs"]}
                />
                <Bar dataKey="count" fill="#f97316" radius={[0, 10, 10, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <EmptyChartState message="No failed runs yet, so there is no failure breakdown to chart." />
        )}
      </div>
    </DashboardPanel>
  );
}

function JobsPipelinePanel({ pipeline }) {
  const [discovered, screened, approved, applied] = pipeline.data;
  const conversions = [
    {
      label: "Screened / discovered",
      value: discovered.value ? screened.value / discovered.value : 0,
    },
    {
      label: "Approved / screened",
      value: screened.value ? approved.value / screened.value : 0,
    },
    {
      label: "Applied / approved",
      value: approved.value ? applied.value / approved.value : 0,
    },
  ];

  return (
    <DashboardPanel>
      <PanelHeader
        action={
          <Link
            className="rounded-full bg-primary/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-primary transition-colors hover:bg-primary/20"
            to="/runs"
          >
            Inspect runs
          </Link>
        }
        description="This funnel is derived from persisted run-stage metrics. Discovery prefers merged-job totals when a merge stage is present, then falls back to acquisition-stage counts."
        eyebrow="Panel 2"
        title="Jobs Pipeline"
      />

      <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {pipeline.data.map((stage) => (
          <StatTile
            detail="Aggregated from run stage metrics."
            key={stage.label}
            label={stage.label}
            value={formatNumber(stage.value)}
          />
        ))}
      </div>

      <div className="mt-8 grid gap-6 xl:grid-cols-[1fr_0.72fr]">
        <div className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-4">
          <div className="h-72">
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={pipeline.data} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                <XAxis dataKey="label" stroke="#94a3b8" tickLine={false} />
                <YAxis allowDecimals={false} stroke="#94a3b8" tickLine={false} />
                <Tooltip
                  contentStyle={{ borderRadius: "1rem", borderColor: "rgba(148,163,184,0.2)" }}
                  cursor={{ fill: "rgba(15, 23, 42, 0.04)" }}
                  formatter={(value) => [formatChartTooltipValue(value), "Jobs"]}
                />
                <Bar dataKey="value" radius={[14, 14, 0, 0]}>
                  {pipeline.data.map((entry) => (
                    <Cell fill={entry.color} key={entry.label} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="space-y-4">
          {conversions.map((conversion) => (
            <div className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-4" key={conversion.label}>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">{conversion.label}</p>
              <p className="mt-3 text-3xl font-black tracking-tight text-on-surface">{formatPercent(conversion.value)}</p>
              <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-surface-container-low">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${Math.max(0, Math.min(100, conversion.value * 100))}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </DashboardPanel>
  );
}

function ApplicationOutcomesPanel({ outcomes }) {
  return (
    <DashboardPanel>
      <PanelHeader
        action={
          <Link
            className="rounded-full bg-primary/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-primary transition-colors hover:bg-primary/20"
            to="/tracker"
          >
            Open tracker
          </Link>
        }
        description="Counts come from the explicit `application_status` on tracker items, including external applications that the tracker imports."
        eyebrow="Panel 3"
        title="Application Outcomes"
      />

      <div className="mt-8 grid gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
        <div className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-4">
          {outcomes.total ? (
            <div className="h-80">
              <ResponsiveContainer height="100%" width="100%">
                <PieChart>
                  <Pie
                    cx="50%"
                    cy="50%"
                    data={outcomes.segments.filter((segment) => segment.value > 0)}
                    dataKey="value"
                    innerRadius={74}
                    outerRadius={112}
                    paddingAngle={2}
                  >
                    {outcomes.segments.filter((segment) => segment.value > 0).map((segment) => (
                      <Cell fill={segment.color} key={segment.label} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ borderRadius: "1rem", borderColor: "rgba(148,163,184,0.2)" }}
                    formatter={(value) => [formatChartTooltipValue(value), "Applications"]}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyChartState message="No tracked applications are available yet." />
          )}
        </div>

        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <StatTile
              detail="Statuses shown in the chart."
              label="Tracked Items"
              value={formatNumber(outcomes.total)}
            />
            <StatTile
              detail="Explicitly marked unknown."
              label="Unknown"
              value={formatNumber(outcomes.unknown)}
            />
          </div>

          <div className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-4">
            <div className="space-y-4">
              {outcomes.segments.map((segment) => (
                <div className="flex items-center justify-between gap-4" key={segment.label}>
                  <div className="flex items-center gap-3">
                    <span aria-hidden="true" className="h-3 w-3 rounded-full" style={{ backgroundColor: segment.color }} />
                    <span className="text-sm text-on-surface">{segment.label}</span>
                  </div>
                  <span className="text-sm font-semibold text-on-surface">{formatNumber(segment.value)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </DashboardPanel>
  );
}

function ReferralOutreachPanel({ referrals }) {
  return (
    <DashboardPanel>
      <PanelHeader
        action={
          <Link
            className="rounded-full bg-primary/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-primary transition-colors hover:bg-primary/20"
            to="/referrals"
          >
            Open referrals
          </Link>
        }
        description="Source-kind totals come from referral contacts. The outreach funnel groups contacts by the furthest saved outreach stage reached across their tracked outreach records."
        eyebrow="Panel 4"
        title="Referral Outreach"
      />

      <div className="mt-8 grid gap-4 md:grid-cols-3">
        <StatTile
          detail="All referral contacts on record."
          label="Contacts Total"
          value={formatNumber(referrals.totalContacts)}
        />
        <StatTile
          detail="Contacts with no tracked outreach yet."
          label="Not Contacted"
          value={formatNumber(referrals.outreachFunnel[0].value)}
        />
        <StatTile
          detail={`${formatNumber(referrals.noReferralCount)} ended in no referral`}
          label="Referral Offered"
          value={formatNumber(referrals.outreachFunnel[3].value)}
        />
      </div>

      <div className="mt-8 grid gap-6 xl:grid-cols-2">
        <div className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-4">
          <div className="mb-4 flex items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">By Source Kind</p>
              <p className="mt-1 text-sm text-on-surface-variant">Counts from `GET /referrals`.</p>
            </div>
            <span className="rounded-full bg-surface-container-low px-3 py-1 text-xs font-semibold text-on-surface-variant">
              {formatNumber(referrals.totalContacts)} total
            </span>
          </div>

          {referrals.contactSources.length ? (
            <div className="h-72">
              <ResponsiveContainer height="100%" width="100%">
                <BarChart data={referrals.contactSources} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                  <XAxis dataKey="label" stroke="#94a3b8" tickLine={false} />
                  <YAxis allowDecimals={false} stroke="#94a3b8" tickLine={false} />
                  <Tooltip
                    contentStyle={{ borderRadius: "1rem", borderColor: "rgba(148,163,184,0.2)" }}
                    cursor={{ fill: "rgba(15, 23, 42, 0.04)" }}
                    formatter={(value) => [formatChartTooltipValue(value), "Contacts"]}
                  />
                  <Bar dataKey="value" radius={[14, 14, 0, 0]}>
                    {referrals.contactSources.map((source) => (
                      <Cell fill={source.color} key={source.label} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyChartState message="No referral contacts are available yet." />
          )}
        </div>

        <div className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-4">
          <div className="mb-4 flex items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">Outreach Funnel</p>
              <p className="mt-1 text-sm text-on-surface-variant">Counts from saved outreach statuses.</p>
            </div>
            <span className="rounded-full bg-surface-container-low px-3 py-1 text-xs font-semibold text-on-surface-variant">
              {formatNumber(referrals.trackedOutreachItems)} status updates
            </span>
          </div>

          {referrals.totalContacts ? (
            <div className="h-72">
              <ResponsiveContainer height="100%" width="100%">
                <BarChart data={referrals.outreachFunnel} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                  <XAxis dataKey="label" stroke="#94a3b8" tickLine={false} />
                  <YAxis allowDecimals={false} stroke="#94a3b8" tickLine={false} />
                  <Tooltip
                    contentStyle={{ borderRadius: "1rem", borderColor: "rgba(148,163,184,0.2)" }}
                    cursor={{ fill: "rgba(15, 23, 42, 0.04)" }}
                    formatter={(value) => [formatChartTooltipValue(value), "Contacts"]}
                  />
                  <Bar dataKey="value" radius={[14, 14, 0, 0]}>
                    {referrals.outreachFunnel.map((stage) => (
                      <Cell fill={stage.color} key={stage.label} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyChartState message="Add referral contacts to start tracking outreach progression." />
          )}
        </div>
      </div>
    </DashboardPanel>
  );
}

function RecentFailuresPanel({ items }) {
  return (
    <DashboardPanel>
      <PanelHeader
        action={
          <Link
            className="rounded-full bg-primary/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-primary transition-colors hover:bg-primary/20"
            to="/runs?status=failed"
          >
            View failed runs
          </Link>
        }
        description="The five most recent failed runs from `GET /runs?status=failed&limit=5`, including the saved error text and the stage that failed."
        eyebrow="Panel 5"
        title="Recent Failures"
      />

      <div className="mt-8 space-y-4">
        {items.length ? (
          items.map((item) => (
            <article className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-4" key={item.id}>
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="rounded-full bg-error/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-error">
                      {item.stage}
                    </span>
                    <span className="text-sm font-medium text-on-surface">{item.workspaceName}</span>
                  </div>
                  <p className="text-sm leading-7 text-on-surface-variant">{item.errorText}</p>
                </div>

                <div className="flex shrink-0 flex-col items-start gap-3 lg:items-end">
                  <span className="text-sm text-on-surface-variant">{formatDateTime(item.timestamp)}</span>
                  <Link
                    className="rounded-full bg-primary/10 px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-primary/20"
                    to={`/runs/${item.id}`}
                  >
                    Open run
                  </Link>
                </div>
              </div>
            </article>
          ))
        ) : (
          <div className="rounded-[1.35rem] border border-dashed border-outline-variant/20 bg-surface p-6 text-sm text-on-surface-variant">
            No recent failures are available.
          </div>
        )}
      </div>
    </DashboardPanel>
  );
}

export default function DashboardPage() {
  const { isConnected, request } = useSession();
  const { data, loading, error, refresh } = useApiResource(() => loadDashboardPayload(request), [request]);

  useEffect(() => {
    if (!isConnected) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      refresh().catch(() => undefined);
    }, 30000);
    return () => window.clearInterval(intervalId);
  }, [isConnected, refresh]);

  if (!isConnected && !loading) {
    return (
      <div className="space-y-6">
        <header className="flex flex-col gap-3">
          <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">Dashboard</h1>
          <p className="max-w-3xl text-sm leading-7 text-on-surface-variant">
            Connect the frontend to the backend API to load live analytics.
          </p>
        </header>

        <section className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest px-6 py-6 text-on-surface-variant shadow-soft">
          Use the API connection controls first, then reopen this page.
        </section>
      </div>
    );
  }

  if (loading && !data) {
    return <DashboardSkeleton />;
  }

  if (error && !data) {
    return <DashboardError error={error} onRetry={refresh} />;
  }

  const model = data?.analytics || buildDashboardViewModel(data || {
    runs: [],
    trackerItems: [],
    contacts: [],
    outreachItems: [],
    recentFailedRuns: [],
  });

  return (
    <div className="space-y-8">
      <DashboardHeader model={model} onRefresh={refresh} refreshing={loading} />

      {error ? (
        <section className="rounded-2xl border border-error/20 bg-error/5 px-5 py-4 text-sm text-error">
          {error}
        </section>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <AutomationHealthPanel automation={model.automation} />
        <RecentFailuresPanel items={model.recentFailures} />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <JobsPipelinePanel pipeline={model.pipeline} />
        <ApplicationOutcomesPanel outcomes={model.outcomes} />
      </div>

      <ReferralOutreachPanel referrals={model.referrals} />
    </div>
  );
}
