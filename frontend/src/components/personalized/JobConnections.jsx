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

  useEffect(() => {
    setEmailResult(null);
    setProfileUrl("");
    setPerson(null);
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
      <span className="job-connection-avatar">{String(item.name || "?").slice(0, 1).toUpperCase()}</span>
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
      <span className="job-connections__tip" tabIndex="0" title="A work email gives you another way to reach out. Response rates vary. A provider credit is used only when an email is found.">ⓘ Email or LinkedIn?</span>
    </div>
    <div className="job-connections__grid">
      <div className="job-connections__card job-connections__card--beyond">
        <h3>Beyond your network</h3>
        {candidates.length ? candidates.map(renderPerson) : <p>{discovery.state === "pending" ? "Finding likely hiring contacts…" : "No likely hiring contact found yet."}</p>}
        <small>Public profile matches are suggestions. Check each profile before reaching out.</small>
      </div>
      <div className="job-connections__card job-connections__card--known">
        <h3>Your connections</h3>
        {known.length ? known.slice(0, 5).map(renderPerson) : <p>No saved connection at this company yet.</p>}
      </div>
      <div className="job-connections__card job-connections__card--shared">
        <h3>Shared background</h3>
        {shared.length ? shared.slice(0, 5).map((item, index) => <div key={`${item.contact_id}-${index}`}>{renderPerson(item, index)}<small>{item.shared_school || item.shared_previous_company}</small></div>) : <p>No confirmed school or previous company link yet.</p>}
      </div>
    </div>
    <form className="job-connections__email" onSubmit={(event) => { event.preventDefault(); lookupEmail(); }}>
      <label htmlFor="job-email-profile">Find a work email</label>
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
