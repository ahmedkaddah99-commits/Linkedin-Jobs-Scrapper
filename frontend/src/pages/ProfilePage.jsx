import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";

const tabs = ["personal", "experience", "education", "preferences", "account"];
const tabLabels = { personal: "Personal", experience: "Experience", education: "Education", preferences: "Preferences", account: "Account" };

function Icon({ children }) { return <span className="material-symbols-outlined" aria-hidden="true">{children}</span>; }
function valueList(value) { return Array.isArray(value) ? value : []; }
function splitList(value) { return String(value || "").split(",").map((item) => item.trim()).filter(Boolean); }
function Field({ label, hint, wide, children }) { return <label className={wide ? "career-field career-field--wide" : "career-field"}><span>{label}</span>{children}{hint ? <small>{hint}</small> : null}</label>; }
function Input({ value, onChange, ...props }) { return <input {...props} onChange={(event) => onChange(event.target.value)} value={value || ""} />; }

export default function ProfilePage() {
  const { request } = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("section") || "personal";
  const [activeTab, setActiveTab] = useState(tabs.includes(requestedTab) ? requestedTab : "personal");
  const [draft, setDraft] = useState(null);
  const [preferences, setPreferences] = useState({});
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const { data, loading, error, refresh } = useApiResource(() => request("/settings"), [], { cacheKey: "settings", staleMs: 30000 });
  const { data: preferenceData, refresh: refreshPreferences } = useApiResource(() => request("/personalized-jobs/preferences"), [], { cacheKey: "job-preferences", staleMs: 30000 });
  const { data: billing } = useApiResource(() => request("/billing/subscription"), [], { cacheKey: "billing-subscription", staleMs: 30000 });

  useEffect(() => { if (data) setDraft(data); }, [data]);
  useEffect(() => { if (preferenceData) setPreferences(preferenceData.preferences || preferenceData); }, [preferenceData]);
  useEffect(() => { const next = searchParams.get("section") || "personal"; if (tabs.includes(next)) setActiveTab(next); }, [searchParams]);

  const profile = draft?.profile || {};
  const account = draft?.account || {};
  const baselinePreferences = preferenceData?.preferences || preferenceData || {};
  const dirty = Boolean(draft && data && JSON.stringify(draft) !== JSON.stringify(data));
  const preferencesDirty = JSON.stringify(preferences) !== JSON.stringify(baselinePreferences);
  const completion = useMemo(() => {
    const values = [profile.name, profile.email || account.email, profile.role_title, profile.industry, profile.location, profile.summary, profile.linkedin_url, valueList(profile.recent_experience).length, valueList(profile.education).length, valueList(preferences.target_roles).length, valueList(preferences.preferred_locations).length];
    return Math.round(values.filter(Boolean).length / values.length * 100);
  }, [account.email, preferences, profile]);

  function updateProfile(patch) { setDraft((current) => ({ ...current, profile: { ...(current?.profile || {}), ...patch } })); setMessage(""); }
  function updateAccount(patch) { setDraft((current) => ({ ...current, account: { ...(current?.account || {}), ...patch } })); setMessage(""); }
  function updatePreference(key, value) { setPreferences((current) => ({ ...current, [key]: value })); setMessage(""); }
  function openTab(tab) { setActiveTab(tab); setSearchParams(tab === "personal" ? {} : { section: tab }); }
  function updateCollection(key, index, patch) { const next = [...valueList(profile[key])]; next[index] = { ...next[index], ...patch }; updateProfile({ [key]: next }); }
  function addCollection(key, item) { updateProfile({ [key]: [...valueList(profile[key]), item] }); }
  function removeCollection(key, index) { updateProfile({ [key]: valueList(profile[key]).filter((_, itemIndex) => itemIndex !== index) }); }

  async function saveChanges() {
    if (!draft) return;
    setSaving(true); setMessage("");
    try {
      if (dirty) await request("/settings", { method: "PUT", body: { profile: draft.profile, account: draft.account } });
      if (preferencesDirty) await request("/personalized-jobs/preferences", { method: "PUT", body: preferences });
      await Promise.all([refresh({ showLoading: false }), refreshPreferences({ showLoading: false })]);
      setMessage("Everything saved");
    } catch (saveError) { setMessage(saveError?.message || "Unable to save changes."); }
    finally { setSaving(false); }
  }

  if (loading && !draft) return <div className="career-profile"><div className="career-loading">Loading your career profile…</div></div>;
  if (error && !draft) return <div className="career-profile"><div className="career-loading">{error}<button onClick={() => refresh()} type="button">Retry</button></div></div>;

  const name = profile.name || account.display_name || "Your profile";
  const initials = name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  return <div className="career-profile">
    <header className="career-heading"><div><span className="career-eyebrow">Your career profile</span><h1>Profile</h1><p>This is the source of truth for matches, autofill, application preparation, and referral context.</p></div><div><button className="career-button career-button--quiet" onClick={() => window.print()} type="button"><Icon>visibility</Icon>Preview profile</button><button className="career-button" disabled={saving || (!dirty && !preferencesDirty)} onClick={saveChanges} type="button"><Icon>save</Icon>{saving ? "Saving…" : "Save changes"}</button></div></header>

    <section className="career-overview"><div className="career-avatar">{initials || "R"}</div><div className="career-identity"><h2>{name}</h2><p>{profile.role_title || "Add your role"} · {profile.location || "Add your location"}</p><span>Profile preview data</span></div><div className="career-completion"><div style={{ "--completion": `${completion * 3.6}deg` }}><strong>{completion}</strong></div><p><b>{completion}% complete</b><span>Add preferences and quantified outcomes to improve matching.</span></p><button onClick={() => openTab("preferences")} type="button">Finish profile</button></div><div className="career-ready"><Icon>verified</Icon><div><b>Match-ready</b><span>Your profile can support evidence-aware ranking.</span></div></div></section>

    <nav className="career-tabs" aria-label="Profile sections">{tabs.map((tab) => <button className={activeTab === tab ? "is-active" : ""} key={tab} onClick={() => openTab(tab)} type="button">{tabLabels[tab]}</button>)}</nav>

    <main className="career-panel">
      {activeTab === "personal" ? <><div className="career-section-head"><div><span className="career-eyebrow">About you</span><h2>Personal details</h2><p>Used for profile context and application autofill.</p></div><span><Icon>cloud_done</Icon>{dirty ? "Unsaved changes" : "Everything saved"}</span></div><div className="career-form-grid">
        <Field label="Display name"><Input onChange={(value) => { updateProfile({ name: value }); updateAccount({ display_name: value }); }} value={profile.name || account.display_name} /></Field>
        <Field label="Profile email"><Input onChange={(value) => updateProfile({ email: value })} type="email" value={profile.email || account.email} /></Field>
        <Field label="Role title"><Input onChange={(value) => updateProfile({ role_title: value })} value={profile.role_title} /></Field>
        <Field label="Industry"><Input onChange={(value) => updateProfile({ industry: value })} value={profile.industry} /></Field>
        <Field label="Location"><Input onChange={(value) => updateProfile({ location: value })} value={profile.location} /></Field>
        <Field label="Website"><Input onChange={(value) => updateProfile({ website: value })} placeholder="https://" value={profile.website} /></Field>
        <Field label="LinkedIn URL"><Input onChange={(value) => updateProfile({ linkedin_url: value })} placeholder="https://linkedin.com/in/" value={profile.linkedin_url} /></Field>
        <Field label="GitHub URL"><Input onChange={(value) => updateProfile({ github_url: value })} placeholder="https://github.com/" value={profile.github_url} /></Field>
        <Field label="Professional headline" hint="Shown in referral and profile previews." wide><Input onChange={(value) => updateProfile({ headline: value })} value={profile.headline || profile.role_title} /></Field>
        <Field label="About" hint="Keep this concise; Runr uses your evidence elsewhere." wide><textarea onChange={(event) => updateProfile({ summary: event.target.value })} rows="5" value={profile.summary || ""} /></Field>
      </div></> : null}

      {activeTab === "experience" ? <><div className="career-section-head"><div><span className="career-eyebrow">Your evidence</span><h2>Experience</h2><p>Give Runr specific outcomes to improve v2 matching and application writing.</p></div><button className="career-button career-button--quiet" onClick={() => addCollection("recent_experience", { title: "", company: "", start_date: "", end_date: "", description: "" })} type="button"><Icon>add</Icon>Add experience</button></div><div className="career-timeline">{valueList(profile.recent_experience).length ? valueList(profile.recent_experience).map((item, index) => <article key={index}><span className="career-timeline__dot"/><div className="career-form-grid"><Field label="Role"><Input onChange={(value) => updateCollection("recent_experience", index, { title: value })} value={item.title || item.role} /></Field><Field label="Company"><Input onChange={(value) => updateCollection("recent_experience", index, { company: value })} value={item.company} /></Field><Field label="Start"><Input onChange={(value) => updateCollection("recent_experience", index, { start_date: value })} value={item.start_date || item.start} /></Field><Field label="End"><Input onChange={(value) => updateCollection("recent_experience", index, { end_date: value })} placeholder="Present" value={item.end_date || item.end} /></Field><Field label="Outcomes and responsibilities" hint="Quantify scope, speed, revenue, savings, or quality where possible." wide><textarea onChange={(event) => updateCollection("recent_experience", index, { description: event.target.value })} rows="4" value={item.description || item.summary || ""}/></Field></div><button className="career-remove" onClick={() => removeCollection("recent_experience", index)} type="button"><Icon>delete</Icon>Remove</button></article>) : <div className="career-empty"><Icon>work_history</Icon><h3>Add your first role</h3><p>Experience evidence helps Runr explain why a job fits—not just which keywords overlap.</p><button className="career-button" onClick={() => addCollection("recent_experience", { title: "", company: "", description: "" })} type="button">Add experience</button></div>}</div></> : null}

      {activeTab === "education" ? <><div className="career-section-head"><div><span className="career-eyebrow">Credentials</span><h2>Education</h2><p>Add degrees, certifications, and relevant programs.</p></div><button className="career-button career-button--quiet" onClick={() => addCollection("education", { institution: "", degree: "", field: "", graduation_year: "" })} type="button"><Icon>add</Icon>Add education</button></div><div className="career-education-grid">{valueList(profile.education).map((item, index) => <article key={index}><Icon>school</Icon><div className="career-form-grid"><Field label="Institution"><Input onChange={(value) => updateCollection("education", index, { institution: value })} value={item.institution || item.school} /></Field><Field label="Degree"><Input onChange={(value) => updateCollection("education", index, { degree: value })} value={item.degree} /></Field><Field label="Field"><Input onChange={(value) => updateCollection("education", index, { field: value })} value={item.field || item.field_of_study} /></Field><Field label="Graduation year"><Input onChange={(value) => updateCollection("education", index, { graduation_year: value })} value={item.graduation_year || item.end_date} /></Field></div><button className="career-remove" onClick={() => removeCollection("education", index)} type="button"><Icon>delete</Icon>Remove</button></article>)}{!valueList(profile.education).length ? <div className="career-empty"><Icon>school</Icon><h3>No education added yet</h3><p>Add formal education or certifications that support your target roles.</p></div> : null}</div></> : null}

      {activeTab === "preferences" ? <><div className="career-section-head"><div><span className="career-eyebrow">Job search</span><h2>Preferences</h2><p>These values power matching and map directly to stable backend keys.</p></div><Link className="career-button career-button--quiet" to="/jobs"><Icon>search</Icon>View matching jobs</Link></div><div className="career-preference-grid">
        <Field label="Target roles" hint="Comma-separated · target_roles"><Input onChange={(value) => updatePreference("target_roles", splitList(value))} value={valueList(preferences.target_roles).join(", ")} /></Field>
        <Field label="Preferred locations" hint="preferred_locations"><Input onChange={(value) => updatePreference("preferred_locations", splitList(value))} value={valueList(preferences.preferred_locations).join(", ")} /></Field>
        <Field label="Workplace" hint="work_arrangements"><select multiple onChange={(event) => updatePreference("work_arrangements", Array.from(event.target.selectedOptions, (option) => option.value))} value={valueList(preferences.work_arrangements)}><option value="remote">Remote</option><option value="hybrid">Hybrid</option><option value="onsite">On-site</option></select></Field>
        <Field label="Employment type" hint="employment_types"><select multiple onChange={(event) => updatePreference("employment_types", Array.from(event.target.selectedOptions, (option) => option.value))} value={valueList(preferences.employment_types)}><option value="full_time">Full-time</option><option value="part_time">Part-time</option><option value="contract">Contract</option><option value="internship">Internship</option></select></Field>
        <Field label="Minimum salary" hint="minimum_salary"><Input min="0" onChange={(value) => updatePreference("minimum_salary", value ? Number(value) : null)} type="number" value={preferences.minimum_salary} /></Field>
        <Field label="Currency" hint="salary_currency"><select onChange={(event) => updatePreference("salary_currency", event.target.value)} value={preferences.salary_currency || "EUR"}><option>EUR</option><option>USD</option><option>GBP</option><option>CHF</option></select></Field>
        <Field label="Work authorization" hint="work_authorization"><Input onChange={(value) => updatePreference("work_authorization", value)} value={preferences.work_authorization} /></Field>
        <Field label="Relocation preference" hint="relocation_preference"><select onChange={(event) => updatePreference("relocation_preference", event.target.value)} value={preferences.relocation_preference || ""}><option value="">Not specified</option><option value="open">Open to relocate</option><option value="not_open">Not open</option><option value="case_by_case">Case by case</option></select></Field>
      </div></> : null}

      {activeTab === "account" ? <><div className="career-section-head"><div><span className="career-eyebrow">Runr account</span><h2>Account</h2><p>Plan, integrations, privacy, and account administration.</p></div></div><div className="career-account-grid"><article><Icon>workspace_premium</Icon><div><span>Current plan</span><h3>{billing?.plan?.display_name || billing?.plan_id || "Free"}</h3><p>Manage billing, quotas, and plan details from Account Settings.</p></div><Link to="/settings">Manage plan</Link></article><article><Icon>link</Icon><div><span>Connected apps</span><h3>Integrations</h3><p>Manage assisted apply and connected services.</p></div><Link to="/settings/assisted-apply">Manage connections</Link></article><article><Icon>shield</Icon><div><span>Privacy</span><h3>Your data and account</h3><p>Review account details or permanently delete your account.</p></div><Link to="/settings">Open account settings</Link></article></div></> : null}
    </main>

    <footer className="career-savebar"><span>{message || (dirty || preferencesDirty ? "Changes stay in this preview until you save." : "Everything saved")}</span><button disabled={!dirty && !preferencesDirty} onClick={() => { setDraft(data); setPreferences(baselinePreferences); setMessage(""); }} type="button">Discard changes</button><button className="career-button" disabled={saving || (!dirty && !preferencesDirty)} onClick={saveChanges} type="button">{saving ? "Saving…" : "Save changes"}</button></footer>
  </div>;
}
