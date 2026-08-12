import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { getApiErrorMessage } from "../lib/api";
import { formatDateTime, labelize } from "../lib/formatters";
import AcquisitionShell from "../components/acquisition/AcquisitionShell";

const SECTIONS = [
  ["overview", "Overview", "dashboard"],
  ["sources", "Sources", "lan"],
  ["imports", "Imports", "download"],
  ["jobs", "Jobs", "work_history"],
  ["companies", "Companies", "business"],
  ["enrichment", "Enrichment", "auto_awesome"],
  ["data-quality", "Data Quality", "fact_check"],
  ["duplicates", "Duplicates", "content_copy"],
  ["reprocessing", "Reprocessing", "replay"],
  ["publication", "Publication", "publish"],
  ["live-catalog", "Live Catalog", "language"],
  ["audit", "Audit", "manage_search"],
  ["rules", "Rules", "rule"],
];

const VALID_SECTIONS = new Set(SECTIONS.map(([key]) => key));

function number(value) {
  return Number.isFinite(Number(value)) ? Number(value).toLocaleString() : "—";
}

function text(value, fallback = "—") {
  const result = String(value ?? "").trim();
  return result || fallback;
}

function date(value) {
  return value ? formatDateTime(value) : "—";
}

function tone(value) {
  const normalized = String(value || "").toLowerCase();
  if (["ready", "completed", "published", "valid", "online", "approved", "pass", "report_only"].some((item) => normalized.includes(item))) return "green";
  if (["failed", "blocked", "paused", "needs_attention", "warning", "candidate", "offline", "missing"].some((item) => normalized.includes(item))) return "amber";
  return "slate";
}

function StatusPill({ value }) {
  const label = text(value, "Unknown").replaceAll("_", " ");
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold capitalize status-pill-${tone(value)}`}><span className="h-1.5 w-1.5 rounded-full bg-current" />{label}</span>;
}

function Metric({ label, value, detail, tone: metricTone = "slate" }) {
  return <article className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-on-surface-variant">{label}</p>
    <div className="mt-3 flex items-end justify-between gap-3"><strong className={`font-headline text-3xl font-extrabold tracking-tight metric-${metricTone}`}>{value}</strong><span className="text-right text-xs text-on-surface-variant">{detail}</span></div>
  </article>;
}

function Panel({ title, description, action, children, className = "" }) {
  return <section className={`overflow-hidden rounded-[1.5rem] border border-outline-variant/20 bg-surface-container-lowest shadow-soft ${className}`}>
    <div className="flex flex-col gap-3 border-b border-outline-variant/10 px-5 py-4 md:flex-row md:items-center md:justify-between">
      <div><h2 className="font-headline text-lg font-bold text-on-surface">{title}</h2>{description ? <p className="mt-1 text-sm text-on-surface-variant">{description}</p> : null}</div>
      {action}
    </div>
    {children}
  </section>;
}

function Empty({ children = "No records found." }) {
  return <div className="px-5 py-10 text-center text-sm text-on-surface-variant">{children}</div>;
}

function Table({ columns, rows, rowKey, onRowClick }) {
  if (!rows.length) return <Empty />;
  const cell = (row, key, render) => typeof render === "function" ? render(row) : (row[key] && typeof row[key] === "object" && row[key].$$typeof ? row[key] : text(row[key]));
  return <div className="overflow-x-auto"><table className="w-full min-w-[48rem] text-left text-sm"><thead className="bg-surface-container-low text-xs font-semibold uppercase tracking-wider text-on-surface-variant"><tr>{columns.map(([key, heading]) => <th className="px-5 py-3" key={key}>{heading}</th>)}</tr></thead><tbody className="divide-y divide-outline-variant/10">{rows.map((row, index) => <tr className={onRowClick ? "cursor-pointer hover:bg-surface-container-low" : ""} key={rowKey ? rowKey(row) : `${index}`} onClick={() => onRowClick?.(row)}>{columns.map(([key, render]) => <td className="px-5 py-4 text-on-surface-variant" key={key}>{cell(row, key, render)}</td>)}</tr>)}</tbody></table></div>;
}

function AdminHeader({ section, onRefresh, loading }) {
  const navigate = useNavigate();
  return <>
    <header className="flex flex-col gap-4 border-b border-outline-variant/10 pb-6 md:flex-row md:items-end md:justify-between">
      <div><Link className="mb-3 inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:text-primary-container" to="/admin"><span className="material-symbols-outlined text-[16px]">arrow_back</span>Back to Admin</Link><p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Admin / Acquisition</p><h1 className="mt-2 font-headline text-4xl font-extrabold tracking-tight text-on-surface">{SECTIONS.find(([key]) => key === section)?.[1] || "Overview"}</h1><p className="mt-2 max-w-3xl text-sm leading-7 text-on-surface-variant">Operate the shared job catalog with bounded imports, explicit quality reports, and human-controlled publication.</p></div>
      <div className="flex flex-wrap gap-3"><button className="rounded-2xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high disabled:opacity-60" disabled={loading} onClick={onRefresh} type="button">{loading ? "Refreshing…" : "Refresh"}</button><button className="rounded-2xl bg-gradient-to-br from-primary to-primary-container px-4 py-3 text-sm font-semibold text-white shadow-sm" onClick={() => navigate("/admin/acquisition/sources")} type="button"><span className="material-symbols-outlined mr-1 align-middle text-[17px]">download</span>Import jobs</button></div>
    </header>
  </>;
}

function Overview({ data, navigate }) {
  const imports = data?.imports || {};
  const review = data?.review || {};
  const publication = data?.publication || {};
  return <div className="space-y-5">
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><Metric label="Import status" value={text(imports.status)} detail={imports.paused ? "server switch paused" : "admin execution"} tone={imports.paused ? "amber" : "green"} /><Metric label="Jobs found" value={number(data?.jobs_found)} detail="latest import plan" /><Metric label="Review queue" value={number(review.needs_review)} detail={`${number(review.approved)} approved`} tone={review.needs_review ? "amber" : "green"} /><Metric label="Live jobs" value={number(data?.current_live_jobs)} detail="current publication" tone="green" /></div>
    <div className="grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
      <Panel title="Acquisition health" description="The overview is derived from the admin read model and never triggers an import."><div className="grid gap-3 p-5 sm:grid-cols-2"><div className="rounded-2xl bg-surface-container-low p-4"><span className="text-xs text-on-surface-variant">Worker</span><div className="mt-2 flex items-center justify-between"><strong className="text-lg text-on-surface">{text(data?.worker?.status)}</strong><StatusPill value={data?.worker?.status} /></div><p className="mt-2 text-xs text-on-surface-variant">{number(data?.worker?.workers)} registered workers</p></div><div className="rounded-2xl bg-surface-container-low p-4"><span className="text-xs text-on-surface-variant">Estimated spend today</span><strong className="mt-2 block text-lg text-on-surface">{data?.estimated_spend_today?.known ? `${number(data.estimated_spend_today.credits)} credits` : "Unknown"}</strong><p className="mt-2 text-xs text-on-surface-variant">No cost is inferred when provider data is unavailable.</p></div><div className="rounded-2xl bg-surface-container-low p-4 sm:col-span-2"><span className="text-xs text-on-surface-variant">Last publication</span><div className="mt-2 flex flex-wrap items-center gap-3"><strong className="font-mono text-sm text-on-surface">{text(data?.last_publication?.publication_id, "No publication")}</strong><StatusPill value={data?.last_publication?.status || "not published"} /><span className="text-xs text-on-surface-variant">{date(data?.last_publication?.published_at)}</span></div></div></div></Panel>
      <Panel title="Quality boundary" description="Quality and duplicate findings remain report-only."><div className="space-y-3 p-5"><div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">Rules can explain missing or conflicting data. They do not silently reject or publish records.</div>{(data?.warnings || []).length ? <ul className="space-y-2 text-sm text-on-surface-variant">{data.warnings.map((warning) => <li className="flex gap-2" key={warning}><span className="text-amber-600">!</span>{warning}</li>)}</ul> : <p className="text-sm text-on-surface-variant">No active warnings in the latest import.</p>}<div className="flex flex-wrap gap-2 pt-2"><button className="rounded-xl bg-primary px-3 py-2 text-xs font-semibold text-white" onClick={() => navigate("/admin/acquisition/rules")} type="button">Inspect rules</button><button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-xs font-semibold text-on-surface" onClick={() => navigate("/admin/acquisition/duplicates")} type="button">Review duplicates</button></div></div></Panel>
    </div>
    <Panel title="Recent imports" description="Imports are queued and reviewed before they can become public."><Table columns={[["status", "Status"], ["import_id", "Import"], ["created_at", "Created"], ["source_ids", "Sources"], ["error_message", "Attention"]]} rows={data?.history || []} rowKey={(row) => row.import_id} /></Panel>
    <div className="grid gap-4 md:grid-cols-3"><button className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5 text-left shadow-soft transition-colors hover:bg-surface-container-low" onClick={() => navigate("/admin/acquisition/sources")} type="button"><span className="material-symbols-outlined text-primary">lan</span><strong className="mt-3 block text-base text-on-surface">Manage sources</strong><span className="mt-1 block text-sm text-on-surface-variant">Choose bounded official or web imports.</span></button><button className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5 text-left shadow-soft transition-colors hover:bg-surface-container-low" onClick={() => navigate("/admin/acquisition/reprocessing")} type="button"><span className="material-symbols-outlined text-primary">replay</span><strong className="mt-3 block text-base text-on-surface">Reprocess preserved data</strong><span className="mt-1 block text-sm text-on-surface-variant">Preview additive mutations before applying.</span></button><button className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5 text-left shadow-soft transition-colors hover:bg-surface-container-low" onClick={() => navigate("/admin/acquisition/publication")} type="button"><span className="material-symbols-outlined text-primary">publish</span><strong className="mt-3 block text-base text-on-surface">Control publication</strong><span className="mt-1 block text-sm text-on-surface-variant">Preview, publish, or undo the current head.</span></button></div>
  </div>;
}

function Sources({ data, request, onMessage }) {
  const sources = data?.sources || [];
  const [selected, setSelected] = useState([]);
  const [busy, setBusy] = useState(false);
  const [maxCredits, setMaxCredits] = useState("20");
  useEffect(() => setSelected(sources.filter((source) => source.status === "ready").map((source) => source.id)), [data]);
  async function startImport() {
    if (!selected.length) return onMessage("Choose at least one ready source.");
    if (!window.confirm("Queue this bounded import? It will collect only the selected sources and will not publish jobs automatically.")) return;
    setBusy(true);
    try {
      const scope = { country: "Germany", max_credits: Number(maxCredits) || 0, max_pages: 1 };
      const plan = await request("/admin/acquisition/imports/plan", { method: "POST", body: { source_ids: selected, scope } });
      if (!plan.can_start) throw new Error(`Import plan blocked: ${(plan.limit_errors || []).join(", ")}`);
      await request("/admin/acquisition/imports", { method: "POST", body: { source_ids: selected, scope, idempotency_key: `admin-acquisition-${Date.now()}` } });
      onMessage("Import queued for review.");
    } catch (error) { onMessage(getApiErrorMessage(error, "Import could not be queued.")); } finally { setBusy(false); }
  }
  return <><div className="border-b border-outline-variant/10 p-5"><label className="block max-w-xs text-xs font-semibold uppercase tracking-wide text-on-surface-variant" htmlFor="acquisition-max-credits">Paid-source credit ceiling</label><div className="mt-2 flex flex-wrap items-center gap-3"><input aria-label="Paid-source credit ceiling" className="w-32 rounded-xl border border-outline-variant/20 bg-surface px-3 py-2 text-sm text-on-surface" id="acquisition-max-credits" min="0" onChange={(event) => setMaxCredits(event.target.value)} type="number" value={maxCredits} /><span className="text-xs text-on-surface-variant">Required for ScrapeOps-backed generic/JSON-LD imports; direct ATS imports consume 0.</span></div></div><Panel title="Acquisition sources" description="Only selected sources run, with server-enforced request and credit ceilings." action={<button className="rounded-xl bg-primary px-3 py-2 text-xs font-semibold text-white disabled:opacity-60" disabled={busy || !selected.length} onClick={startImport} type="button">{busy ? "Queueing…" : `Queue import (${selected.length})`}</button>}>
    <div className="grid gap-4 p-5 lg:grid-cols-2">{sources.map((source) => <label className={`cursor-pointer rounded-2xl border p-4 transition-colors ${selected.includes(source.id) ? "border-primary/40 bg-primary/5" : "border-outline-variant/20 bg-surface"}`} key={source.id}><div className="flex items-start gap-3"><input checked={selected.includes(source.id)} disabled={source.status !== "ready" || busy} onChange={(event) => setSelected((current) => event.target.checked ? [...current, source.id] : current.filter((id) => id !== source.id))} type="checkbox" /><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center justify-between gap-2"><strong className="text-base text-on-surface">{text(source.name)}</strong><StatusPill value={source.status} /></div><p className="mt-1 text-sm text-on-surface-variant">{text(source.company)} · {text(source.source_type)}</p><div className="mt-3 grid gap-2 text-xs text-on-surface-variant sm:grid-cols-2"><span>Method: <b className="text-on-surface">{text(source.method)}</b></span><span>Max pages: <b className="text-on-surface">{number(source.max_pages)}</b></span><span>Last import: <b className="text-on-surface">{date(source.last_import)}</b></span><span>Jobs found: <b className="text-on-surface">{number(source.jobs_found)}</b></span></div>{source.reason ? <p className="mt-3 text-xs text-amber-700">{source.reason}</p> : null}<p className="mt-3 truncate font-mono text-[11px] text-on-surface-variant">{(source.request_hosts || []).join(", ") || "host not declared"}</p></div></div></label>)}</div>
  </Panel></>;
}

function Jobs({ data, request, onMessage, onInspect }) {
  const [draft, setDraft] = useState({ search: "", source: "", function: "", workplace: "", employment_type: "", language: "", seniority: "", application_method: "", freshness: "", warning_type: "", duplicate_state: "", completeness_state: "", publication_state: "" });
  const [filters, setFilters] = useState(draft);
  const [jobData, setJobData] = useState(data || {});
  const jobs = jobData?.jobs || [];
  const query = useMemo(() => { const params = new URLSearchParams({ limit: "100" }); Object.entries(filters).forEach(([key, value]) => value && params.set(key, value)); return params.toString(); }, [filters]);
  useEffect(() => { setJobData(data || {}); }, [data]);
  useEffect(() => { let cancelled = false; request(`/admin/acquisition/jobs?${query}`).then((value) => { if (!cancelled) { setJobData(value || {}); onMessage(value?.summary ? `Showing ${number(value.summary.total)} catalog jobs.` : "Jobs refreshed."); } }).catch((error) => { if (!cancelled) onMessage(getApiErrorMessage(error, "Jobs could not be loaded.")); }); return () => { cancelled = true; }; }, [query, request, onMessage]);
  const input = (key, label, placeholder) => <input aria-label={label} className="rounded-xl border border-outline-variant/20 bg-surface px-3 py-2 text-sm text-on-surface" onChange={(event) => setDraft({ ...draft, [key]: event.target.value })} placeholder={placeholder} value={draft[key]} />;
  return <div className="space-y-5"><Panel title="Canonical jobs" description="Filter typed canonical fields and report state. Selecting a row opens the admin inspection read model."><form className="grid gap-3 border-b border-outline-variant/10 p-5 sm:grid-cols-2 lg:grid-cols-4" onSubmit={(event) => { event.preventDefault(); setFilters(draft); }}>{input("search", "Search jobs", "Search title, company, ID")}{input("source", "Source", "Connector or source")}{input("function", "Runr function", "Runr function")}{input("workplace", "Workplace", "Remote, hybrid, on-site")}{input("employment_type", "Employment type", "Full-time, contract")}{input("language", "Language", "Language")}{input("seniority", "Experience", "Seniority")}{input("application_method", "Application method", "Direct, same-page")}{input("freshness", "Freshness", "Fresh or stale")}{input("warning_type", "Warning", "Warning code")}{input("duplicate_state", "Duplicate state", "Candidate or distinct")}<select aria-label="Completeness" className="rounded-xl border border-outline-variant/20 bg-surface px-3 py-2 text-sm text-on-surface" onChange={(event) => setDraft({ ...draft, completeness_state: event.target.value })} value={draft.completeness_state}><option value="">All quality states</option><option value="complete">Complete</option><option value="incomplete">Incomplete</option><option value="unknown">Unknown</option></select><select aria-label="Publication" className="rounded-xl border border-outline-variant/20 bg-surface px-3 py-2 text-sm text-on-surface" onChange={(event) => setDraft({ ...draft, publication_state: event.target.value })} value={draft.publication_state}><option value="">All publication states</option><option value="published">Published</option><option value="unpublished">Unpublished</option></select><button className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white" type="submit">Apply typed filters</button></form><Table columns={[["title", "Job"], ["company", "Company"], ["location", "Location"], ["source_id", "Source"], ["state", "State"], ["apply_status", "Apply"]]} rows={jobs} rowKey={(row) => row.canonical_job_id} onRowClick={onInspect} /></Panel><div className="rounded-2xl border border-primary/15 bg-primary/5 p-4 text-sm text-on-surface-variant">Quality, completeness, warnings, and duplicate matches are reports for administrators. They do not change the public catalog by themselves.</div></div>;
}

function Duplicates({ data }) {
  return <Panel title="Duplicate candidates" description="Candidate clusters preserve provenance and require a human review. No automatic merge is available here."><Table columns={[["cluster_id", "Cluster"], ["state", "State"], ["confidence", "Confidence"], ["members", "Members"], ["reasons", "Evidence"]]} rows={(data?.clusters || []).map((cluster) => ({ ...cluster, members: cluster.members?.length || 0, reasons: (cluster.reasons || []).join(" · ") }))} rowKey={(row) => row.cluster_id} /></Panel>;
}

function InteractiveDuplicates({ data, request, onMessage }) {
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const clusters = data?.clusters || [];
  async function decide(decision) {
    if (!selected) return;
    if (!window.confirm(`Record the ${decision} decision for ${selected.cluster_id}? The backend records an event and plan only; it does not physically merge, split, or publish identities.`)) return;
    let operationPlan;
    if (decision === "merged" || decision === "split") {
      const planText = window.prompt(`${decision} requires a JSON plan. Enter the repository-approved plan details.`);
      if (!planText) return;
      try { operationPlan = JSON.parse(planText); } catch { onMessage(`${decision} requires valid JSON plan details.`); return; }
      if (!operationPlan || typeof operationPlan !== "object" || Array.isArray(operationPlan)) { onMessage(`${decision} requires an object plan.`); return; }
    }
    setBusy(true);
    try {
      await request(`/admin/acquisition/duplicate-clusters/${encodeURIComponent(selected.cluster_id)}/decisions`, { method: "POST", body: { decision, reason: reason || `Admin decision: ${decision}`, evidence: { source: "admin_review", cluster_id: selected.cluster_id }, affected_ids: (selected.member_records || []).map((member) => member.canonical_job_id), rule_version: "duplicate_review_v1", merge_plan: decision === "merged" ? operationPlan : undefined, split_plan: decision === "split" ? operationPlan : undefined } });
      onMessage(`Duplicate cluster marked ${decision}. No records were merged or published.`);
    } catch (error) { onMessage(getApiErrorMessage(error, "Duplicate decision failed.")); } finally { setBusy(false); }
  }
  async function undo() {
    if (!selected) return;
    if (!window.confirm(`Undo the recorded duplicate decision for ${selected.cluster_id}? This appends an undo event and preserves all observations and provenance.`)) return;
    setBusy(true);
    try { await request(`/admin/acquisition/duplicate-clusters/${encodeURIComponent(selected.cluster_id)}/undo`, { method: "POST", body: { reason: reason || "Admin undo", evidence: { source: "admin_review", cluster_id: selected.cluster_id } } }); onMessage("Duplicate decision undone; immutable evidence was preserved."); } catch (error) { onMessage(getApiErrorMessage(error, "Duplicate undo failed.")); } finally { setBusy(false); }
  }
  const rows = clusters.map((cluster) => ({ ...cluster, member_records: cluster.members || [], members: cluster.members?.length || 0, reasons: (cluster.reasons || []).join(" · "), current_decision: cluster.current_decision?.decision || "candidate" }));
  return <>
    <Panel title="Duplicate candidates" description="Candidate clusters preserve provenance and require human review. Decisions are append-only and reversible; merge and publication remain separate explicit operations.">
      <Table columns={[["cluster_id", "Cluster"], ["state", "State"], ["confidence", "Confidence"], ["members", "Members"], ["reasons", "Evidence"], ["current_decision", "Decision"]]} rows={rows} rowKey={(row) => row.cluster_id} onRowClick={setSelected} />
    </Panel>
    {selected ? <section aria-label="Duplicate decision review" className="rounded-2xl border border-primary/20 bg-primary/5 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-mono text-xs text-primary">{selected.cluster_id}</p><h3 className="mt-1 font-headline text-lg font-bold text-on-surface">Human decision</h3><p className="mt-1 text-sm text-on-surface-variant">No automatic merge, canonical rewrite, or publication occurs from this control.</p></div><button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-xs font-semibold text-on-surface" onClick={() => setSelected(null)} type="button">Close</button></div>
      <textarea aria-label="Decision reason" className="mt-4 w-full rounded-xl border border-outline-variant/20 bg-surface px-3 py-2 text-sm text-on-surface" onChange={(event) => setReason(event.target.value)} placeholder="Reason and evidence reference" value={reason} />
      <div className="mt-3 flex flex-wrap gap-2">
        {["candidate", "confirmed_duplicate", "distinct", "ignored", "merged", "split"].map((decision) => <button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-xs font-semibold text-on-surface disabled:opacity-60" disabled={busy} key={decision} onClick={() => decide(decision)} type="button">{labelize(decision)}</button>)}
        <button className="rounded-xl border border-amber-300 px-3 py-2 text-xs font-semibold text-amber-800 disabled:opacity-60" disabled={busy || !(selected.decision_history || []).length} onClick={undo} type="button">Undo decision</button>
      </div>
      <div className="mt-4 space-y-2 text-xs text-on-surface-variant">{(selected.decision_history || []).map((item) => <div className="rounded-xl bg-surface-container-low p-3" key={item.decision_id}><b className="text-on-surface">{item.decision}</b> · {text(item.actor_user_id)} · {date(item.created_at)}<p className="mt-1">{text(item.reason)}</p></div>)}</div>
    </section> : null}
  </>;
}

function Companies({ data, request, onMessage }) {
  const [search, setSearch] = useState("");
  const [applied, setApplied] = useState("");
  const [companyData, setCompanyData] = useState(data || {});
  const companies = companyData?.companies || [];
  useEffect(() => { setCompanyData(data || {}); }, [data]);
  useEffect(() => { const params = new URLSearchParams({ limit: "100" }); if (applied) params.set("search", applied); request(`/admin/acquisition/companies?${params}`).then((value) => setCompanyData(value || {})).catch((error) => onMessage(getApiErrorMessage(error, "Companies could not be loaded."))); }, [applied, request, onMessage]);
  return <Panel title="Canonical companies" description="Company identity, profile fields, URLs, and job counts remain separate from raw source evidence."><form className="flex flex-col gap-3 border-b border-outline-variant/10 p-5 sm:flex-row" onSubmit={(event) => { event.preventDefault(); setApplied(search.trim()); }}><input aria-label="Search companies" className="min-w-0 flex-1 rounded-xl border border-outline-variant/20 bg-surface px-3 py-2 text-sm text-on-surface" onChange={(event) => setSearch(event.target.value)} placeholder="Search company or provenance URL" value={search} /><button className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white" type="submit">Search</button></form><Table columns={[["canonical_name", "Company"], ["job_count", "Jobs"], ["provenance_url", "Provenance"], ["profile", "Profile"], ["urls", "URLs"]]} rows={companies.map((company) => ({ ...company, profile: company.profile && Object.keys(company.profile).length ? "Available" : "Not enriched", urls: company.urls?.length || 0 }))} rowKey={(row) => row.company_id} /></Panel>;
}

function InteractiveCompanies({ data, request, onMessage }) {
  const [search, setSearch] = useState("");
  const [applied, setApplied] = useState("");
  const [companyData, setCompanyData] = useState(data || {});
  const [selected, setSelected] = useState(null);
  const companies = companyData?.companies || [];
  useEffect(() => { setCompanyData(data || {}); }, [data]);
  useEffect(() => { const params = new URLSearchParams({ limit: "100" }); if (applied) params.set("search", applied); request(`/admin/acquisition/companies?${params}`).then((value) => setCompanyData(value || {})).catch((error) => onMessage(getApiErrorMessage(error, "Companies could not be loaded."))); }, [applied, request, onMessage]);
  async function open(company) { try { const value = await request(`/admin/acquisition/companies/${encodeURIComponent(company.company_id)}`); setSelected(value.company || value); } catch (error) { onMessage(getApiErrorMessage(error, "Company detail could not be loaded.")); } }
  return <>
    <Panel title="Canonical companies" description="Inspect identity, official/homepage/careers/ATS URLs, validation, provenance, logo state, and job counts.">
      <form className="flex flex-col gap-3 border-b border-outline-variant/10 p-5 sm:flex-row" onSubmit={(event) => { event.preventDefault(); setApplied(search.trim()); }}>
        <input aria-label="Search companies" className="min-w-0 flex-1 rounded-xl border border-outline-variant/20 bg-surface px-3 py-2 text-sm text-on-surface" onChange={(event) => setSearch(event.target.value)} placeholder="Search company or provenance URL" value={search} />
        <button className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white" type="submit">Search</button>
      </form>
      <Table columns={[["canonical_name", "Company"], ["job_count", "Jobs"], ["provenance_url", "Provenance"], ["profile", "Profile"], ["urls", "URLs"]]} rows={companies.map((company) => ({ ...company, profile: company.profile && Object.keys(company.profile).length ? "Available" : "Not enriched", urls: company.urls?.length || 0 }))} rowKey={(row) => row.company_id} onRowClick={open} />
    </Panel>
    {selected ? <section aria-label="Company detail" className="rounded-2xl border border-primary/20 bg-primary/5 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><p className="font-mono text-xs text-primary">{selected.company_id}</p><h3 className="mt-1 font-headline text-lg font-bold text-on-surface">{text(selected.canonical_name)}</h3><p className="mt-1 text-sm text-on-surface-variant">{number(selected.job_count)} jobs · identity and enrichment are separate projections</p></div>
        <button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-xs font-semibold text-on-surface" onClick={() => setSelected(null)} type="button">Close</button>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {(selected.urls || []).map((url) => <div className="rounded-xl bg-surface-container-low p-3" key={url.company_url_id || url.canonical_url}><p className="text-xs font-semibold uppercase text-on-surface-variant">{text(url.url_type)}</p><a className="mt-1 block break-all text-xs text-primary" href={url.canonical_url || url.url} rel="noreferrer" target="_blank">{text(url.canonical_url || url.url)}</a><p className="mt-1 text-xs text-on-surface-variant">{text(url.validation_status)} · {text(url.source, "unknown source")}</p></div>)}
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl bg-surface-container-low p-3 text-sm text-on-surface-variant"><b className="text-on-surface">Logo:</b> {text(selected.logo_source_url, "Deterministic monogram fallback")} · {text(selected.logo_verified_at, "not verified")}</div>
        <div className="rounded-xl bg-surface-container-low p-3 text-sm text-on-surface-variant"><b className="text-on-surface">Reconciliation:</b> {text(selected.reconciliation_state, "identity projection only")}</div>
      </div>
      {(selected.logo_enrichments || []).length ? <div className="mt-3 space-y-2 text-xs text-on-surface-variant">{selected.logo_enrichments.map((logo) => <div className="rounded-xl bg-surface-container-low p-3" key={logo.logo_enrichment_id}><b className="text-on-surface">{text(logo.provider)}</b> · {text(logo.status)} · {text(logo.source_url)}</div>)}</div> : null}
      <JsonDetails label="Company identity and provenance" value={{ profile: selected.profile, aliases: selected.aliases, link_candidates: selected.link_candidates, source_relationships: selected.source_relationships }} />
      <p className="mt-3 text-xs text-on-surface-variant">Identity reconciliation is inspectable here; physical merges and automatic enrichment are not exposed without a supported, explicitly scoped backend operation.</p>
    </section> : null}
  </>;
}

function Rules({ data, request, onMessage }) {
  const renderCounts = (items, keys) => <div className="space-y-2">{(items || []).length ? items.map((item, index) => <div className="flex items-center justify-between gap-3 rounded-xl bg-surface-container-low px-3 py-2 text-xs" key={`${JSON.stringify(item)}-${index}`}><span className="text-on-surface-variant">{keys.map((key) => text(item[key], "—")).join(" · ")}</span><b className="text-on-surface">{number(item.count)}</b></div>) : <p className="text-sm text-on-surface-variant">No report rows yet.</p>}</div>;
  return <div className="space-y-5"><div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><b>Report-only quality contract.</b> Rule version {text(data?.rule_version)} explains coverage, warnings, and stage outcomes. It is not a publication gate.</div><div className="grid gap-5 xl:grid-cols-2"><Panel title="Field provenance" description="Selected and unselected field states by entity.">{renderCounts(data?.field_states, ["entity_kind", "field_name", "state"])}</Panel><Panel title="Pipeline stages" description="Stage status across acquisition executions.">{renderCounts(data?.stage_states, ["stage_name", "status"])}</Panel><Panel title="Completeness" description="Completeness reports by state.">{renderCounts(data?.completeness_states, ["state"])}</Panel><Panel title="Quality warnings" description="Warnings are retained for diagnosis and review.">{renderCounts(data?.warnings, ["warning_code", "severity"])}</Panel></div></div>;
}

function ConnectorCapabilities({ request, onMessage }) {
  const [rows, setRows] = useState([]);
  useEffect(() => { request("/admin/acquisition/connectors/capabilities?limit=200").then((value) => setRows(value?.connectors || [])).catch((error) => onMessage(getApiErrorMessage(error, "Connector capabilities could not be loaded."))); }, [request, onMessage]);
  return <Panel title="Connector capability and raw-retention contract" description="Workday, Personio, Recruitee, and SmartRecruiters are production-registered with bounded direct requests. Capability reports do not publish jobs automatically."><Table columns={[["connector", "Connector"], ["state", "State"], ["production_registered", "Registered"], ["raw_retention", "Raw retention"], ["failure_policy", "Failure policy"]]} rows={rows.map((item) => ({ ...item, production_registered: item.production_registered ? "yes" : "no", raw_retention: item.raw_retention?.required ? "required · admin-only" : "unknown" }))} rowKey={(row) => row.connector} /></Panel>;
}

function Reprocessing({ data, request, onMessage }) {
  const [busy, setBusy] = useState(false);
  async function run() {
    if (!window.confirm("Run additive reprocessing on preserved observations? It will not publish or merge jobs automatically.")) return;
    setBusy(true);
    try { const result = await request("/admin/acquisition/reprocessing/run", { method: "POST", body: { apply: true, batch_size: 100, idempotency_key: `admin-reprocess-${Date.now()}` } }); onMessage(result.status === "completed" ? "Reprocessing completed." : `Reprocessing ${text(result.status)}.`); } catch (error) { onMessage(getApiErrorMessage(error, "Reprocessing failed.")); } finally { setBusy(false); }
  }
  const counts = data?.plan?.counts_before || {};
  return <div className="space-y-5"><Panel title="Reprocessing plan" description="The plan is read-only. Apply is additive, resumable, backed up locally, and never promotes publication automatically." action={<button className="rounded-xl bg-primary px-3 py-2 text-xs font-semibold text-white disabled:opacity-60" disabled={busy} onClick={run} type="button">{busy ? "Running…" : "Run additive reprocessing"}</button>}><div className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-4">{Object.entries(counts).map(([key, value]) => <div className="rounded-xl bg-surface-container-low p-3" key={key}><span className="text-xs text-on-surface-variant">{labelize(key)}</span><b className="mt-1 block text-lg text-on-surface">{number(value)}</b></div>)}</div><div className="border-t border-outline-variant/10 px-5 py-4 text-xs text-on-surface-variant">Rule version: <b className="font-mono text-on-surface">{text(data?.plan?.rule_version)}</b> · Environment: <b className="text-on-surface">{text(data?.plan?.environment?.configured_environment)}</b></div></Panel><Panel title="Recent runs" description="Checkpoint, counts, and rollback metadata are visible to administrators."><Table columns={[["status", "Status"], ["reprocessing_id", "Run"], ["rule_version", "Rule version"], ["created_at", "Created"], ["completed_at", "Completed"]]} rows={data?.runs || []} rowKey={(row) => row.reprocessing_id} /></Panel></div>;
}

function Publication({ data, request, onMessage }) {
  const [importId, setImportId] = useState("");
  const [publicationId, setPublicationId] = useState("");
  const [busy, setBusy] = useState(false);
  async function action(path, body, message) { if (path.endsWith("/publish") && !window.confirm(`Publish preview ${body.publication_id}? This changes the live publication head and publishes only that explicit preview.`)) return; if (path.endsWith("/undo") && !window.confirm(`Undo the current publication head ${data?.current_head?.publication_id || ""}? The backend will restore its reversible prior state.`)) return; setBusy(true); try { const result = await request(path, { method: "POST", body }); if (result.publication_id) setPublicationId(result.publication_id); onMessage(message); } catch (error) { onMessage(getApiErrorMessage(error, "Publication action failed.")); } finally { setBusy(false); } }
  const head = data?.current_head;
  return <div className="space-y-5"><div className="rounded-2xl border border-green-200 bg-green-50 p-4 text-sm text-green-900"><b>Manual publication only.</b> Automatic promotion is {data?.automatic_promotion ? "enabled" : "disabled"}; the current head is the only public catalog pointer.</div><div className="grid gap-5 xl:grid-cols-[1fr_1fr]"><Panel title="Current publication head" description="The public catalog is served from this validated head."><div className="space-y-3 p-5"><div className="flex flex-wrap items-center gap-3"><strong className="font-mono text-sm text-on-surface">{text(head?.publication_id, "No current head")}</strong><StatusPill value={head?.status || "not published"} /></div><p className="text-sm text-on-surface-variant">{number(data?.current_job_count)} jobs · published {date(head?.published_at)}</p><div className="flex flex-wrap gap-2 pt-2"><button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-xs font-semibold text-on-surface" disabled={busy || !head?.publication_id} onClick={() => action("/admin/acquisition/publication/undo", {}, "Last publication undone.")} type="button">Undo last publication</button></div></div></Panel><Panel title="Preview and publish" description="Preview an approved import, then publish only the explicit preview ID."><div className="space-y-3 p-5"><input aria-label="Import ID" className="w-full rounded-xl border border-outline-variant/20 bg-surface px-3 py-2 text-sm text-on-surface" onChange={(event) => setImportId(event.target.value)} placeholder="Approved import ID" value={importId} /><button className="rounded-xl border border-primary/20 bg-primary/10 px-3 py-2 text-xs font-semibold text-primary" disabled={busy || !importId} onClick={async () => { setBusy(true); try { const preview = await request("/admin/acquisition/publication/preview", { method: "POST", body: { import_id: importId } }); setPublicationId(preview.publication_id || ""); onMessage("Publication preview created."); } catch (error) { onMessage(getApiErrorMessage(error, "Preview failed.")); } finally { setBusy(false); } }} type="button">Create preview</button><input aria-label="Publication ID" className="w-full rounded-xl border border-outline-variant/20 bg-surface px-3 py-2 text-sm text-on-surface" onChange={(event) => setPublicationId(event.target.value)} placeholder="Publication preview ID" value={publicationId} /><button className="rounded-xl bg-primary px-3 py-2 text-xs font-semibold text-white" disabled={busy || !publicationId} onClick={() => action("/admin/acquisition/publication/publish", { publication_id: publicationId }, "Publication promoted to the current head.")} type="button">Publish preview</button></div></Panel></div><Panel title="Publication states" description="Historical publication records by state."><Table columns={[["status", "Status"], ["count", "Count"]]} rows={data?.publication_states || []} /></Panel></div>;
}

function JsonDetails({ label = "Structured payload", value }) {
  return <details className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-3"><summary className="cursor-pointer text-xs font-semibold text-on-surface">{label}</summary><pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-on-surface-variant">{JSON.stringify(value ?? {}, null, 2)}</pre></details>;
}

function Imports({ data, request, onMessage }) {
  const [sources, setSources] = useState([]);
  const [selectedSources, setSelectedSources] = useState([]);
  const [scope, setScope] = useState({ country: "Germany", max_pages: 1, max_requests: 20, max_credits: 20 });
  const [plan, setPlan] = useState(null);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const imports = data?.imports || [];

  useEffect(() => {
    request("/admin/acquisition/sources")
      .then((value) => {
        const rows = value?.sources || [];
        setSources(rows);
        setSelectedSources((current) => current.length ? current : rows.filter((item) => item.status === "ready").map((item) => item.id));
      })
      .catch((error) => onMessage(getApiErrorMessage(error, "Sources could not be loaded for import planning.")));
  }, [onMessage, request]);

  function updateScope(key, value) {
    setScope((current) => ({ ...current, [key]: key === "country" ? value : Math.max(0, Number(value) || 0) }));
  }

  async function createPlan(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await request("/admin/acquisition/imports/plan", { method: "POST", body: { source_ids: selectedSources, scope } });
      setPlan(result);
      onMessage(result.can_start ? "Import plan created. Review its bounded scope before queueing." : "Import plan is blocked by server-enforced limits.");
    } catch (error) { onMessage(getApiErrorMessage(error, "Import plan could not be created.")); } finally { setBusy(false); }
  }

  async function queueImport() {
    if (!plan?.can_start) return;
    if (!window.confirm("Queue this bounded import? It will collect only the planned scope, retain observations for review, and will not publish jobs.")) return;
    setBusy(true);
    try {
      await request("/admin/acquisition/imports", { method: "POST", body: { source_ids: selectedSources, scope: plan.scope || scope, idempotency_key: `admin-acquisition-${Date.now()}` } });
      onMessage("Import queued. Monitor its status here; publication remains a separate explicit action.");
      setPlan(null);
    } catch (error) { onMessage(getApiErrorMessage(error, "Import could not be queued.")); } finally { setBusy(false); }
  }

  async function inspectImport(importId) {
    try { setDetail(await request(`/admin/acquisition/imports/${encodeURIComponent(importId)}`)); } catch (error) { onMessage(getApiErrorMessage(error, "Import detail could not be loaded.")); }
  }

  return <div className="space-y-5">
    <Panel title="Plan a bounded import" description="Planning shows scope, request ceilings, and warnings before anything is queued. A completed import is not an exhaustive collection and never publishes automatically.">
      <form className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-4" onSubmit={createPlan}>
        <label className="text-xs font-semibold text-on-surface-variant">Sources<select aria-label="Import sources" className="mt-2 min-h-10 w-full rounded-xl border border-outline-variant/20 bg-surface px-3 text-sm font-normal text-on-surface" multiple onChange={(event) => setSelectedSources(Array.from(event.target.selectedOptions, (option) => option.value))} value={selectedSources}>{sources.map((source) => <option disabled={source.status !== "ready"} key={source.id} value={source.id}>{source.name || source.id} · {source.status}</option>)}</select></label>
        <label className="text-xs font-semibold text-on-surface-variant">Country<input className="mt-2 min-h-10 w-full rounded-xl border border-outline-variant/20 bg-surface px-3 text-sm font-normal text-on-surface" onChange={(event) => updateScope("country", event.target.value)} value={scope.country} /></label>
        <label className="text-xs font-semibold text-on-surface-variant">Max pages<input className="mt-2 min-h-10 w-full rounded-xl border border-outline-variant/20 bg-surface px-3 text-sm font-normal text-on-surface" min="1" onChange={(event) => updateScope("max_pages", event.target.value)} type="number" value={scope.max_pages} /></label>
        <label className="text-xs font-semibold text-on-surface-variant">Max requests<input className="mt-2 min-h-10 w-full rounded-xl border border-outline-variant/20 bg-surface px-3 text-sm font-normal text-on-surface" min="1" onChange={(event) => updateScope("max_requests", event.target.value)} type="number" value={scope.max_requests} /></label>
        <label className="text-xs font-semibold text-on-surface-variant">Max credits<input className="mt-2 min-h-10 w-full rounded-xl border border-outline-variant/20 bg-surface px-3 text-sm font-normal text-on-surface" min="0" onChange={(event) => updateScope("max_credits", event.target.value)} type="number" value={scope.max_credits} /></label>
        <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-3"><button className="min-h-10 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={busy || !selectedSources.length} type="submit">{busy ? "Planning…" : "Create plan"}</button><button className="min-h-10 rounded-xl border border-primary/20 bg-primary/5 px-4 py-2 text-sm font-semibold text-primary disabled:opacity-60" disabled={busy || !plan?.can_start} onClick={queueImport} type="button">Queue planned import</button></div>
      </form>
      {plan ? <div className="border-t border-outline-variant/10 p-5"><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Metric label="Expected requests" value={number(plan.maximum_requests)} detail="server-bounded" /><Metric label="Maximum pages" value={number(plan.maximum_pages)} detail="per selected source" /><Metric label="Effective jobs" value={number(plan.sources?.reduce((sum, item) => sum + Number(item.effective_job_limit || 0), 0))} detail="ceiling, not a promise" /><Metric label="Cost" value={plan.estimated_cost?.known ? number(plan.estimated_cost.maximum) : "Unknown"} detail={plan.estimated_cost?.currency || "provider data unavailable"} /></div>{(plan.limit_errors || []).length ? <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Plan warnings: {plan.limit_errors.join(" · ")}</div> : <p className="mt-4 text-sm text-on-surface-variant">This plan is ready to queue. Collection remains bounded and review-only.</p>}</div> : null}
    </Panel>
    <Panel title="Import history" description="Inspect status, timestamps, selected sources, counts, and attention messages. Select an import for its durable detail record."><Table columns={[["status", "Status"], ["import_id", "Import"], ["created_at", "Created"], ["source_ids", "Sources"], ["error_message", "Attention"]]} rows={imports.map((item) => ({ ...item, source_ids: (item.source_ids || []).join(" · ") || "—" }))} rowKey={(row) => row.import_id} onRowClick={(row) => inspectImport(row.import_id)} /></Panel>
    {detail ? <section aria-label="Import detail" className="rounded-2xl border border-primary/20 bg-primary/5 p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-mono text-xs text-primary">{text(detail.import_id)}</p><h2 className="mt-1 font-headline text-xl font-bold text-on-surface">Import detail</h2><p className="mt-1 text-sm text-on-surface-variant">{text(detail.status)} · {date(detail.created_at)}</p></div><button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-xs font-semibold text-on-surface" onClick={() => setDetail(null)} type="button">Close</button></div><div className="mt-4 grid gap-3 sm:grid-cols-3"><div className="rounded-xl bg-surface-container-low p-3 text-sm"><span className="text-xs text-on-surface-variant">Sources</span><b className="mt-1 block text-on-surface">{(detail.source_ids || []).join(" · ") || "Unavailable"}</b></div><div className="rounded-xl bg-surface-container-low p-3 text-sm"><span className="text-xs text-on-surface-variant">Cycle</span><b className="mt-1 block font-mono text-xs text-on-surface">{text(detail.cycle_id)}</b></div><div className="rounded-xl bg-surface-container-low p-3 text-sm"><span className="text-xs text-on-surface-variant">Publication</span><b className="mt-1 block text-on-surface">Not automatic</b></div></div><JsonDetails label="Import plan and scope" value={{ scope: detail.scope, plan: detail.plan }} /></section> : null}
  </div>;
}

function Enrichment({ data, request, onMessage }) {
  const [provider, setProvider] = useState("null");
  const [targetType, setTargetType] = useState("company");
  const [fields, setFields] = useState("website,industry");
  const [busy, setBusy] = useState(false);
  const capabilities = data?.capabilities || {};
  const runs = data?.runs || [];
  const plans = data?.plans || [];
  const proposals = data?.proposals || [];
  const providers = capabilities.providers || [];

  async function createPlan(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await request("/admin/enrichment/plans", { method: "POST", body: { scope_type: "query", target_type: targetType, provider_id: provider, selected_fields: fields.split(",").map((item) => item.trim()).filter(Boolean), query_snapshot: {}, expected_request_count: 0, expected_cost: 0, idempotency_key: `admin-enrichment-${Date.now()}` } });
      onMessage(`Report-only enrichment plan ${text(result.plan_id)} created.`);
    } catch (error) { onMessage(getApiErrorMessage(error, "Enrichment plan could not be created.")); } finally { setBusy(false); }
  }

  async function startPlan(plan) {
    if (!window.confirm(`Start report-only enrichment plan ${plan.plan_id}? Raw observations remain unchanged and nothing will be published.`)) return;
    setBusy(true);
    try { await request(`/admin/enrichment/plans/${encodeURIComponent(plan.plan_id)}/start`, { method: "POST", body: { idempotency_key: `admin-enrichment-run-${Date.now()}` } }); onMessage("Enrichment run started in report-only mode."); } catch (error) { onMessage(getApiErrorMessage(error, "Enrichment run could not be started.")); } finally { setBusy(false); }
  }

  async function reviewProposal(proposal, action) {
    if (!window.confirm(`${action === "accept" ? "Accept" : "Reject"} this proposed value? Raw evidence remains preserved and publication is not changed.`)) return;
    setBusy(true);
    try { await request(`/admin/enrichment/proposals/${encodeURIComponent(proposal.proposal_id)}/${action}`, { method: "POST", body: { reason: `Admin ${action}` } }); onMessage(`Proposal ${action}ed.`); } catch (error) { onMessage(getApiErrorMessage(error, "Enrichment proposal review failed.")); } finally { setBusy(false); }
  }

  return <div className="space-y-5"><div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><b>Report-only boundary.</b> Live network providers, AI, and paid budgets are not activated here. The offline fixture remains report-only; proposed values require review and never publish automatically.</div><Panel title="Provider and policy state" description="Use the backend capability report instead of assuming connector completeness."><div className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-3"><div className="rounded-xl bg-surface-container-low p-3"><span className="text-xs text-on-surface-variant">Policy</span><b className="mt-1 block text-on-surface">{text(capabilities.policy_version, "Unavailable")}</b></div><div className="rounded-xl bg-surface-container-low p-3"><span className="text-xs text-on-surface-variant">Execution</span><b className="mt-1 block text-on-surface">{capabilities.report_only === true ? "Report-only" : "Unavailable"}</b></div><div className="rounded-xl bg-surface-container-low p-3"><span className="text-xs text-on-surface-variant">Providers returned</span><b className="mt-1 block text-on-surface">{number(providers.length)}</b></div></div><div className="divide-y divide-outline-variant/10">{providers.map((item) => <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 text-sm" key={item.provider_id}><span className="font-mono text-on-surface">{item.provider_id}</span><span className="text-on-surface-variant">{text(item.state || item.status, "Unavailable")} · {item.enabled ? "enabled" : "disabled"} · {item.report_only ? "report-only" : "activation unavailable"}</span></div>)}</div></Panel><Panel title="Create a report-only plan" description="Planning is additive and records scope, fields, provider, and request/cost expectations before a run exists."><form className="grid gap-3 p-5 sm:grid-cols-3" onSubmit={createPlan}><label className="text-xs font-semibold text-on-surface-variant">Target<select className="mt-2 min-h-10 w-full rounded-xl border border-outline-variant/20 bg-surface px-3 text-sm font-normal text-on-surface" onChange={(event) => setTargetType(event.target.value)} value={targetType}><option value="company">Company</option><option value="job">Job</option></select></label><label className="text-xs font-semibold text-on-surface-variant">Provider<select className="mt-2 min-h-10 w-full rounded-xl border border-outline-variant/20 bg-surface px-3 text-sm font-normal text-on-surface" onChange={(event) => setProvider(event.target.value)} value={provider}><option value="null">null · no live provider</option><option value="fixture">offline fixture · report-only</option></select></label><label className="text-xs font-semibold text-on-surface-variant">Fields<input className="mt-2 min-h-10 w-full rounded-xl border border-outline-variant/20 bg-surface px-3 text-sm font-normal text-on-surface" onChange={(event) => setFields(event.target.value)} value={fields} /></label><button className="min-h-10 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-60 sm:col-span-3 sm:w-fit" disabled={busy} type="submit">{busy ? "Creating…" : "Create report-only plan"}</button></form></Panel><Panel title="Plans and runs" description="Progress, budgets, failures, and audit records are backend-owned. Retry/process controls are shown only for explicit existing run contracts."><Table columns={[["plan_id", "Plan"], ["target_type", "Object"], ["provider_id", "Provider"], ["report_only", "Mode"], ["status", "Status"], ["created_at", "Created"]]} rows={plans.map((item) => ({ ...item, report_only: item.report_only ? "report-only" : "Unavailable" }))} rowKey={(row) => row.plan_id} onRowClick={(plan) => startPlan(plan)} /><Table columns={[["run_id", "Run"], ["status", "Status"], ["result_count", "Results"], ["failure_count", "Failures"], ["created_at", "Created"]]} rows={runs} rowKey={(row) => row.run_id} /></Panel><Panel title="Proposed values" description="Evidence, confidence, provider, and provenance stay visible before acceptance."><Table columns={[["proposal_id", "Proposal"], ["field_path", "Field"], ["provider_id", "Provider"], ["confidence", "Confidence"], ["status", "Status"]]} rows={proposals} rowKey={(row) => row.proposal_id} onRowClick={(proposal) => reviewProposal(proposal, "accept")} /></Panel></div>;
}

function DataQuality({ data, request, onMessage }) {
  return <div className="space-y-5"><Rules data={data?.rules || data} /><Reprocessing data={{ plan: data?.plan, runs: data?.runs }} request={request} onMessage={onMessage} /></div>;
}

function LiveCatalog({ data, request, onMessage }) {
  const location = useLocation();
  const navigate = useNavigate();
  const offset = Math.max(0, Number(new URLSearchParams(location.search).get("offset") || 0));
  const [catalog, setCatalog] = useState(data || {});
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const rows = catalog?.jobs || [];
  const total = Number(catalog?.total || 0);
  const limit = 50;
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    request(`/admin/acquisition/live-catalog?limit=${limit}&offset=${offset}`).then((value) => { if (!cancelled) setCatalog(value || {}); }).catch((error) => { if (!cancelled) onMessage(getApiErrorMessage(error, "Live catalog could not be loaded.")); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [offset, onMessage, request]);
  async function inspect(row) { try { setSelected(await request(`/admin/acquisition/jobs/${encodeURIComponent(row.canonical_job_id || row.id)}`)); } catch (error) { onMessage(getApiErrorMessage(error, "Published job inspection could not be loaded.")); } }
  return <div className="space-y-5"><div className="rounded-2xl border border-primary/15 bg-primary/5 p-4 text-sm text-on-surface-variant"><b className="text-on-surface">Read-only live catalog.</b> Publication {text(catalog?.publication?.publication_id)} · {date(catalog?.publication?.published_at)} · {number(total)} published jobs. Newer canonical or proposed values are not shown as live until an explicit publication.</div>{loading ? <div aria-label="Loading live catalog" className="rounded-2xl bg-surface-container p-8 text-sm text-on-surface-variant" role="status">Loading published jobs…</div> : null}<Panel title="Published jobs" description="This view never mutates the publication head."><Table columns={[["title", "Job"], ["company", "Company"], ["location", "Location"], ["apply_url", "Apply"]]} rows={rows} rowKey={(row) => row.canonical_job_id || row.id} onRowClick={inspect} /></Panel>{total > limit ? <div className="flex flex-wrap items-center justify-between gap-3"><span className="text-xs text-on-surface-variant">Page {Math.floor(offset / limit) + 1} of {Math.max(1, Math.ceil(total / limit))}</span><div className="flex gap-2"><button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-sm font-semibold disabled:opacity-40" disabled={!offset} onClick={() => navigate(`/admin/acquisition/live-catalog?offset=${Math.max(0, offset - limit)}`)} type="button">Previous</button><button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-sm font-semibold disabled:opacity-40" disabled={offset + limit >= total} onClick={() => navigate(`/admin/acquisition/live-catalog?offset=${offset + limit}`)} type="button">Next</button></div></div> : null}{selected ? <Inspection onClose={() => setSelected(null)} value={selected} /> : null}</div>;
}

function Audit({ data, request, onMessage }) {
  const location = useLocation();
  const navigate = useNavigate();
  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const [draft, setDraft] = useState({ event: params.get("event") || "", actor: params.get("actor") || "", entity_type: params.get("entity_type") || "", occurred_from: params.get("occurred_from") || "", occurred_to: params.get("occurred_to") || "" });
  const [audit, setAudit] = useState(data || {});
  const [loading, setLoading] = useState(false);
  const apply = (event) => { event.preventDefault(); const next = new URLSearchParams(); Object.entries(draft).forEach(([key, value]) => value && next.set(key, value)); next.set("limit", "50"); next.set("offset", "0"); navigate(`/admin/acquisition/audit?${next.toString()}`); };
  useEffect(() => {
    setDraft({ event: params.get("event") || "", actor: params.get("actor") || "", entity_type: params.get("entity_type") || "", occurred_from: params.get("occurred_from") || "", occurred_to: params.get("occurred_to") || "" });
    let cancelled = false;
    setLoading(true);
    request(`/admin/acquisition/audit?${params.toString() || "limit=50&offset=0"}`).then((value) => { if (!cancelled) setAudit(value || {}); }).catch((error) => { if (!cancelled) onMessage(getApiErrorMessage(error, "Acquisition audit could not be loaded.")); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [location.search, onMessage, params, request]);
  const events = audit?.events || [];
  const pagination = audit?.pagination || {};
  return <div className="space-y-5"><Panel title="Acquisition audit" description="Dedicated acquisition audit with bounded date ranges, actor/action/target filters, correlation identifiers, and redacted structured payloads."><form className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-5" onSubmit={apply}>{[["event", "Action / event"], ["actor", "Actor"], ["entity_type", "Target object"], ["occurred_from", "From"], ["occurred_to", "To"]].map(([key, label]) => <label className="text-xs font-semibold text-on-surface-variant" key={key}>{label}<input className="mt-2 min-h-10 w-full rounded-xl border border-outline-variant/20 bg-surface px-3 text-sm font-normal text-on-surface" onChange={(event) => setDraft((current) => ({ ...current, [key]: event.target.value }))} value={draft[key]} /></label>)}<button className="min-h-10 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white sm:w-fit" type="submit">Apply filters</button></form></Panel>{loading ? <div aria-label="Loading acquisition audit" className="rounded-2xl bg-surface-container p-8 text-sm text-on-surface-variant" role="status">Loading audit…</div> : null}<Panel title="Events" description={`${number(pagination.total)} matching events · page offset ${number(pagination.offset)}`}><Table columns={[["event", "Event"], ["actor", "Actor"], ["entity_type", "Target"], ["entity_id", "Identifier"], ["operation_id", "Operation"], ["created_at", "Occurred"], ["payload", "Payload"]]} rows={events.map((item) => ({ ...item, payload: <JsonDetails label="View redacted payload" value={item.payload} /> }))} rowKey={(row) => row.event_id} /></Panel></div>;
}

function Inspection({ value, onClose }) {
  useEffect(() => {
    if (!value) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, value]);
  if (!value) return null;
  return <div className="fixed inset-0 z-50 flex items-end justify-end bg-slate-950/30 p-0 sm:p-5" role="presentation"><button aria-label="Close inspection" className="absolute inset-0 cursor-default" onClick={onClose} type="button" /><aside className="relative max-h-[92vh] w-full overflow-y-auto rounded-t-[1.5rem] bg-surface-container-lowest p-5 shadow-2xl sm:max-w-2xl sm:rounded-[1.5rem]"><div className="flex items-start justify-between gap-4"><div><p className="font-mono text-xs text-primary">{text(value.job?.canonical_job_id)}</p><h2 className="mt-1 font-headline text-2xl font-extrabold text-on-surface">{text(value.job?.title)}</h2><p className="mt-1 text-sm text-on-surface-variant">{text(value.company?.name)} · {text(value.job?.location_raw)}</p></div><button aria-label="Close" className="rounded-xl border border-outline-variant/20 px-3 py-2 text-sm text-on-surface" onClick={onClose} type="button">Close</button></div><div className="mt-5 grid gap-3 sm:grid-cols-2"><div className="rounded-xl bg-surface-container-low p-3"><span className="text-xs text-on-surface-variant">Apply URL</span><strong className="mt-1 block text-sm text-on-surface">{text(value.apply_url?.status)}</strong><p className="mt-1 break-all text-xs text-on-surface-variant">{text(value.apply_url?.user_facing_url || value.apply_url?.resolved_url)}</p></div><div className="rounded-xl bg-surface-container-low p-3"><span className="text-xs text-on-surface-variant">Completeness</span><strong className="mt-1 block text-sm text-on-surface">{number(value.completeness?.overall_percent)}%</strong><p className="mt-1 text-xs text-on-surface-variant">Report-only quality result</p></div></div><h3 className="mt-5 font-headline text-base font-bold text-on-surface">Admin provenance</h3><dl className="mt-2 grid gap-2 text-sm sm:grid-cols-2">{[["Connector", value.admin?.connector], ["Source observations", value.admin?.source_observation_ids?.length], ["Posting version", value.admin?.posting_version], ["Review state", value.admin?.review_state], ["Publication", value.admin?.publication_status]].map(([key, item]) => <div className="rounded-xl border border-outline-variant/10 p-3" key={key}><dt className="text-xs text-on-surface-variant">{key}</dt><dd className="mt-1 font-medium text-on-surface">{text(item)}</dd></div>)}</dl><p className="mt-5 rounded-xl border border-primary/15 bg-primary/5 p-3 text-xs text-on-surface-variant">Raw source evidence is intentionally not rendered in this panel. It remains available only behind the admin inspection API; the quality result above is report-only.</p></aside></div>;
}

export default function AdminAcquisitionPage() {
  const { section: routeSection } = useParams();
  const section = VALID_SECTIONS.has(routeSection) ? routeSection : "overview";
  const { request } = useSession();
  const navigate = useNavigate();
  const [data, setData] = useState({});
  const [inspection, setInspection] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const pathBySection = { overview: "/admin/acquisition/overview", sources: "/admin/acquisition/sources", imports: "/admin/acquisition/imports?limit=50&offset=0", jobs: "/admin/acquisition/jobs?limit=100", duplicates: "/admin/acquisition/duplicates?limit=100", companies: "/admin/acquisition/companies?limit=100", rules: "/admin/acquisition/rules", publication: "/admin/acquisition/publication", "live-catalog": "/admin/acquisition/live-catalog?limit=50&offset=0", audit: "/admin/acquisition/audit?limit=50&offset=0" };
      if (section === "overview") {
        const [overview, publication] = await Promise.all([request(pathBySection.overview), request(pathBySection.publication)]);
        setData({ ...overview, publication });
      } else if (section === "enrichment") {
        const [capabilities, runs, plans, proposals, budgets] = await Promise.all([
          request("/admin/enrichment/capabilities"),
          request("/admin/enrichment/runs?limit=50"),
          request("/admin/enrichment/plans?limit=50"),
          request("/admin/enrichment/proposals?limit=100"),
          request("/admin/enrichment/budgets"),
        ]);
        setData({ capabilities, runs: runs.runs || [], plans: plans.plans || [], proposals: proposals.proposals || [], budgets: budgets.budgets || [] });
      } else if (section === "data-quality") {
        const [rules, plan, runs] = await Promise.all([request("/admin/acquisition/rules"), request("/admin/acquisition/reprocessing/plan"), request("/admin/acquisition/reprocessing?limit=50")]);
        setData({ rules, plan, runs: runs.runs || [] });
      } else if (section === "reprocessing") {
        const [plan, runs] = await Promise.all([request("/admin/acquisition/reprocessing/plan"), request("/admin/acquisition/reprocessing?limit=50")]);
        setData({ plan, runs: runs.runs || [] });
      } else {
        setData(await request(pathBySection[section]));
      }
      setMessage("");
    } catch (error) { setMessage(getApiErrorMessage(error, "Admin acquisition data could not be loaded.")); } finally { setLoading(false); }
  }, [request, section]);

  useEffect(() => { load(); }, [load]);
  const inspectJob = useCallback(async (row) => { try { setInspection(await request(`/admin/acquisition/jobs/${encodeURIComponent(row.canonical_job_id)}`)); } catch (error) { setMessage(getApiErrorMessage(error, "Job inspection could not be loaded.")); } }, [request]);
  const content = section === "overview" ? <Overview data={data} navigate={navigate} /> : section === "sources" ? <Sources data={data} request={request} onMessage={setMessage} /> : section === "imports" ? <Imports data={data} request={request} onMessage={setMessage} /> : section === "jobs" ? <Jobs data={data} request={request} onMessage={setMessage} onInspect={inspectJob} /> : section === "companies" ? <InteractiveCompanies data={data} request={request} onMessage={setMessage} /> : section === "enrichment" ? <Enrichment data={data} request={request} onMessage={setMessage} /> : section === "data-quality" ? <DataQuality data={data} request={request} onMessage={setMessage} /> : section === "duplicates" ? <InteractiveDuplicates data={data} request={request} onMessage={setMessage} /> : section === "rules" ? <><Rules data={data} /><ConnectorCapabilities request={request} onMessage={setMessage} /></> : section === "reprocessing" ? <Reprocessing data={data} request={request} onMessage={setMessage} /> : section === "publication" ? <Publication data={data} request={request} onMessage={setMessage} /> : section === "live-catalog" ? <LiveCatalog data={data} request={request} onMessage={setMessage} /> : <Audit data={data} request={request} onMessage={setMessage} />;
  return <AcquisitionShell><div className="space-y-6"><AdminHeader loading={loading} onRefresh={() => load().catch(() => undefined)} section={section} />{loading ? <div aria-label="Loading acquisition section" className="rounded-2xl bg-surface-container p-6 text-sm text-on-surface-variant" role="status">Loading acquisition data…</div> : null}{message ? <div aria-live="polite" className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="alert">{message}</div> : null}{content}<Inspection onClose={() => setInspection(null)} value={inspection} /></div></AcquisitionShell>;
}
