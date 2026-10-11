import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import ProfilePage from "../../pages/ProfilePage";
import { profileMissingFields } from "../../lib/profileCompletion";

const sections = [["personal", "Personal"], ["education", "Education"], ["experience", "Work experience"], ["skills", "Skills"], ["preferences", "Preferences"]];
const items = value => Array.isArray(value) ? value : [];
function Icon({ children }) { return <span className="material-symbols-outlined" aria-hidden="true">{children}</span>; }

export default function ProfileOverview({ settings, preferences, onSaved }) {
  const [editing, setEditing] = useState(null);
  const dialog = useRef(null);
  const opener = useRef(null);
  const profile = settings?.profile || {};
  const missing = profileMissingFields(settings, preferences);
  useEffect(() => {
    if (!editing) return;
    const element = dialog.current;
    element.showModal();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { element.close(); document.body.style.overflow = overflow; opener.current?.focus(); };
  }, [editing]);
  function edit(section, event) { opener.current = event.currentTarget; setEditing(section); }
  function editButton(section, label) { return <button aria-label={`Edit ${label}`} onClick={event => edit(section, event)} type="button"><Icon>edit</Icon></button>; }
  return <div className="runr-profile-overview">
    <header><div><span className="runr-profile-eyebrow">YOUR PROFILE</span><h1>Make your next move.</h1><p>Your experience, ready for better matches and easier applications.</p></div><Link to="/jobs">Back to jobs<Icon>arrow_forward</Icon></Link></header>
    <div className="runr-profile-layout"><main>
      <div className="runr-profile-privacy"><Icon>verified_user</Icon>Your profile is private and secure.</div>
      <nav aria-label="Profile overview sections">{sections.map(([id, label]) => <a href={`#profile-${id}`} key={id}>{label}</a>)}</nav>
      <section id="profile-personal" className="runr-profile-identity"><div className="runr-profile-section-title"><div><h2>{profile.name || settings?.account?.display_name || "Your name"}</h2><p>{profile.headline || profile.role_title || "Add your professional headline"}</p></div>{editButton("personal", "personal details")}</div><div className="runr-profile-contact"><span><Icon>location_on</Icon>{profile.location || "Add location"}</span><span><Icon>mail</Icon>{profile.email || settings?.account?.email || "Add email"}</span></div>{profile.summary ? <p className="runr-profile-summary">{profile.summary}</p> : <button className="runr-profile-add" onClick={e => edit("personal", e)} type="button">+ Add a little about yourself</button>}</section>
      <section id="profile-education"><div className="runr-profile-section-title"><h2>Education</h2>{editButton("education", "education")}</div><div className="runr-profile-timeline">{items(profile.education).map((entry, i) => <article key={i}><h3>{entry.institution || entry.school || "Your institution"}</h3><p>{[entry.degree, entry.field || entry.field_of_study].filter(Boolean).join(" · ")}</p><small>{entry.graduation_year || entry.end_date}</small></article>)}</div>{!items(profile.education).length ? <button className="runr-profile-add" onClick={e => edit("education", e)} type="button">+ Add education</button> : null}</section>
      <section id="profile-experience"><div className="runr-profile-section-title"><h2>Work experience</h2>{editButton("experience", "work experience")}</div><div className="runr-profile-timeline">{items(profile.recent_experience).map((entry, i) => <article key={i}><h3>{entry.company || "Your company"}</h3><p>{entry.title || entry.role}</p><small>{[entry.start_date || entry.start, entry.end_date || entry.end || "Present"].filter(Boolean).join(" – ")}</small><p className="runr-profile-summary">{entry.description || entry.summary}</p></article>)}</div>{!items(profile.recent_experience).length ? <button className="runr-profile-add" onClick={e => edit("experience", e)} type="button">+ Add work experience</button> : null}</section>
      <section id="profile-skills"><div className="runr-profile-section-title"><h2>Skills</h2>{editButton("personal", "skills")}</div><div className="runr-profile-tags">{items(profile.competencies).map((skill, i) => <span key={i}>{skill}</span>)}</div>{!items(profile.competencies).length ? <button className="runr-profile-add" onClick={e => edit("personal", e)} type="button">+ Add your skills</button> : null}</section>
      <section id="profile-preferences"><div className="runr-profile-section-title"><h2>Job preferences</h2>{editButton("preferences", "preferences")}</div><p>{items(preferences.target_roles).join(" · ") || "Choose your target roles"}</p><small>{items(preferences.preferred_locations).join(" · ") || "Choose where you want to work"}</small></section>
    </main><aside aria-label="Profile actions"><Icon>person_check</Icon><h2>Your next opportunity starts here.</h2><p>{missing.length ? `${missing.length} details left to help Runr understand your experience.` : "Your profile is ready. Keep it current as your career grows."}</p><progress aria-label="Profile completion" max="11" value={11 - missing.length} /><button className="career-button" onClick={e => edit("complete", e)} type="button">Fill profile<Icon>arrow_forward</Icon></button><Link to="/documents"><Icon>description</Icon>Manage my resumes</Link><button onClick={e => edit("personal", e)} type="button"><Icon>link</Icon>Update LinkedIn URL</button></aside></div>
    {editing ? <dialog ref={dialog} className={`runr-profile-editor ${editing === "complete" ? "runr-profile-editor--complete" : ""}`} aria-label={editing === "complete" ? "Fill profile" : "Edit profile section"} onCancel={() => setEditing(null)}><header><h2>{editing === "complete" ? "Fill your profile" : sections.find(([id]) => id === editing)?.[1]}</h2><button aria-label="Close profile editor" onClick={() => setEditing(null)} type="button"><Icon>close</Icon></button></header><ProfilePage completionFlow={editing === "complete"} editor initialSection={editing === "complete" ? "personal" : editing} onSaved={(saved, prefs) => { onSaved(saved, prefs); setEditing(null); }} /></dialog> : null}
  </div>;
}
