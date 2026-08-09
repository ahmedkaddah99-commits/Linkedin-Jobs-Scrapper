import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { getApiErrorMessage } from "../lib/api";
import { formatDateTime } from "../lib/formatters";
import inspectorStyles from "../adminInspectorV3.css?raw";

const NAV = ["Overview", "Jobs", "Companies", "Imports", "Operations", "Review", "System"];
const DATA_TABS = ["coverage", "job", "company", "admin", "complete"];

function countFields(value) {
  const entries = Object.entries(value || {});
  const missing = entries
    .filter(([, item]) => item === null || item === "" || (Array.isArray(item) && item.length === 0))
    .map(([key]) => key);
  return { total: entries.length, present: entries.length - missing.length, missing };
}

function Status({ value }) {
  const normalized = String(value || "Unknown");
  const tone = normalized.includes("verified") || normalized === "Published" || normalized === "Pass"
    ? "green"
    : normalized.includes("missing") || normalized.includes("invalid") || normalized === "Review" || normalized === "Fail"
      ? "red"
      : "amber";
  return <span className={`status status-${tone}`}><i />{normalized.replaceAll("_", " ")}</span>;
}

function JsonView({ value, search }) {
  const lines = JSON.stringify(value ?? null, null, 2).split("\n");
  const normalized = String(search || "").trim().toLowerCase();
  return <pre className="json-view" aria-label="JSON record">{lines.map((line, index) => <span className={normalized && line.toLowerCase().includes(normalized) ? "json-hit" : ""} key={`${index}-${line}`}><b>{String(index + 1).padStart(2, "0")}</b>{line}</span>)}</pre>;
}

function applyStatus(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "verified") return "verified";
  if (normalized === "missing") return "missing";
  return "invalid";
}

function recordFrom(row, inspection) {
  const job = inspection?.job || {
    canonical_job_id: row?.canonical_job_id,
    title: row?.title,
    company: row?.company,
    location_raw: row?.location,
    apply_url: row?.apply_url || null,
  };
  const companyData = inspection?.company || { name: row?.company || null };
  const admin = inspection?.admin || {};
  const apply = inspection?.apply_url || {};
  return {
    id: String(row?.canonical_job_id || job.canonical_job_id || ""),
    title: String(row?.title || job.title || "Unknown title"),
    company: String(row?.company || companyData.name || "Unknown company"),
    location: String(row?.location || job.location_raw || "Unknown location"),
    source: String(row?.source || admin.connector || "Unknown source"),
    state: String(row?.state || "Review"),
    freshness: row?.freshness ? `Observed ${formatDateTime(row.freshness)}` : "Freshness unknown",
    completeness: Number(inspection?.completeness?.overall_percent ?? 0),
    applyStatus: applyStatus(apply.status || row?.apply_status),
    job,
    companyData,
    admin,
    raw: inspection?.raw || {},
    inspection: inspection || null,
  };
}

function useInspectorStyles() {
  useEffect(() => {
    const style = document.createElement("style");
    style.dataset.runrAdminInspector = "v3";
    style.textContent = inspectorStyles;
    document.head.appendChild(style);
    return () => style.remove();
  }, []);
}

export default function AdminJobImportPage() {
  useInspectorStyles();
  const { request } = useSession();
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState({});
  const [selectedId, setSelectedId] = useState("");
  const [inspection, setInspection] = useState(null);
  const [tab, setTab] = useState("coverage");
  const [query, setQuery] = useState("");
  const [jsonSearch, setJsonSearch] = useState("");
  const [copied, setCopied] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Last cycle unavailable");
  const [filterMode, setFilterMode] = useState("all");
  const [recordMenuOpen, setRecordMenuOpen] = useState(false);

  const loadCatalog = useCallback(async () => {
    const response = await request("/admin/job-import/jobs?limit=200");
    const nextRows = response.jobs || [];
    setRows(nextRows);
    setSummary(response.summary || {});
    setSelectedId(current => current && nextRows.some(item => item.canonical_job_id === current)
      ? current
      : String(nextRows[0]?.canonical_job_id || ""));
  }, [request]);

  useEffect(() => {
    loadCatalog().catch(error => setMessage(getApiErrorMessage(error, "Catalog unavailable")));
  }, [loadCatalog]);

  useEffect(() => {
    if (!selectedId) {
      setInspection(null);
      return undefined;
    }
    let cancelled = false;
    setInspection(null);
    request(`/admin/job-import/jobs/${encodeURIComponent(selectedId)}/inspection`)
      .then(value => {
        if (!cancelled) {
          setInspection(value);
          setMessage(value?.job?.last_seen_at ? `Last cycle ${formatDateTime(value.job.last_seen_at)}` : "Last cycle unavailable");
        }
      })
      .catch(error => {
        if (!cancelled) setMessage(getApiErrorMessage(error, "Inspection unavailable"));
      });
    return () => { cancelled = true; };
  }, [request, selectedId]);

  const selectedRow = rows.find(item => String(item.canonical_job_id) === selectedId) || rows[0] || null;
  const selected = useMemo(() => recordFrom(selectedRow, inspection), [inspection, selectedRow]);
  const filtered = rows.filter(item => {
    const matchesQuery = `${item.title || ""} ${item.company || ""} ${item.location || ""} ${item.source || ""} ${item.canonical_job_id || ""}`.toLowerCase().includes(query.toLowerCase());
    const matchesFilter = filterMode === "all"
      || (filterMode === "missing" && item.apply_status !== "present")
      || (filterMode === "incomplete" && (!item.description || !item.company_id || item.apply_status !== "present"));
    return matchesQuery && matchesFilter;
  });
  const jobCoverage = countFields(selected.job);
  const companyCoverage = countFields(selected.companyData);
  const adminCoverage = countFields(selected.admin);
  const completeRecord = selected.inspection || { job: selected.job, company: selected.companyData, admin: selected.admin };
  const activeJson = tab === "job" ? selected.job : tab === "company" ? selected.companyData : tab === "admin" ? selected.admin : completeRecord;
  const criticalChecks = selected.inspection?.completeness?.critical_checks || [
    ["Canonical identity", selected.id ? "Pass" : "Fail", selected.id || "Missing"],
    ["Direct employer Apply URL", selected.applyStatus === "verified" ? "Pass" : "Fail", selected.job.apply_url || "Missing"],
    ["Full description", selected.job.description ? "Pass" : "Fail", selected.job.description ? "Stored" : "Missing"],
    ["Source provenance", selected.admin.source_observation_ids?.length ? "Pass" : "Fail", selected.admin.source_observation_ids?.join(", ") || "Missing"],
    ["Company identity", selected.companyData.canonical_company_id ? "Pass" : "Fail", selected.companyData.canonical_company_id || "Missing"],
  ].map(([name, status, detail]) => ({ name, status: status.toLowerCase(), detail }));
  const attentionCount = criticalChecks.filter(item => item.status !== "pass").length;

  async function copyJson() {
    try {
      await navigator.clipboard?.writeText(JSON.stringify(activeJson, null, 2));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch (error) {
      setMessage(getApiErrorMessage(error, "Copy unavailable"));
    }
  }

  function downloadJson() {
    const blob = new Blob([JSON.stringify(activeJson, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${selected.id || "runr-admin-record"}-${tab}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function resolveApplyUrl() {
    if (!selected.id) return;
    setBusy(true);
    try {
      const response = await request(`/admin/job-import/jobs/${encodeURIComponent(selected.id)}/resolve-apply-url`, { method: "POST", body: {} });
      setInspection(response);
      setMessage("Apply URL resolution recorded");
      await loadCatalog();
    } catch (error) {
      setMessage(getApiErrorMessage(error, "Apply URL resolution failed"));
    } finally {
      setBusy(false);
    }
  }

  function focusInspector(nextTab = "coverage") {
    setTab(nextTab);
    setMenuOpen(false);
    setRecordMenuOpen(false);
    window.requestAnimationFrame(() => document.querySelector(".inspector")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  async function refreshSelected() {
    if (!selected.id) return;
    setBusy(true);
    try {
      const response = await request(`/admin/job-import/jobs/${encodeURIComponent(selected.id)}/inspection`);
      setInspection(response);
      setMessage("Record refreshed");
    } catch (error) {
      setMessage(getApiErrorMessage(error, "Record refresh failed"));
    } finally {
      setBusy(false);
    }
  }

  async function importJobs() {
    setBusy(true);
    try {
      const sourceResponse = await request("/admin/job-import/sources");
      const sourceIds = (sourceResponse.sources || []).filter(item => item.status === "ready").map(item => item.id);
      if (!sourceIds.length) throw new Error("No ready acquisition sources are available.");
      await request("/admin/job-import/imports", {
        method: "POST",
        body: { source_ids: sourceIds, scope: {}, idempotency_key: `admin-inspector-${Date.now()}` },
      });
      setMessage("Import queued");
    } catch (error) {
      setMessage(getApiErrorMessage(error, "Import could not be queued"));
    } finally {
      setBusy(false);
    }
  }

  async function publishSelected() {
    const importId = selected.raw?.imports?.find(item => item.import_id)?.import_id;
    if (!importId) {
      setMessage("This record has no import publication context");
      return;
    }
    setBusy(true);
    try {
      const preview = await request("/admin/job-import/preview", { method: "POST", body: { import_id: importId } });
      if (!preview.publication_id) throw new Error("Publication preview did not return an ID.");
      await request("/admin/job-import/publish", { method: "POST", body: { publication_id: preview.publication_id } });
      setMessage("Record published");
      await loadCatalog();
    } catch (error) {
      setMessage(getApiErrorMessage(error, "Publication failed"));
    } finally {
      setBusy(false);
    }
  }

  async function recordDecision(decision) {
    const importId = selected.raw?.imports?.find(item => item.import_id)?.import_id;
    if (!importId || !selected.id) {
      setMessage("This record has no import decision context");
      return;
    }
    setBusy(true);
    try {
      await request("/admin/job-import/review/decision", { method: "POST", body: { import_id: importId, canonical_job_id: selected.id, decision } });
      setMessage(decision === "approve" ? "Record approved" : "Record sent to review");
      await loadCatalog();
    } catch (error) {
      setMessage(getApiErrorMessage(error, "Review decision failed"));
    } finally {
      setBusy(false);
    }
  }

  function handleNavigation(item) {
    const routes = {
      Overview: "/admin",
      Jobs: "/admin/job-import",
      Operations: "/admin/scrapeops",
      System: "/admin/events",
    };
    if (routes[item]) {
      navigate(routes[item]);
      return;
    }
    if (item === "Companies") {
      focusInspector("company");
      setMessage("Company data is shown for the selected canonical job");
      return;
    }
    if (item === "Imports") {
      setMenuOpen(false);
      importJobs();
      return;
    }
    focusInspector("coverage");
    setMessage("Review actions are available below the selected record");
  }

  function handleWorkflow(step) {
    if (step === "Import") return importJobs();
    if (step === "Inspect data") return focusInspector("coverage");
    if (step === "Review") return focusInspector("coverage");
    if (step === "Publish") return publishSelected();
    return navigate("/jobs");
  }

  return <div className="app-shell">
    <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
      <div className="brand"><span>r</span><div><strong>runr</strong><small>ADMIN CONSOLE</small></div></div>
      <nav>{NAV.map((item, index) => <button aria-current={item === "Jobs" ? "page" : undefined} className={item === "Jobs" ? "active" : ""} key={item} onClick={() => handleNavigation(item)} type="button"><span>{["⌂", "▤", "◇", "↗", "↻", "✓", "···"][index]}</span>{item}{item === "Jobs" ? <i>{summary.catalog_records ?? "—"}</i> : item === "Review" ? <i>{attentionCount}</i> : null}</button>)}</nav>
      <div className="system-on"><span className="pulse"/><div><b>Acquisition enabled</b><small>{message}</small></div></div>
      <button aria-label="Open administrator profile" className="profile" onClick={() => navigate("/profile")} type="button"><span>AK</span><div><b>Ahmed Kaddah</b><small>Administrator</small></div><i>⌄</i></button>
    </aside>

    <main>
      <header className="topbar">
        <button className="menu" onClick={() => setMenuOpen(value => !value)} type="button">☰</button>
        <div><p>Admin / Jobs</p><h1>Data inspector</h1></div>
        <div className="top-state"><span className="pulse"/><b>Real catalog</b><small>{message}</small></div>
        <button className="primary" disabled={busy} onClick={importJobs} type="button">Import jobs</button>
      </header>

      <div className="workflow">
        {["Import", "Inspect data", "Review", "Publish", "View live"].map((step, index) => <div aria-current={index === 1 ? "step" : undefined} className={index === 1 ? "current" : index === 0 ? "done" : ""} key={step} onClick={() => handleWorkflow(step)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); handleWorkflow(step); } }} role="button" tabIndex={0}><span>{index === 0 ? "✓" : index + 1}</span><b>{step}</b></div>)}
      </div>

      <section className="summary-strip">
        <div><span>Catalog records</span><strong>{summary.catalog_records ?? "—"}</strong><small>all centralized jobs</small></div>
        <div><span>Complete direct Apply URL</span><strong>{summary.apply_url_present ?? "—"}</strong><small className="good">stored URLs</small></div>
        <div><span>Apply URL missing or invalid</span><strong>{summary.apply_url_missing_or_invalid ?? "—"}</strong><small className="bad">blocks user Apply</small></div>
        <div><span>Company profiles incomplete</span><strong>{summary.company_profiles_incomplete ?? "—"}</strong><small className="warn">visible as Unknown</small></div>
      </section>

      <section className="workspace">
        <aside className="job-list card">
          <div className="list-head"><div><h2>Collected jobs</h2><p>Select a record to inspect every stored field</p></div><span>{filtered.length}</span></div>
          <label className="search"><span>⌕</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search jobs, companies, IDs…" /></label>
          <div className="quick-filters"><button aria-pressed={filterMode === "all"} className={filterMode === "all" ? "active" : ""} onClick={() => setFilterMode("all")} type="button">All</button><button aria-pressed={filterMode === "missing"} className={filterMode === "missing" ? "active" : ""} onClick={() => setFilterMode("missing")} type="button">Missing Apply <b>{summary.apply_url_missing_or_invalid ?? "—"}</b></button><button aria-pressed={filterMode === "incomplete"} className={filterMode === "incomplete" ? "active" : ""} onClick={() => setFilterMode("incomplete")} type="button">Incomplete</button></div>
          <div className="records">{filtered.map(record => <button className={String(record.canonical_job_id) === selected.id ? "selected" : ""} key={record.canonical_job_id} onClick={() => { setSelectedId(String(record.canonical_job_id)); setTab("coverage"); setRecordMenuOpen(false); }} type="button">
            <span className="company-mark">{String(record.company || "?").slice(0, 2).toUpperCase()}</span>
            <span className="record-copy"><b>{record.title || "Unknown title"}</b><small>{record.company || "Unknown company"} · {record.location || "Unknown location"}</small><em>{record.canonical_job_id}</em></span>
            <span className={`apply-dot ${record.apply_status === "present" ? "verified" : "missing"}`} title={`Apply URL ${record.apply_status || "unknown"}`} />
          </button>)}</div>
        </aside>

        <article className="inspector card">
          <header className="record-head">
            <div className="record-title"><span className="company-mark large">{selected.company.slice(0, 2).toUpperCase()}</span><div><div className="eyebrow">{selected.id || "No canonical record selected"}</div><h2>{selected.title}</h2><p>{selected.company} · {selected.location} · {selected.source}</p></div></div>
            <div className="record-actions"><Status value={selected.state}/><div className="record-menu-wrap"><button aria-expanded={recordMenuOpen} aria-label="Record actions" onClick={() => setRecordMenuOpen(value => !value)} type="button">⋯</button>{recordMenuOpen ? <div className="record-menu"><button onClick={() => focusInspector("company")} type="button">Inspect company</button><button disabled={busy} onClick={() => { setRecordMenuOpen(false); refreshSelected(); }} type="button">Refresh record</button><button disabled={busy} onClick={() => { setRecordMenuOpen(false); recordDecision("undo"); }} type="button">Send to review</button></div> : null}</div></div>
          </header>

          <section className={`apply-check apply-${selected.applyStatus}`}>
            <span className="apply-icon">{selected.applyStatus === "verified" ? "✓" : "!"}</span>
            <div><small>DIRECT EMPLOYER APPLY URL</small><strong>{selected.applyStatus === "verified" ? "Verified and ready for users" : selected.applyStatus === "missing" ? "Missing — the Apply button cannot work" : "Invalid — resolves to a listing page"}</strong><code>{String(selected.inspection?.apply_url?.user_facing_url || selected.inspection?.apply_url?.resolved_url || selected.job.apply_url || "No direct application URL stored")}</code></div>
            <div className="apply-actions"><button className="secondary" disabled={busy || !selected.id} onClick={resolveApplyUrl} type="button">Resolve URL</button>{selected.applyStatus === "verified" && selected.inspection?.apply_url?.user_facing_url ? <a className="primary" href={selected.inspection.apply_url.user_facing_url} rel="noreferrer" target="_blank">Test Apply ↗</a> : <button className="primary" disabled type="button">Test Apply ↗</button>}</div>
          </section>

          <div className="tabs" role="tablist">
            {DATA_TABS.map(item => <button role="tab" aria-selected={tab === item} className={tab === item ? "active" : ""} onClick={() => setTab(item)} key={item} type="button">{item === "coverage" ? "Data coverage" : item === "complete" ? "Complete JSON" : `${item[0].toUpperCase()}${item.slice(1)} JSON`}</button>)}
          </div>

          {tab === "coverage" ? <div className="coverage-page">
            <div className="coverage-intro"><div><h3>Is this record complete enough to publish?</h3><p>Every missing value is shown explicitly. No value is invented and missing does not mean false.</p></div><div className="score"><strong>{selected.completeness}%</strong><small>overall coverage</small></div></div>
            <div className="coverage-grid">
              {[["Job data", jobCoverage, "Title, description, location, requirements and application destination"], ["Company data", companyCoverage, "Identity, website, profile, funding, leadership and growth"], ["Admin data", adminCoverage, "Source observation, versions, requests, review and publication"]].map(([label, stats, help]) => <section key={label}>
                <header><div><h4>{label}</h4><p>{help}</p></div><strong>{stats.present}/{stats.total}</strong></header>
                <div className="bar"><i style={{ width: `${Math.round(stats.present / Math.max(stats.total, 1) * 100)}%` }}/></div>
                <div className="missing"><b>{stats.missing.length ? `${stats.missing.length} missing fields` : "No missing fields"}</b>{stats.missing.slice(0, 7).map(field => <span key={field}>{field}</span>)}{stats.missing.length > 7 ? <em>+{stats.missing.length - 7} more</em> : null}</div>
                <button onClick={() => setTab(label.startsWith("Job") ? "job" : label.startsWith("Company") ? "company" : "admin")} type="button">Inspect exact JSON →</button>
              </section>)}
            </div>
            <section className="field-checklist"><header><h3>Critical publication checks</h3><span>{attentionCount} need attention</span></header>{criticalChecks.map(item => <div key={item.name}><span className={item.status === "pass" ? "check-pass" : "check-fail"}>{item.status === "pass" ? "✓" : "!"}</span><b>{item.name}</b><code>{typeof item.detail === "string" ? item.detail : JSON.stringify(item.detail)}</code><Status value={item.status === "pass" ? "Pass" : "Fail"}/></div>)}</section>
          </div> : <div className="json-page">
            <div className="json-toolbar"><div><h3>{tab === "complete" ? "Complete stored record" : `${tab[0].toUpperCase()}${tab.slice(1)} data`}</h3><p>Exact backend response. Null and empty values remain visible.</p></div><label><span>⌕</span><input value={jsonSearch} onChange={event => setJsonSearch(event.target.value)} placeholder="Find a field or value…" /></label><button onClick={copyJson} type="button">{copied ? "Copied ✓" : "Copy JSON"}</button><button onClick={downloadJson} type="button">Download</button></div>
            <JsonView value={activeJson} search={jsonSearch}/>
          </div>}

          <footer className="inspector-footer"><div><span className="pulse"/><p><b>Real backend record</b><small>{selected.freshness} · Version {String(selected.admin.posting_version || "Unknown")}</small></p></div><div><button className="secondary" disabled={busy} onClick={() => recordDecision("undo")} type="button">Send to review</button><button className="primary" disabled={busy} onClick={() => recordDecision("approve")} type="button">Approve record</button></div></footer>
        </article>
      </section>
    </main>
    {menuOpen ? <button className="mobile-backdrop" onClick={() => setMenuOpen(false)} aria-label="Close navigation" type="button"/> : null}
  </div>;
}
