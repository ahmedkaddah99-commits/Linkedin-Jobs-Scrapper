import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { getApiErrorMessage } from "../lib/api";
import { formatDateTime, labelize } from "../lib/formatters";

const SECTIONS = [
  ["overview", "Overview", "dashboard"],
  ["sources", "Sources", "lan"],
  ["jobs", "Jobs", "work_history"],
  ["duplicates", "Duplicates", "content_copy"],
  ["companies", "Companies", "business"],
  ["rules", "Rules", "rule"],
  ["reprocessing", "Reprocessing", "replay"],
  ["publication", "Publication", "publish"],
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
  return <div className="overflow-x-auto"><table className="w-full min-w-[48rem] text-left text-sm"><thead className="bg-surface-container-low text-xs font-semibold uppercase tracking-wider text-on-surface-variant"><tr>{columns.map(([key, heading]) => <th className="px-5 py-3" key={key}>{heading}</th>)}</tr></thead><tbody className="divide-y divide-outline-variant/10">{rows.map((row, index) => <tr className={onRowClick ? "cursor-pointer hover:bg-surface-container-low" : ""} key={rowKey ? rowKey(row) : `${index}`} onClick={() => onRowClick?.(row)}>{columns.map(([key, render]) => <td className="px-5 py-4 text-on-surface-variant" key={key}>{typeof render === "function" ? render(row) : text(row[key])}</td>)}</tr>)}</tbody></table></div>;
}

function AdminHeader({ section, onRefresh, loading }) {
  const navigate = useNavigate();
  return <>
    <header className="flex flex-col gap-4 border-b border-outline-variant/10 pb-6 md:flex-row md:items-end md:justify-between">
      <div><Link className="mb-3 inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:text-primary-container" to="/admin"><span className="material-symbols-outlined text-[16px]">arrow_back</span>Back to Admin</Link><p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Admin / Acquisition</p><h1 className="mt-2 font-headline text-4xl font-extrabold tracking-tight text-on-surface">{SECTIONS.find(([key]) => key === section)?.[1] || "Overview"}</h1><p className="mt-2 max-w-3xl text-sm leading-7 text-on-surface-variant">Operate the shared job catalog with bounded imports, explicit quality reports, and human-controlled publication.</p></div>
      <div className="flex flex-wrap gap-3"><button className="rounded-2xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high disabled:opacity-60" disabled={loading} onClick={onRefresh} type="button">{loading ? "Refreshing…" : "Refresh"}</button><button className="rounded-2xl bg-gradient-to-br from-primary to-primary-container px-4 py-3 text-sm font-semibold text-white shadow-sm" onClick={() => navigate("/admin/acquisition/sources")} type="button"><span className="material-symbols-outlined mr-1 align-middle text-[17px]">download</span>Import jobs</button></div>
    </header>
    <nav aria-label="Acquisition admin sections" className="flex gap-1 overflow-x-auto rounded-2xl bg-surface-container-low p-1.5">{SECTIONS.map(([key, label, icon]) => <button aria-current={key === section ? "page" : undefined} className={`flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-semibold transition-colors ${key === section ? "bg-surface-container-lowest text-on-surface shadow-soft" : "text-on-surface-variant hover:bg-surface-container-high"}`} key={key} onClick={() => navigate(`/admin/acquisition/${key === "overview" ? "" : key}`)} type="button"><span className="material-symbols-outlined text-[17px]">{icon}</span>{label}</button>)}</nav>
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
    setBusy(true);
    try {
      await request(`/admin/acquisition/duplicate-clusters/${encodeURIComponent(selected.cluster_id)}/decisions`, { method: "POST", body: { decision, reason: reason || `Admin decision: ${decision}`, evidence: { source: "admin_review", cluster_id: selected.cluster_id }, affected_ids: (selected.members || []).map((member) => member.canonical_job_id), rule_version: "duplicate_review_v1" } });
      onMessage(`Duplicate cluster marked ${decision}. No records were merged or published.`);
    } catch (error) { onMessage(getApiErrorMessage(error, "Duplicate decision failed.")); } finally { setBusy(false); }
  }
  async function undo() {
    if (!selected) return;
    setBusy(true);
    try { await request(`/admin/acquisition/duplicate-clusters/${encodeURIComponent(selected.cluster_id)}/undo`, { method: "POST", body: { reason: reason || "Admin undo", evidence: { source: "admin_review", cluster_id: selected.cluster_id } } }); onMessage("Duplicate decision undone; immutable evidence was preserved."); } catch (error) { onMessage(getApiErrorMessage(error, "Duplicate undo failed.")); } finally { setBusy(false); }
  }
  return <><Panel title="Duplicate candidates" description="Candidate clusters preserve provenance and require human review. Decisions are append-only and reversible; merge and publication remain separate explicit operations."><Table columns={[["cluster_id", "Cluster"], ["state", "State"], ["confidence", "Confidence"], ["members", "Members"], ["reasons", "Evidence"], ["current_decision", "Decision"]]} rows={clusters.map((cluster) => ({ ...cluster, members: cluster.members?.length || 0, reasons: (cluster.reasons || []).join(" · "), current_decision: cluster.current_decision?.decision || "candidate" }))} rowKey={(row) => row.cluster_id} onRowClick={setSelected} /></Panel>{selected ? <div className="rounded-2xl border border-primary/20 bg-primary/5 p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-mono text-xs text-primary">{selected.cluster_id}</p><h3 className="mt-1 font-headline text-lg font-bold text-on-surface">Human decision</h3><p className="mt-1 text-sm text-on-surface-variant">No automatic merge, canonical rewrite, or publication occurs from this control.</p></div><button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-xs font-semibold text-on-surface" onClick={() => setSelected(null)} type="button">Close</button></div><textarea aria-label="Decision reason" className="mt-4 w-full rounded-xl border border-outline-variant/20 bg-surface px-3 py-2 text-sm text-on-surface" onChange={(event) => setReason(event.target.value)} placeholder="Reason and evidence reference" value={reason} /><div className="mt-3 flex flex-wrap gap-2"><button className="rounded-xl bg-primary px-3 py-2 text-xs font-semibold text-white disabled:opacity-60" disabled={busy} onClick={() => decide("confirmed_duplicate")} type="button">Confirm duplicate</button><button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-xs font-semibold text-on-surface disabled:opacity-60" disabled={busy} onClick={() => decide("distinct")} type="button">Mark distinct</button><button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-xs font-semibold text-on-surface disabled:opacity-60" disabled={busy} onClick={() => decide("ignored")} type="button">Ignore</button><button className="rounded-xl border border-amber-300 px-3 py-2 text-xs font-semibold text-amber-800 disabled:opacity-60" disabled={busy || !(selected.decision_history || []).length} onClick={undo} type="button">Undo decision</button></div><div className="mt-4 space-y-2 text-xs text-on-surface-variant">{(selected.decision_history || []).map((item) => <div className="rounded-xl bg-surface-container-low p-3" key={item.decision_id}><b className="text-on-surface">{item.decision}</b> · {text(item.actor_user_id)} · {date(item.created_at)}<p className="mt-1">{text(item.reason)}</p></div>)}</div></div> : null}</>;
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
  const [busy, setBusy] = useState(false);
  const companies = companyData?.companies || [];
  useEffect(() => { setCompanyData(data || {}); }, [data]);
  useEffect(() => { const params = new URLSearchParams({ limit: "100" }); if (applied) params.set("search", applied); request(`/admin/acquisition/companies?${params}`).then((value) => setCompanyData(value || {})).catch((error) => onMessage(getApiErrorMessage(error, "Companies could not be loaded."))); }, [applied, request, onMessage]);
  async function open(company) { try { const value = await request(`/admin/acquisition/companies/${encodeURIComponent(company.company_id)}`); setSelected(value.company || value); } catch (error) { onMessage(getApiErrorMessage(error, "Company detail could not be loaded.")); } }
  async function enrich() { if (!selected) return; setBusy(true); try { const result = await request(`/admin/acquisition/companies/${encodeURIComponent(selected.company_id)}/enrich`, { method: "POST", body: { max_companies: 1, concurrency: 1, request_budget: 5 } }); onMessage(`Company enrichment ${text(result.status, "requested")}.`); } catch (error) { onMessage(getApiErrorMessage(error, "Company enrichment failed.")); } finally { setBusy(false); } }
  return <><Panel title="Canonical companies" description="Inspect identity, official/homepage/careers/ATS URLs, validation, provenance, logo state, and bounded enrichment attempts."><form className="flex flex-col gap-3 border-b border-outline-variant/10 p-5 sm:flex-row" onSubmit={(event) => { event.preventDefault(); setApplied(search.trim()); }}><input aria-label="Search companies" className="min-w-0 flex-1 rounded-xl border border-outline-variant/20 bg-surface px-3 py-2 text-sm text-on-surface" onChange={(event) => setSearch(event.target.value)} placeholder="Search company or provenance URL" value={search} /><button className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white" type="submit">Search</button></form><Table columns={[["canonical_name", "Company"], ["job_count", "Jobs"], ["provenance_url", "Provenance"], ["profile", "Profile"], ["urls", "URLs"]]} rows={companies.map((company) => ({ ...company, profile: company.profile && Object.keys(company.profile).length ? "Available" : "Not enriched", urls: company.urls?.length || 0 }))} rowKey={(row) => row.company_id} onRowClick={open} /></Panel>{selected ? <div className="rounded-2xl border border-primary/20 bg-primary/5 p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-mono text-xs text-primary">{selected.company_id}</p><h3 className="mt-1 font-headline text-lg font-bold text-on-surface">{text(selected.canonical_name)}</h3><p className="mt-1 text-sm text-on-surface-variant">{number(selected.job_count)} jobs · identity and enrichment are separate projections</p></div><div className="flex gap-2"><button className="rounded-xl bg-primary px-3 py-2 text-xs font-semibold text-white disabled:opacity-60" disabled={busy} onClick={enrich} type="button">{busy ? "Enriching…" : "Run bounded enrichment"}</button><button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-xs font-semibold text-on-surface" onClick={() => setSelected(null)} type="button">Close</button></div></div><div className="mt-4 grid gap-3 sm:grid-cols-2">{(selected.urls || []).map((url) => <div className="rounded-xl bg-surface-container-low p-3" key={url.company_url_id || url.canonical_url}><p className="text-xs font-semibold uppercase text-on-surface-variant">{text(url.url_type)}</p><a className="mt-1 block break-all text-xs text-primary" href={url.canonical_url || url.url} rel="noreferrer" target="_blank">{text(url.canonical_url || url.url)}</a><p className="mt-1 text-xs text-on-surface-variant">{text(url.validation_status)} · {text(url.source, "unknown source")}</p></div>)}</div><div className="mt-4 rounded-xl bg-surface-container-low p-3 text-sm text-on-surface-variant"><b className="text-on-surface">Logo:</b> {text(selected.logo_source_url, "Deterministic monogram fallback")} · {text(selected.logo_verified_at, "not verified")}</div>{(selected.logo_enrichments || []).length ? <div className="mt-3 space-y-2 text-xs text-on-surface-variant">{selected.logo_enrichments.map((logo) => <div className="rounded-xl bg-surface-container-low p-3" key={logo.logo_enrichment_id}><b className="text-on-surface">{text(logo.provider)}</b> · {text(logo.status)} · {text(logo.source_url)}</div>)}</div> : null}</div> : null}</>;
}

function Rules({ data, request, onMessage }) {
  const renderCounts = (items, keys) => <div className="space-y-2">{(items || []).length ? items.map((item, index) => <div className="flex items-center justify-between gap-3 rounded-xl bg-surface-container-low px-3 py-2 text-xs" key={`${JSON.stringify(item)}-${index}`}><span className="text-on-surface-variant">{keys.map((key) => text(item[key], "—")).join(" · ")}</span><b className="text-on-surface">{number(item.count)}</b></div>) : <p className="text-sm text-on-surface-variant">No report rows yet.</p>}</div>;
  return <div className="space-y-5"><div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><b>Report-only quality contract.</b> Rule version {text(data?.rule_version)} explains coverage, warnings, and stage outcomes. It is not a publication gate.</div><div className="grid gap-5 xl:grid-cols-2"><Panel title="Field provenance" description="Selected and unselected field states by entity.">{renderCounts(data?.field_states, ["entity_kind", "field_name", "state"])}</Panel><Panel title="Pipeline stages" description="Stage status across acquisition executions.">{renderCounts(data?.stage_states, ["stage_name", "status"])}</Panel><Panel title="Completeness" description="Completeness reports by state.">{renderCounts(data?.completeness_states, ["state"])}</Panel><Panel title="Quality warnings" description="Warnings are retained for diagnosis and review.">{renderCounts(data?.warnings, ["warning_code", "severity"])}</Panel></div></div>;
}

function ConnectorCapabilities({ request, onMessage }) {
  const [rows, setRows] = useState([]);
  useEffect(() => { request("/admin/acquisition/connectors/capabilities?limit=200").then((value) => setRows(value?.connectors || [])).catch((error) => onMessage(getApiErrorMessage(error, "Connector capabilities could not be loaded."))); }, [request, onMessage]);
  return <Panel title="Connector capability and raw-retention contract" description="Workday, Personio, Recruitee, and SmartRecruiters remain disabled and unregistered by default. Capability reports do not enable production acquisition."><Table columns={[["connector", "Connector"], ["state", "State"], ["production_registered", "Registered"], ["raw_retention", "Raw retention"], ["failure_policy", "Failure policy"]]} rows={rows.map((item) => ({ ...item, production_registered: item.production_registered ? "yes" : "no", raw_retention: item.raw_retention?.required ? "required · admin-only" : "unknown" }))} rowKey={(row) => row.connector} /></Panel>;
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
  async function action(path, body, message) { setBusy(true); try { const result = await request(path, { method: "POST", body }); if (result.publication_id) setPublicationId(result.publication_id); onMessage(message); } catch (error) { onMessage(getApiErrorMessage(error, "Publication action failed.")); } finally { setBusy(false); } }
  const head = data?.current_head;
  return <div className="space-y-5"><div className="rounded-2xl border border-green-200 bg-green-50 p-4 text-sm text-green-900"><b>Manual publication only.</b> Automatic promotion is {data?.automatic_promotion ? "enabled" : "disabled"}; the current head is the only public catalog pointer.</div><div className="grid gap-5 xl:grid-cols-[1fr_1fr]"><Panel title="Current publication head" description="The public catalog is served from this validated head."><div className="space-y-3 p-5"><div className="flex flex-wrap items-center gap-3"><strong className="font-mono text-sm text-on-surface">{text(head?.publication_id, "No current head")}</strong><StatusPill value={head?.status || "not published"} /></div><p className="text-sm text-on-surface-variant">{number(data?.current_job_count)} jobs · published {date(head?.published_at)}</p><div className="flex flex-wrap gap-2 pt-2"><button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-xs font-semibold text-on-surface" disabled={busy || !head?.publication_id} onClick={() => action("/admin/acquisition/publication/undo", {}, "Last publication undone.")} type="button">Undo last publication</button></div></div></Panel><Panel title="Preview and publish" description="Preview an approved import, then publish only the explicit preview ID."><div className="space-y-3 p-5"><input aria-label="Import ID" className="w-full rounded-xl border border-outline-variant/20 bg-surface px-3 py-2 text-sm text-on-surface" onChange={(event) => setImportId(event.target.value)} placeholder="Approved import ID" value={importId} /><button className="rounded-xl border border-primary/20 bg-primary/10 px-3 py-2 text-xs font-semibold text-primary" disabled={busy || !importId} onClick={async () => { setBusy(true); try { const preview = await request("/admin/acquisition/publication/preview", { method: "POST", body: { import_id: importId } }); setPublicationId(preview.publication_id || ""); onMessage("Publication preview created."); } catch (error) { onMessage(getApiErrorMessage(error, "Preview failed.")); } finally { setBusy(false); } }} type="button">Create preview</button><input aria-label="Publication ID" className="w-full rounded-xl border border-outline-variant/20 bg-surface px-3 py-2 text-sm text-on-surface" onChange={(event) => setPublicationId(event.target.value)} placeholder="Publication preview ID" value={publicationId} /><button className="rounded-xl bg-primary px-3 py-2 text-xs font-semibold text-white" disabled={busy || !publicationId} onClick={() => action("/admin/acquisition/publication/publish", { publication_id: publicationId }, "Publication promoted to the current head.")} type="button">Publish preview</button></div></Panel></div><Panel title="Publication states" description="Historical publication records by state."><Table columns={[["status", "Status"], ["count", "Count"]]} rows={data?.publication_states || []} /></Panel></div>;
}

function Inspection({ value, onClose }) {
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
      const pathBySection = { overview: "/admin/acquisition/overview", sources: "/admin/acquisition/sources", jobs: "/admin/acquisition/jobs?limit=100", duplicates: "/admin/acquisition/duplicates?limit=100", companies: "/admin/acquisition/companies?limit=100", rules: "/admin/acquisition/rules", publication: "/admin/acquisition/publication" };
      if (section === "overview") {
        const [overview, publication] = await Promise.all([request(pathBySection.overview), request(pathBySection.publication)]);
        setData({ ...overview, publication });
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
  const content = section === "overview" ? <Overview data={data} navigate={navigate} /> : section === "sources" ? <Sources data={data} request={request} onMessage={setMessage} /> : section === "jobs" ? <Jobs data={data} request={request} onMessage={setMessage} onInspect={inspectJob} /> : section === "duplicates" ? <InteractiveDuplicates data={data} request={request} onMessage={setMessage} /> : section === "companies" ? <InteractiveCompanies data={data} request={request} onMessage={setMessage} /> : section === "rules" ? <><Rules data={data} /><ConnectorCapabilities request={request} onMessage={setMessage} /></> : section === "reprocessing" ? <Reprocessing data={data} request={request} onMessage={setMessage} /> : <Publication data={data} request={request} onMessage={setMessage} />;
  return <div className="space-y-6"><AdminHeader loading={loading} onRefresh={() => load().catch(() => undefined)} section={section} />{message ? <div aria-live="polite" className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{message}</div> : null}{content}<Inspection onClose={() => setInspection(null)} value={inspection} /></div>;
}
