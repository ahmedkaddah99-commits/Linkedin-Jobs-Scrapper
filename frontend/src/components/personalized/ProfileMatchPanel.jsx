import { Link } from "react-router-dom";
import { MATCH_DIMENSIONS, matchLabel, matchScore } from "../../lib/profileJobMatch";

export default function ProfileMatchPanel({ job }) {
  const match = job.matchIntelligence || {};
  return <section aria-label="Profile job match" className="profile-job-match">
    <header><strong>{matchScore(match.score)}</strong><span>{matchLabel(match)}</span></header>
    <p>Based on your saved profile</p>
    <div className="profile-job-match__dimensions">{MATCH_DIMENSIONS.map((key) => {
      const dimension = match.dimensions?.[key] || {};
      const label = dimension.label || ({ experience_level: "Experience Level", skill: "Skill", industry_experience: "Industry Exp." })[key];
      return <details key={key}><summary><span>{label}</span><strong>{matchScore(dimension.score)}</strong></summary>
        <p>{dimension.score == null ? "There is not enough established information to calculate this dimension." : dimension.explanation}</p>
        {dimension.relevant_years != null ? <p>{dimension.relevant_years} years of relevant dated work{dimension.required_years != null ? `; ${dimension.required_years} required` : ""}.</p> : null}
        {dimension.required_levels?.length ? <p>Job level: {dimension.required_levels.join(", ")}.</p> : null}
        {dimension.profile_evidence?.length ? <ul>{dimension.profile_evidence.map((value, index) => <li key={index}>{value}</li>)}</ul> : null}
        {dimension.mappings?.length ? <ul>{dimension.mappings.map((item, index) => <li key={index}><b>{item.name || item.industry}</b><span>{({ supported: "Supported by your profile", not_evidenced: "Not established in your profile", direct: "Direct industry alignment", related: "Related industry experience" })[item.status] || item.status}</span>{item.job_evidence ? <small>Job: {item.job_evidence}</small> : null}{item.profile_evidence ? <small>Profile: {item.profile_evidence}</small> : null}</li>)}</ul> : null}
        {dimension.profile_industries?.length ? <p>Your industries: {dimension.profile_industries.join(", ")}.</p> : null}
      </details>;
    })}</div>
    {match.state === "partial" ? <small>Partial assessment · {match.coverage} of 3 dimensions established</small> : null}
    <Link to="/profile">Review your profile <span aria-hidden="true">→</span></Link>
    <details className="profile-job-match__method"><summary>How this is calculated</summary><p>{match.formula || "Matching uses professional information saved in your profile. Uploaded resumes do not change your match."}</p><p>This estimates fit, not the chance of an interview.</p></details>
  </section>;
}
