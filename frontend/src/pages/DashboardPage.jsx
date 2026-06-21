import { useEffect } from "react";
import { Link } from "react-router-dom";
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
const ACTIVE_RUN_STATUSES = ["planned", "queued", "running", "cancel_requested"];

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
  roleStrategy: {
    summary: "",
    totalApplications: 0,
    averageResponseRate: 0,
    roles: [],
  },
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
    roleStrategy: {
      summary: String(insights.roleStrategy?.summary || ""),
      totalApplications: getNumericValue(insights.roleStrategy?.totalApplications),
      averageResponseRate: getNumericValue(insights.roleStrategy?.averageResponseRate),
      roles: Array.isArray(insights.roleStrategy?.roles)
        ? insights.roleStrategy.roles.map((role) => ({
          ...role,
          applications: getNumericValue(role?.applications),
          applicationShare: getNumericValue(role?.applicationShare),
          responses: getNumericValue(role?.responses),
          interviews: getNumericValue(role?.interviews),
          offers: getNumericValue(role?.offers),
          rejected: getNumericValue(role?.rejected),
          withdrawn: getNumericValue(role?.withdrawn),
          responseRate: getNumericValue(role?.responseRate),
          interviewRate: getNumericValue(role?.interviewRate),
        }))
        : [],
    },
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

function hasWeeklyActivity(weeklySummary) {
  const keys = ["applications", "responses", "interviews", "offers", "referralUpdates"];
  const current = weeklySummary?.current || {};
  const previous = weeklySummary?.previous || {};
  return keys.some((key) => getNumericValue(current[key]) > 0 || getNumericValue(previous[key]) > 0);
}

function hasDataQualityIssues(dataQuality) {
  return getNumericValue(dataQuality?.issueCount) > 0;
}

function hasActionableAging(stages) {
  return Array.isArray(stages)
    && stages.some((stage) => getNumericValue(stage?.count) > 0 || getNumericValue(stage?.staleCount) > 0);
}

function hasRoleStrategy(roleStrategy) {
  return Array.isArray(roleStrategy?.roles)
    && roleStrategy.roles.some((role) => getNumericValue(role?.applications) > 0);
}

function meaningfulSources(sources) {
  return Array.isArray(sources)
    ? sources.filter((source) => (
      getNumericValue(source?.applied)
      + getNumericValue(source?.responses)
      + getNumericValue(source?.interviews)
      + getNumericValue(source?.offers)
    ) > 0)
    : [];
}

function buildUserDashboardModel(payload) {
  const outcomes = normalizeOutcomes(payload?.analytics?.outcomes || EMPTY_OUTCOMES);
  const referrals = normalizeReferrals(payload?.analytics?.referrals || EMPTY_REFERRALS);
  const insights = normalizeCandidateInsights(payload?.analytics?.candidateInsights);

  const interviewing = findValueByLabel(outcomes.segments, "Interviewing");
  const waitingReviewCount = findValueByLabel(payload?.cards, "Jobs Waiting Review");

  const notContacted = findValueByLabel(referrals.outreachFunnel, "Not contacted");

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

function EmptyChartState({ message }) {
  return (
    <div className="flex h-full min-h-48 items-center justify-center rounded-[1.35rem] border border-dashed border-outline-variant/20 bg-surface text-sm text-on-surface-variant">
      {message}
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

function DashboardHeader({ onRefresh, refreshing }) {
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
              See what needs attention today, what is stuck, and which sources are actually moving
              the search forward.
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

function DashboardLoadingNotice() {
  return (
    <section className="flex items-center gap-3 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest px-5 py-4 text-sm text-on-surface-variant">
      <span className="material-symbols-outlined animate-spin text-primary">progress_activity</span>
      Loading dashboard data...
    </section>
  );
}

function roleRecommendationClass(recommendation) {
  if (recommendation === "Increase focus") {
    return "bg-emerald-500/10 text-emerald-600";
  }
  if (recommendation === "Reduce effort") {
    return "bg-amber-500/10 text-amber-600";
  }
  if (recommendation === "Needs cleaner data") {
    return "bg-rose-500/10 text-rose-600";
  }
  if (recommendation === "Test more") {
    return "bg-sky-500/10 text-sky-600";
  }
  return "bg-primary/10 text-primary";
}

function RoleStrategyPanel({ roleStrategy }) {
  const roles = Array.isArray(roleStrategy?.roles) ? roleStrategy.roles : [];
  const topRole = roles[0];
  const strongestRole = roles
    .filter((role) => getNumericValue(role?.responses) > 0)
    .sort((first, second) => (
      getNumericValue(second.responseRate) - getNumericValue(first.responseRate)
      || getNumericValue(second.responses) - getNumericValue(first.responses)
      || getNumericValue(second.applications) - getNumericValue(first.applications)
    ))[0];
  const attentionRole = roles.find((role) => role.recommendation === "Reduce effort" || role.recommendation === "Needs cleaner data");

  return (
    <DashboardPanel>
      <PanelHeader
        eyebrow="Strategy"
        title="Role Strategy"
        description="Compare application concentration and outcomes by role target so your next batch goes where the search is working."
      />

      <div className="mt-8 grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">Executive Summary</p>
          <p className="mt-3 text-sm leading-7 text-on-surface-variant">
            {roleStrategy?.summary || "Role strategy will appear after applications have role labels and outcomes."}
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
          <div className="rounded-[1.15rem] bg-surface p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-on-surface-variant">Top Volume</p>
            <p className="mt-2 text-sm font-semibold text-on-surface">{topRole?.label || "No role yet"}</p>
            <p className="mt-1 text-xs text-on-surface-variant">{formatPercent(topRole?.applicationShare || 0)} of applications</p>
          </div>
          <div className="rounded-[1.15rem] bg-surface p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-on-surface-variant">Best Response</p>
            <p className="mt-2 text-sm font-semibold text-on-surface">{strongestRole?.label || "No responses yet"}</p>
            <p className="mt-1 text-xs text-on-surface-variant">{formatPercent(strongestRole?.responseRate || 0)} response rate</p>
          </div>
          <div className="rounded-[1.15rem] bg-surface p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-on-surface-variant">Watch</p>
            <p className="mt-2 text-sm font-semibold text-on-surface">{attentionRole?.label || "No role flagged"}</p>
            <p className="mt-1 text-xs text-on-surface-variant">{attentionRole?.recommendation || "Keep current focus"}</p>
          </div>
        </div>
      </div>

      <div className="mt-8 hidden overflow-x-auto md:block">
        <div className="min-w-[52rem] space-y-3">
          <div className="grid grid-cols-[minmax(12rem,1fr)_5rem_repeat(4,5.5rem)_8rem] gap-3 px-4 text-xs font-semibold uppercase tracking-[0.15em] text-on-surface-variant">
            <span>Role Target</span>
            <span className="text-right">Share</span>
            <span className="text-right">Apps</span>
            <span className="text-right">Responses</span>
            <span className="text-right">Interviews</span>
            <span className="text-right">Offers</span>
            <span>Recommendation</span>
          </div>
          {roles.map((role) => (
            <div
              className="grid grid-cols-[minmax(12rem,1fr)_5rem_repeat(4,5.5rem)_8rem] items-center gap-3 rounded-[1.2rem] border border-outline-variant/15 bg-surface px-4 py-4"
              key={role.label}
            >
              <div>
                <p className="font-semibold text-on-surface">{role.label}</p>
                <p className="mt-1 text-xs text-on-surface-variant">{formatPercent(role.responseRate)} response rate</p>
              </div>
              <span className="text-right font-semibold text-on-surface">{formatPercent(role.applicationShare)}</span>
              <span className="text-right font-semibold text-on-surface">{formatNumber(role.applications)}</span>
              <span className="text-right font-semibold text-on-surface">{formatNumber(role.responses)}</span>
              <span className="text-right font-semibold text-on-surface">{formatNumber(role.interviews)}</span>
              <span className="text-right font-semibold text-on-surface">{formatNumber(role.offers)}</span>
              <span className={["w-fit rounded-full px-3 py-1 text-xs font-semibold", roleRecommendationClass(role.recommendation)].join(" ")}>
                {role.recommendation}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-8 grid gap-4 md:hidden">
        {roles.map((role) => (
          <article className="rounded-[1.2rem] border border-outline-variant/15 bg-surface p-4" key={role.label}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="font-semibold text-on-surface">{role.label}</p>
                <p className="mt-1 text-xs text-on-surface-variant">{formatPercent(role.applicationShare)} of applications</p>
              </div>
              <span className={["rounded-full px-3 py-1 text-xs font-semibold", roleRecommendationClass(role.recommendation)].join(" ")}>
                {role.recommendation}
              </span>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 text-sm text-on-surface-variant">
              <span><strong className="text-on-surface">{formatNumber(role.applications)}</strong> applications</span>
              <span><strong className="text-on-surface">{formatNumber(role.responses)}</strong> responses</span>
              <span><strong className="text-on-surface">{formatNumber(role.interviews)}</strong> interviews</span>
              <span><strong className="text-on-surface">{formatNumber(role.offers)}</strong> offers</span>
            </div>
          </article>
        ))}
      </div>
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

function WeeklySummaryPanel({ weeklySummary }) {
  const current = weeklySummary?.current || {};
  const previous = weeklySummary?.previous || {};
  const metrics = [
    { key: "applications", label: "Applications", icon: "send" },
    { key: "responses", label: "Responses", icon: "mark_email_read" },
    { key: "interviews", label: "Interviews", icon: "calendar_month" },
    { key: "referralUpdates", label: "Referral Updates", icon: "group" },
  ].filter((metric) => (
    getNumericValue(current[metric.key]) > 0 || getNumericValue(previous[metric.key]) > 0
  ));

  return (
    <DashboardPanel>
      <PanelHeader
        eyebrow="Momentum"
        title="Weekly Search Summary"
        description={`Meaningful activity from the last ${formatNumber(weeklySummary?.windowDays || 7)} days compared with the prior week.`}
      />

      {metrics.length ? (
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
      ) : (
        <div className="mt-8">
          <EmptyChartState message="No meaningful application, response, interview, or referral activity in the last two weeks." />
        </div>
      )}
    </DashboardPanel>
  );
}

function DataQualityPanel({ dataQuality }) {
  return (
    <DashboardPanel>
      <div className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">Data To Fix</p>
            <p className="mt-2 text-3xl font-black tracking-tight text-on-surface">
              {formatNumber(dataQuality?.issueCount)}
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
          Missing or unclear tracker fields currently reduce reporting confidence to{" "}
          <strong className="text-on-surface">{formatNumber(dataQuality?.confidence)}%</strong>.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {getNumericValue(dataQuality?.unknownStatuses) ? (
            <div className="rounded-xl bg-surface-container-low p-3 text-sm text-on-surface-variant">
              <strong className="text-on-surface">{formatNumber(dataQuality?.unknownStatuses)}</strong> unknown statuses
            </div>
          ) : null}
          {getNumericValue(dataQuality?.missingApplicationDates) ? (
            <div className="rounded-xl bg-surface-container-low p-3 text-sm text-on-surface-variant">
              <strong className="text-on-surface">{formatNumber(dataQuality?.missingApplicationDates)}</strong> missing dates
            </div>
          ) : null}
          {getNumericValue(dataQuality?.missingSources) ? (
            <div className="rounded-xl bg-surface-container-low p-3 text-sm text-on-surface-variant">
              <strong className="text-on-surface">{formatNumber(dataQuality?.missingSources)}</strong> missing sources
            </div>
          ) : null}
        </div>
      </div>
    </DashboardPanel>
  );
}

function PipelineAgingPanel({ stages }) {
  const visibleStages = Array.isArray(stages)
    ? stages.filter((stage) => getNumericValue(stage?.count) > 0 || getNumericValue(stage?.staleCount) > 0)
    : [];

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
        {visibleStages.map((stage) => (
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
  const visibleSources = meaningfulSources(sources);

  return (
    <DashboardPanel>
      <PanelHeader
        eyebrow="Strategy"
        title="Source Effectiveness"
        description="Compare sources by submitted applications and employer responses, not only by the number of jobs found."
      />

      {visibleSources.length ? (
        <div className="mt-8 overflow-x-auto">
          <div className="min-w-[42rem] space-y-3">
            <div className="grid grid-cols-[minmax(11rem,1fr)_repeat(4,5.5rem)] gap-3 px-4 text-xs font-semibold uppercase tracking-[0.15em] text-on-surface-variant">
              <span>Source</span>
              <span className="text-right">Applied</span>
              <span className="text-right">Responses</span>
              <span className="text-right">Interviews</span>
              <span className="text-right">Response rate</span>
            </div>
            {visibleSources.map((source) => (
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
          <EmptyChartState message="Source performance will appear after a source produces submitted applications or responses." />
        </div>
      )}
    </DashboardPanel>
  );
}

export default function DashboardPage() {
  const { error: sessionError, isConnected, request, status } = useSession();
  const { data, loading, error, refresh } = useApiResource(() => loadDashboardPayload(request), [request], {
    cacheKey: "dashboard",
    staleMs: 30000,
    backgroundRefresh: true,
  });
  const hasActiveDashboardWork = Boolean(
    (data?.recent_runs || []).some((run) => ACTIVE_RUN_STATUSES.includes(String(run.status || "").trim()))
    || (data?.cards || []).some((card) =>
      ["Queued Runs", "Running Workers"].includes(String(card?.label || "").trim())
      && Number(card?.value || 0) > 0
    ),
  );

  useEffect(() => {
    if (!isConnected || !hasActiveDashboardWork) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      refresh().catch(() => undefined);
    }, 30000);
    return () => window.clearInterval(intervalId);
  }, [hasActiveDashboardWork, isConnected, refresh]);

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

  if (error && !data) {
    return <DashboardError error={error} onRetry={refresh} />;
  }

  const model = buildUserDashboardModel(data || {});
  const showWeeklySummary = hasWeeklyActivity(model.insights.weeklySummary);
  const showDataQuality = hasDataQualityIssues(model.insights.dataQuality);
  const showPipelineAging = hasActionableAging(model.insights.pipelineAging);
  const showRoleStrategy = hasRoleStrategy(model.insights.roleStrategy);
  const showSourceEffectiveness = meaningfulSources(model.insights.sourceEffectiveness).length > 0;

  return (
    <div className="space-y-8">
      <DashboardHeader onRefresh={refresh} refreshing={loading} />

      {loading && !data ? <DashboardLoadingNotice /> : null}

      {error ? (
        <section className="rounded-2xl border border-error/20 bg-error/5 px-5 py-4 text-sm text-error">
          {error}
        </section>
      ) : null}

      <FocusPanel items={model.focusItems} />

      <SearchFunnelPanel funnel={model.insights.funnel} />

      {showRoleStrategy ? (
        <RoleStrategyPanel roleStrategy={model.insights.roleStrategy} />
      ) : null}

      {showWeeklySummary || showDataQuality ? (
        <div className={[
          "grid gap-6",
          showWeeklySummary && showDataQuality ? "xl:grid-cols-[1.05fr_0.95fr]" : "",
        ].join(" ")}>
          {showWeeklySummary ? (
            <WeeklySummaryPanel weeklySummary={model.insights.weeklySummary} />
          ) : null}
          {showDataQuality ? (
            <DataQualityPanel dataQuality={model.insights.dataQuality} />
          ) : null}
        </div>
      ) : null}

      {showPipelineAging || showSourceEffectiveness ? (
        <div className={[
          "grid gap-6",
          showPipelineAging && showSourceEffectiveness ? "xl:grid-cols-[0.85fr_1.15fr]" : "",
        ].join(" ")}>
          {showPipelineAging ? (
            <PipelineAgingPanel stages={model.insights.pipelineAging} />
          ) : null}
          {showSourceEffectiveness ? (
            <SourceEffectivenessPanel sources={model.insights.sourceEffectiveness} />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
