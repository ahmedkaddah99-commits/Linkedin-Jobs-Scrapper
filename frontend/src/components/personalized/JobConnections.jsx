import { useEffect, useState } from "react";

function initialMessage(person, job) {
  const firstName = String(person.name || "there").split(" ")[0];
  return `Hi ${firstName}, I'm interested in the ${job.title} role at ${job.company}. I'd value the chance to connect and learn more about the team.`.slice(0, 200);
}

export default function JobConnections({ job, request }) {
  const discovery = job.network_discovery || { state: "pending", candidates: [] };
  const candidates = Array.isArray(discovery.candidates) ? discovery.candidates : [];
  const known = Array.isArray(job.network_connections) ? job.network_connections : [];
  const shared = Array.isArray(job.shared_background_connections) ? job.shared_background_connections : [];
  const [person, setPerson] = useState(null);
  const [message, setMessage] = useState("");
  const [copied, setCopied] = useState(false);
  const [profileUrl, setProfileUrl] = useState("");
  const [emailResult, setEmailResult] = useState(null);
  const [emailBusy, setEmailBusy] = useState(false);
  const [expanded, setExpanded] = useState('');

  useEffect(() => {
    setEmailResult(null);
    setProfileUrl("");
    setPerson(null);
    setExpanded('');
  }, [job.id]);

  useEffect(() => {
    if (!person) return undefined;
    const onKeyDown = (event) => { if (event.key === "Escape") setPerson(null); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [person]);

  function openProfile(target) {
    setPerson(target);
    setMessage(initialMessage(target, job));
    setCopied(false);
  }

  async function lookupEmail(url = profileUrl) {
    setEmailBusy(true);
    setEmailResult(null);
    try {
      const result = await request(`/personalized-jobs/${encodeURIComponent(job.id)}/email-lookup`, {
        method: "POST", body: { linkedin_url: url },
      });
      setEmailResult({ ...result, person: [...candidates, ...known, ...shared].find((item) => item.linkedin_url === url)
        || { name: "this person", linkedin_url: url } });
    } catch (error) {
      setEmailResult({ state: "error", message: error.message || "Email lookup failed." });
    } finally {
      setEmailBusy(false);
    }
  }

  const renderPerson = (item, index) => (
    <div className="job-connection-person" key={`${item.linkedin_url || item.contact_id || item.name}-${index}`}>
      <div><strong>{item.name}</strong><small>{item.role || item.company || "Connection"}</small></div>
      <div className="job-connection-person__actions">
        {item.linkedin_url ? <>
          <button aria-label={`Find ${item.name}'s work email`} onClick={() => lookupEmail(item.linkedin_url)} title="Find work email" type="button">✉</button>
          <button aria-label={`Open ${item.name}'s LinkedIn message`} onClick={() => openProfile(item)} title="Connect on LinkedIn" type="button">in</button>
        </> : null}
      </div>
    </div>
  );

  return <section className="job-connections" aria-label="Connections for this job">
    <div className="job-connections__heading">
      <div><h2>Insider connections at {job.company}</h2><p>Explore people who may know this team.</p></div>
      <span className="job-connections__tip">A warm introduction starts here</span>
    </div>
    <div className="job-connections__grid">
      {[
        { id: 'beyond', title: 'Beyond your network', icon: 'travel_explore', items: candidates, description: 'Meet people close to the team.', empty: discovery.state === 'pending' ? 'Finding potential contacts for this role…' : 'No hiring contacts found yet. You can still explore the company on LinkedIn.' },
        { id: 'known', title: 'Your connections', icon: 'hub', items: known, description: 'Turn familiar names into a first conversation.', empty: 'Your next introduction could start here. Import your connections to discover people at this company.' },
        { id: 'shared', title: 'Shared background', icon: 'school', items: shared, description: 'A shared school. A former workplace. Common ground.', empty: 'No confirmed overlap yet. Add education and career history to help uncover shared connections.' },
      ].map(card => <div className={`job-connections__card job-connections__card--${card.id} ${expanded === card.id ? 'is-expanded' : ''}`} key={card.id}>
        <button className="job-connections__card-trigger" type="button" aria-expanded={expanded === card.id} aria-controls={`connections-${card.id}`} onClick={() => setExpanded(expanded === card.id ? '' : card.id)}>
          <span className="job-connections__card-top"><span className="material-symbols-outlined">{card.icon}</span><span className="job-connections__count">{card.items.length ? `${card.items.length} ${card.items.length === 1 ? 'person' : 'people'}` : 'Discover'}</span></span>
          <h3>{card.title}</h3><p>{card.description}</p><span className="job-connections__card-action">{expanded === card.id ? 'Close details' : card.items.length ? 'See connections' : 'Explore connections'}<span aria-hidden="true">↗</span></span>
        </button>
        {expanded === card.id ? <div className="job-connections__people" id={`connections-${card.id}`}>{card.items.length ? card.items.map((item, index) => <div key={`${item.contact_id || item.linkedin_url}-${index}`}>{renderPerson(item, index)}{card.id === 'shared' ? <small className="job-connections__shared-label">{item.shared_school ? `School · ${item.shared_school}` : `Previous company · ${item.shared_previous_company}`}</small> : null}</div>) : <div className="job-connections__empty"><p>{card.empty}</p><a href={card.id === 'known' ? '/referrals' : card.id === 'shared' ? '/career-profiles' : `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(job.company)}`}>{card.id === 'known' ? 'Manage connections' : card.id === 'shared' ? 'Update career profile' : 'Explore on LinkedIn'} →</a></div>}{card.id === 'beyond' ? <small>Suggested public profiles; check their current role before reaching out.</small> : null}</div> : null}
      </div>)}
    </div>
    <form className="job-connections__email" onSubmit={(event) => { event.preventDefault(); lookupEmail(); }}>
      <label htmlFor="job-email-profile">Find a work email</label>
      <p className="job-connections__email-benefit"><span>3×</span> <span>Jobright reports higher response rates through work email than LinkedIn.<small>A useful alternative for your referral outreach; results vary. <a href="https://www.linkedin.com/posts/jobright-ai_jobright-jobsearch-opentowork-activity-7246911791543267328-6aEN" target="_blank" rel="noopener noreferrer">Source: Jobright</a></small></span></p>
      <div><input id="job-email-profile" onChange={(event) => setProfileUrl(event.target.value)} placeholder="LinkedIn profile URL" type="url" value={profileUrl} required /><button disabled={emailBusy} type="submit">{emailBusy ? "Searching…" : "Find email"}</button></div>
    </form>
    {emailResult ? <div className="job-connections__result" role="status">
      {emailResult.state === "found" ? <><strong>{emailResult.email}</strong><button onClick={() => navigator.clipboard.writeText(emailResult.email)} type="button">Copy</button></> :
        emailResult.state === "not_found" ? <><span>Contact info not found.</span>{emailResult.person?.linkedin_url ? <button onClick={() => openProfile(emailResult.person)} type="button">Connect on LinkedIn</button> : null}</> :
        <span>{emailResult.state === "unavailable" ? "Email lookup is not available yet." :
          emailResult.state === "limit_reached" ? "Daily email lookup limit reached." :
          emailResult.state === "pending" ? "This lookup is already in progress." : emailResult.message}</span>}
    </div> : null}
    {person ? <div className="job-connections__backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setPerson(null); }}>
      <div aria-label="Connect on LinkedIn" aria-modal="true" className="job-connections__dialog" role="dialog">
        <h2>Connect on LinkedIn</h2>
        <p>Copy this note, then open {person.name}'s profile.</p>
        <textarea aria-label="Connection message" maxLength={200} onChange={(event) => setMessage(event.target.value)} value={message} />
        <small>{message.length} / 200</small>
        <button onClick={async () => { await navigator.clipboard.writeText(message); setCopied(true); }} type="button">{copied ? "Copied" : "Copy message"}</button>
        <div className="job-connections__dialog-actions"><button onClick={() => setPerson(null)} type="button">Cancel</button><a href={person.linkedin_url} rel="noopener noreferrer" target="_blank">View LinkedIn profile</a></div>
      </div>
    </div> : null}
  </section>;
}
