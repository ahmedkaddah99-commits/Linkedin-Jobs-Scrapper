import { useState } from "react";

function summary(filters = {}) {
  const values = [filters.company_label, filters.role, filters.location, filters.work_arrangement, filters.employment_type];
  return values.flat().filter(Boolean).join(" · ") || "All selected criteria";
}

export default function SavedFiltersPanel({ items, activeId, modified, busy, error, onSave, onActivate, onEdit, onDelete }) {
  const [editing, setEditing] = useState(null);
  const [name, setName] = useState("");
  return <aside aria-label="Saved filters" className="jobs-saved-panel">
    <header><h2>Your saved filters</h2><button aria-label="Add saved filter" disabled={busy} onClick={() => { setEditing({}); setName(""); }} type="button"><span aria-hidden="true" className="material-symbols-outlined">add</span></button></header>
    <p>Save a search. Pick it up where you left off.</p>
    {error ? <p className="jobs-saved-panel__error" role="alert">{error}</p> : null}
    <div className="jobs-saved-panel__list">{items.map((item) => <div className={`jobs-saved-filter ${item.filter_set_id === activeId ? "is-active" : ""}`} key={item.filter_set_id}>
      <button aria-label={`Activate ${item.name}`} aria-pressed={item.filter_set_id === activeId && !modified} disabled={busy} onClick={() => onActivate(item)} type="button"><strong>{item.name}</strong><small>{summary(item.filters)}</small>{item.filter_set_id === activeId ? <em>{modified ? "Unsaved changes" : "Active · opens on your next visit"}</em> : null}</button>
      <div><button aria-label={`Edit ${item.name}`} disabled={busy} onClick={() => { setEditing(item); setName(item.name); onEdit(item); }} type="button"><span aria-hidden="true" className="material-symbols-outlined">edit</span></button><button aria-label={`Delete ${item.name}`} disabled={busy} onClick={() => onDelete(item.filter_set_id)} type="button"><span aria-hidden="true" className="material-symbols-outlined">delete</span></button></div>
    </div>)}</div>
    {!items.length ? <div className="jobs-saved-panel__empty"><span aria-hidden="true" className="material-symbols-outlined">bookmark_border</span><strong>Your searches, ready when you are</strong><p>Choose your filters or a company, then save the search here.</p></div> : null}
    {editing ? <form className="jobs-saved-panel__editor" onSubmit={async (event) => {
      event.preventDefault();
      if (await onSave(name.trim(), editing.filter_set_id)) { setEditing(null); setName(""); }
    }}><label>Filter name<input aria-label="Filter name" autoFocus disabled={busy} maxLength={80} onChange={(event) => setName(event.target.value)} placeholder="e.g. Analyst roles in Berlin" required value={name} /></label><small>{editing.filter_set_id ? "Update this search with the filters currently shown." : "Your current filters will open on your next visit."}</small><button className="jobs-primary-button" disabled={busy || !name.trim()} type="submit">{editing.filter_set_id ? "Update saved filter" : "Save current filters"}</button><button className="jobs-text-link" disabled={busy} onClick={() => setEditing(null)} type="button">Cancel</button></form> : <button className="jobs-outline-button jobs-saved-panel__save" disabled={busy} onClick={() => { setEditing({}); setName(""); }} type="button"><span aria-hidden="true" className="material-symbols-outlined">bookmark_add</span>Save current search</button>}
  </aside>;
}
