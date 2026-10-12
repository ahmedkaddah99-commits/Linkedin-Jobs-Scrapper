import { useEffect, useRef, useState } from "react";
import { MultiChoice, TagField, RangeField, LocationField, FunctionField, CHOICES } from "./AllJobFilters";

export default function QuickJobFilter({ name, label, filters, onApply }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(filters);
  const root = useRef(null);
  const set = (key, value) => setDraft((current) => ({ ...current, [key]: value }));
  useEffect(() => {
    if (!open) return;
    const close = (event) => { if (!root.current?.contains(event.target)) setOpen(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);
  const value = filters[name];
  const count = name === "location" ? [filters.country, filters.location].flat().filter(Boolean).length : name === "requiredExperience" ? [filters.requiredExperienceMin, filters.requiredExperienceMax].some((item) => item !== "" && item != null) ? 1 : 0 : Array.isArray(value) ? value.length : value && value !== "all" ? 1 : 0;
  const invalid = name === "requiredExperience" && draft.requiredExperienceMin !== "" && draft.requiredExperienceMax !== "" && Number(draft.requiredExperienceMin) > Number(draft.requiredExperienceMax);
  const values = name === "location" ? [filters.country, filters.location].flat().filter(Boolean) : Array.isArray(value) ? value : value && value !== "all" ? [value] : [];
  const first = values[0];
  const selectedLabel = CHOICES[name]?.find(([value]) => value === first)?.[1] || first;
  const text = name === "requiredExperience" && count ? `${filters.requiredExperienceMin || 0}â€“${filters.requiredExperienceMax || "Any"} years` : selectedLabel ? `${selectedLabel}${values.length > 1 ? ` (+${values.length - 1})` : ""}` : label;
  return <div className="jobs-quick-filter" data-filter={name} ref={root} onKeyDown={(event) => { if (event.key === "Escape") { setOpen(false); root.current?.querySelector("button")?.focus(); } }}>
    <button aria-label={`${label}: ${text}`} aria-expanded={open} className={`jobs-filter-pill ${count ? "is-active" : ""}`} onClick={() => { setDraft(filters); setOpen(!open); }} title={text} type="button"><span className="jobs-filter-pill__label">{text}</span><span aria-hidden="true" className="material-symbols-outlined">arrow_drop_down</span></button>
    {open ? <div aria-label={label} className={`jobs-quick-filter__menu ${name === "role" ? "jobs-quick-filter__menu--functions" : ""}`} role="group">
      {name === "role" ? <FunctionField filters={draft} set={set} /> : name === "location" ? <LocationField filters={draft} set={set} /> : name === "requiredExperience" ? <RangeField filters={draft} set={set} /> : name === "industry" ? <TagField label="Industry" name={name} filters={draft} set={set} suggestions={["Information Technology", "Artificial Intelligence (AI)", "Financial Services", "Consulting", "Software", "Healthcare", "Education", "Manufacturing"]} /> : name === "datePosted" ? <div className="runr-filter-options">{[["all", "Any time"], ...CHOICES.datePosted].map(([value, text]) => <label key={value}><input type="radio" checked={draft.datePosted === value} onChange={() => set("datePosted", value)} />{text}</label>)}</div> : <MultiChoice label={label} name={name} options={CHOICES[name]} filters={draft} set={set} />}
      {invalid ? <p role="alert">Minimum years must not exceed maximum years.</p> : null}
      <button className="jobs-primary-button runr-filter-confirm" disabled={invalid} onClick={() => { onApply(draft); setOpen(false); }} type="button">Confirm</button>
    </div> : null}
  </div>;
}
