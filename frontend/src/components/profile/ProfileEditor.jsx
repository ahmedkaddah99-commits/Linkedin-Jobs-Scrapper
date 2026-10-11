import { useEffect, useRef, useState } from "react";
import { useSession } from "../../context/SessionContext";
import { clearApiResourceCache, useApiResource } from "../../hooks/useApiResource";
import { employmentQuestions, educationRecord, list, profileSectionLabels, profileSections, profileWithResumeDefaults, readyResume } from "../../lib/profileEditor";
import { BulletEditor, Chips, Choices, Field, TextField } from "./ProfileFields";

export default function ProfileEditor({ completionFlow, initialSection = "personal", onSaved, onBusy }) {
  const { request } = useSession();
  const settings = useApiResource(() => request("/settings"), [], { cacheKey: "settings", staleMs: 30000 });
  const prefs = useApiResource(() => request("/personalized-jobs/preferences"), [], { cacheKey: "job-preferences", staleMs: 30000 });
  const [profile, setProfile] = useState(null);
  const [preferences, setPreferences] = useState(null);
  const [section, setSection] = useState(initialSection);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");
  const [source, setSource] = useState("");
  const panel = useRef(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { if (settings.data) setProfile(current => current || profileWithResumeDefaults(settings.data)); }, [settings.data]);
  useEffect(() => { if (prefs.data) setPreferences(current => current || prefs.data.preferences || prefs.data); }, [prefs.data]);
  useEffect(() => { panel.current?.closest("dialog")?.scrollTo({ top: 0 }); panel.current?.focus({ preventScroll: true }); }, [section]);
  useEffect(() => { onBusy?.(saving || uploading || !profile || !preferences); return () => onBusy?.(false); }, [saving, uploading, profile, preferences, onBusy]);
  const resume = readyResume(settings.data);
  function update(patch) { setProfile(current => ({ ...current, ...patch })); setMessage(""); }
  function preference(key, value) { setPreferences(current => ({ ...current, [key]: value })); setMessage(""); }
  function record(key, index, patch) { update({ [key]: list(profile[key]).map((old, i) => i === index ? { ...old, ...patch } : old) }); }
  function remove(key, index) { update({ [key]: list(profile[key]).filter((_, i) => i !== index) }); }
  async function save() {
    if (!profile || !preferences || prefs.error || saving || uploading) return;
    for (const entry of [...list(profile.education), ...list(profile.recent_experience)]) {
      if (entry.start_date && entry.end_date && entry.start_date > entry.end_date) { setMessage("End date must be after the start date."); return; }
    }
    setSaving(true); setMessage("");
    try {
      const fields = Object.keys(profile).filter(key => JSON.stringify(profile[key]) !== JSON.stringify(settings.data?.profile?.[key]));
      const saved = await request("/settings", { method: "PUT", body: { profile, profile_edited_fields: fields } });
      const savedPreferences = await request("/personalized-jobs/preferences", { method: "PUT", body: preferences });
      settings.setData(saved); prefs.setData(savedPreferences);
      onSaved?.(saved, savedPreferences);
      if (alive.current) setMessage("Saved");
    } catch (error) { if (alive.current) setMessage(error.message || "Unable to save. Please try again."); }
    finally { if (alive.current) setSaving(false); }
  }
  async function upload(file) {
    if (!file) return;
    setUploading(true); setUploadStatus("Uploading resume...");
    try {
      const body = new FormData(); body.append("document_file", file);
      const uploaded = await request(`/documents/upload?${new URLSearchParams({ asset_kind: "workspace_cv", display_name: file.name, purposes: "extract_career_facts,include_in_applications" })}`, { method: "POST", body });
      clearApiResourceCache("documents:all");
      if (uploaded.status_url) {
        for (let attempt = 0; attempt < 60 && alive.current; attempt++) {
          setUploadStatus("Reading your resume...");
          const result = await request(uploaded.status_url.replace(/^\/v1/, ""));
          if (result.status === "failed") throw new Error(result.error || "Could not read this resume.");
          if (result.status === "ready") { update({ ...result.parsed }); setSource(file.name); await settings.refresh({ showLoading: false }); setUploadStatus("Resume details added. Review them before saving."); return; }
          await new Promise(resolve => setTimeout(resolve, 2000));
        }
        if (alive.current) setUploadStatus("Your resume is still processing. Reopen your profile shortly to review the extracted details.");
      } else {
        const parsed = uploaded.parsed || uploaded.asset?.metadata?.parsed_profile;
        if (parsed && Object.keys(parsed).length) { update(parsed); setSource(file.name); setUploadStatus("Resume details added. Review them before saving."); }
        else setUploadStatus(`${file.name} uploaded. Your resume is available in Documents.`);
      }
    } catch (error) { if (alive.current) setUploadStatus(error.message || "Unable to upload resume."); }
    finally { if (alive.current) setUploading(false); }
  }
  if (!profile || !preferences) return <div className="profile-editor-state" role="status">{settings.error || prefs.error || "Loading profile..."}{settings.error || prefs.error ? <button onClick={() => { settings.refresh().catch(() => {}); prefs.refresh().catch(() => {}); }} type="button">Retry</button> : null}</div>;
  const tf = (label, key, props = {}) => <TextField label={label} value={profile[key]} onChange={value => update({ [key]: value })} {...props} />;
  return <form id="profile-section-editor-form" className="profile-reference-editor" onSubmit={event => { event.preventDefault(); void save(); }}>
    {completionFlow ? <nav aria-label="Profile sections" className="profile-reference-steps">{profileSections.map((key, index) => <button aria-current={section === key ? "step" : undefined} className={section === key ? "is-active" : ""} onClick={() => setSection(key)} key={key} type="button"><span>{index + 1}</span>{profileSectionLabels[key]}</button>)}</nav> : null}
    <main tabIndex="-1" ref={panel} aria-label={`${profileSectionLabels[section]} details`}>
      {prefs.error ? <p role="alert">{prefs.error}<button onClick={() => prefs.refresh().catch(() => {})} type="button">Retry preferences</button></p> : null}
      {section === "personal" ? <><div className="profile-edit-source"><label>Upload resume<input aria-label="Upload resume" type="file" accept=".pdf,.doc,.docx,.txt" disabled={uploading} onChange={e => { void upload(e.target.files?.[0]); e.target.value = ""; }} /></label>{resume ? <button type="button" onClick={() => { update({ ...resume.metadata.parsed_profile }); setSource(resume.display_name); }}>Use details from {resume.display_name || "uploaded resume"}</button> : null}<span role="status">{uploadStatus || (source ? `Reviewing ${source}` : "")}</span></div><h3>Personal details</h3><div className="profile-edit-grid">{tf("Display name", "name")}{tf("Profile email", "email", { type: "email" })}{tf("Phone", "phone", { type: "tel" })}{tf("Location", "location")}{tf("Role title", "role_title")}{tf("Industry", "industry")}{tf("LinkedIn URL", "linkedin_url", { type: "url", wide: true })}{tf("Website", "website", { type: "url" })}{tf("GitHub URL", "github_url", { type: "url" })}<Field label="About" wide><textarea rows="4" value={profile.summary || ""} onChange={e => update({ summary: e.target.value })} /></Field></div></> : null}
      {section === "education" ? <><h3>Education</h3>{list(profile.education).map((raw, i) => { const entry = educationRecord(raw); const change = patch => record("education", i, { ...entry, ...patch }); return <section className="profile-edit-record" key={i}><header><h4>Education {i + 1}</h4><button aria-label={`Remove education ${i + 1}`} onClick={() => remove("education", i)} type="button">×</button></header><div className="profile-edit-grid"><TextField label="Institution" wide value={entry.institution} onChange={institution => change({ institution })} /><TextField label="Major" value={entry.field} onChange={field => change({ field })} /><TextField label="Degree" value={entry.degree_title} onChange={degree_title => change({ degree_title })} /><TextField label="GPA" value={entry.gpa} onChange={gpa => change({ gpa })} /><TextField label="Start date" type="month" value={entry.start_date} onChange={start_date => change({ start_date })} /><TextField label="End date" type="month" value={entry.end_date} onChange={end_date => change({ end_date })} />{entry.period && !entry.start_date ? <TextField label="Dates from resume" value={entry.period} onChange={period => change({ period })} /> : null}</div><label className="profile-current"><input type="checkbox" checked={Boolean(entry.current)} onChange={e => change({ current: e.target.checked, end_date: e.target.checked ? "" : entry.end_date })} />I currently study here</label></section>; })}<button className="profile-edit-add" onClick={() => update({ education: [...list(profile.education), { institution: "", degree_title: "", field: "", start_date: "", end_date: "" }] })} type="button">+ Add education</button></> : null}
      {section === "experience" ? <><h3>Work experience</h3>{list(profile.recent_experience).map((entry, i) => { const change = patch => record("recent_experience", i, patch); return <section className="profile-edit-record" key={i}><header><h4>Work experience {i + 1}</h4><button aria-label={`Remove experience ${i + 1}`} onClick={() => remove("recent_experience", i)} type="button">×</button></header><div className="profile-edit-grid"><TextField label="Role" wide value={entry.title || entry.role} onChange={title => change({ title, role: title })} /><TextField label="Company" wide value={entry.company} onChange={company => change({ company })} /><Field label="Job type"><select value={entry.job_type || ""} onChange={e => change({ job_type: e.target.value })}><option value="">Select job type</option><option>Full-time</option><option>Part-time</option><option>Contract</option><option>Internship</option><option>Self-employed</option></select></Field><TextField label="Location" value={entry.location} onChange={location => change({ location })} /><TextField label="Industry" value={entry.industry} onChange={industry => change({ industry })} /><TextField label="Start date" type="month" value={entry.start_date} onChange={start_date => change({ start_date })} /><TextField label="End date" type="month" value={entry.end_date} onChange={end_date => change({ end_date })} />{entry.period && !entry.start_date ? <TextField label="Dates from resume" value={entry.period} onChange={period => change({ period })} /> : null}<Field label="Experience summary" wide><textarea rows="3" value={entry.description || ""} onChange={e => change({ description: e.target.value })} /></Field></div><label className="profile-current"><input type="checkbox" checked={Boolean(entry.current)} onChange={e => change({ current: e.target.checked, end_date: e.target.checked ? "" : entry.end_date })} />I currently work here</label><BulletEditor values={list(entry.bullets)} onChange={bullets => change({ bullets, bulletsText: bullets.join("\n") })} /></section>; })}<button className="profile-edit-add" onClick={() => update({ recent_experience: [...list(profile.recent_experience), { title: "", company: "", start_date: "", end_date: "", bullets: [] }] })} type="button">+ Add experience</button></> : null}
      {section === "skills" ? <><h3>Skills</h3><Chips label="Skills" values={list(profile.competencies)} onChange={competencies => update({ competencies })} /></> : null}
      {section === "employment" ? <><h3>Equal employment</h3><p className="profile-edit-optional">Optional. Choose what you want to share for applications.</p>{employmentQuestions.map(([key, label, options]) => <fieldset className="profile-choice-field" key={key}><legend>{label}</legend>{options.map(value => <button aria-pressed={profile.application_details?.[key] === value} key={value} onClick={() => update({ application_details: { ...(profile.application_details || {}), [key]: profile.application_details?.[key] === value ? "" : value } })} type="button">{value}</button>)}</fieldset>)}</> : null}
      {section === "preferences" ? <><h3>Preferences</h3><Chips label="Target roles" values={list(preferences.target_roles)} onChange={value => preference("target_roles", value)} /><Chips label="Preferred locations" values={list(preferences.preferred_locations)} onChange={value => preference("preferred_locations", value)} /><Choices label="Workplace" values={list(preferences.work_arrangements)} options={[["remote", "Remote"], ["hybrid", "Hybrid"], ["onsite", "On-site"]]} onChange={value => preference("work_arrangements", value)} /><Choices label="Employment type" values={list(preferences.employment_types)} options={[["full_time", "Full-time"], ["part_time", "Part-time"], ["contract", "Contract"], ["internship", "Internship"]]} onChange={value => preference("employment_types", value)} /><div className="profile-edit-grid"><TextField label="Work authorization" value={preferences.work_authorization} onChange={value => preference("work_authorization", value)} /><Field label="Relocation"><select value={preferences.relocation_preference || ""} onChange={e => preference("relocation_preference", e.target.value)}><option value="">Select preference</option><option value="open">Open to relocate</option><option value="not_open">Not open</option><option value="case_by_case">Case by case</option></select></Field></div></> : null}
    </main>
    <footer><span role="status">{message}</span>{completionFlow && section !== profileSections[0] ? <button disabled={saving || uploading} onClick={() => setSection(profileSections[profileSections.indexOf(section) - 1])} type="button">Back</button> : null}{completionFlow && section !== profileSections.at(-1) ? <button className="profile-edit-primary" disabled={saving || uploading} onClick={() => setSection(profileSections[profileSections.indexOf(section) + 1])} type="button">Next</button> : completionFlow ? <button className="profile-edit-primary" disabled={saving || uploading || Boolean(prefs.error)} onClick={save} type="button">{saving ? "Saving..." : "Save and close"}</button> : null}</footer>
  </form>;
}
