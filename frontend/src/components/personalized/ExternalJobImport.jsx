import { useEffect, useRef, useState } from "react";
import CHOICES from "../../../../backend/domain/job_filter_choices.json";

const EMPTY = { url: "", title: "", company: "", location: "", description: "", employment_type: "", experience_level: "", work_arrangement: "" };

export default function ExternalJobImport({ request, onImported, connected }) {
  const [fields, setFields] = useState(EMPTY);
  const [manual, setManual] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [duplicate, setDuplicate] = useState("");
  const duplicateDialog = useRef(null);
  const dialog = useRef(null);
  const opener = useRef(null);
  useEffect(() => {
    if (!duplicate) return;
    const element = duplicateDialog.current;
    element.showModal();
    return () => { element.close(); opener.current?.focus(); };
  }, [duplicate]);
  useEffect(() => {
    if (!manual) return;
    const element = dialog.current;
    element.showModal();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { element.close(); document.body.style.overflow = previousOverflow; opener.current?.focus(); };
  }, [manual]);
  function change(name, value) {
    setFields(current => ({ ...current, [name]: value }));
    if (name === "url") { setManual(false); setMessage(""); setError(""); }
  }
  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await request("/personalized-jobs/import", { method: "POST", body: manual ? { ...fields, manual: true } : { url: fields.url, preview: true }, timeoutMs: 120000 });
      if (result.state === "duplicate") {
        setManual(false);
        setDuplicate(result.message);
      } else if (result.state === "review_required" || result.state === "manual_required") {
        setFields({ ...EMPTY, ...result.fields });
        setManual(true);
        setMessage(result.message);
      } else if (result.job?.canonical_job_id) {
        onImported(result.job);
        setFields(EMPTY);
        setManual(false);
        setMessage("");
      } else {
        setError("Unable to add this job. Try again.");
      }
    } catch (failure) {
      setError(failure?.message || "Unable to add this job. Try again.");
      if (!manual) { setManual(true); setMessage("Unable to fetch this job from the URL. Complete the job details below."); }
    } finally { setBusy(false); }
  }
  return <div><form className="external-job-import" onSubmit={submit}>
    <label htmlFor="external-job-url">Job URL</label>
    <div className="external-job-import__url"><input autoComplete="url" disabled={busy} id="external-job-url" maxLength={2048} onChange={event => change("url", event.target.value)} placeholder="Paste a job posting URL" required type="url" value={fields.url} /><button className="jobs-primary-button" disabled={!connected || busy} ref={opener} type="submit">{busy ? "Loading job…" : "Add job"}</button></div>
    {busy ? <p aria-live="polite" role="status">Fetching the posting and preparing its details…</p> : null}
    {error && !manual ? <p className="external-job-import__error" role="alert">{error}</p> : null}
  </form>
    {manual ? <dialog aria-labelledby="external-job-review-title" className="external-job-review" onCancel={event => { event.preventDefault(); if (!busy) setManual(false); }} ref={dialog}><form className="external-job-import" onSubmit={submit}>
      <header><div><h2 id="external-job-review-title">Review job details</h2><p>Check the details, then save this job.</p></div><button aria-label="Close job review" className="jobs-text-link" disabled={busy} onClick={() => setManual(false)} type="button">×</button></header>
      {message ? <p role="status">{message}</p> : null}
      {error ? <p className="external-job-import__error" role="alert">{error}</p> : null}
      <fieldset disabled={busy}>
      <div className="external-job-import__fields">{[["title", "Job title", 200, true], ["company", "Company", 200, false], ["location", "Location", 300, false]].map(([name, label, limit, required]) => <label key={name}>{label}<input maxLength={limit} minLength={required ? 2 : undefined} onChange={event => change(name, event.target.value)} required={required} value={fields[name]} /></label>)}
      {[["employment_type", "Job type", "employmentType"], ["experience_level", "Experience level", "experienceLevel"], ["work_arrangement", "Work model", "workArrangement"]].map(([name, label, choices]) => <label key={name}>{label}<select onChange={event => change(name, event.target.value)} value={fields[name]}><option value="">Unspecified</option>{CHOICES[choices].map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>)}</div>
      <label>Job description<textarea maxLength={50000} minLength={100} onChange={event => change("description", event.target.value)} required rows={8} value={fields.description} /></label>
      <small>{fields.description.length.toLocaleString()}/50,000 characters · minimum 100</small>
    </fieldset><footer><button className="jobs-outline-button" disabled={busy} onClick={() => setManual(false)} type="button">Cancel</button><button className="jobs-primary-button" disabled={busy} type="submit">{busy ? "Saving job…" : "Save job"}</button></footer>
    </form></dialog> : null}
    {duplicate ? <dialog aria-labelledby="external-job-duplicate-title" className="external-job-duplicate" onCancel={() => setDuplicate("")} ref={duplicateDialog}><h2 id="external-job-duplicate-title">Job already exists</h2><p>{duplicate}</p><button className="jobs-primary-button" onClick={() => setDuplicate("")} type="button">OK</button></dialog> : null}
  </div>;
}
