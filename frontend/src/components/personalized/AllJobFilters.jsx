import { loadCityOptions } from "../../lib/locationOptions";
import { jobFilterSummary } from "../../lib/jobFilterSummary";
import JOB_FUNCTIONS from "../../../../backend/domain/job_function_taxonomy.json";
import { useEffect, useId, useRef, useState } from "react";

const SECTIONS = ["Basic Job Criteria", "Compensation & Sponsorship", "Areas of Interests", "Company Insights"];
const FUNCTIONS = JOB_FUNCTIONS;
const SECTION_HINTS = ["Job Function / Job Type / Work Model", "Annual Salary / Work Authorization", "Industry / Skill / Role Type", "Company / Stage / Job Source"];

import CHOICES from "../../../../backend/domain/job_filter_choices.json";
import COUNTRIES from "../../../../backend/domain/job_filter_countries.json";
import { INITIAL_PERSONALIZED_JOB_FILTERS } from "../../lib/personalizedJobsApi";
export { CHOICES };

const asList = (value) => Array.isArray(value) ? value : value && value !== "all" ? [value] : [];

export function MultiChoice({ label, name, options, filters, set }) {
  const selected = asList(filters[name]);
  return <div className="runr-filter-card"><strong>{label}<button className="runr-filter-clear" onClick={() => set(name, [])} type="button">Clear all</button></strong><div className="runr-filter-options">{options.map(([value, text]) => <label key={value}><input checked={selected.includes(value)} onChange={() => set(name, selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value])} type="checkbox" />{text}</label>)}</div></div>;
}

export function TagField({ label, name, filters, set, suggestions = [], request }) {
  const [input, setInput] = useState("");
  const [active, setActive] = useState(-1);
  const [expanded, setExpanded] = useState(false);
  const id = useId();
  const [remoteOptions, setRemoteOptions] = useState([]);
  useEffect(() => {
    if (!request || !["company", "hiddenCompanies"].includes(name)) return;
    let current = true;
    const timer = setTimeout(() => { request(`/personalized-jobs/companies?q=${encodeURIComponent(input)}`).then((result) => { if (current) setRemoteOptions((result.companies || []).map((company) => company.name)); }).catch(() => { if (current) setRemoteOptions([]); }); }, 250);
    return () => { current = false; clearTimeout(timer); };
  }, [input, name, request]);
  const allowed = ["company", "hiddenCompanies"].includes(name) ? remoteOptions : suggestions;
  const values = asList(filters[name]);
  const options = allowed.filter((item) => !values.includes(item) && item.toLowerCase().includes(input.trim().toLowerCase())).sort((a, b) => Number(!a.toLowerCase().startsWith(input.toLowerCase())) - Number(!b.toLowerCase().startsWith(input.toLowerCase()))).slice(0, 12);
  const strict = !["excludedTitle"].includes(name);
  const add = (value) => {
    const chosen = strict ? allowed.find((item) => item.toLowerCase() === value.trim().toLowerCase()) : value.trim();
    if (!chosen || values.includes(chosen)) return;
    set(name, [...values, chosen]); setInput(""); setActive(-1); setExpanded(false);
  };
  const accept = () => add(options[Math.max(0, Math.min(active, options.length - 1))] || (strict ? "" : input));
  return <div className="runr-filter-card"><strong>{label}<button className="runr-filter-clear" onClick={() => set(name, [])} type="button">Clear all</button></strong><div className="runr-filter-tags">{values.map((value) => <button key={value} onClick={() => set(name, values.filter((item) => item !== value))} type="button">{value} {"\u00d7"}</button>)}</div><div className="runr-filter-add"><input aria-label={label} role={strict ? "combobox" : undefined} aria-autocomplete={strict ? "list" : undefined} aria-controls={strict ? id : undefined} aria-expanded={strict ? expanded : undefined} aria-activedescendant={expanded && options.length ? `${id}-${Math.max(0, Math.min(active, options.length - 1))}` : undefined} onFocus={() => setExpanded(true)} onChange={(event) => { setInput(event.target.value); setActive(-1); setExpanded(true); }} onKeyDown={(event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setExpanded(true); setActive((index) => Math.max(0, Math.min(options.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)))); }
    if (event.key === "Enter") { event.preventDefault(); accept(); }
    if (event.key === "Escape" && expanded) { event.stopPropagation(); setExpanded(false); }
  }} placeholder={`Select ${label.toLowerCase()}`} value={input} /><button disabled={strict && !options.length} onClick={accept} type="button">Add</button></div>{expanded && strict ? <div className="runr-filter-suggestions" id={id} role="listbox" aria-label={`${label} suggestions`}>{options.map((item, index) => <button aria-selected={index === active} id={`${id}-${index}`} role="option" key={item} onMouseEnter={() => setActive(index)} onClick={() => add(item)} type="button">{item}</button>)}{!options.length ? <span>No matching options</span> : null}</div> : null}</div>;
}

export default function AllJobFilters({ filters, initialSection = SECTIONS[0], initialSave = false, request, onApply, onClose }) {
  const [save, setSave] = useState(initialSave);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const confirm = async () => { if (save && !name.trim()) { setError("Enter a filter name."); return; } setBusy(true); try { const ok = await onApply(draft, save ? name.trim() : ""); if (ok === false) setError("Unable to save. Try again."); } finally { setBusy(false); } };
  const dialog = useRef(null);
  const [draft, setDraft] = useState(() => ({ ...filters }));
  const [section, setSection] = useState(initialSection);

  useEffect(() => {
    if (initialSection !== SECTIONS[0]) document.getElementById(`runr-filter-${SECTIONS.indexOf(initialSection)}`)?.scrollIntoView({ block: "start" });
  }, [initialSection]);
  useEffect(() => {
    const previous = document.activeElement;
    const node = dialog.current;
    node?.querySelector("button")?.focus();
    const keyboard = (event) => {
      if (event.key === "Escape") { event.preventDefault(); onClose(); }
      if (event.key !== "Tab") return;
      const focusable = [...node.querySelectorAll('button:not(:disabled), input, select, [tabindex="0"]')];
      const first = focusable[0], last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    node?.addEventListener("keydown", keyboard);
    return () => { node?.removeEventListener("keydown", keyboard); previous?.focus(); };
  }, []);
  const invalid = draft.requiredExperienceMin !== "" && draft.requiredExperienceMax !== "" && Number(draft.requiredExperienceMin) > Number(draft.requiredExperienceMax);
  const set = (key, value) => setDraft((current) => ({ ...current, [key]: value }));
  const tags = jobFilterSummary(draft);
  const removeTag = (key, item) => set(key, Array.isArray(draft[key]) ? draft[key].filter((value) => value !== item) : typeof draft[key] === "boolean" ? false : key === "datePosted" ? "all" : "");
  return <div className="jobs-filter-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><aside ref={dialog} aria-label="All Filters" aria-modal="true" className="runr-all-filters" role="dialog">
    <header><button aria-label="Close filters" onClick={onClose} type="button">‹</button><h2>All Filters</h2><Toggle label="Confirm and save" checked={save} onChange={setSave} /><button className="jobs-primary-button runr-filter-confirm" disabled={invalid || busy} onClick={confirm} type="button">Confirm</button></header>
    {save ? <label className="runr-save-name">Filter name<input maxLength={80} aria-label="Filter name" value={name} onChange={(event) => { setName(event.target.value); setError(""); }} /></label> : null}
    {error ? <p role="alert">{error}</p> : null}
    {tags.length ? <div className="runr-filter-summary">{tags.map(({key, value: item, label}) => <button key={`${key}-${item}`} onClick={() => removeTag(key, item)} type="button">{label} ×</button>)}</div> : null}
    <div className="runr-filter-layout"><nav aria-label="Filter sections">{SECTIONS.map((name, index) => <button className={section === name ? "is-active" : ""} key={name} onClick={() => { setSection(name); document.getElementById(`runr-filter-${SECTIONS.indexOf(name)}`)?.scrollIntoView({ block: "start", behavior: "smooth" }); }} type="button">{name}<small>{SECTION_HINTS[index]}</small></button>)}<p className="runr-filter-help">Applying for specific companies? Use Company Insights to choose employers and exclude staffing agencies.</p></nav><div className="runr-filter-content" onScroll={(event) => { const nodes = [...event.currentTarget.querySelectorAll("section[id]")]; const visible = nodes.filter((node) => node.getBoundingClientRect().top < 300).at(-1); if (visible) setSection(visible.dataset.name); }}>
      <section data-name={SECTIONS[0]} id="runr-filter-0"><h3>Basic Job Criteria</h3><FunctionField filters={draft} set={set} />
      <TagField filters={draft} label="Excluded title" name="excludedTitle" set={set} /><MultiChoice filters={draft} label="Job Type" name="employmentType" options={CHOICES.employmentType} set={set} /><MultiChoice filters={draft} label="Work Model" name="workArrangement" options={CHOICES.workArrangement} set={set} />
      <LocationField filters={draft} set={set} />
      <MultiChoice filters={draft} label="Experience Level" name="experienceLevel" options={CHOICES.experienceLevel} set={set} /><RangeField filters={draft} set={set} /><div className="runr-filter-card"><strong>Date Posted<button className="runr-filter-clear" onClick={() => set("datePosted", "all")} type="button">Clear all</button></strong><div className="runr-filter-options">{[["all", "Any time"], ...CHOICES.datePosted].map(([value, label]) => <label key={value}><input checked={draft.datePosted === value} onChange={() => set("datePosted", value)} type="radio" />{label}</label>)}</div></div></section>
      <section data-name={SECTIONS[1]} id="runr-filter-1"><h3>Compensation &amp; Sponsorship</h3><div className="runr-filter-card"><strong>Minimum Annual Salary</strong><label className="runr-filter-check"><input checked={draft.salaryMin === "" || draft.salaryMin == null} onChange={(event) => set("salaryMin", event.target.checked ? "" : "0")} type="checkbox" />Open to all salaries</label><input aria-label="Minimum annual salary" min="0" onChange={(event) => set("salaryMin", event.target.value)} placeholder="Any salary" type="number" value={draft.salaryMin ?? ""} /><input aria-label="Minimum annual salary slider" min="0" max={Math.max(250000, Number(draft.salaryMin) || 0)} step="1000" type="range" value={draft.salaryMin || 0} onChange={(event) => set("salaryMin", event.target.value)} /><label>Salary currency<select onChange={(event) => set("salaryCurrency", event.target.value)} value={draft.salaryCurrency || ""}><option value="">Any currency</option>{["EUR", "USD", "GBP", "CHF", "CAD", "AUD"].map((currency) => <option key={currency}>{currency}</option>)}</select></label></div><div className="runr-filter-card"><strong>Work Authorization</strong><label className="runr-filter-check"><input checked={Boolean(draft.h1bSponsorship)} onChange={(event) => set("h1bSponsorship", event.target.checked)} type="checkbox" />H1B sponsorship</label></div><div className="runr-filter-card"><strong>Exclude Jobs with Limitations</strong>{[["excludeSecurityClearance", "Security Clearance Required"], ["excludeCitizenshipRequired", "US Citizen Only"]].map(([key, label]) => <label className="runr-filter-check" key={key}><input checked={Boolean(draft[key])} onChange={(event) => set(key, event.target.checked)} type="checkbox" />{label}</label>)}</div></section>
      <section data-name={SECTIONS[2]} id="runr-filter-2"><h3>Areas of Interests</h3><TagField filters={draft} label="Industry" name="industry" set={set} suggestions={["Information Technology", "Artificial Intelligence (AI)", "Financial Services", "Consulting", "Software", "Healthcare", "Education", "Manufacturing"]} /><TagField filters={draft} label="Excluded industry" name="excludedIndustry" set={set} suggestions={["Information Technology", "Artificial Intelligence (AI)", "Financial Services", "Consulting", "Software", "Healthcare", "Education", "Manufacturing"]} /><TagField filters={draft} label="Skill" name="skillsInclude" set={set} suggestions={["SQL", "Python", "Java", "JavaScript", "TypeScript", "Excel", "Power BI", "Tableau", "Project Management", "Data Analysis", "AWS", "Azure", "Agile/Scrum", "Communication", "Leadership", "React", "Sales", "Accounting"]} /><TagField filters={draft} label="Excluded skill" name="skillsExclude" set={set} suggestions={["SQL", "Python", "Java", "JavaScript", "TypeScript", "Excel", "Power BI", "Tableau", "Project Management", "Data Analysis", "AWS", "Azure", "Agile/Scrum", "Communication", "Leadership", "React", "Sales", "Accounting"]} /><div className="runr-filter-card"><strong>Role Type</strong><div className="runr-filter-options">{[["", "Any"], ["ic", "IC"], ["manager", "Manager"]].map(([value, label]) => <label key={label}><input checked={(draft.roleType || "") === value} onChange={() => set("roleType", value)} type="radio" />{label}</label>)}</div></div></section>
      <section data-name={SECTIONS[3]} id="runr-filter-3"><h3>Company Insights</h3><TagField filters={draft} label="Company" name="company" set={set} request={request} /><MultiChoice filters={draft} label="Company Stage" name="companyStage" options={CHOICES.companyStage} set={set} /><div className="runr-filter-card"><strong>Job Source</strong><label className="runr-filter-check"><input checked={Boolean(draft.excludeStaffingAgency)} onChange={(event) => set("excludeStaffingAgency", event.target.checked)} type="checkbox" />Exclude Staffing Agency</label></div><TagField filters={draft} label="Exclude company" name="hiddenCompanies" set={set} request={request} /></section>
    </div></div>
    {invalid ? <p role="alert">Minimum years must not exceed maximum years.</p> : null}
    <footer><button onClick={() => setDraft({ ...INITIAL_PERSONALIZED_JOB_FILTERS })} type="button">Clear all filters</button><button className="jobs-primary-button runr-filter-confirm" disabled={invalid || busy} onClick={confirm} type="button">Show results</button></footer>
  </aside></div>;
}

export function LocationField({ filters, set }) {
  const [cities, setCities] = useState([]);
  useEffect(() => {
    let active = true;
    setCities([]);
    const code = COUNTRIES[filters.country] || filters.country;
    if (code) loadCityOptions(code).then((options) => { if (active) setCities(options); }).catch(() => { if (active) setCities([]); });
    return () => { active = false; };
  }, [filters.country]);
  return <div className="runr-filter-card"><strong>Location<button className="runr-filter-clear" onClick={() => { set("country", ""); set("location", []); }} type="button">Clear all</button></strong><label>Country<select aria-label="Country" onChange={(event) => { set("country", event.target.value); set("location", []); }} value={filters.country || ""}><option value="">Any country</option>{Object.keys(COUNTRIES).sort().map((country) => <option key={country} value={country}>{country}</option>)}</select></label><TagField filters={filters} label="Cities or areas" name="location" set={set} suggestions={cities} /></div>;
}

export function Toggle({ label, checked, onChange }) {
  return <label className="runr-toggle"><span>{label}</span><input type="checkbox" role="switch" checked={checked} onChange={(event) => onChange(event.target.checked)} /><span className="runr-toggle-track" aria-hidden="true" /></label>;
}

export function RangeField({ filters, set }) {
  const open = (filters.requiredExperienceMin === "" || filters.requiredExperienceMin == null) && (filters.requiredExperienceMax === "" || filters.requiredExperienceMax == null);
  const low = Number(filters.requiredExperienceMin || 0), high = Number(filters.requiredExperienceMax || 0);
  return <div className="runr-filter-card"><strong>Required Experience</strong><Toggle label="Open to all experience requirements" checked={open} onChange={(value) => { set("requiredExperienceMin", value ? "" : "0"); set("requiredExperienceMax", value ? "" : "0"); }} /><fieldset disabled={open} className="runr-experience-range"><legend>{open ? "Any experience" : `${low}-${high} years`}</legend><div className="runr-range-track"><input aria-label="Minimum years" type="range" min="0" max="30" step="0.5" value={low} onChange={(event) => { const value = Number(event.target.value); set("requiredExperienceMin", String(value)); if (value > high) set("requiredExperienceMax", String(value)); }} /><input aria-label="Maximum years" type="range" min="0" max="30" step="0.5" value={high} onChange={(event) => set("requiredExperienceMax", String(Math.max(Number(event.target.value), low)))} /></div><div className="runr-range-labels"><span>0 years</span><span>30 years</span></div></fieldset></div>;
}

export function FunctionField({ filters, set }) {
  const [group, setGroup] = useState(() => Object.keys(FUNCTIONS).find((group) => Object.values(FUNCTIONS[group]).flat().some((role) => asList(filters.role).includes(role))) || Object.keys(FUNCTIONS)[0]);
  const [query, setQuery] = useState("");
  const selected = asList(filters.role);
  const groups = query ? { "Search results": [...new Set(Object.values(FUNCTIONS).flatMap((group) => Object.values(group).flat()))].filter((role) => role.toLowerCase().includes(query.toLowerCase())) } : FUNCTIONS[group];
  return <div className="runr-filter-card"><strong>Job Function<button className="runr-filter-clear" onClick={() => set("role", [])} type="button">Clear all</button></strong><input aria-label="Search job functions" placeholder="Search job functions" value={query} onChange={(event) => setQuery(event.target.value)} /><div className="runr-function-picker"><div>{Object.keys(FUNCTIONS).map((name) => <button className={name === group ? "is-active" : ""} key={name} onMouseEnter={() => { setGroup(name); setQuery(""); }} onFocus={() => { setGroup(name); setQuery(""); }} onClick={() => { setGroup(name); setQuery(""); }} type="button">{name}</button>)}</div><div>{Object.entries(groups).map(([heading, roles]) => <section className="runr-function-group" key={heading}><h4>{heading}</h4><div>{roles.map((role) => <button aria-pressed={selected.includes(role)} className={selected.includes(role) ? "is-active" : ""} key={role} onClick={() => set("role", selected.includes(role) ? selected.filter((item) => item !== role) : [...selected, role])} type="button">{role}</button>)}</div></section>)}</div></div><TagField filters={filters} label="Other job functions" name="role" set={set} suggestions={[...new Set(Object.values(FUNCTIONS).flatMap((group) => Object.values(group).flat()))]} /></div>;
}
