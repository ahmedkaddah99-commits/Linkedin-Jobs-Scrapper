import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { employmentQuestions } from "../../lib/profileEditor";
import ProfilePage from "../../pages/ProfilePage";

const sections = [["personal", "Personal"], ["education", "Education"], ["experience", "Work experience"], ["skills", "Skills"], ["employment", "Equal employment"], ["preferences", "Preferences"]];
const items = value => Array.isArray(value) ? value : [];
function Icon({ children }) { return <span className="material-symbols-outlined" aria-hidden="true">{children}</span>; }

export default function ProfileOverview({ settings, preferences, onSaved }) {
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const dialog = useRef(null);
  const opener = useRef(null);
  const profile = settings?.profile || {};
  const [activeSection, setActiveSection] = useState("personal");
  useEffect(() => {
    function trackSection() {
      let current = "personal";
      for (const [id] of sections) {
        if ((document.getElementById(`profile-${id}`)?.getBoundingClientRect().top ?? Infinity) < 170) current = id;
      }
      setActiveSection(current);
    }
    window.addEventListener("scroll", trackSection, true);
    return () => window.removeEventListener("scroll", trackSection, true);
  }, []);
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
    <header className="runr-profile-toolbar"><h1>Profile</h1><div><Link to="/documents">Manage resumes</Link><button className="career-button" onClick={e => edit("complete", e)} type="button">Fill profile</button></div></header>
    <div className="runr-profile-layout"><main>
      <nav aria-label="Profile overview sections">{sections.map(([id, label]) => <a aria-current={activeSection === id ? "location" : undefined} className={activeSection === id ? "is-active" : ""} onClick={() => setActiveSection(id)} href={`#profile-${id}`} key={id}>{label}</a>)}</nav>
      <section id="profile-personal" className="runr-profile-identity"><div className="runr-profile-section-title"><div><h2>{profile.name || settings?.account?.display_name || "Your name"}</h2><p>{profile.headline || profile.role_title || ""}</p></div>{editButton("personal", "personal details")}</div><div className="runr-profile-contact"><span><Icon>location_on</Icon>{profile.location || "Add location"}</span><span><Icon>mail</Icon>{profile.email || settings?.account?.email || "Add email"}</span>{profile.phone ? <span><Icon>call</Icon>{profile.phone}</span> : null}{[profile.website, profile.linkedin_url, profile.github_url].filter(url => /^https?:\/\//.test(url || "")).map(url => <span key={url}><Icon>link</Icon><a href={url} target="_blank" rel="noreferrer">{url}</a></span>)}</div>{profile.summary ? <p className="runr-profile-summary">{profile.summary}</p> : <button className="runr-profile-add" onClick={e => edit("personal", e)} type="button">+ Add a little about yourself</button>}</section>
      <section id="profile-education"><div className="runr-profile-section-title"><h2>Education</h2>{editButton("education", "education")}</div><div className="runr-profile-timeline">{items(profile.education).map((entry, i) => <article key={i}><h3>{entry.institution || entry.school || "Your institution"}</h3><p>{[entry.degree_title || entry.degree, entry.field || entry.field_of_study].filter(Boolean).join(" · ")}</p><small>{[entry.start_date, entry.current ? "Present" : entry.end_date].filter(Boolean).join(" - ") || entry.period || entry.graduation_year}</small></article>)}</div>{!items(profile.education).length ? <button className="runr-profile-add" onClick={e => edit("education", e)} type="button">+ Add education</button> : null}</section>
      <section id="profile-experience"><div className="runr-profile-section-title"><h2>Work experience</h2>{editButton("experience", "work experience")}</div><div className="runr-profile-timeline">{items(profile.recent_experience).map((entry, i) => <article key={i}><h3>{entry.company || "Your company"}</h3><p>{entry.title || entry.role}</p><small>{[entry.start_date || entry.start, entry.current ? "Present" : entry.end_date || entry.end].filter(Boolean).join(" – ")}</small>{entry.description || entry.summary ? <p className="runr-profile-summary">{entry.description || entry.summary}</p> : null}<ul>{items(entry.bullets).map((bullet, j) => <li key={j}>{bullet}</li>)}</ul></article>)}</div>{!items(profile.recent_experience).length ? <button className="runr-profile-add" onClick={e => edit("experience", e)} type="button">+ Add work experience</button> : null}</section>
      <section id="profile-skills"><div className="runr-profile-section-title"><h2>Skills</h2>{editButton("skills", "skills")}</div><div className="runr-profile-tags">{items(profile.competencies).map((skill, i) => <span key={i}>{skill}</span>)}</div>{!items(profile.competencies).length ? <button className="runr-profile-add" onClick={e => edit("skills", e)} type="button">+ Add your skills</button> : null}</section>
      <section id="profile-employment"><div className="runr-profile-section-title"><h2>Equal employment</h2>{editButton("employment", "equal employment")}</div><dl className="profile-employment-summary">{employmentQuestions.map(([key, question]) => <div key={key}><dt>{question}</dt><dd>{profile.application_details?.[key] || "Not provided"}</dd></div>)}</dl></section>
      <section id="profile-preferences"><div className="runr-profile-section-title"><h2>Job preferences</h2>{editButton("preferences", "preferences")}</div><p>{items(preferences.target_roles).join(" · ") || "Choose your target roles"}</p><small>{items(preferences.preferred_locations).join(" · ") || "Choose where you want to work"}</small></section>
    </main></div>
    {editing ? <dialog ref={dialog} className={`runr-profile-editor ${editing === "complete" ? "runr-profile-editor--complete" : ""}`} aria-label={editing === "complete" ? "Fill profile" : "Edit profile section"} onCancel={() => setEditing(null)}><header><h2>{editing === "complete" ? "Fill your profile" : sections.find(([id]) => id === editing)?.[1]}</h2>{editing !== "complete" ? <button className="profile-header-update" disabled={busy} form="profile-section-editor-form" type="submit">{busy ? "Please wait..." : "Update"}</button> : null}<button aria-label="Close profile editor" onClick={() => setEditing(null)} type="button"><Icon>close</Icon></button></header><ProfilePage completionFlow={editing === "complete"} editor onBusy={setBusy} initialSection={editing === "complete" ? "personal" : editing} onSaved={(saved, prefs) => { onSaved(saved, prefs); setEditing(null); }} /></dialog> : null}
  </div>;
}
