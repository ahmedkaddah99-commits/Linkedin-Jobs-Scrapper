import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../../context/SessionContext";
import { logPersonalizedEvent } from "../../lib/personalizedAnalytics";
import {
  countPersonalizedJobFilters,
  buildPersonalizedJobsQuery,
  companyProfileField,
  filtersFromSavedSearch,
  formatJobDate,
  INITIAL_PERSONALIZED_JOB_FILTERS,
  toPersonalizedJobView,
  toPersonalizedJobsFilterPayload,
  unknownCompanyCharacteristics,
} from "../../lib/personalizedJobsApi";

const CATEGORY_OPTIONS = [
  "Operations & Strategy",
  "Business Operations",
  "Product Management",
  "Program Management",
  "Project Management",
  "Quality Assurance",
  "Data Analysis",
  "Administrative Support",
  "Electrical Engineering",
  "Mechanical Engineering",
  "Software Engineering",
];

const NETWORK_ITEMS = [
  ["hiring", "People hiring for this team", "Recruiters & hiring leads", "work"],
  ["alumni", "Alumni from your school", "From your saved profile", "school"],
  ["direct", "Direct contacts", "Connection data unavailable", "lock"],
  ["warm", "Warm intros", "Connection data unavailable", "lock"],
];

function Icon({ children, className = "", ...props }) {
  return <span className={["material-symbols-outlined", className].join(" ")} {...props}>{children}</span>;
}

function CompanyMark({ company, large = false, logoUrl = "" }) {
  const name = String(company || "?");
  const color = ["#0d628c", "#0f7c74", "#6d50c7", "#c35c35", "#2b6cae"][name.length % 5];
  return logoUrl ? <span aria-hidden="true" className={["jobs-company-mark", large ? "jobs-company-mark--large" : ""].join(" ")} style={{ "--company-color": color }}><img alt="" src={logoUrl} /></span> : <span aria-hidden="true" className={["jobs-company-mark", large ? "jobs-company-mark--large" : ""].join(" ")} style={{ "--company-color": color }}>{name.slice(0, 1).toUpperCase()}</span>;
}

function FilterPill({ icon, label, onChange, options, value }) {
  const active = value && value !== "all";
  return <label className={["jobs-filter-pill", active ? "is-active" : ""].join(" ")}>
    <Icon>{icon}</Icon>
    <span>{label}{active ? " (1)" : ""}</span>
    <select aria-label={label} onChange={(event) => onChange(event.target.value)} value={value || "all"}>
      {options.map((option) => <option key={`${option.value}-${option.label}`} value={option.value}>{option.label}</option>)}
    </select>
    <Icon className="jobs-filter-pill__chevron">expand_more</Icon>
  </label>;
}

function JobListCard({ isSaved, job, onSave, onSelect, selected }) {
  const arrangement = job.workArrangement === "onsite" ? "On-site" : job.workArrangement === "unknown" ? "Unknown" : job.workArrangement;
  return <article className={["jobs-list-card", selected ? "is-selected" : ""].join(" ")}>
    <button className="jobs-list-card__select" onClick={onSelect} type="button">
      <div className="jobs-list-card__company"><CompanyMark company={job.company} /><span>{job.company}</span><span className="jobs-list-card__source">{job.source}</span></div>
      <strong>{job.title}</strong>
      <div className="jobs-list-card__meta">
        <span><Icon>calendar_month</Icon>{job.experienceLevel}</span>
        <span><Icon>location_on</Icon>{job.location}</span>
        <span><Icon>{job.workArrangement === "remote" ? "wifi" : job.workArrangement === "hybrid" ? "sync_alt" : "business"}</Icon>{arrangement}</span>
        {job.applicantLabel !== "Unknown" ? <span><Icon>groups</Icon>{job.applicantLabel}</span> : null}
      </div>
    </button>
    <button aria-label={isSaved ? `Unsave ${job.title}` : `Save ${job.title}`} aria-pressed={isSaved} className={["jobs-list-card__save", isSaved ? "is-saved" : ""].join(" ")} onClick={() => onSave(job)} type="button">
      <Icon style={isSaved ? { fontVariationSettings: "'FILL' 1" } : undefined}>bookmark</Icon>
    </button>
  </article>;
}

function InfoRow({ icon, label, children }) {
  return <div className="jobs-info-row"><Icon>{icon}</Icon><div><strong>{label}</strong><span>{children}</span></div></div>;
}

function NetworkCard({ icon, onClick, subtitle, title, tone }) {
  return <button className={["jobs-network-card", tone ? `jobs-network-card--${tone}` : "", "is-locked"].join(" ")} onClick={onClick} type="button">
    <span className="jobs-network-card__badge"><Icon>{icon}</Icon></span>
    <strong>{title}</strong>
    <span>{subtitle}</span>
    <em>Manage network <Icon>arrow_forward</Icon></em>
  </button>;
}

function ReferralSection({ onOpenNetwork }) {
  return <section className="jobs-section jobs-referral-section">
    <div className="jobs-section__heading"><div><h3>Get referred to this company</h3><p>See people who can refer or advise you</p></div><button className="jobs-text-link" onClick={() => onOpenNetwork("hiring")} type="button">Manage network <Icon>arrow_forward</Icon></button></div>
    <div className="jobs-network-grid">{NETWORK_ITEMS.map(([key, title, subtitle, icon], index) => <NetworkCard icon={icon} key={key} onClick={() => onOpenNetwork(key)} subtitle={subtitle} title={title} tone={index === 0 ? "purple" : index === 1 ? "blue" : ""} />)}</div>
  </section>;
}

function CatalogStateBanner({ error, feed, loading }) {
  const state = loading && !feed ? "loading" : String(feed?.evaluation?.state || "unavailable");
  const labels = {
    loading: "Loading the shared jobs catalog…",
    partial: "Some job fields are unknown. Runr is showing only verified values.",
    stale: "The shared catalog is stale. Results remain visible with their last verification time.",
    unavailable: "The shared jobs catalog is currently unavailable.",
  };
  if (!error && state === "available") return null;
  return <div className={["jobs-catalog-state", `jobs-catalog-state--${state}`].join(" ")} role={error ? "alert" : "status"}><Icon>{state === "available" ? "info" : state === "loading" ? "progress_activity" : "cloud_off"}</Icon><span>{error || labels[state] || "Catalog state is unknown."}</span></div>;
}

function intelligenceValues(value) {
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object") return Object.values(value);
  return value ? [value] : [];
}

function IntelligenceList({ empty = "Unknown", items, evidence = false }) {
  const values = intelligenceValues(items).map((item) => {
    if (!evidence || !item || typeof item !== "object") return String(item);
    return `${item.requirement || "Requirement"}: ${item.evidence || "Evidence unavailable"}`;
  }).filter(Boolean);
  return values.length ? <ul className="jobs-intelligence-list">{values.map((value, index) => <li key={`${value}-${index}`}>{value}</li>)}</ul> : <p className="jobs-unknown-value">{empty}</p>;
}

function RunrSummary({ job }) {
  const summary = job.runrSummary || {};
  return <section className="jobs-section jobs-runr-summary">
    <div className="jobs-section__heading"><div><h3>Runr Summary</h3><p>Grounded in this job-description version</p></div><span className="jobs-data-badge">Free</span></div>
    <p className="jobs-summary-overview">{summary.overview || "Unknown"}</p>
    <div className="jobs-summary-grid">
      <div><strong>Main responsibilities</strong><IntelligenceList items={summary.main_responsibilities} /></div>
      <div><strong>Essential requirements</strong><IntelligenceList items={summary.essential_requirements} /></div>
      <div><strong>Preferred qualifications</strong><IntelligenceList items={summary.preferred_qualifications} /></div>
      <div><strong>Important application details</strong><IntelligenceList items={summary.important_application_details} /></div>
    </div>
  </section>;
}

function CompetitionPanel({ job }) {
  const intelligence = job.applicantIntelligence || {};
  const pro = intelligence.pro || null;
  const change = pro?.change;
  const changeLabel = change?.state === "available" && Number.isFinite(Number(change.delta))
    ? `${Number(change.delta) >= 0 ? "+" : ""}${change.delta} applicants since first observation`
    : "Trend unknown until two exact observations are available.";
  return <section className="jobs-section jobs-competition-panel">
    <div className="jobs-section__heading"><div><h3>Applicant competition</h3><p>Only explicit source observations are shown.</p></div><span className="jobs-data-badge">{pro ? "Pro" : "Verified source"}</span></div>
    <div className="jobs-summary-grid">
      <div><strong>Latest applicants</strong><span>{job.applicantLabel}</span></div>
      <div><strong>Freshness</strong><span>{job.applicantFreshness === "unknown" ? "Unknown" : job.applicantFreshness}</span></div>
      <div><strong>Apply method</strong><span>{job.applicantApplyMethod === "direct_apply" ? "Direct Apply" : job.applicantApplyMethod}</span></div>
      <div><strong>Change over time</strong><span>{pro ? changeLabel : "Detailed trend available in Runr Pro."}</span></div>
    </div>
  </section>;
}

function EvaluationPanel({ job }) {
  const evaluation = job.evaluation || {};
  const match = job.matchIntelligence || {};
  const state = String(match.state || evaluation.state || "unknown");
  const scoreMatch = match.v1 || match.v2 || {};
  const score = Number.isFinite(Number(scoreMatch.score)) ? Number(scoreMatch.score) : null;
  const missing = intelligenceValues(scoreMatch.missing_keywords).map(String).filter(Boolean).slice(0, 6);
  return <section className={["jobs-match-card", "jobs-evaluation-card", `jobs-evaluation-card--${state}`].join(" ")}>
    <div className="jobs-ats-summary">
      <div className="jobs-ats-score" style={{ "--ats-score": `${score ?? 0}%` }}><strong>{score ?? "—"}</strong></div>
      <div className="jobs-ats-copy"><strong>Resume match</strong><span>{score === null ? "Not available" : score >= 70 ? "Good match" : "Low match"}</span></div>
    </div>
    {missing.length ? <div className="jobs-ats-missing"><strong>{missing.length} missing {missing.length === 1 ? "keyword" : "keywords"}</strong><div>{missing.map((value, index) => <span key={`${value}-${index}`}>{value}</span>)}</div></div> : null}
    {score !== null ? <Link className="jobs-text-link jobs-improve-button" to="/cv-studio">Improve resume <Icon>arrow_forward</Icon></Link> : null}
  </section>;
}

function DescriptionBlock({ description }) {
  const paragraphs = String(description || "").split(/\n+/).map((paragraph) => paragraph.trim()).filter(Boolean);
  return paragraphs.length ? paragraphs.map((paragraph, index) => <p key={`${paragraph.slice(0, 20)}-${index}`}>{paragraph}</p>) : <p> No verified description is available for this job.</p>;
}

function JobDescription({ job }) {
  return <section className="jobs-section jobs-description"><h3>Job description</h3><DescriptionBlock description={job.description} /></section>;
}

function StructuredDescription({ job }) {
  const structured = job.structuredDescription || {};
  const sections = [
    ["Responsibilities", structured.responsibilities],
    ["Requirements", structured.requirements],
    ["Skills", structured.skills],
    ["Education", structured.education],
    ["Languages", structured.languages],
    ["Authorization", structured.authorization],
    ["Benefits", structured.benefits],
    ["Salary", structured.salary],
    ["Workplace arrangement", structured.workplace_arrangement],
  ];
  return <section className="jobs-section jobs-structured-description"><h3>Structured Description</h3><div className="jobs-structured-grid">{sections.map(([label, value]) => <div key={label}><strong>{label}</strong>{label === "Salary" ? <span>{job.salaryLabel !== "Unknown" ? job.salaryLabel : "Unknown"}</span> : <IntelligenceList items={value} />}</div>)}</div></section>;
}

function OriginalPosting({ job }) {
  const original = job.originalPosting || {};
  return <section className="jobs-section jobs-original-posting"><h3>Original Posting</h3><p className="jobs-original-posting__note">Preserved from the employer source for job version {original.version_number || job.version || "Unknown"}.</p><DescriptionBlock description={original.description} /></section>;
}

function FullPostingPanel({ job }) {
  return <section className="jobs-full-posting">
    <div className="jobs-full-posting__metadata"><InfoRow icon="category" label="Category">{job.category}</InfoRow><InfoRow icon="language" label="Languages">{job.languages.length ? job.languages.join(", ") : "Unknown"}</InfoRow><InfoRow icon="verified_user" label="Work authorization">{job.work_authorization || "Unknown"}</InfoRow><InfoRow icon="business_center" label="Sponsorship">{job.sponsorship || "Unknown"}</InfoRow><InfoRow icon="schedule" label="Lifecycle">{job.lifecycleState}</InfoRow><InfoRow icon="update" label="Last verified">{formatJobDate(job.last_verified_at)}</InfoRow></div>
    <StructuredDescription job={job} />
    <OriginalPosting job={job} />
    <div className="jobs-source-links"><span>Source links</span>{job.canonicalUrl ? <a href={job.canonicalUrl} rel="noreferrer" target="_blank">Canonical job <Icon>open_in_new</Icon></a> : <span>Canonical job: Unknown</span>}{job.observationUrl ? <a href={job.observationUrl} rel="noreferrer" target="_blank">Observation <Icon>open_in_new</Icon></a> : null}</div>
  </section>;
}

function CompanyOverview({ company, job, onOpenNetwork }) {
  const detail = company || {};
  const characteristics = unknownCompanyCharacteristics(detail.characteristics || {});
  const profile = detail.profile || job.companyProfile || {};
  const field = (name, fallback) => companyProfileField(profile, name, fallback);
  const website = field("website");
  const description = field("description");
  const industry = field("industry");
  const size = field("company_size", characteristics.size);
  const headquarters = field("headquarters", characteristics.headquarters);
  const founded = field("founded_year", characteristics.foundedYear);
  const fundingStage = field("funding_stage", characteristics.fundingStage);
  const totalFunding = field("total_funding");
  const fundingYear = field("funding_year");
  const leadership = field("leadership_type");
  const benefits = field("benefits");
  const sponsorship = field("sponsorship");
  const sourceUrl = website.state === "known" ? website.value : detail.provenance_url || job.companyDetail?.provenance_url;
  const logoUrl = profile.logo_url || profile.fields?.logo?.value || "";
  return <div className="jobs-company-overview">
    <div className="jobs-company-overview__hero"><CompanyMark company={detail.name || job.company} large logoUrl={logoUrl} /><div><h2>{detail.name || job.company}</h2><div className="jobs-company-actions">{sourceUrl ? <a className="jobs-outline-button" href={sourceUrl} rel="noreferrer" target="_blank"><Icon>language</Icon>Website</a> : <span className="jobs-outline-button jobs-outline-button--disabled"><Icon>language</Icon>Website unknown</span>}</div></div><span className="jobs-company-data-status">Verified company data only</span></div>
    <p className="jobs-company-description">{description.value}</p>
    <div className="jobs-company-stats"><div><span>Company size</span><strong>{size.value}</strong></div><div><span>Company stage</span><strong>{characteristics.stage}</strong></div><div><span>Headquarters</span><strong>{headquarters.value}</strong></div><div><span>Founded</span><strong>{founded.value}</strong></div></div>
    <section className="jobs-section"><div className="jobs-section__heading"><div><h3>Company information</h3><p>Unknown means no verified source-backed value is available yet.</p></div></div><div className="jobs-company-catalog-facts"><span>Industry: {industry.value}</span><span>Funding stage: {fundingStage.value}</span><span>Total funding: {totalFunding.value}</span><span>Funding year: {fundingYear.value}</span><span>Leadership: {leadership.value}</span><span>Benefits: {benefits.value}</span><span>Sponsorship: {sponsorship.value}</span><span>Jobs in catalog: {detail.job_count ?? "Unknown"}</span></div></section>
    <ReferralSection onOpenNetwork={onOpenNetwork} />
    <section className="jobs-section"><h3>Benefits</h3><IntelligenceList items={benefits.value === "Unknown" ? [] : benefits.value} /></section>
  </div>;
}

function JobOverview({ job, onOpenNetwork, onPrepare, onReport, onHide, rightPanelTab, setRightPanelTab }) {
  const arrangement = job.workArrangement === "onsite" ? "On-site" : job.workArrangement;
  const skills = Array.isArray(job.skills) ? job.skills.filter(Boolean) : [];
  return <div className="jobs-overview-grid">
    <main className="jobs-overview-main">
      <div className="jobs-detail-heading"><span className="jobs-season-pill">{formatJobDate(job.postedAt)}</span><h1>{job.title}</h1><p>{job.company} · {job.source}</p><div className="jobs-detail-heading__actions"><button className="jobs-outline-button" onClick={onPrepare} type="button"><Icon>auto_awesome</Icon>Prepare</button><button aria-label="Share job" className="jobs-round-button" onClick={() => navigator.clipboard?.writeText(job.canonicalUrl || job.applyUrl || window.location.href)} type="button"><Icon>share</Icon></button><button aria-label="Report job" className="jobs-round-button" onClick={onReport} type="button"><Icon>flag</Icon></button><button aria-label={job.userState === "hidden" ? "Restore job" : "Hide job"} className={["jobs-round-button", job.userState === "hidden" ? "is-selected" : ""].join(" ")} onClick={onHide} type="button"><Icon>{job.userState === "hidden" ? "visibility" : "visibility_off"}</Icon></button></div></div>
      <div className="jobs-company-inline"><CompanyMark company={job.company} large /><div><h2>{job.company}</h2><p>{job.companyDetail?.entity_kind || "Employer"} · {job.location}</p></div></div>
      <p className="jobs-role-summary">{job.descriptionSummary}</p>
      <div className="jobs-info-grid"><InfoRow icon="payments" label="Salary">{job.salaryLabel}</InfoRow><InfoRow icon="work_history" label="Job type">{job.employmentType}</InfoRow><InfoRow icon="location_on" label="Location">{job.location}</InfoRow><InfoRow icon={job.workArrangement === "remote" ? "wifi" : "business"} label="Workplace">{arrangement}</InfoRow></div>
      <section className="jobs-section"><div className="jobs-section__heading"><div><h3>Category</h3><p>How this role is grouped</p></div></div><div className="jobs-category-card"><Icon>category</Icon><div><strong>{job.category}</strong><span>Source category</span></div><small>Verified</small></div></section>
      <section className="jobs-section"><div className="jobs-section__heading"><div><h3>Required skills</h3><p>Skills explicitly provided by the source</p></div></div><div className="jobs-skill-list">{skills.length ? skills.map((skill) => <span key={skill}><Icon>check_circle</Icon>{skill}</span>) : <span><Icon>help</Icon>Unknown</span>}</div></section>
      <ReferralSection onOpenNetwork={onOpenNetwork} />
      <JobDescription job={job} />
    </main>
    <aside className="jobs-overview-side"><div className="jobs-segmented-control"><button className={rightPanelTab === "summary" ? "is-active" : ""} onClick={() => setRightPanelTab("summary")} type="button">Summary</button><button className={rightPanelTab === "posting" ? "is-active" : ""} onClick={() => setRightPanelTab("posting")} type="button">Full job posting</button></div>{rightPanelTab === "summary" ? <><RunrSummary job={job} /><CompetitionPanel job={job} /><EvaluationPanel job={job} /><section className="jobs-side-network"><h3>Get referred to {job.company}</h3><p>Connections can help your application get noticed.</p><ReferralSection onOpenNetwork={onOpenNetwork} /></section></> : <FullPostingPanel job={job} />}</aside>
  </div>;
}

function FilterDrawer({ capabilities = {}, filters, onChange, onClear, onClose, onApply }) {
  const available = (name) => Boolean(capabilities[name]);
  return <div className="jobs-filter-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <aside aria-label="All filters" aria-modal="true" className="jobs-filter-drawer" role="dialog">
      <header className="jobs-filter-drawer__header"><div><p className="jobs-eyebrow">Job search</p><h2>All filters</h2></div><button aria-label="Close filters" className="jobs-modal-close" onClick={onClose} type="button"><Icon>close</Icon></button></header>
      <div className="jobs-filter-drawer__body">
        <section><h3>Job details</h3><label>Employment type<select onChange={(event) => onChange("employmentType", event.target.value)} value={filters.employmentType}><option value="all">Any employment type</option><option value="full-time">Full-time</option><option value="part-time">Part-time</option><option value="contract">Contract</option><option value="internship">Internship</option></select></label>{available("salary") ? <><label>Salary minimum<input inputMode="numeric" onChange={(event) => onChange("salaryMin", event.target.value)} placeholder="e.g. 60000" value={filters.salaryMin} /></label><label>Salary maximum<input inputMode="numeric" onChange={(event) => onChange("salaryMax", event.target.value)} placeholder="e.g. 100000" value={filters.salaryMax} /></label></> : null}{available("language") ? <label>Language requirements<input onChange={(event) => onChange("language", event.target.value)} placeholder="e.g. German" value={filters.language} /></label> : null}{available("work_authorization") ? <label>Work authorization<input onChange={(event) => onChange("workAuthorization", event.target.value)} placeholder="e.g. EU / EEA" value={filters.workAuthorization} /></label> : null}{available("sponsorship") ? <label>Sponsorship<select onChange={(event) => onChange("sponsorship", event.target.value)} value={filters.sponsorship}><option value="">Any sponsorship status</option><option value="yes">Sponsorship available</option><option value="no">No sponsorship</option><option value="unknown">Unknown only</option></select></label> : null}{available("education") ? <label>Education<input onChange={(event) => onChange("education", event.target.value)} placeholder="e.g. Bachelor's" value={filters.education} /></label> : null}{available("preferred_major") ? <label>Preferred majors<input onChange={(event) => onChange("preferredMajor", event.target.value)} placeholder="e.g. Electrical Engineering" value={filters.preferredMajor} /></label> : null}{available("security_clearance") ? <label>Security clearance<input onChange={(event) => onChange("securityClearance", event.target.value)} placeholder="e.g. eligible" value={filters.securityClearance} /></label> : null}{available("lifting_requirement") ? <label>Physical / lifting requirements<input onChange={(event) => onChange("liftingRequirement", event.target.value)} placeholder="e.g. up to 25 lb" value={filters.liftingRequirement} /></label> : null}</section>
        <section><h3>Company</h3><label>Company<input onChange={(event) => onChange("company", event.target.value)} placeholder="Search company" value={filters.company} /></label>{available("hidden_companies") ? <label>Hidden companies<input onChange={(event) => onChange("hiddenCompanies", event.target.value)} placeholder="Filter out companies" value={filters.hiddenCompanies} /></label> : null}{available("industry") ? <label>Industry<input onChange={(event) => onChange("industry", event.target.value)} placeholder="e.g. Financial Services" value={filters.industry} /></label> : null}{available("company_size") ? <label>Company size<select onChange={(event) => onChange("companySize", event.target.value)} value={filters.companySize}><option value="">Any company size</option><option>1-10</option><option>11-50</option><option>51-200</option><option>201-500</option><option>501-1,000</option><option>1,001-5,000</option></select></label> : null}{available("company_stage") ? <label>Company stage<input onChange={(event) => onChange("companyStage", event.target.value)} placeholder="e.g. Growth" value={filters.companyStage} /></label> : null}{available("funding_stage") ? <label>Funding stage<input onChange={(event) => onChange("fundingStage", event.target.value)} placeholder="e.g. Series A" value={filters.fundingStage} /></label> : null}{available("funding_range") ? <><label>Funding minimum<input inputMode="numeric" onChange={(event) => onChange("fundingMin", event.target.value)} placeholder="e.g. 1000000" value={filters.fundingMin} /></label><label>Funding maximum<input inputMode="numeric" onChange={(event) => onChange("fundingMax", event.target.value)} placeholder="e.g. 10000000" value={filters.fundingMax} /></label></> : null}{available("founded_year") ? <><label>Founded from<input inputMode="numeric" onChange={(event) => onChange("foundedYearMin", event.target.value)} placeholder="e.g. 2010" value={filters.foundedYearMin} /></label><label>Founded to<input inputMode="numeric" onChange={(event) => onChange("foundedYearMax", event.target.value)} placeholder="e.g. 2020" value={filters.foundedYearMax} /></label></> : null}{available("funding_year") ? <><label>Funding year from<input inputMode="numeric" onChange={(event) => onChange("fundingYearMin", event.target.value)} placeholder="e.g. 2020" value={filters.fundingYearMin} /></label><label>Funding year to<input inputMode="numeric" onChange={(event) => onChange("fundingYearMax", event.target.value)} placeholder="e.g. 2025" value={filters.fundingYearMax} /></label></> : null}</section>
        {available("posting_recency") ? <section><h3>Posting age</h3><div className="jobs-filter-radio-list">{[["all", "Any time"], ["24h", "Past 24 hours"], ["7d", "Past 7 days"], ["30d", "Past 30 days"]].map(([value, label]) => <label key={value}><input checked={filters.datePosted === value} name="posting-age" onChange={() => onChange("datePosted", value)} type="radio" />{label}</label>)}</div></section> : null}
      </div>
      <footer className="jobs-filter-drawer__footer"><button className="jobs-outline-button" onClick={onClear} type="button">Clear all</button><button className="jobs-primary-button" onClick={onApply} type="button">Show results</button></footer>
    </aside>
  </div>;
}

function ReportDialog({ onClose, onSubmit }) {
  const [reason, setReason] = useState("incorrect_location");
  return <div className="jobs-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section aria-labelledby="report-job-title" aria-modal="true" className="jobs-report-modal" role="dialog"><header><div><p className="jobs-eyebrow">Catalog feedback</p><h2 id="report-job-title">Report incorrect filtering</h2></div><button aria-label="Close report dialog" className="jobs-modal-close" onClick={onClose} type="button"><Icon>close</Icon></button></header><p>Tell Runr what looks wrong. This report is recorded against the job and does not trigger acquisition.</p><label>Reason<select onChange={(event) => setReason(event.target.value)} value={reason}><option value="incorrect_location">Incorrect location</option><option value="incorrect_experience">Incorrect experience level</option><option value="incorrect_language">Incorrect language requirement</option><option value="incorrect_company">Incorrect employer</option><option value="other">Other</option></select></label><footer><button className="jobs-outline-button" onClick={onClose} type="button">Cancel</button><button className="jobs-primary-button" onClick={() => onSubmit(reason)} type="button">Send report</button></footer></section></div>;
}

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() => typeof window !== "undefined" && window.matchMedia("(max-width: 800px)").matches);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 800px)");
    const update = () => setIsMobile(media.matches);
    update();
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);
  return isMobile;
}

export default function JobsWorkspace({ initialJobId = "" }) {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { isConnected, request } = useSession();
  const routeJobId = initialJobId || searchParams.get("job") || "";
  const isMobile = useIsMobile();
  const [filters, setFilters] = useState(INITIAL_PERSONALIZED_JOB_FILTERS);
  const [feed, setFeed] = useState(null);
  const [detailJob, setDetailJob] = useState(null);
  const [selectedJobId, setSelectedJobId] = useState(routeJobId);
  const [activeTab, setActiveTab] = useState("overview");
  const [rightPanelTab, setRightPanelTab] = useState("summary");
  const [companyDetail, setCompanyDetail] = useState(null);
  const [companyLoading, setCompanyLoading] = useState(false);
  const [companyError, setCompanyError] = useState("");
  const [feedError, setFeedError] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [preparing, setPreparing] = useState(searchParams.get("prepare") === "1");
  const [feedback, setFeedback] = useState("");
  const [busyAction, setBusyAction] = useState("");

  const rawJobs = Array.isArray(feed?.jobs) ? feed.jobs : [];
  const jobs = useMemo(() => rawJobs.map(toPersonalizedJobView), [rawJobs]);
  const selectedRawJob = detailJob || rawJobs.find((job) => String(job.canonical_job_id || job.posting_id) === String(selectedJobId)) || (!routeJobId ? rawJobs[0] : null);
  const selectedJob = selectedRawJob ? toPersonalizedJobView(selectedRawJob) : null;
  const activeFilterCount = countPersonalizedJobFilters(filters);
  const showMobileList = isMobile && !routeJobId;

  useEffect(() => {
    setSelectedJobId(routeJobId);
    setDetailJob(null);
    setPreparing(searchParams.get("prepare") === "1");
  }, [routeJobId, searchParams]);

  useEffect(() => {
    if (!isConnected) return undefined;
    let active = true;
    request("/personalized-jobs/saved-search")
      .then((payload) => {
        if (!active || !payload?.filters || Object.keys(payload.filters).length === 0) return;
        setFilters((current) => ({ ...current, ...filtersFromSavedSearch(payload) }));
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [isConnected, request]);

  useEffect(() => {
    if (!isConnected) return undefined;
    let active = true;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setFeedError("");
      setFeed(null);
      try {
        const query = buildPersonalizedJobsQuery(filters, { limit: 25 });
        const payload = await request(`/personalized-jobs?${query}`);
        if (active) setFeed(payload || { jobs: [], total: 0 });
      } catch (error) {
        if (active) setFeedError(error?.message || "Unable to load the shared jobs catalog.");
      } finally {
        if (active) setLoading(false);
      }
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [filters, isConnected, request]);

  useEffect(() => {
    if (!isConnected || !routeJobId) return undefined;
    let active = true;
    request(`/personalized-jobs/${encodeURIComponent(routeJobId)}`)
      .then((payload) => { if (active) { setDetailJob(payload); setFeedError(""); } })
      .catch((error) => { if (active) setFeedError(error?.message || "This job is not available in the shared catalog."); });
    return () => { active = false; };
  }, [isConnected, request, routeJobId]);

  useEffect(() => {
    if (!routeJobId && !selectedJobId && jobs[0]) setSelectedJobId(jobs[0].id);
    if (!routeJobId && selectedJobId && rawJobs.length && !rawJobs.some((job) => String(job.canonical_job_id || job.posting_id) === String(selectedJobId))) setSelectedJobId(jobs[0]?.id || "");
  }, [jobs, rawJobs, routeJobId, selectedJobId]);

  useEffect(() => {
    if (activeTab !== "company" || !selectedJob?.company_id) return undefined;
    let active = true;
    setCompanyLoading(true);
    setCompanyError("");
    request(`/personalized-jobs/companies/${encodeURIComponent(selectedJob.company_id)}`)
      .then((payload) => { if (active) setCompanyDetail(payload); })
      .catch((error) => { if (active) setCompanyError(error?.message || "Company details are unavailable."); })
      .finally(() => { if (active) setCompanyLoading(false); });
    return () => { active = false; };
  }, [activeTab, request, selectedJob?.company_id]);

  function updateFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
    setFeedback("");
    logPersonalizedEvent("jobs_filter_changed", { route: "/jobs", filterName: name });
  }

  function clearFilters() {
    setFilters(INITIAL_PERSONALIZED_JOB_FILTERS);
    setFeedback("Filters cleared.");
  }

  function setRawUserState(id, state) {
    const matches = (job) => String(job.canonical_job_id || job.posting_id) === String(id);
    setFeed((current) => current ? { ...current, jobs: (current.jobs || []).map((job) => matches(job) ? { ...job, user_state: state } : job) } : current);
    setDetailJob((current) => current && matches(current) ? { ...current, user_state: state } : current);
  }

  async function saveJob(job) {
    const nextState = job.userState === "saved" ? "none" : "saved";
    setBusyAction("save");
    try {
      await request(`/personalized-jobs/${encodeURIComponent(job.id)}/save`, { method: nextState === "none" ? "DELETE" : "POST", body: {} });
      setRawUserState(job.id, nextState);
      setFeedback(nextState === "saved" ? `${job.title} saved.` : `${job.title} removed from saved jobs.`);
      logPersonalizedEvent(nextState === "saved" ? "job_saved" : "job_unsaved", { route: "/jobs", jobId: job.id });
    } catch (error) {
      setFeedback(error?.message || "Unable to update this saved job.");
    } finally {
      setBusyAction("");
    }
  }

  async function toggleHide() {
    if (!selectedJob) return;
    const hiding = selectedJob.userState !== "hidden";
    setBusyAction("hide");
    try {
      await request(`/personalized-jobs/${encodeURIComponent(selectedJob.id)}/${hiding ? "hide" : "restore"}`, { method: "POST", body: {} });
      setRawUserState(selectedJob.id, hiding ? "hidden" : "none");
      setFeedback(hiding ? "This job is hidden. You can restore it from Hidden jobs." : "This job is back in your shortlist.");
    } catch (error) {
      setFeedback(error?.message || "Unable to update this job.");
    } finally {
      setBusyAction("");
    }
  }

  async function markApplied() {
    if (!selectedJob || selectedJob.userState === "applied") return;
    setBusyAction("applied");
    try {
      await request(`/personalized-jobs/${encodeURIComponent(selectedJob.id)}/applied`, { method: "POST", body: {} });
      setRawUserState(selectedJob.id, "applied");
      setFeedback("Marked as applied.");
    } catch (error) {
      setFeedback(error?.message || "Unable to mark this job as applied.");
    } finally {
      setBusyAction("");
    }
  }

  async function reportJob(reason) {
    if (!selectedJob) return;
    setReportOpen(false);
    try {
      await request(`/personalized-jobs/${encodeURIComponent(selectedJob.id)}/report`, { method: "POST", body: { reason_code: reason } });
      setFeedback("Thanks. Your report was recorded for this job.");
    } catch (error) {
      setFeedback(error?.message || "Unable to send this report.");
    }
  }

  async function saveSearch() {
    try {
      await request("/personalized-jobs/saved-search", { method: "PUT", body: { name: "Default search", filters: toPersonalizedJobsFilterPayload(filters) } });
      setFeedback("Search saved.");
    } catch (error) {
      setFeedback(error?.message || "Unable to save this search.");
    }
  }

  async function loadMore() {
    if (!feed?.next_cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const query = buildPersonalizedJobsQuery(filters, { cursor: feed.next_cursor, limit: 25 });
      const payload = await request(`/personalized-jobs?${query}`);
      setFeed((current) => current ? { ...payload, jobs: [...(current.jobs || []), ...(payload?.jobs || [])] } : payload);
    } catch (error) {
      setFeedback(error?.message || "Unable to load more jobs.");
    } finally {
      setLoadingMore(false);
    }
  }

  function selectJob(job) {
    setSelectedJobId(job.id);
    setDetailJob(null);
    setActiveTab("overview");
    setRightPanelTab("summary");
    if (isMobile) navigate(`/jobs/${encodeURIComponent(job.id)}`);
  }

  function applyToJob() {
    if (!selectedJob?.applyUrl) {
      setFeedback("No verified employer or official ATS Apply URL is available for this job.");
      return;
    }
    window.open(selectedJob.applyUrl, "_blank", "noopener,noreferrer");
    setFeedback("The verified employer application opened in a new tab.");
  }

  function openNetwork() {
    setFeedback("Network connections are not available in this Jobs API response yet.");
  }

  const detailContent = selectedJob ? <>
    <div className="jobs-detail-toolbar"><div className="jobs-detail-tabs"><button className={activeTab === "overview" ? "is-active" : ""} onClick={() => setActiveTab("overview")} type="button">Overview</button><button className={activeTab === "company" ? "is-active" : ""} onClick={() => setActiveTab("company")} type="button">Company</button></div><div className="jobs-detail-toolbar__actions"><button className="jobs-back-link jobs-mobile-back" onClick={() => navigate("/jobs")} type="button"><Icon>arrow_back</Icon>Back to jobs</button><button className="jobs-text-link" disabled={busyAction === "applied" || selectedJob.userState === "applied"} onClick={markApplied} type="button">{selectedJob.userState === "applied" ? "Already applied" : "Already applied?"}</button><button className={selectedJob.userState === "saved" ? "jobs-outline-button is-selected" : "jobs-outline-button"} disabled={busyAction === "save"} onClick={() => saveJob(selectedJob)} type="button"><Icon style={selectedJob.userState === "saved" ? { fontVariationSettings: "'FILL' 1" } : undefined}>bookmark</Icon>{selectedJob.userState === "saved" ? "Saved" : "Save"}</button><button className="jobs-primary-button" disabled={!selectedJob.applyUrl} onClick={applyToJob} title={selectedJob.applyUrl ? "Open employer application" : "No verified Apply URL"} type="button"><Icon>bolt</Icon>Apply</button></div></div>
    <div className="jobs-detail-scroll">{activeTab === "company" ? companyLoading ? <div className="jobs-empty"><Icon>progress_activity</Icon><strong>Loading company details</strong></div> : companyError ? <div className="jobs-empty"><Icon>cloud_off</Icon><strong>{companyError}</strong></div> : <CompanyOverview company={companyDetail} job={selectedJob} onOpenNetwork={openNetwork} /> : <JobOverview job={selectedJob} onHide={toggleHide} onOpenNetwork={openNetwork} onPrepare={() => setPreparing(true)} onReport={() => setReportOpen(true)} rightPanelTab={rightPanelTab} setRightPanelTab={setRightPanelTab} />}{preparing ? <section className="jobs-preparation-panel"><div><span className="jobs-eyebrow">Application preparation</span><h2>Prepare this application with Runr</h2><p>Review the verified job details, then tailor your documents before opening the employer application.</p></div><div className="jobs-preparation-actions"><Link className="jobs-outline-button" to="/documents"><Icon>description</Icon>Documents</Link><Link className="jobs-outline-button" to="/cv-studio"><Icon>edit_note</Icon>CV Studio</Link><button className="jobs-text-link" onClick={() => setPreparing(false)} type="button">Close</button></div></section> : null}</div>
  </> : <div className="jobs-empty jobs-empty--detail"><Icon>work_off</Icon><strong>{routeJobId ? "Loading job details" : "Select a job"}</strong><span>{routeJobId ? "Runr is checking the shared catalog." : "Choose a role from the shortlist to see details."}</span></div>;

  return <div className="jobs-experience">
    <section className="jobs-search-bar" aria-label="Job search filters">
      <label className="jobs-search-input"><Icon>search</Icon><input aria-label="Search jobs" onChange={(event) => updateFilter("query", event.target.value)} placeholder="Search title, company, or skill" type="search" value={filters.query} /></label>
      <FilterPill icon="location_on" label="Location" onChange={(value) => updateFilter("location", value === "all" ? "" : value)} options={[{ label: "All locations", value: "all" }, { label: "Berlin", value: "Berlin" }, { label: "Germany", value: "Germany" }, { label: "Remote in Germany", value: "Remote in Germany" }]} value={filters.location || "all"} />
      <FilterPill icon="work_outline" label="Job type" onChange={(value) => updateFilter("workArrangement", value)} options={[{ label: "Any workplace", value: "all" }, { label: "Remote", value: "remote" }, { label: "Hybrid", value: "hybrid" }, { label: "On-site", value: "onsite" }]} value={filters.workArrangement} />
      <FilterPill icon="stairs" label="Experience level" onChange={(value) => updateFilter("experienceLevel", value)} options={[{ label: "Any experience", value: "all" }, { label: "Entry", value: "entry" }, { label: "Mid-level", value: "mid" }, { label: "Senior", value: "senior" }, { label: "Lead", value: "lead" }]} value={filters.experienceLevel} />
      <FilterPill icon="category" label="Category" onChange={(value) => updateFilter("category", value === "all" ? "" : value)} options={[{ label: "All categories", value: "all" }, ...CATEGORY_OPTIONS.map((value) => ({ label: value, value }))]} value={filters.category || "all"} />
      <button className={["jobs-filter-pill", activeFilterCount > 5 ? "is-active" : ""].join(" ")} onClick={() => setFiltersOpen(true)} type="button"><Icon>tune</Icon><span>More filters{activeFilterCount > 5 ? ` (${activeFilterCount - 5})` : ""}</span><Icon className="jobs-filter-pill__chevron">expand_more</Icon></button>
      <button className="jobs-search-link" onClick={saveSearch} type="button"><Icon>favorite</Icon>Save search</button>
      {activeFilterCount ? <button className="jobs-search-link jobs-search-link--muted" onClick={clearFilters} type="button">Clear all filters</button> : null}
    </section>
    <CatalogStateBanner error={feedError} feed={feed} loading={loading} />
    {feedback ? <div className="jobs-feedback" role="status"><Icon>check_circle</Icon>{feedback}<button aria-label="Dismiss" onClick={() => setFeedback("")} type="button"><Icon>close</Icon></button></div> : null}
    <div className={["jobs-workspace", showMobileList ? "jobs-workspace--mobile-list" : "", isMobile && routeJobId ? "jobs-workspace--mobile-detail" : ""].join(" ")}>
      {!isMobile || showMobileList ? <aside className="jobs-list-panel"><div className="jobs-list-panel__header"><strong>Showing {jobs.length} of {feed?.total ?? 0} jobs</strong><label><span className="jobs-switch"><input checked={filters.sort === "newest"} onChange={(event) => updateFilter("sort", event.target.checked ? "newest" : "best")} type="checkbox" /><span /></span>Most recent</label></div><div className="jobs-list-panel__body">{loading && !feed ? <div className="jobs-empty"><Icon>progress_activity</Icon><strong>Loading jobs</strong></div> : jobs.length ? <>{jobs.map((job) => <JobListCard isSaved={job.userState === "saved"} job={job} key={job.id} onSave={saveJob} onSelect={() => selectJob(job)} selected={selectedJob?.id === job.id} />)}{feed?.next_cursor ? <button className="jobs-load-more" disabled={loadingMore} onClick={loadMore} type="button">{loadingMore ? "Loading…" : "Load more jobs"}</button> : null}</> : <div className="jobs-empty"><Icon>search_off</Icon><strong>No jobs match</strong><span>Clear a filter to see more roles.</span><button className="jobs-outline-button" onClick={clearFilters} type="button">Clear filters</button></div>}</div></aside> : null}
      {!isMobile || !showMobileList ? <section className="jobs-detail-panel">{detailContent}</section> : null}
    </div>
    {filtersOpen ? <FilterDrawer capabilities={feed?.filter_capabilities || {}} filters={filters} onApply={() => setFiltersOpen(false)} onChange={updateFilter} onClear={clearFilters} onClose={() => setFiltersOpen(false)} /> : null}
    {reportOpen ? <ReportDialog onClose={() => setReportOpen(false)} onSubmit={reportJob} /> : null}
  </div>;
}
