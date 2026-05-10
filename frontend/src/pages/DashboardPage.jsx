import { Link } from "react-router-dom";

const DASHBOARD_ANALYTICS_PREVIEW = {
  periodLabel: "Last 12 weeks",
  appliedJobs: 154,
  activePipeline: 36,
  interviewsAndOffers: 37,
  acceptanceRate: 24,
  rejectionRate: 47,
  averageReplyDays: 6.2,
  last30DaysApplied: 42,
  momentum: [
    { label: "Feb", applications: 8, interviews: 1 },
    { label: "Mar", applications: 11, interviews: 2 },
    { label: "Apr", applications: 13, interviews: 3 },
    { label: "May", applications: 15, interviews: 4 },
    { label: "Jun", applications: 12, interviews: 3 },
    { label: "Jul", applications: 14, interviews: 4 },
    { label: "Aug", applications: 18, interviews: 5 },
    { label: "Sep", applications: 16, interviews: 4 },
    { label: "Oct", applications: 12, interviews: 3 },
    { label: "Nov", applications: 14, interviews: 3 },
    { label: "Dec", applications: 10, interviews: 2 },
    { label: "Jan", applications: 11, interviews: 3 },
  ],
  outcomes: [
    { label: "Accepted / progressing", value: 37, color: "#14b8a6" },
    { label: "Rejected", value: 72, color: "#f97316" },
    { label: "Awaiting reply", value: 36, color: "#38bdf8" },
    { label: "Withdrawn", value: 9, color: "#94a3b8" },
  ],
  funnel: [
    { label: "Jobs sourced", value: 462, color: "#0f766e" },
    { label: "Shortlisted", value: 244, color: "#14b8a6" },
    { label: "Applied", value: 154, color: "#38bdf8" },
    { label: "Interviewing", value: 31, color: "#f59e0b" },
    { label: "Offers", value: 6, color: "#22c55e" },
  ],
  dataSources: ["Tracker status", "Review decisions", "Job descriptions", "CV skill artifacts"],
  roles: [
    {
      role: "Product Analyst",
      focus: "Best-converting lane right now",
      color: "#14b8a6",
      applications: 52,
      positive: 15,
      pending: 17,
      rejected: 20,
      skills: [
        { name: "SQL", count: 32 },
        { name: "A/B Testing", count: 26 },
        { name: "Tableau", count: 23 },
        { name: "Python", count: 18 },
        { name: "Stakeholder Management", count: 15 },
      ],
    },
    {
      role: "Growth Analyst",
      focus: "Good volume, needs tighter targeting",
      color: "#38bdf8",
      applications: 48,
      positive: 11,
      pending: 10,
      rejected: 27,
      skills: [
        { name: "SQL", count: 29 },
        { name: "Experimentation", count: 24 },
        { name: "GA4", count: 20 },
        { name: "Looker", count: 17 },
        { name: "Attribution", count: 14 },
      ],
    },
    {
      role: "Revenue Operations Analyst",
      focus: "Lowest yield, strongest tooling demand",
      color: "#f59e0b",
      applications: 54,
      positive: 11,
      pending: 9,
      rejected: 34,
      skills: [
        { name: "Salesforce", count: 27 },
        { name: "Excel", count: 24 },
        { name: "SQL", count: 21 },
        { name: "Forecasting", count: 18 },
        { name: "HubSpot", count: 13 },
      ],
    },
  ],
  cardTrends: {
    appliedJobs: [10, 12, 14, 11, 17, 18, 20],
    activePipeline: [24, 27, 25, 29, 31, 34, 36],
    interviewsAndOffers: [2, 3, 4, 4, 5, 6, 7],
    averageReplyDays: [9, 8, 8, 7, 7, 6, 6],
  },
};

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatPercent(value) {
  return `${Math.round(value)}%`;
}

function formatDays(value) {
  return `${value.toFixed(1)}d`;
}

function getPositiveRate(role) {
  if (!role.applications) {
    return 0;
  }
  return (role.positive / role.applications) * 100;
}

function aggregateSkillDemand(roles) {
  const totals = new Map();
  for (const role of roles) {
    for (const skill of role.skills) {
      totals.set(skill.name, (totals.get(skill.name) || 0) + skill.count);
    }
  }
  return Array.from(totals.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((left, right) => right.count - left.count);
}

function buildChartPoints(values, width, height, padding) {
  const maxValue = Math.max(...values, 1);
  const innerWidth = width - padding * 2;
  const innerHeight = height - padding * 2;

  return values.map((value, index) => {
    const x =
      values.length === 1 ? width / 2 : padding + (index * innerWidth) / Math.max(values.length - 1, 1);
    const y = height - padding - (value / maxValue) * innerHeight;
    return { x, y, value };
  });
}

function buildLinePath(points) {
  return points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
}

function buildAreaPath(points, height, padding) {
  if (!points.length) {
    return "";
  }
  return [
    buildLinePath(points),
    `L ${points[points.length - 1].x} ${height - padding}`,
    `L ${points[0].x} ${height - padding}`,
    "Z",
  ].join(" ");
}

function buildExecutiveSummary(data) {
  const rankedRoles = [...data.roles].sort((left, right) => getPositiveRate(right) - getPositiveRate(left));
  const bestRole = rankedRoles[0];
  const weakestRole = rankedRoles[rankedRoles.length - 1];
  const skillDemand = aggregateSkillDemand(data.roles);
  const topSkill = skillDemand[0];
  const secondSkill = skillDemand[1];
  const awaitingReply = data.outcomes.find((segment) => segment.label === "Awaiting reply")?.value || 0;

  return {
    headline: `${bestRole.role} is the clearest lane to double down on.`,
    body: `${formatPercent(getPositiveRate(bestRole))} of applications in this lane are moving forward, and ${topSkill.name} is the most repeated skill signal across your target roles.`,
    actions: [
      {
        icon: "trending_up",
        title: `Increase volume on ${bestRole.role}`,
        detail: `It is returning ${bestRole.positive} positive signals from ${bestRole.applications} tracked applications.`,
      },
      {
        icon: "auto_awesome",
        title: `Push ${topSkill.name} and ${secondSkill.name} higher in your CV`,
        detail: "They appear most often in job descriptions and should be visible in your headline, skills block, and first experience bullets.",
      },
      {
        icon: "filter_alt",
        title: `Tighten targeting for ${weakestRole.role}`,
        detail: `${weakestRole.rejected} rejections suggest this lane needs better filtering or deeper tailoring before more volume goes out.`,
      },
      {
        icon: "mail",
        title: "Follow up on slow-moving applications",
        detail: `${awaitingReply} applications are still in play, which is enough volume to justify a follow-up pass on older submissions.`,
      },
    ],
  };
}

function AnalyticsCard({ children, className = "" }) {
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

function MiniBarStrip({ values, color }) {
  const maxValue = Math.max(...values, 1);

  return (
    <div className="mt-4 flex items-end gap-1.5">
      {values.map((value, index) => {
        const ratio = value / maxValue;
        return (
          <span
            aria-hidden="true"
            className="block w-2 rounded-full"
            key={`${color}-${index}-${value}`}
            style={{
              height: `${22 + ratio * 26}px`,
              background: color,
              opacity: 0.35 + ratio * 0.65,
            }}
          />
        );
      })}
    </div>
  );
}

function HeroTrendChart({ series }) {
  const width = 720;
  const height = 260;
  const padding = 24;
  const applicationPoints = buildChartPoints(
    series.map((item) => item.applications),
    width,
    height,
    padding,
  );
  const interviewPoints = buildChartPoints(
    series.map((item) => item.interviews),
    width,
    height,
    padding,
  );

  return (
    <div className="rounded-[1.75rem] border border-white/10 bg-white/5 p-5 backdrop-blur-sm">
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="font-headline text-xl font-bold text-white">Application Momentum</h2>
          <p className="text-sm text-white/65">Weekly applications vs. interview activity.</p>
        </div>
        <div className="flex flex-wrap gap-3 text-xs font-semibold uppercase tracking-[0.22em] text-white/65">
          <span className="inline-flex items-center gap-2">
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full bg-cyan-300" />
            Applications
          </span>
          <span className="inline-flex items-center gap-2">
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full bg-amber-300" />
            Interviews
          </span>
        </div>
      </div>

      <svg aria-hidden="true" className="h-64 w-full" viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <linearGradient id="dashboard-application-area" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="rgba(56, 189, 248, 0.55)" />
            <stop offset="100%" stopColor="rgba(56, 189, 248, 0.03)" />
          </linearGradient>
          <linearGradient id="dashboard-interview-area" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="rgba(245, 158, 11, 0.35)" />
            <stop offset="100%" stopColor="rgba(245, 158, 11, 0)" />
          </linearGradient>
        </defs>

        {Array.from({ length: 5 }).map((_, index) => {
          const y = padding + (index * (height - padding * 2)) / 4;
          return (
            <line
              key={`grid-${index}`}
              stroke="rgba(255,255,255,0.08)"
              strokeDasharray="4 8"
              x1={padding}
              x2={width - padding}
              y1={y}
              y2={y}
            />
          );
        })}

        <path d={buildAreaPath(applicationPoints, height, padding)} fill="url(#dashboard-application-area)" />
        <path d={buildAreaPath(interviewPoints, height, padding)} fill="url(#dashboard-interview-area)" />
        <path
          d={buildLinePath(applicationPoints)}
          fill="none"
          stroke="#7dd3fc"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="4"
        />
        <path
          d={buildLinePath(interviewPoints)}
          fill="none"
          stroke="#fcd34d"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="3"
        />

        {applicationPoints.map((point, index) => (
          <circle
            cx={point.x}
            cy={point.y}
            fill="#7dd3fc"
            key={`applications-point-${index}`}
            r="4.5"
            stroke="rgba(15, 23, 42, 0.9)"
            strokeWidth="2"
          />
        ))}
        {interviewPoints.map((point, index) => (
          <circle
            cx={point.x}
            cy={point.y}
            fill="#fcd34d"
            key={`interview-point-${index}`}
            r="4"
            stroke="rgba(15, 23, 42, 0.9)"
            strokeWidth="2"
          />
        ))}
      </svg>

      <div className="mt-4 grid grid-cols-4 gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-white/45 sm:grid-cols-6 xl:grid-cols-12">
        {series.map((item) => (
          <span className="truncate" key={item.label}>
            {item.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function OutcomeDonutChart({ centerLabel, centerValue, segments }) {
  const radius = 56;
  const circumference = 2 * Math.PI * radius;
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);
  let offset = 0;

  return (
    <div className="relative mx-auto h-44 w-44">
      <svg aria-hidden="true" className="h-full w-full" viewBox="0 0 160 160">
        <circle cx="80" cy="80" fill="none" r={radius} stroke="rgba(148, 163, 184, 0.18)" strokeWidth="16" />
        {segments.map((segment) => {
          const segmentLength = (segment.value / total) * circumference;
          const circle = (
            <circle
              cx="80"
              cy="80"
              fill="none"
              key={segment.label}
              r={radius}
              stroke={segment.color}
              strokeDasharray={`${segmentLength} ${circumference - segmentLength}`}
              strokeDashoffset={-offset}
              strokeLinecap="round"
              strokeWidth="16"
              transform="rotate(-90 80 80)"
            />
          );
          offset += segmentLength;
          return circle;
        })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <p className="text-3xl font-extrabold tracking-tight text-on-surface">{centerValue}</p>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">{centerLabel}</p>
      </div>
    </div>
  );
}

function FunnelChart({ stages }) {
  const maxValue = Math.max(...stages.map((stage) => stage.value), 1);

  return (
    <div className="mt-6 space-y-4">
      {stages.map((stage, index) => {
        const previousValue = stages[index - 1]?.value || stage.value;
        const conversion = Math.round((stage.value / previousValue) * 100);
        const width = 28 + (stage.value / maxValue) * 72;

        return (
          <div key={stage.label}>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span
                  aria-hidden="true"
                  className="inline-flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold text-white"
                  style={{ backgroundColor: stage.color }}
                >
                  {index + 1}
                </span>
                <div>
                  <p className="font-semibold text-on-surface">{stage.label}</p>
                  <p className="text-xs text-on-surface-variant">
                    {index === 0 ? "Starting volume" : `${conversion}% from previous stage`}
                  </p>
                </div>
              </div>
              <span className="text-sm font-semibold text-on-surface">{formatNumber(stage.value)}</span>
            </div>
            <div className="flex justify-center">
              <div
                className="h-11 rounded-2xl shadow-[inset_0_1px_0_rgba(255,255,255,0.24)]"
                style={{
                  width: `${width}%`,
                  background: `linear-gradient(90deg, ${stage.color}, rgba(255,255,255,0.82))`,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function RoleSkillCard({ role }) {
  const maxSkillCount = Math.max(...role.skills.map((skill) => skill.count), 1);

  return (
    <div className="rounded-[1.5rem] border border-outline-variant/15 bg-surface p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-on-surface-variant">{role.role}</p>
          <p className="mt-2 text-sm text-on-surface-variant">{role.focus}</p>
        </div>
        <span
          className="rounded-full px-3 py-1 text-xs font-semibold"
          style={{
            backgroundColor: `${role.color}1a`,
            color: role.color,
          }}
        >
          {formatPercent(getPositiveRate(role))} positive
        </span>
      </div>

      <div className="mt-5 flex items-center gap-3 text-xs font-medium text-on-surface-variant">
        <span>{formatNumber(role.applications)} applications</span>
        <span aria-hidden="true">/</span>
        <span>{role.positive} moved forward</span>
      </div>

      <div className="mt-6 space-y-4">
        {role.skills.map((skill) => (
          <div key={`${role.role}-${skill.name}`}>
            <div className="mb-2 flex items-center justify-between gap-4 text-sm">
              <span className="font-medium text-on-surface">{skill.name}</span>
              <span className="text-on-surface-variant">{skill.count}</span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-surface-container-low">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${(skill.count / maxSkillCount) * 100}%`,
                  background: `linear-gradient(90deg, ${role.color}, rgba(255,255,255,0.92))`,
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function RoleResponseRow({ role }) {
  const total = role.positive + role.pending + role.rejected;

  return (
    <div className="space-y-3 rounded-[1.35rem] border border-outline-variant/15 bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-semibold text-on-surface">{role.role}</p>
          <p className="text-xs text-on-surface-variant">
            {role.positive} positive / {role.pending} pending / {role.rejected} rejected
          </p>
        </div>
        <span
          className="rounded-full px-3 py-1 text-xs font-semibold"
          style={{
            backgroundColor: `${role.color}14`,
            color: role.color,
          }}
        >
          {formatPercent(getPositiveRate(role))}
        </span>
      </div>

      <div className="flex h-3 overflow-hidden rounded-full bg-surface-container-low">
        <span className="h-full bg-teal-500" style={{ width: `${(role.positive / total) * 100}%` }} />
        <span className="h-full bg-sky-400" style={{ width: `${(role.pending / total) * 100}%` }} />
        <span className="h-full bg-orange-400" style={{ width: `${(role.rejected / total) * 100}%` }} />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const analytics = DASHBOARD_ANALYTICS_PREVIEW;
  const executiveSummary = buildExecutiveSummary(analytics);

  return (
    <div className="space-y-8">
      <section className="relative overflow-hidden rounded-[2rem] bg-slate-950 px-6 py-8 text-white shadow-[0_28px_80px_rgba(15,23,42,0.28)] sm:px-8">
        <div
          aria-hidden="true"
          className="absolute inset-0 opacity-90"
          style={{
            background:
              "radial-gradient(circle at top left, rgba(20,184,166,0.34), transparent 35%), radial-gradient(circle at 80% 20%, rgba(56,189,248,0.24), transparent 28%), linear-gradient(135deg, rgba(15,23,42,1), rgba(8,47,73,0.94) 55%, rgba(17,24,39,1))",
          }}
        />
        <div className="relative z-10 space-y-8">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div className="max-w-3xl">
              <div className="mb-4 flex flex-wrap gap-3">
                <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/8 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-white/80">
                  <span aria-hidden="true" className="h-2 w-2 rounded-full bg-emerald-300" />
                  Analytics Preview
                </span>
                <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/8 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-white/70">
                  {analytics.periodLabel}
                </span>
              </div>

              <h1 className="font-headline text-4xl font-black tracking-[-0.05em] text-white sm:text-5xl">
                Dashboard
              </h1>
              <p className="mt-4 max-w-2xl text-base leading-7 text-white/72 sm:text-lg">
                An analytics-first view of the job search: application volume, skills requested most by role,
                acceptance vs. rejection, and the clearest next actions to improve outcomes.
              </p>
            </div>

            <div className="max-w-lg rounded-[1.5rem] border border-white/10 bg-white/8 p-5 backdrop-blur-sm">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-white/60">Executive snapshot</p>
              <p className="mt-3 text-2xl font-bold tracking-tight text-white">{executiveSummary.headline}</p>
              <p className="mt-3 text-sm leading-6 text-white/70">{executiveSummary.body}</p>
            </div>
          </div>

          <div className="grid gap-8 xl:grid-cols-[1.2fr_0.8fr]">
            <div className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-[1.5rem] border border-white/10 bg-white/8 p-5 backdrop-blur-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-white/60">Applied Jobs</p>
                  <p className="mt-3 text-4xl font-black tracking-[-0.05em] text-white">
                    {formatNumber(analytics.appliedJobs)}
                  </p>
                  <p className="mt-2 text-sm text-white/68">{analytics.last30DaysApplied} submitted in the last 30 days</p>
                  <MiniBarStrip color="#7dd3fc" values={analytics.cardTrends.appliedJobs} />
                </div>

                <div className="rounded-[1.5rem] border border-white/10 bg-white/8 p-5 backdrop-blur-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-white/60">Active Pipeline</p>
                  <p className="mt-3 text-4xl font-black tracking-[-0.05em] text-white">
                    {formatNumber(analytics.activePipeline)}
                  </p>
                  <p className="mt-2 text-sm text-white/68">Still waiting for a reply or next step</p>
                  <MiniBarStrip color="#34d399" values={analytics.cardTrends.activePipeline} />
                </div>

                <div className="rounded-[1.5rem] border border-white/10 bg-white/8 p-5 backdrop-blur-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-white/60">Interviews + Offers</p>
                  <p className="mt-3 text-4xl font-black tracking-[-0.05em] text-white">
                    {formatNumber(analytics.interviewsAndOffers)}
                  </p>
                  <p className="mt-2 text-sm text-white/68">
                    {formatPercent(analytics.acceptanceRate)} of applications are moving forward
                  </p>
                  <MiniBarStrip color="#fcd34d" values={analytics.cardTrends.interviewsAndOffers} />
                </div>

                <div className="rounded-[1.5rem] border border-white/10 bg-white/8 p-5 backdrop-blur-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-white/60">Average Reply</p>
                  <p className="mt-3 text-4xl font-black tracking-[-0.05em] text-white">
                    {formatDays(analytics.averageReplyDays)}
                  </p>
                  <p className="mt-2 text-sm text-white/68">Time to first clear signal after applying</p>
                  <MiniBarStrip color="#c4b5fd" values={analytics.cardTrends.averageReplyDays} />
                </div>
              </div>

              <HeroTrendChart series={analytics.momentum} />
            </div>

            <div className="space-y-6">
              <div className="rounded-[1.75rem] border border-white/10 bg-white/8 p-6 backdrop-blur-sm">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-white/60">What this view is modeled on</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {analytics.dataSources.map((source) => (
                    <span
                      className="rounded-full border border-white/10 bg-white/8 px-3 py-1.5 text-xs font-medium text-white/72"
                      key={source}
                    >
                      {source}
                    </span>
                  ))}
                </div>
                <p className="mt-4 text-sm leading-6 text-white/65">
                  Dummy data is seeded around fields the product already tracks or can derive: application status,
                  review outcomes, job descriptions, and tailored CV skill data.
                </p>
              </div>

              <div className="rounded-[1.75rem] border border-white/10 bg-white/8 p-6 backdrop-blur-sm">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-white/60">Focus next</p>
                <div className="mt-4 space-y-4">
                  {executiveSummary.actions.slice(0, 3).map((action) => (
                    <div className="rounded-[1.25rem] border border-white/10 bg-white/8 p-4" key={action.title}>
                      <div className="flex items-start gap-3">
                        <span className="material-symbols-outlined text-cyan-200">{action.icon}</span>
                        <div>
                          <p className="font-semibold text-white">{action.title}</p>
                          <p className="mt-1 text-sm leading-6 text-white/68">{action.detail}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-6 flex flex-wrap gap-3">
                  <Link
                    className="inline-flex items-center justify-center rounded-full border border-white/65 bg-slate-50 px-5 py-3 text-sm font-semibold text-slate-950 shadow-[0_12px_30px_rgba(2,6,23,0.2)] transition-all hover:-translate-y-0.5 hover:bg-white"
                    to="/tracker"
                  >
                    Open Tracker
                  </Link>
                  <Link
                    className="inline-flex items-center justify-center rounded-full border border-white/12 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-white/10"
                    to="/quick-apply"
                  >
                    Review Quick Apply
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <AnalyticsCard>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-on-surface-variant">
                Outcome Split
              </p>
              <h2 className="mt-2 font-headline text-2xl font-bold tracking-tight text-on-surface">
                Acceptance vs. rejection
              </h2>
              <p className="mt-2 text-sm text-on-surface-variant">
                Positive outcomes combine interview invitations and offers so the rate reflects forward motion, not just final offers.
              </p>
            </div>
            <div className="rounded-full bg-surface-container-low px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">
              {analytics.periodLabel}
            </div>
          </div>

          <div className="mt-8 grid gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
            <OutcomeDonutChart
              centerLabel="tracked"
              centerValue={formatNumber(analytics.appliedJobs)}
              segments={analytics.outcomes}
            />

            <div className="space-y-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">Acceptance</p>
                  <p className="mt-2 text-3xl font-black tracking-tight text-on-surface">
                    {formatPercent(analytics.acceptanceRate)}
                  </p>
                  <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-surface-container-low">
                    <div className="h-full rounded-full bg-teal-500" style={{ width: `${analytics.acceptanceRate}%` }} />
                  </div>
                </div>
                <div className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">Rejection</p>
                  <p className="mt-2 text-3xl font-black tracking-tight text-on-surface">
                    {formatPercent(analytics.rejectionRate)}
                  </p>
                  <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-surface-container-low">
                    <div className="h-full rounded-full bg-orange-400" style={{ width: `${analytics.rejectionRate}%` }} />
                  </div>
                </div>
              </div>

              <div className="space-y-4">
                {analytics.outcomes.map((segment) => (
                  <div className="flex items-center justify-between gap-4" key={segment.label}>
                    <div className="flex items-center gap-3">
                      <span aria-hidden="true" className="h-3 w-3 rounded-full" style={{ backgroundColor: segment.color }} />
                      <span className="text-sm text-on-surface">{segment.label}</span>
                    </div>
                    <span className="text-sm font-semibold text-on-surface">
                      {formatNumber(segment.value)} jobs
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </AnalyticsCard>

        <AnalyticsCard>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-on-surface-variant">
                Pipeline Funnel
              </p>
              <h2 className="mt-2 font-headline text-2xl font-bold tracking-tight text-on-surface">
                From sourcing to offer
              </h2>
              <p className="mt-2 text-sm text-on-surface-variant">
                A funnel is the cleanest way to show where volume drops and which stage needs the next optimization pass.
              </p>
            </div>
            <span className="rounded-full bg-surface-container-low px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">
              Workflow health
            </span>
          </div>

          <FunnelChart stages={analytics.funnel} />
        </AnalyticsCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <AnalyticsCard>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-on-surface-variant">
                Skill Demand By Role
              </p>
              <h2 className="mt-2 font-headline text-2xl font-bold tracking-tight text-on-surface">
                Most requested skills per target role
              </h2>
              <p className="mt-2 text-sm text-on-surface-variant">
                Horizontal bars are the right comparison tool here because they make skill frequency easy to scan within each role.
              </p>
            </div>
            <span className="rounded-full bg-surface-container-low px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">
              Parsed from job descriptions
            </span>
          </div>

          <div className="mt-8 grid gap-5 lg:grid-cols-3">
            {analytics.roles.map((role) => (
              <RoleSkillCard key={role.role} role={role} />
            ))}
          </div>
        </AnalyticsCard>

        <div className="space-y-6">
          <AnalyticsCard>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-on-surface-variant">
              Executive Summary
            </p>
            <h2 className="mt-2 font-headline text-2xl font-bold tracking-tight text-on-surface">
              What the user should do next
            </h2>
            <p className="mt-3 text-sm leading-7 text-on-surface-variant">{executiveSummary.body}</p>

            <div className="mt-6 space-y-4">
              {executiveSummary.actions.map((action) => (
                <div className="rounded-[1.35rem] border border-outline-variant/15 bg-surface p-4" key={action.title}>
                  <div className="flex items-start gap-3">
                    <span className="material-symbols-outlined text-primary">{action.icon}</span>
                    <div>
                      <p className="font-semibold text-on-surface">{action.title}</p>
                      <p className="mt-1 text-sm leading-6 text-on-surface-variant">{action.detail}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </AnalyticsCard>

          <AnalyticsCard>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-on-surface-variant">
                  Role Response Board
                </p>
                <h2 className="mt-2 font-headline text-2xl font-bold tracking-tight text-on-surface">
                  Which lane is paying off
                </h2>
              </div>
              <div className="flex flex-wrap gap-3 text-xs font-medium text-on-surface-variant">
                <span className="inline-flex items-center gap-2">
                  <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full bg-teal-500" />
                  Positive
                </span>
                <span className="inline-flex items-center gap-2">
                  <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full bg-sky-400" />
                  Pending
                </span>
                <span className="inline-flex items-center gap-2">
                  <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full bg-orange-400" />
                  Rejected
                </span>
              </div>
            </div>

            <div className="mt-6 space-y-4">
              {analytics.roles.map((role) => (
                <RoleResponseRow key={`${role.role}-response`} role={role} />
              ))}
            </div>
          </AnalyticsCard>
        </div>
      </div>
    </div>
  );
}
