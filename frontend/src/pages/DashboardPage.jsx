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

const APPLICATION_OUTCOME_SEGMENTS = [
  { label: "Applied", color: "#38bdf8" },
  { label: "Interviewing", color: "#f59e0b" },
  { label: "Offer", color: "#22c55e" },
  { label: "Rejected", color: "#f97316" },
  { label: "Withdrawn", color: "#94a3b8" },
];

const REFERRAL_FUNNEL_STAGES = [
  { label: "Not contacted", color: "#94a3b8" },
  { label: "Contacted", color: "#38bdf8" },
  { label: "Replied", color: "#14b8a6" },
  { label: "Referral offered", color: "#22c55e" },
];

const EMPTY_OUTCOMES = {
  total: 0,
  unknown: 0,
  trackerTotal: 0,
  submittedTotal: 0,
  segments: APPLICATION_OUTCOME_SEGMENTS.map((segment) => ({ ...segment, value: 0 })),
};

const EMPTY_REFERRALS = {
  totalContacts: 0,
  noReferralCount: 0,
  trackedOutreachItems: 0,
  contactSources: [],
  outreachFunnel: REFERRAL_FUNNEL_STAGES.map((stage) => ({ ...stage, value: 0 })),
};

const EMPTY_CANDIDATE_INSIGHTS = {
  actionPlan: [],
  funnel: { stages: [] },
  pipelineAging: [],
  sourceEffectiveness: [],
  weeklySummary: {
    windowDays: 7,
    current: {},
    previous: {},
  },
  dataQuality: {
    confidence: 100,
    issueCount: 0,
    unknownStatuses: 0,
    missingApplicationDates: 0,
    missingSources: 0,
  },
};

function loadDashboardPayload(request) {
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

function formatChartTooltipValue(value) {
  return formatNumber(value);
}

function findValueByLabel(items, label) {
  const match = Array.isArray(items)
    ? items.find((item) => String(item?.label || "").trim() === label)
    : null;
  return getNumericValue(match?.value);
}

function normalizeOutcomes(rawOutcomes) {
  return {
    total: getNumericValue(rawOutcomes?.total),
    unknown: getNumericValue(rawOutcomes?.unknown),
    trackerTotal: getNumericValue(rawOutcomes?.trackerTotal),
    submittedTotal: getNumericValue(rawOutcomes?.submittedTotal),
    segments: APPLICATION_OUTCOME_SEGMENTS.map((segment) => ({
      ...segment,
      value: findValueByLabel(rawOutcomes?.segments, segment.label),
    })),
  };
}

function normalizeReferrals(rawReferrals) {
  return {
    totalContacts: getNumericValue(rawReferrals?.totalContacts),
    noReferralCount: getNumericValue(rawReferrals?.noReferralCount),
    trackedOutreachItems: getNumericValue(rawReferrals?.trackedOutreachItems),
    contactSources: Array.isArray(rawReferrals?.contactSources) ? rawReferrals.contactSources : [],
    outreachFunnel: REFERRAL_FUNNEL_STAGES.map((stage) => {
      const match = Array.isArray(rawReferrals?.outreachFunnel)
        ? rawReferrals.outreachFunnel.find((item) => String(item?.label || "").trim() === stage.label)
        : null;
      return {
        ...stage,
        value: getNumericValue(match?.value),
        color: String(match?.color || stage.color),
      };
    }),
  };
}

function normalizeCandidateInsights(rawInsights) {
  const insights = rawInsights || EMPTY_CANDIDATE_INSIGHTS;
  const normalizePeriod = (period) => ({
    applications: getNumericValue(period?.applications),
    responses: getNumericValue(period?.responses),
    interviews: getNumericValue(period?.interviews),
    offers: getNumericValue(period?.offers),
    referralUpdates: getNumericValue(period?.referralUpdates),
  });
  return {
    actionPlan: Array.isArray(insights.actionPlan) ? insights.actionPlan : [],
    funnel: {
      stages: Array.isArray(insights.funnel?.stages)
        ? insights.funnel.stages.map((stage) => ({
          ...stage,
          value: getNumericValue(stage?.value),
          conversionRate: getNumericValue(stage?.conversionRate),
        }))
        : [],
    },
    pipelineAging: Array.isArray(insights.pipelineAging)
      ? insights.pipelineAging.map((stage) => ({
        ...stage,
        count: getNumericValue(stage?.count),
        staleCount: getNumericValue(stage?.staleCount),
        medianAgeDays: getNumericValue(stage?.medianAgeDays),
        staleAfterDays: getNumericValue(stage?.staleAfterDays),
      }))
      : [],
    sourceEffectiveness: Array.isArray(insights.sourceEffectiveness)
      ? insights.sourceEffectiveness.map((source) => ({
        ...source,
        tracked: getNumericValue(source?.tracked),
        applied: getNumericValue(source?.applied),
        responses: getNumericValue(source?.responses),
        interviews: getNumericValue(source?.interviews),
        offers: getNumericValue(source?.offers),
        responseRate: getNumericValue(source?.responseRate),
      }))
      : [],
    weeklySummary: {
      windowDays: getNumericValue(insights.weeklySummary?.windowDays) || 7,
      current: normalizePeriod(insights.weeklySummary?.current),
      previous: normalizePeriod(insights.weeklySummary?.previous),
    },
    dataQuality: {
      confidence: getNumericValue(insights.dataQuality?.confidence),
      issueCount: getNumericValue(insights.dataQuality?.issueCount),
      unknownStatuses: getNumericValue(insights.dataQuality?.unknownStatuses),
      missingApplicationDates: getNumericValue(insights.dataQuality?.missingApplicationDates),
      missingSources: getNumericValue(insights.dataQuality?.missingSources),
    },
  };
}

function actionAccentClass(priority) {
  if (priority === "high") {
    return "text-rose-600";
  }
  if (priority === "medium") {
    return "text-amber-600";
  }
  return "text-primary";
}

function buildUserDashboardModel(payload) {
  const outcomes = normalizeOutcomes(payload?.analytics?.outcomes || EMPTY_OUTCOMES);
  const referrals = normalizeReferrals(payload?.analytics?.referrals || EMPTY_REFERRALS);
  const insights = normalizeCandidateInsights(payload?.analytics?.candidateInsights);

  const applied = findValueByLabel(outcomes.segments, "Applied");
  const interviewing = findValueByLabel(outcomes.segments, "Interviewing");
  const offers = findValueByLabel(outcomes.segments, "Offer");
  const rejected = findValueByLabel(outcomes.segments, "Rejected");
  const withdrawn = findValueByLabel(outcomes.segments, "Withdrawn");
  const waitingReviewCount = findValueByLabel(payload?.cards, "Jobs Waiting Review");

  const notContacted = findValueByLabel(referrals.outreachFunnel, "Not contacted");
  const contacted = findValueByLabel(referrals.outreachFunnel, "Contacted");
  const replied = findValueByLabel(referrals.outreachFunnel, "Replied");
  const referralOffered = findValueByLabel(referrals.outreachFunnel, "Referral offered");

  const knownApplications = outcomes.total;
  const activeApplications = applied + interviewing + offers;
  const heardBackCount = interviewing + offers + rejected;
  const heardBackRate = knownApplications ? heardBackCount / knownApplications : 0;

  const fallbackFocusItems = [
    {
      title: "Jobs Waiting Review",
      value: waitingReviewCount,
      detail: waitingReviewCount
        ? "Open your runs and decide which jobs should move forward."
        : "Nothing is waiting on a review decision right now.",
      icon: "fact_check",
      to: "/runs",
      actionLabel: waitingReviewCount ? "Review jobs" : "Open runs",
      accentClass: waitingReviewCount ? "text-primary" : "text-on-surface",
    },
    {
      title: "Tracker Cleanup",
      value: outcomes.unknown,
      detail: outcomes.unknown
        ? "Some tracked applications still need a real status."
        : "Tracker statuses are already clean and up to date.",
      icon: "rule",
      to: "/tracker",
      actionLabel: outcomes.unknown ? "Clean up tracker" : "Open tracker",
      accentClass: outcomes.unknown ? "text-amber-600" : "text-on-surface",
    },
    {
      title: "Interviews In Motion",
      value: interviewing,
      detail: interviewing
        ? "Keep follow-up notes and scheduling details current."
        : "Interview invites will show up here once employers reply.",
      icon: "calendar_month",
      to: "/tracker",
      actionLabel: interviewing ? "View interviews" : "Open tracker",
      accentClass: interviewing ? "text-emerald-600" : "text-on-surface",
    },
    {
      title: "People To Contact",
      value: notContacted,
      detail: notContacted
        ? "These contacts are saved but still waiting for outreach."
        : "No saved contacts are waiting on a first message.",
      icon: "outgoing_mail",
      to: "/referrals",
      actionLabel: notContacted ? "Open referrals" : "Manage referrals",
      accentClass: notContacted ? "text-sky-600" : "text-on-surface",
    },
  ];
  const focusItems = insights.actionPlan.length
    ? insights.actionPlan.map((item) => ({
      ...item,
      value: getNumericValue(item?.count),
      accentClass: actionAccentClass(item?.priority),
    }))
    : fallbackFocusItems;

  return {
    focusItems,
    insights,
    outcomes,
    referrals,
    summary: {
      waitingReviewCount,
      trackedApplications: outcomes.trackerTotal || outcomes.total + outcomes.unknown,
      submittedApplications: outcomes.submittedTotal || outcomes.total,
      activeApplications,
      interviewing,
      offers,
      rejected,
      withdrawn,
      unknownApplications: outcomes.unknown,
      heardBackCount,
      heardBackRate,
      notContacted,
      contacted,
      replied,
      referralOffered,
    },
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

function MetricTile({ label, value, detail, accentClass = "text-on-surface" }) {
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
        <SkeletonBlock className="mt-4 h-12 w-72 bg-white/10" />
        <SkeletonBlock className="mt-4 h-5 w-full max-w-2xl bg-white/10" />
        <div className="mt-8 grid gap-4 md:grid-cols-4">
          <SkeletonBlock className="h-28 bg-white/10" />
          <SkeletonBlock className="h-28 bg-white/10" />
          <SkeletonBlock className="h-28 bg-white/10" />
          <SkeletonBlock className="h-28 bg-white/10" />
        </div>
      </section>

      <DashboardPanel>
        <div className="grid gap-4 md:grid-cols-2">
          <SkeletonBlock className="h-40" />
          <SkeletonBlock className="h-40" />
          <SkeletonBlock className="h-40" />
          <SkeletonBlock className="h-40" />
        </div>
      </DashboardPanel>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <DashboardPanel>
          <SkeletonBlock className="h-96" />
        </DashboardPanel>
        <DashboardPanel>
          <SkeletonBlock className="h-96" />
        </DashboardPanel>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <DashboardPanel>
          <SkeletonBlock className="h-96" />
        </DashboardPanel>
        <DashboardPanel>
          <SkeletonBlock className="h-96" />
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
    </div>
  );
}

function DashboardError({ error, onRetry }) {
  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-3">
        <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">Dashboard</h1>
        <p className="max-w-3xl text-sm leading-7 text-on-surface-variant">
          Track applications, review work, and referral follow-up from one place.
        </p>
      </header>

      <section className="rounded-[1.75rem] border border-error/20 bg-error/5 px-6 py-6 text-error shadow-soft">
        <p className="font-semibold">Unable to load your dashboard.</p>
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
                Candidate view
              </span>
            </div>

            <h1 className="font-headline text-4xl font-black tracking-[-0.05em] text-white sm:text-5xl">
              Dashboard
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-7 text-white/72 sm:text-lg">
              See what needs attention across applications, pending reviews, and referral outreach
              without the internal run telemetry.
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
              to="/tracker"
            >
              Open Tracker
            </Link>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-[1.5rem] border border-white/10 bg-white/8 p-5 backdrop-blur-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-white/60">Submitted Applications</p>
            <p className="mt-3 text-4xl font-black tracking-[-0.05em] text-white">
              {formatNumber(model.summary.submittedApplications)}
            </p>
            <p className="mt-2 text-sm text-white/68">
              {formatNumber(model.summary.trackedApplications)} total tracker items
            </p>
          </div>

          <div className="rounded-[1.5rem] border border-white/10 bg-white/8 p-5 backdrop-blur-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-white/60">Jobs To Review</p>
            <p className="mt-3 text-4xl font-black tracking-[-0.05em] text-white">
              {formatNumber(model.summary.waitingReviewCount)}
            </p>
            <p className="mt-2 text-sm text-white/68">
              Waiting in runs for your decision
            </p>
          </div>

          <div className="rounded-[1.5rem] border border-white/10 bg-white/8 p-5 backdrop-blur-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-white/60">Interviews</p>
            <p className="mt-3 text-4xl font-black tracking-[-0.05em] text-white">
              {formatNumber(model.summary.interviewing)}
            </p>
            <p className="mt-2 text-sm text-white/68">
              {formatNumber(model.summary.heardBackCount)} employer responses tracked
            </p>
          </div>

          <div className="rounded-[1.5rem] border border-white/10 bg-white/8 p-5 backdrop-blur-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-white/60">People To Contact</p>
            <p className="mt-3 text-4xl font-black tracking-[-0.05em] text-white">
              {formatNumber(model.summary.notContacted)}
            </p>
            <p className="mt-2 text-sm text-white/68">
              {formatNumber(model.summary.referralOffered)} referral offers so far
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function FocusPanel({ items }) {
  return (
    <DashboardPanel>
      <PanelHeader
        eyebrow="Today"
        title="Your Action Plan"
        description="Prioritized work that will move your search forward fastest."
      />

      <div className="mt-8 grid gap-4 md:grid-cols-2">
        {items.map((item) => (
          <article className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-5" key={item.title}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">{item.title}</p>
                <p className={["mt-3 text-4xl font-black tracking-tight", item.accentClass].join(" ")}>
                  {formatNumber(item.value)}
                </p>
              </div>
              <span className={["material-symbols-outlined text-2xl", item.accentClass].join(" ")}>
                {item.icon}
              </span>
            </div>

            <p className="mt-3 text-sm leading-7 text-on-surface-variant">{item.detail}</p>

            <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
              {item.priority ? (
                <span className={["rounded-full bg-surface-container-low px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em]", item.accentClass].join(" ")}>
                  {item.priority} priority
                </span>
              ) : <span />}
              <Link
                className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-4 py-2 text-sm font-semibold text-primary transition-colors hover:bg-primary/20"
                to={item.to}
              >
                {item.actionLabel}
                <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
              </Link>
            </div>
          </article>
        ))}
      </div>
    </DashboardPanel>
  );
}

function SearchFunnelPanel({ funnel }) {
  const stages = Array.isArray(funnel?.stages) ? funnel.stages : [];
  const maxValue = Math.max(1, ...stages.map((stage) => getNumericValue(stage?.value)));

  return (
    <DashboardPanel>
      <PanelHeader
        eyebrow="Progress"
        title="Job Search Funnel"
        description="Follow the path from discovered roles to submitted applications, employer responses, interviews, and offers."
      />

      {stages.length ? (
        <div className="mt-8 space-y-5">
          {stages.map((stage, index) => {
            const value = getNumericValue(stage?.value);
            return (
              <div key={stage.label}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span
                      aria-hidden="true"
                      className="h-3 w-3 rounded-full"
                      style={{ backgroundColor: String(stage.color || "#38bdf8") }}
                    />
                    <span className="text-sm font-semibold text-on-surface">{stage.label}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    {index > 0 ? (
                      <span className="text-xs font-medium text-on-surface-variant">
                        {formatPercent(stage.conversionRate)} from prior stage
                      </span>
                    ) : null}
                    <span className="text-lg font-black text-on-surface">{formatNumber(value)}</span>
                  </div>
                </div>
                <div className="mt-2 h-3 overflow-hidden rounded-full bg-surface-container-low">
                  <div
                    className="h-full rounded-full transition-[width]"
                    style={{
                      backgroundColor: String(stage.color || "#38bdf8"),
                      width: value ? `${Math.max(5, (value / maxValue) * 100)}%` : "0%",
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="mt-8">
          <EmptyChartState message="Run discovery and update your tracker to build the search funnel." />
        </div>
      )}
    </DashboardPanel>
  );
}

function weeklyDelta(current, previous) {
  const difference = getNumericValue(current) - getNumericValue(previous);
  if (difference > 0) {
    return { label: `+${formatNumber(difference)} vs prior week`, className: "text-emerald-600" };
  }
  if (difference < 0) {
    return { label: `${formatNumber(difference)} vs prior week`, className: "text-amber-600" };
  }
  return { label: "No change vs prior week", className: "text-on-surface-variant" };
}

function WeeklySummaryPanel({ weeklySummary, dataQuality }) {
  const current = weeklySummary?.current || {};
  const previous = weeklySummary?.previous || {};
  const metrics = [
    { key: "applications", label: "Applications", icon: "send" },
    { key: "responses", label: "Responses", icon: "mark_email_read" },
    { key: "interviews", label: "Interviews", icon: "calendar_month" },
    { key: "referralUpdates", label: "Referral Updates", icon: "group" },
  ];

  return (
    <DashboardPanel>
      <PanelHeader
        eyebrow="Momentum"
        title="Weekly Search Summary"
        description={`Meaningful activity from the last ${formatNumber(weeklySummary?.windowDays || 7)} days compared with the prior week.`}
      />

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {metrics.map((metric) => {
          const delta = weeklyDelta(current[metric.key], previous[metric.key]);
          return (
            <div className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-4" key={metric.key}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">{metric.label}</p>
                  <p className="mt-3 text-3xl font-black tracking-tight text-on-surface">
                    {formatNumber(current[metric.key])}
                  </p>
                </div>
                <span className="material-symbols-outlined text-xl text-primary">{metric.icon}</span>
              </div>
              <p className={["mt-2 text-sm font-medium", delta.className].join(" ")}>{delta.label}</p>
            </div>
          );
        })}
      </div>

      <div className="mt-6 rounded-[1.35rem] border border-outline-variant/15 bg-surface p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">Dashboard Confidence</p>
            <p className="mt-2 text-3xl font-black tracking-tight text-on-surface">
              {formatNumber(dataQuality?.confidence)}%
            </p>
          </div>
          <Link
            className="rounded-full bg-primary/10 px-4 py-2 text-sm font-semibold text-primary transition-colors hover:bg-primary/20"
            to="/tracker"
          >
            Improve data
          </Link>
        </div>
        <p className="mt-3 text-sm leading-7 text-on-surface-variant">
          {dataQuality?.issueCount
            ? `${formatNumber(dataQuality.issueCount)} missing or unclear tracker fields currently reduce reporting confidence.`
            : "Tracker statuses, dates, and source attribution are complete."}
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl bg-surface-container-low p-3 text-sm text-on-surface-variant">
            <strong className="text-on-surface">{formatNumber(dataQuality?.unknownStatuses)}</strong> unknown statuses
          </div>
          <div className="rounded-xl bg-surface-container-low p-3 text-sm text-on-surface-variant">
            <strong className="text-on-surface">{formatNumber(dataQuality?.missingApplicationDates)}</strong> missing dates
          </div>
          <div className="rounded-xl bg-surface-container-low p-3 text-sm text-on-surface-variant">
            <strong className="text-on-surface">{formatNumber(dataQuality?.missingSources)}</strong> missing sources
          </div>
        </div>
      </div>
    </DashboardPanel>
  );
}

function PipelineAgingPanel({ stages }) {
  return (
    <DashboardPanel>
      <PanelHeader
        action={(
          <Link
            className="rounded-full bg-primary/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-primary transition-colors hover:bg-primary/20"
            to="/tracker"
          >
            Open tracker
          </Link>
        )}
        eyebrow="Follow-Up"
        title="Pipeline Aging"
        description="Spot applications and interviews that have remained in one stage long enough to need attention."
      />

      <div className="mt-8 space-y-4">
        {(stages || []).map((stage) => (
          <article className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-5" key={stage.label}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-on-surface">{stage.label}</p>
                <p className="mt-2 text-sm leading-6 text-on-surface-variant">{stage.detail}</p>
              </div>
              <p className="text-3xl font-black tracking-tight text-on-surface">{formatNumber(stage.count)}</p>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl bg-surface-container-low p-3 text-sm text-on-surface-variant">
                <strong className={stage.staleCount ? "text-amber-600" : "text-on-surface"}>
                  {formatNumber(stage.staleCount)}
                </strong>{" "}
                need attention after {formatNumber(stage.staleAfterDays)} days
              </div>
              <div className="rounded-xl bg-surface-container-low p-3 text-sm text-on-surface-variant">
                Median age: <strong className="text-on-surface">{formatNumber(stage.medianAgeDays)} days</strong>
              </div>
            </div>
          </article>
        ))}
      </div>
    </DashboardPanel>
  );
}

function SourceEffectivenessPanel({ sources }) {
  return (
    <DashboardPanel>
      <PanelHeader
        eyebrow="Strategy"
        title="Source Effectiveness"
        description="Compare sources by submitted applications and employer responses, not only by the number of jobs found."
      />

      {sources?.length ? (
        <div className="mt-8 overflow-x-auto">
          <div className="min-w-[42rem] space-y-3">
            <div className="grid grid-cols-[minmax(11rem,1fr)_repeat(4,5.5rem)] gap-3 px-4 text-xs font-semibold uppercase tracking-[0.15em] text-on-surface-variant">
              <span>Source</span>
              <span className="text-right">Applied</span>
              <span className="text-right">Responses</span>
              <span className="text-right">Interviews</span>
              <span className="text-right">Response rate</span>
            </div>
            {sources.map((source) => (
              <div
                className="grid grid-cols-[minmax(11rem,1fr)_repeat(4,5.5rem)] items-center gap-3 rounded-[1.2rem] border border-outline-variant/15 bg-surface px-4 py-4"
                key={source.label}
              >
                <div>
                  <p className="font-semibold text-on-surface">{source.label}</p>
                  <p className="mt-1 text-xs text-on-surface-variant">{formatNumber(source.tracked)} tracker items</p>
                </div>
                <span className="text-right font-semibold text-on-surface">{formatNumber(source.applied)}</span>
                <span className="text-right font-semibold text-on-surface">{formatNumber(source.responses)}</span>
                <span className="text-right font-semibold text-on-surface">{formatNumber(source.interviews)}</span>
                <span className="text-right font-black text-primary">{formatPercent(source.responseRate)}</span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="mt-8">
          <EmptyChartState message="Source performance will appear after applications are tracked with source attribution." />
        </div>
      )}
    </DashboardPanel>
  );
}

function ApplicationProgressPanel({ outcomes, summary }) {
  const visibleSegments = outcomes.segments.filter((segment) => segment.value > 0);

  return (
    <DashboardPanel>
      <PanelHeader
        action={(
          <Link
            className="rounded-full bg-primary/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-primary transition-colors hover:bg-primary/20"
            to="/tracker"
          >
            Open tracker
          </Link>
        )}
        eyebrow="Applications"
        title="Application Progress"
        description="Everything already in your tracker, including imported email confirmations and manual status updates."
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
                    data={visibleSegments}
                    dataKey="value"
                    innerRadius={74}
                    outerRadius={112}
                    paddingAngle={2}
                  >
                    {visibleSegments.map((segment) => (
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
            <EmptyChartState message="Tracked applications will appear here once they move into the tracker." />
          )}
        </div>

        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <MetricTile
              detail="Applied, interviewing, and offer stages combined."
              label="Active"
              value={formatNumber(summary.activeApplications)}
            />
            <MetricTile
              detail={`${formatPercent(summary.heardBackRate)} of known statuses heard back`}
              label="Heard Back"
              value={formatNumber(summary.heardBackCount)}
            />
            <MetricTile
              accentClass="text-emerald-600"
              detail="Offers currently saved in the tracker."
              label="Offers"
              value={formatNumber(summary.offers)}
            />
            <MetricTile
              accentClass={summary.unknownApplications ? "text-amber-600" : "text-on-surface"}
              detail="Rows that still need a clearer application status."
              label="Unknown"
              value={formatNumber(summary.unknownApplications)}
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

function ReferralOutreachPanel({ referrals, summary }) {
  const sourceScaleMax = Math.max(
    1,
    ...referrals.contactSources.map((source) => getNumericValue(source?.value)),
  );

  return (
    <DashboardPanel>
      <PanelHeader
        action={(
          <Link
            className="rounded-full bg-primary/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-primary transition-colors hover:bg-primary/20"
            to="/referrals"
          >
            Open referrals
          </Link>
        )}
        eyebrow="Referrals"
        title="Referral Follow-Up"
        description="Keep warm contacts moving forward and spot where you still need to send a first message."
      />

      <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricTile
          detail="All referral contacts currently saved."
          label="Contacts"
          value={formatNumber(referrals.totalContacts)}
        />
        <MetricTile
          accentClass={summary.notContacted ? "text-sky-600" : "text-on-surface"}
          detail="Saved contacts still waiting for outreach."
          label="Not Contacted"
          value={formatNumber(summary.notContacted)}
        />
        <MetricTile
          accentClass={summary.replied ? "text-teal-600" : "text-on-surface"}
          detail="Contacts who already replied."
          label="Replied"
          value={formatNumber(summary.replied)}
        />
        <MetricTile
          accentClass={summary.referralOffered ? "text-emerald-600" : "text-on-surface"}
          detail={`${formatNumber(referrals.noReferralCount)} ended with no referral`}
          label="Referral Offered"
          value={formatNumber(summary.referralOffered)}
        />
      </div>

      <div className="mt-8 grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <div className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-4">
          <div className="mb-4 flex items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">Outreach Funnel</p>
              <p className="mt-1 text-sm text-on-surface-variant">Counts from saved outreach statuses.</p>
            </div>
            <span className="rounded-full bg-surface-container-low px-3 py-1 text-xs font-semibold text-on-surface-variant">
              {formatNumber(referrals.trackedOutreachItems)} updates
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
            <EmptyChartState message="Add or import contacts to start tracking referral outreach." />
          )}
        </div>

        <div className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-4">
          <div className="mb-4">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">Contact Sources</p>
            <p className="mt-1 text-sm text-on-surface-variant">
              A quick look at where your referral pool currently comes from.
            </p>
          </div>

          {referrals.contactSources.length ? (
            <div className="space-y-4">
              {referrals.contactSources.map((source) => {
                const sourceValue = getNumericValue(source?.value);
                return (
                  <div key={source.label}>
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <span
                          aria-hidden="true"
                          className="h-3 w-3 rounded-full"
                          style={{ backgroundColor: String(source.color || "#38bdf8") }}
                        />
                        <span className="text-sm text-on-surface">{source.label}</span>
                      </div>
                      <span className="text-sm font-semibold text-on-surface">{formatNumber(sourceValue)}</span>
                    </div>
                    <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-surface-container-low">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.max(6, (sourceValue / sourceScaleMax) * 100)}%`,
                          backgroundColor: String(source.color || "#38bdf8"),
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="rounded-[1.15rem] border border-dashed border-outline-variant/20 bg-surface-container-low p-6 text-sm text-on-surface-variant">
              No referral contacts are saved yet.
            </div>
          )}
        </div>
      </div>
    </DashboardPanel>
  );
}

export default function DashboardPage() {
  const { error: sessionError, isConnected, request, status } = useSession();
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
    const guidance = status === "error"
      ? (sessionError || "The frontend could not authenticate with the backend API.")
      : "Sign in and let the frontend finish the backend session check.";
    return (
      <p className="sr-only" role="status">
        {guidance}
      </p>
    );
  }

  if (loading && !data) {
    return <DashboardSkeleton />;
  }

  if (error && !data) {
    return <DashboardError error={error} onRetry={refresh} />;
  }

  const model = buildUserDashboardModel(data || {});

  return (
    <div className="space-y-8">
      <DashboardHeader model={model} onRefresh={refresh} refreshing={loading} />

      {error ? (
        <section className="rounded-2xl border border-error/20 bg-error/5 px-5 py-4 text-sm text-error">
          {error}
        </section>
      ) : null}

      <FocusPanel items={model.focusItems} />

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <SearchFunnelPanel funnel={model.insights.funnel} />
        <WeeklySummaryPanel
          dataQuality={model.insights.dataQuality}
          weeklySummary={model.insights.weeklySummary}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <PipelineAgingPanel stages={model.insights.pipelineAging} />
        <SourceEffectivenessPanel sources={model.insights.sourceEffectiveness} />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <ApplicationProgressPanel outcomes={model.outcomes} summary={model.summary} />
        <ReferralOutreachPanel referrals={model.referrals} summary={model.summary} />
      </div>
    </div>
  );
}
