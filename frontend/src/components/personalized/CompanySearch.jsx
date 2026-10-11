import { useEffect, useRef, useState } from "react";

export default function CompanySearch({ request, connected, value, selected, onQuery, onSelect, onClear }) {
  const [open, setOpen] = useState(false);
  const [companies, setCompanies] = useState([]);
  const [state, setState] = useState("idle");
  const [highlighted, setHighlighted] = useState(-1);
  const rootRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!connected || !open || !value.trim() || selected) {
      setCompanies([]);
      setState("idle");
      return undefined;
    }
    let active = true;
    const controller = new AbortController();
    setState("loading");
    setCompanies([]);
    setHighlighted(-1);
    const timer = setTimeout(async () => {
      try {
        const result = await request(`/personalized-jobs/companies?q=${encodeURIComponent(value.trim())}`, { signal: controller.signal, timeoutMs: 10000 });
        if (active) {
          setCompanies(result.companies || []);
          setState("ready");
        }
      } catch {
        if (active) setState("error");
      }
    }, 250);
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [connected, open, value, selected, request]);

  useEffect(() => {
    const dismiss = (event) => { if (!rootRef.current?.contains(event.target)) setOpen(false); };
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, []);

  function select(company) {
    onSelect(company);
    setOpen(false);
    setHighlighted(-1);
    inputRef.current?.focus();
  }

  const showSuggestions = open && Boolean(value.trim()) && !selected;
  return <div className="jobs-company-search" ref={rootRef}>
    <div className="jobs-company-search__input">
      <span aria-hidden="true" className="material-symbols-outlined">search</span>
      <input
        aria-activedescendant={showSuggestions && highlighted >= 0 ? `company-option-${highlighted}` : undefined}
        aria-autocomplete="list" aria-controls="jobs-company-options" aria-expanded={showSuggestions}
        aria-label="Search job title or company" autoComplete="off" placeholder="Search job title or company"
        onBlur={(event) => { if (!rootRef.current?.contains(event.relatedTarget)) setOpen(false); }}
        onChange={(event) => { onQuery(event.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === "Escape") { setOpen(false); return; }
          if (["ArrowDown", "ArrowUp"].includes(event.key) && companies.length) {
            event.preventDefault(); setOpen(true);
            setHighlighted((current) => event.key === "ArrowDown" ? (current + 1) % companies.length : (current <= 0 ? companies.length - 1 : current - 1));
          } else if (event.key === "Enter" && showSuggestions && highlighted >= 0 && companies[highlighted]) {
            event.preventDefault(); select(companies[highlighted]);
          }
        }} ref={inputRef} role="combobox" value={value} />
      {value ? <button aria-label="Clear search" onClick={() => { onClear(); setOpen(false); inputRef.current?.focus(); }} type="button"><span aria-hidden="true" className="material-symbols-outlined">close</span></button> : null}
    </div>
    {selected ? <span className="jobs-company-search__hint">Showing jobs at {value}</span> : null}
    {showSuggestions ? <div className="jobs-company-search__suggestions">
      <div className="jobs-company-search__label">Companies</div>
      <div aria-label="Matching companies" id="jobs-company-options" role="listbox">
        {companies.map((company, index) => <div aria-selected={index === highlighted} className="jobs-company-option" id={`company-option-${index}`} key={company.company_id} onClick={() => select(company)} onMouseDown={(event) => event.preventDefault()} onMouseEnter={() => setHighlighted(index)} role="option">
          <span aria-hidden="true" className="jobs-company-option__mark">{company.logo_url ? <img alt="" src={company.logo_url} /> : company.name.slice(0, 1)}</span><span>{company.name}</span>
        </div>)}
      </div>
      <p role="status">{state === "loading" ? "Finding companies…" : state === "error" ? "Unable to load companies. Try typing again." : !companies.length ? "No matching companies" : "Select a company to see its jobs."}</p>
    </div> : null}
  </div>;
}
