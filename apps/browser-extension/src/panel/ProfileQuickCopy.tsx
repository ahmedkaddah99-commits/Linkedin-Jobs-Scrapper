import { useState } from "react";
import type { CandidateProfile } from "@runr/ats-core/generic-planner";
import { profileDetails, type ProfileDetail } from "./profile-details";

export default function ProfileQuickCopy({ profile, details, answers = false }: { profile?: CandidateProfile; details?: ProfileDetail[]; answers?: boolean }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const rows = (details ?? (profile ? profileDetails(profile) : [])).filter((row) => `${row.section} ${row.label} ${row.value}`.toLowerCase().includes(search.toLowerCase()));
  async function copy(label: string, value: string) {
    try { await navigator.clipboard.writeText(value); setStatus(`${label} copied`); }
    catch { setStatus("Couldn't copy. Select the text and copy it manually."); }
  }
  return <div data-testid="runr-profile-quick-copy">
    {!answers && profile ? <button type="button" className="icon-button" data-testid="runr-panel-copy-profile" onClick={() => void copy("Profile", profileDetails(profile).map((row) => `${row.section} · ${row.label}: ${row.value}`).join("\n"))}>Copy all profile details</button> : null}
    <label className="section-title" htmlFor={answers ? "runr-answer-search" : "runr-profile-search"}>{answers ? "Find an answer" : "Find a profile detail"}</label>
    <input id={answers ? "runr-answer-search" : "runr-profile-search"} className="profile-search" type="search" placeholder={answers ? "Search a question or answer…" : "Search name, skills, experience…"} value={search} onChange={(event) => setSearch(event.target.value)} />
    <ul className="field-list profile-details">{rows.map((row, index) => <li className="profile-detail" key={`${row.section}-${row.label}-${index}`}>
      <span><span className="job-meta">{row.section} · {row.label}</span><span className="profile-value">{row.value}</span></span>
      <button type="button" className="icon-button" onClick={() => void copy(row.label, row.value)} aria-label={`Copy ${row.section} ${row.label}`}>Copy</button>
    </li>)}</ul>
    {!rows.length ? <p className="empty">{search ? "No matching details." : answers ? "No saved answers yet. Add answers in your Runr profile or application review." : "Add your contact details and experience in your Runr profile."}</p> : null}
    {status ? <p className="job-meta" role="status">{status}</p> : null}
  </div>;
}
