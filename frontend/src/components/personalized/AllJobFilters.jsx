import { useEffect, useState } from "react";

const SECTIONS = ["Basic Job Criteria", "Compensation & Sponsorship", "Areas of Interests", "Company Insights"];
const FUNCTIONS = {
  "Software/Internet/AI": {
    "Backend Engineering": ["Backend Engineer", "Full Stack Engineer"],
    "Data & Analytics": ["Data Analyst", "Data Scientist", "Data Engineer", "Business/BI Analyst"],
    "Machine Learning & AI": ["Machine Learning Engineer", "AI Engineer"],
    "Frontend/Mobile/Game": ["Frontend Software Engineer"],
    "System Reliability & Security": ["DevOps", "Cyber Security Analyst"],
    Testing: ["Software Testing/Quality Assurance Engineer"],
    "Project Management": ["Project/Program Manager"],
    "Technical Leadership": ["Engineering Manager"],
  },
  Consulting: {
    "IT Consulting": ["Business Analyst", "Data Consultant", "IT Consultant"],
    "Business Strategy & Management Consulting": ["Business Strategy Consultant", "Market Research Analyst", "Operations Consultant"],
    "Financial Advisory": ["Financial Consultant"],
  },
  Marketing: {
    "SEO and Content Marketing": ["Content Marketing/Strategy", "Social Media Management", "SEO", "Copywriter"],
    "Brand and Communications Marketing": ["Brand Manager"],
    "Growth Marketing": ["Growth Marketing", "Performance Marketing"],
    "Product Marketing": ["Product Marketing"],
  },
  Finance: {
    "Investment/Financing": ["Financial Analyst", "Risk Analyst", "Quantitative Analyst/Researcher", "Portfolio Manager"],
    Banking: ["Investment Banker", "Credit Analyst"],
    "Corporate Finance": ["Corporate Finance Analyst"],
    Insurance: ["Underwriter", "Actuary"],
  },
  Product: { "Product Management": ["Product Manager", "Product Analyst", "Technical Product Manager", "AI Product Manager", "Game Designer"] },
  Healthcare: {
    "Healthcare IT": ["Healthcare Data Analyst"],
    "Health Product & Operations Management": ["Health Product Manager"],
    "Clinical & Regulatory": ["Clinical Research Associate", "Clinical Research Scientist", "Biostatistician", "Medical Writer"],
    "Biomedical Engineering & Technology": ["Biomedical Engineer"],
  },
  "Electrical Engineering": {
    "Electronics & Hardware": ["Embedded Software Engineer", "Electronics Engineer", "Hardware Engineer"],
    "Electrical & Automation": ["Electrical Engineer", "Robotics Engineer"],
    Telecommunications: ["Network Engineer"],
    "Electrical Vehicles": ["Battery Engineer"],
  },
  "Human Resource/Administrative/Legal": {
    "Executive and Administrative": ["Administrative Assistant", "Executive Assistant", "Office Manager"],
    "Human Resource": ["Human Resource Specialist", "Recruiter/Sourcer"],
    Legal: ["Paralegal", "Corporate Counsel"],
  },
  Sales: {
    "Business Development": ["Business Development"],
    "Inside Sales": ["Sales Development Representative", "Account Executive"],
    "Sales Management": ["Sales Manager"],
    "Outside Sales": ["Enterprise Sales"],
    "Retail Sales": ["Retail Sales"],
    "Medical Sales": ["Medical Sales"],
  },
  "Production/Manufacturing": {
    "Mechanical Design & Manufacturing": ["Mechanical Engineer", "Manufacturing Engineer", "Process Engineer"],
    "Operations & Safety": ["Operations Manager/Director"],
    "Quality Management": ["Quality Assurance Specialist"],
    "Automotive R&D & Manufacturing": ["Automotive Engineer"],
  },
  "Customer Service": { "Customer Service": ["Customer Service Representative", "Customer Service Manager"], "Customer Support": ["Customer Support"], "Customer Success": ["Customer Success"] },
  "Creative & Design": { "UI/UX Design": ["UX Designer", "UI Designer", "Graphic Designer", "UX Researcher"], "Art/3D/Animation": ["Video Editor", "Illustrator", "3D Designer"], "Industrial Design": ["Industrial Designer"] },
  "Logistics/Supply Chain": { "Supply Chain Management": ["Supply Chain Manager", "Inventory Manager"], "Logistics Operations": ["Logistics Manager", "Warehouse Manager"], "Procurement and Facilities": ["Procurement Manager"] },
  "Public Sector and Government": { "Non-profit": ["Program Manager"], "Policy and Planning": ["Policy Analyst"], "Public Administration": ["Government Relations Manager"] },
  "Legal Services": { "Compliance & Risk Management": ["Compliance Specialist"], "Paralegals & Legal Support": ["Legal Assistant", "Paralegal"], "Legal Operations & Administration": ["Legal Operations Manager"], "Legal Practice": ["Lawyer"] },
  "Education and Training": { "Academic Teaching": ["Higher Education Teaching", "K-12 Teaching"], "Corporate Training and Development": ["Corporate Training and Development"], "Educational Administration": ["Educational Administration"] },
  Accounting: { Accounting: ["Accountant", "Controller"], "Tax and Audit": ["Auditor", "Tax Specialist"] },
  "Real Estate/Architecture": { Construction: ["Construction Project Manager", "Civil Engineer"], "Real Estate": ["Property Manager"], Architecture: ["Architect", "Urban Planner"] },
  "Energy/Environmental": { "Energy Engineering": ["Renewable Energy Engineer", "Energy Engineer"], "Environmental Engineering": ["Environmental Scientist", "Environmental Engineer"] },
};

const CHOICES = {
  employmentType: [["full_time", "Full-time"], ["contract", "Contract"], ["part_time", "Part-time"], ["internship", "Internship"]],
  workArrangement: [["onsite", "Onsite"], ["hybrid", "Hybrid"], ["remote", "Remote"]],
  experienceLevel: [["intern", "Intern/New Grad"], ["entry", "Entry Level"], ["mid", "Mid Level"], ["senior", "Senior Level"], ["lead", "Lead/Staff"], ["director", "Director/Executive"]],
  datePosted: [["24h", "Past 24 hours"], ["3d", "Past 3 days"], ["7d", "Past week"], ["30d", "Past month"]],
  companyStage: [["early", "Early Stage"], ["growth", "Growth Stage"], ["late", "Late Stage"], ["public", "Public Company"]],
};

const asList = (value) => Array.isArray(value) ? value : value && value !== "all" ? [value] : [];
const choiceLabel = (key, value) => CHOICES[key]?.find(([item]) => item === value)?.[1] || value;

function MultiChoice({ label, name, options, filters, set }) {
  const selected = asList(filters[name]);
  return <div className="runr-filter-card"><strong>{label}</strong><div className="runr-filter-options">{options.map(([value, text]) => <label key={value}><input checked={selected.includes(value)} onChange={() => set(name, selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value])} type="checkbox" />{text}</label>)}</div></div>;
}

function TagField({ label, name, filters, set, suggestions = [] }) {
  const [input, setInput] = useState("");
  const values = asList(filters[name]);
  const add = (value) => { const trimmed = value.trim(); if (trimmed && !values.some((item) => item.toLowerCase() === trimmed.toLowerCase())) set(name, [...values, trimmed]); setInput(""); };
  return <div className="runr-filter-card"><strong>{label}</strong><div className="runr-filter-tags">{values.map((value) => <button key={value} onClick={() => set(name, values.filter((item) => item !== value))} type="button">{value} ×</button>)}</div><div className="runr-filter-add"><input aria-label={label} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); add(input); } }} placeholder={`Add ${label.toLowerCase()}`} value={input} /><button onClick={() => add(input)} type="button">Add</button></div>{input && suggestions.length ? <div className="runr-filter-suggestions">{suggestions.filter((item) => item.toLowerCase().includes(input.toLowerCase()) && !values.includes(item)).slice(0, 8).map((item) => <button key={item} onClick={() => add(item)} type="button">{item}</button>)}</div> : null}</div>;
}

export default function AllJobFilters({ filters, initialSection = SECTIONS[0], onApply, onClose }) {
  const [draft, setDraft] = useState(() => ({ ...filters }));
  const [section, setSection] = useState(initialSection);
  const [functionGroup, setFunctionGroup] = useState("Software/Internet/AI");
  useEffect(() => {
    if (initialSection !== SECTIONS[0]) document.getElementById(`runr-filter-${SECTIONS.indexOf(initialSection)}`)?.scrollIntoView({ block: "start" });
  }, [initialSection]);
  const set = (key, value) => setDraft((current) => ({ ...current, [key]: value }));
  const tags = Object.entries(draft).flatMap(([key, value]) => ["role", "employmentType", "workArrangement", "experienceLevel", "country", "location", "industry", "skillsInclude", "company", "companyStage"].includes(key) ? asList(value).map((item) => [key, item]) : []);
  const removeTag = (key, item) => set(key, Array.isArray(draft[key]) ? draft[key].filter((value) => value !== item) : "");
  return <div className="jobs-filter-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><aside aria-label="All Filters" aria-modal="true" className="runr-all-filters" role="dialog">
    <header><button aria-label="Close filters" onClick={onClose} type="button">‹</button><h2>All Filters</h2><button className="runr-filter-confirm" onClick={() => onApply(draft)} type="button">Confirm</button></header>
    {tags.length ? <div className="runr-filter-summary">{tags.map(([key, item]) => <button key={`${key}-${item}`} onClick={() => removeTag(key, item)} type="button">{choiceLabel(key, item)} ×</button>)}</div> : null}
    <div className="runr-filter-layout"><nav aria-label="Filter sections">{SECTIONS.map((name) => <button className={section === name ? "is-active" : ""} key={name} onClick={() => { setSection(name); document.getElementById(`runr-filter-${SECTIONS.indexOf(name)}`)?.scrollIntoView({ block: "start", behavior: "smooth" }); }} type="button">{name}</button>)}</nav><div className="runr-filter-content" onScroll={(event) => { const nodes = [...event.currentTarget.querySelectorAll("section[id]")]; const visible = nodes.filter((node) => node.getBoundingClientRect().top < 300).at(-1); if (visible) setSection(visible.dataset.name); }}>
      <section data-name={SECTIONS[0]} id="runr-filter-0"><h3>Basic Job Criteria</h3><div className="runr-filter-card"><strong>Job Function</strong><div className="runr-function-picker"><div>{Object.keys(FUNCTIONS).map((group) => <button className={group === functionGroup ? "is-active" : ""} key={group} onClick={() => setFunctionGroup(group)} type="button">{group}</button>)}</div><div>{Object.entries(FUNCTIONS[functionGroup]).map(([heading, roles]) => <section className="runr-function-group" key={heading}><h4>{heading}</h4><div>{roles.map((role) => <button className={asList(draft.role).includes(role) ? "is-active" : ""} key={role} onClick={() => set("role", asList(draft.role).includes(role) ? asList(draft.role).filter((item) => item !== role) : [...asList(draft.role), role])} type="button">{role}</button>)}</div></section>)}</div></div><TagField filters={draft} label="Other job functions" name="role" set={set} /></div>
      <TagField filters={draft} label="Excluded title" name="excludedTitle" set={set} /><MultiChoice filters={draft} label="Job Type" name="employmentType" options={CHOICES.employmentType} set={set} /><MultiChoice filters={draft} label="Work Model" name="workArrangement" options={CHOICES.workArrangement} set={set} />
      <div className="runr-filter-card"><strong>Location</strong><div className="runr-filter-grid"><label>Country<select onChange={(event) => set("country", event.target.value)} value={draft.country || ""}><option value="">Any country</option>{["United States", "Canada", "United Kingdom", "Australia", "Ireland", "New Zealand", "Germany"].map((country) => <option key={country}>{country}</option>)}</select></label><label>City or area<input onChange={(event) => set("location", event.target.value)} placeholder="Anywhere" value={draft.location || ""} /></label></div></div>
      <MultiChoice filters={draft} label="Experience Level" name="experienceLevel" options={CHOICES.experienceLevel} set={set} /><div className="runr-filter-card"><strong>Required Experience</strong><div className="runr-filter-grid"><label>Minimum years<input min="0" onChange={(event) => set("requiredExperienceMin", event.target.value)} type="number" value={draft.requiredExperienceMin || ""} /></label><label>Maximum years<input min="0" onChange={(event) => set("requiredExperienceMax", event.target.value)} type="number" value={draft.requiredExperienceMax || ""} /></label></div></div><div className="runr-filter-card"><strong>Date Posted</strong><div className="runr-filter-options">{[["all", "Any time"], ...CHOICES.datePosted].map(([value, label]) => <label key={value}><input checked={draft.datePosted === value} onChange={() => set("datePosted", value)} type="radio" />{label}</label>)}</div></div></section>
      <section data-name={SECTIONS[1]} id="runr-filter-1"><h3>Compensation &amp; Sponsorship</h3><div className="runr-filter-card"><strong>Minimum Annual Salary</strong><input aria-label="Minimum annual salary" min="0" onChange={(event) => set("salaryMin", event.target.value)} placeholder="Any salary" type="number" value={draft.salaryMin || ""} /></div><div className="runr-filter-card"><strong>Work Authorization</strong><label className="runr-filter-check"><input checked={Boolean(draft.h1bSponsorship)} onChange={(event) => set("h1bSponsorship", event.target.checked)} type="checkbox" />H1B sponsorship</label></div><div className="runr-filter-card"><strong>Exclude Jobs with Limitations</strong>{[["excludeSecurityClearance", "Security Clearance Required"], ["excludeCitizenshipRequired", "US Citizen Only"]].map(([key, label]) => <label className="runr-filter-check" key={key}><input checked={Boolean(draft[key])} onChange={(event) => set(key, event.target.checked)} type="checkbox" />{label}</label>)}</div></section>
      <section data-name={SECTIONS[2]} id="runr-filter-2"><h3>Areas of Interests</h3><TagField filters={draft} label="Industry" name="industry" set={set} suggestions={["Information Technology", "Artificial Intelligence (AI)", "Financial Services", "Consulting", "Software", "Healthcare", "Education", "Manufacturing"]} /><TagField filters={draft} label="Excluded industry" name="excludedIndustry" set={set} /><TagField filters={draft} label="Skill" name="skillsInclude" set={set} /><TagField filters={draft} label="Excluded skill" name="skillsExclude" set={set} /><div className="runr-filter-card"><strong>Role Type</strong><div className="runr-filter-options">{[["", "Any"], ["ic", "IC"], ["manager", "Manager"]].map(([value, label]) => <label key={label}><input checked={(draft.roleType || "") === value} onChange={() => set("roleType", value)} type="radio" />{label}</label>)}</div></div></section>
      <section data-name={SECTIONS[3]} id="runr-filter-3"><h3>Company Insights</h3><TagField filters={draft} label="Company" name="company" set={set} /><MultiChoice filters={draft} label="Company Stage" name="companyStage" options={CHOICES.companyStage} set={set} /><div className="runr-filter-card"><strong>Job Source</strong><label className="runr-filter-check"><input checked={Boolean(draft.excludeStaffingAgency)} onChange={(event) => set("excludeStaffingAgency", event.target.checked)} type="checkbox" />Exclude Staffing Agency</label></div><TagField filters={draft} label="Exclude company" name="hiddenCompanies" set={set} /></section>
    </div></div>
  </aside></div>;
}
