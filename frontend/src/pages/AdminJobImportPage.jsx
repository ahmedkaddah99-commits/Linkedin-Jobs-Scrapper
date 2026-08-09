import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { getApiErrorMessage } from "../lib/api";
import { formatDateTime, statusTone } from "../lib/formatters";

const WORKFLOW = [
  ["import", "Import"],
  ["inspect", "Inspect data"],
  ["review", "Review"],
  ["publish", "Publish"],
  ["live", "View live"],
];

const INSPECTOR_TABS = [
  ["coverage", "Data coverage"],
  ["job", "Job JSON"],
  ["company", "Company JSON"],
  ["admin", "Admin JSON"],
  ["complete", "Complete JSON"],
];

const INITIAL_SCOPE = {
  country: "Germany",
  cities: "",
  remote: false,
  department: "",
  category: "",
  keywords: "",
  full_source_import: false,
  max_pages: 20,
  max_requests: 100,
  max_credits: "",
};

function Card({ children, className = "" }) {
  return <section className={`rounded-[1.35rem] border border-outline-variant/20 bg-surface-container-lowest shadow-soft ${className}`}>{children}</section>;
}

function Pill({ children, tone = "neutral" }) {
  const colors = {
    green: "bg-primary/10 text-primary",
    red: "bg-error-container text-on-error-container",
    amber: "bg-tertiary-container/30 text-tertiary",
    neutral: "bg-surface-container text-on-surface-variant",
  };
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.08em] ${colors[tone] || colors.neutral}`}><span className="h-1.5 w-1.5 rounded-full bg-current" />{children}</span>;
}

function ErrorNotice({ message }) {
  if (!message) return null;
  return <p className="rounded-2xl border border-error/20 bg-error-container px-4 py-3 text-sm text-on-error-container">{message}</p>;
}

function JsonViewer({ value, search }) {
  const lines = useMemo(() => JSON.stringify(value ?? null, null, 2).split("\n"), [value]);
  const needle = String(search || "").trim().toLowerCase();
  return (
    <pre className="max-h-[42rem] overflow-auto rounded-2xl bg-[#0b1c30] p-4 text-[12px] leading-6 text-slate-200 shadow-inner" aria-label="JSON record">
      {lines.map((line, index) => <span className={`block min-w-max ${needle && line.toLowerCase().includes(needle) ? "rounded bg-yellow-300/30" : ""}`} key={`${index}-${line}`}><span className="mr-5 inline-block w-8 select-none text-right text-slate-500">{String(index + 1).padStart(3, "0")}</span>{line}</span>)}
    </pre>
  );
}

function EmptyState({ title, body }) {
  return <div className="flex min-h-72 flex-col items-center justify-center rounded-2xl border border-dashed border-outline-variant/30 bg-surface-container-low px-6 text-center"><span className="material-symbols-outlined text-4xl text-on-surface-variant">database_search</span><h3 className="mt-3 font-headline text-lg font-bold text-on-surface">{title}</h3><p className="mt-2 max-w-md text-sm leading-6 text-on-surface-variant">{body}</p></div>;
}

function Metric({ label, value, hint, tone = "neutral" }) {
  return <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest px-4 py-4"><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-on-surface-variant">{label}</p><strong className={`mt-2 block font-headline text-2xl font-extrabold ${tone === "bad" ? "text-error" : tone === "good" ? "text-primary" : "text-on-surface"}`}>{value ?? "—"}</strong><small className="mt-1 block text-xs text-on-surface-variant">{hint || "Backend value"}</small></div>;
}

function coverageTone(stats) {
  if (!stats || !stats.total) return "neutral";
  if (stats.present === stats.total) return "green";
  if (stats.present === 0) return "red";
  return "amber";
}

function CoverageSection({ label, description, stats, onInspect, critical = [] }) {
  const percentage = stats?.total ? Math.round((stats.present / stats.total) * 100) : 0;
  const tone = coverageTone(stats);
  return <section className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4"><div className="flex items-start justify-between gap-4"><div><h3 className="font-headline text-base font-bold text-on-surface">{label}</h3><p className="mt-1 text-xs leading-5 text-on-surface-variant">{description}</p></div><Pill tone={tone}>{stats ? `${stats.present}/${stats.total}` : "Unknown"}</Pill></div><div className="mt-4 h-2 overflow-hidden rounded-full bg-surface-container"><span className={`block h-full rounded-full ${tone === "green" ? "bg-primary" : tone === "red" ? "bg-error" : "bg-tertiary"}`} style={{ width: `${percentage}%` }} /></div><p className="mt-2 text-xs text-on-surface-variant">{stats ? `${percentage}% present` : "Coverage unavailable"}</p>{stats?.missing_fields?.length ? <div className="mt-3 flex flex-wrap gap-1.5">{stats.missing_fields.slice(0, 12).map((field) => <span className="rounded-lg bg-surface-container-highest px-2 py-1 font-mono text-[10px] text-on-surface-variant" key={field}>{field}</span>)}{stats.missing_fields.length > 12 ? <span className="rounded-lg bg-surface-container-highest px-2 py-1 text-[10px] text-on-surface-variant">+{stats.missing_fields.length - 12} more</span> : null}</div> : <p className="mt-3 text-xs font-semibold text-primary">No missing fields reported.</p>}{critical.length ? <div className="mt-4 space-y-2 border-t border-outline-variant/15 pt-3">{critical.map((item) => <div className="flex items-center gap-2 text-xs" key={item.name}><span className={item.status === "pass" ? "text-primary" : "text-error"}>{item.status === "pass" ? "✓" : "!"}</span><span className="font-semibold text-on-surface">{item.name}</span><code className="ml-auto max-w-[45%] truncate text-on-surface-variant">{typeof item.detail === "string" ? item.detail : JSON.stringify(item.detail)}</code></div>)}</div> : null}<button className="mt-4 text-xs font-bold text-primary hover:underline" onClick={onInspect} type="button">Inspect exact JSON →</button></section>;
}

function ImportPanel({ sources, overview, selectedSources, setSelectedSources, scope, setScope, plan, busy, onPlan, onStart }) {
  function updateScope(key, value) {
    setScope((current) => ({ ...current, [key]: value }));
  }
  return <div className="space-y-4"><Card className="p-5"><div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between"><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-primary">Import</p><h2 className="mt-2 font-headline text-2xl font-extrabold text-on-surface">Choose real acquisition sources</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-on-surface-variant">This uses the existing centralized manifest, worker and Turso acquisition path. Nothing publishes automatically.</p></div><Pill tone={overview?.imports?.paused ? "red" : "green"}>{overview?.imports?.paused ? "Paused" : "Ready"}</Pill></div><div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{sources.map((source) => { const disabled = source.status !== "ready" || overview?.imports?.paused; return <label className={`rounded-2xl border p-4 ${selectedSources.includes(source.id) ? "border-primary bg-primary/5" : "border-outline-variant/20"} ${disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`} key={source.id}><div className="flex gap-3"><input checked={selectedSources.includes(source.id)} disabled={disabled} onChange={(event) => setSelectedSources((current) => event.target.checked ? [...current, source.id] : current.filter((item) => item !== source.id))} type="checkbox" /><span className="min-w-0"><span className="block font-semibold text-on-surface">{source.company || source.name}</span><span className="mt-1 block text-xs text-on-surface-variant">{source.source_type} · {source.connector || "Unknown connector"}</span><span className="mt-1 block text-xs text-on-surface-variant">{source.status === "ready" ? "Ready" : source.reason || "Not available"}</span></span></div></label>; })}</div></Card><Card className="p-5"><h2 className="font-headline text-xl font-bold text-on-surface">Scope and limits</h2><div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{[["country", "Country"], ["cities", "City or region"], ["department", "Department"], ["category", "Category"], ["keywords", "Keywords"]].map(([key, label]) => <label className="space-y-2 text-sm" key={key}><span className="font-semibold text-on-surface">{label}</span><input className="w-full rounded-xl border border-outline-variant/20 bg-surface-container-low px-3 py-2.5 text-on-surface outline-none focus:border-primary" disabled={scope.full_source_import} onChange={(event) => updateScope(key, event.target.value)} placeholder={key === "cities" || key === "keywords" ? "Comma separated" : "Optional"} value={scope[key]} /></label>)}<label className="flex items-center gap-2 pt-7 text-sm font-semibold text-on-surface"><input checked={scope.remote} disabled={scope.full_source_import} onChange={(event) => updateScope("remote", event.target.checked)} type="checkbox" /> Remote jobs</label><label className="flex items-center gap-2 pt-7 text-sm font-semibold text-on-surface"><input checked={scope.full_source_import} onChange={(event) => updateScope("full_source_import", event.target.checked)} type="checkbox" /> Full source import</label></div><details className="mt-5 text-sm text-on-surface-variant"><summary className="cursor-pointer font-semibold">Advanced request and credit ceilings</summary><div className="mt-3 grid gap-4 md:grid-cols-3"><label>Maximum pages<input className="mt-2 w-full rounded-xl border border-outline-variant/20 bg-surface-container-low px-3 py-2" min="1" max="20" onChange={(event) => updateScope("max_pages", event.target.value)} type="number" value={scope.max_pages} /></label><label>Maximum requests<input className="mt-2 w-full rounded-xl border border-outline-variant/20 bg-surface-container-low px-3 py-2" min="1" max="100" onChange={(event) => updateScope("max_requests", event.target.value)} type="number" value={scope.max_requests} /></label><label>Maximum ScrapeOps credits<input className="mt-2 w-full rounded-xl border border-outline-variant/20 bg-surface-container-low px-3 py-2" min="0" max="10000" onChange={(event) => updateScope("max_credits", event.target.value)} placeholder="Required for paid sources" type="number" value={scope.max_credits} /></label></div></details><div className="mt-5 flex flex-wrap gap-3"><button className="rounded-xl border border-primary/20 px-4 py-3 text-sm font-bold text-primary disabled:opacity-50" disabled={busy || !selectedSources.length} onClick={onPlan} type="button">Calculate plan</button><button className="rounded-xl bg-primary px-4 py-3 text-sm font-bold text-white disabled:opacity-50" disabled={busy || !plan?.can_start || overview?.imports?.paused} onClick={onStart} type="button">{busy ? "Working…" : "Start import"}</button></div>{plan ? <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric label="Maximum requests" value={plan.maximum_requests} /><Metric label="Maximum pages" value={plan.maximum_pages} /><Metric label="Maximum credits" value={plan.maximum_credits || 0} /><Metric label="Estimated cost" value={plan.estimated_cost?.known ? `${plan.estimated_cost.maximum} ${plan.estimated_cost.currency || "USD"}` : "Unknown"} tone={plan.estimated_cost?.known ? "neutral" : "bad"} /></div> : null}</Card></div>;
}

function ReviewPanel({ imports, selectedImportId, setSelectedImportId, reviewStatus, setReviewStatus, reviewSearch, setReviewSearch, reviewJobs, onLoad, onDecision }) {
  return <div className="space-y-4"><Card className="p-5"><div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between"><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-primary">Review</p><h2 className="mt-2 font-headline text-2xl font-extrabold text-on-surface">Inspect and decide on collected jobs</h2><p className="mt-2 text-sm text-on-surface-variant">Rejected and incomplete results remain visible with their source evidence.</p></div><select className="rounded-xl border border-outline-variant/20 bg-surface-container-low px-3 py-2 text-sm" onChange={(event) => setSelectedImportId(event.target.value)} value={selectedImportId}>{imports.map((item) => <option key={item.import_id} value={item.import_id}>{item.import_id} · {item.status}</option>)}</select></div><div className="mt-5 flex flex-wrap gap-2">{[["needs_review", "Needs review"], ["approved", "Approved"], ["not_accepted", "Not accepted"], ["already_live", "Already live"], ["all", "All results"]].map(([key, label]) => <button className={`rounded-full px-3 py-2 text-xs font-bold ${reviewStatus === key ? "bg-primary text-white" : "bg-surface-container text-on-surface-variant"}`} key={key} onClick={() => setReviewStatus(key)} type="button">{label}</button>)}<input className="min-w-[15rem] flex-1 rounded-xl border border-outline-variant/20 bg-surface-container-low px-3 py-2 text-sm" onChange={(event) => setReviewSearch(event.target.value)} onKeyDown={(event) => event.key === "Enter" && onLoad()} placeholder="Search company, title, location" value={reviewSearch} /><button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-sm font-bold" onClick={onLoad} type="button">Filter</button></div></Card><Card className="overflow-x-auto p-0"><table className="w-full min-w-[68rem] text-left text-sm"><thead className="bg-surface-container-low text-[10px] font-bold uppercase tracking-[0.14em] text-on-surface-variant"><tr>{["Company", "Title", "Location", "Apply", "Quality", "Review", "Actions"].map((label) => <th className="px-5 py-4" key={label}>{label}</th>)}</tr></thead><tbody className="divide-y divide-outline-variant/10">{reviewJobs.map((job) => <tr className="hover:bg-surface-container-low" key={`${job.canonical_job_id || job.external_job_id}-${job.source_id}`}><td className="px-5 py-4 font-semibold text-on-surface">{job.company || "Unknown"}<span className="block text-xs font-normal text-on-surface-variant">{job.source_id || "Unknown source"}</span></td><td className="px-5 py-4 text-on-surface">{job.title || "Unknown"}<details className="mt-1 text-xs text-on-surface-variant"><summary className="cursor-pointer">Description and raw source</summary><p className="mt-2 max-w-xl whitespace-pre-wrap">{job.description || "Not available"}</p><pre className="mt-2 max-w-xl overflow-auto rounded bg-surface-container-low p-2">{JSON.stringify(job.source_payload || {}, null, 2)}</pre></details></td><td className="px-5 py-4 text-on-surface-variant">{job.location || "Unknown"}</td><td className="px-5 py-4">{job.apply_url ? <a className="font-bold text-primary" href={job.apply_url} rel="noreferrer" target="_blank">Open URL</a> : <span className="font-bold text-error">Missing</span>}</td><td className="px-5 py-4 text-xs text-on-surface-variant">{(job.quality_warnings || []).join(", ") || "No warnings"}</td><td className="px-5 py-4"><StatusBadge tone={statusTone(job.review_state)}>{job.review_state}</StatusBadge></td><td className="px-5 py-4"><div className="flex gap-2">{job.canonical_job_id && job.review_state === "needs_review" ? <><button className="rounded-lg bg-primary px-3 py-2 text-xs font-bold text-white" onClick={() => onDecision(job, "approve")} type="button">Approve</button><button className="rounded-lg border border-error/20 px-3 py-2 text-xs font-bold text-error" onClick={() => onDecision(job, "reject")} type="button">Reject</button></> : null}</div></td></tr>)}</tbody></table>{!reviewJobs.length ? <p className="p-8 text-sm text-on-surface-variant">No review results are available for this import yet.</p> : null}</Card></div>;
}

function PublishPanel({ imports, selectedImportId, setSelectedImportId, preview, busy, onPreview, onPublish, onUndo }) {
  return <div className="space-y-4"><Card className="p-5"><p className="text-xs font-bold uppercase tracking-[0.16em] text-primary">Publish</p><h2 className="mt-2 font-headline text-2xl font-extrabold text-on-surface">Move approved records to the live catalog</h2><p className="mt-2 text-sm leading-6 text-on-surface-variant">Preview is separate from publication. Customer APIs change only after an explicit publish action.</p><div className="mt-5 flex flex-wrap gap-3"><select className="rounded-xl border border-outline-variant/20 bg-surface-container-low px-3 py-2 text-sm" onChange={(event) => setSelectedImportId(event.target.value)} value={selectedImportId}>{imports.map((item) => <option key={item.import_id} value={item.import_id}>{item.import_id} · {item.status}</option>)}</select><button className="rounded-xl border border-primary/20 px-4 py-3 text-sm font-bold text-primary" disabled={!selectedImportId || busy} onClick={onPreview} type="button">Create preview</button></div>{preview ? <div className="mt-5 rounded-2xl bg-surface-container-low p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-bold text-on-surface">{preview.total} records in preview</p><p className="mt-1 text-xs text-on-surface-variant">Publication {preview.publication_id} · {preview.status}</p></div><Pill tone={preview.status === "staging" ? "amber" : "green"}>{preview.status}</Pill></div><div className="mt-4 flex flex-wrap gap-3"><button className="rounded-xl bg-primary px-4 py-3 text-sm font-bold text-white" disabled={busy || !preview.publication_id} onClick={onPublish} type="button">Publish approved jobs</button><button className="rounded-xl border border-error/20 px-4 py-3 text-sm font-bold text-error" disabled={busy} onClick={onUndo} type="button">Undo last publish</button><Link className="rounded-xl border border-outline-variant/20 px-4 py-3 text-sm font-bold text-primary" to="/jobs">View live Jobs</Link></div></div> : null}</Card></div>;
}

function InspectorView({
  activeTab,
  apply,
  busy,
  copyJson,
  critical,
  downloadJson,
  inspection,
  jobs,
  jsonSearch,
  resolveApplyUrl,
  search,
  selectedId,
  selectedJob,
  selectTab,
  setJsonSearch,
  setSearch,
  setSelectedId,
  setView,
  summary,
}) {
  if (!inspection) {
    return <EmptyState title="Loading selected record" body="The complete job, company, admin, and raw provenance payload is being loaded." />;
  }
  const directReady = apply.status === "verified" && apply.user_facing_url;
  const sourceUrl = apply.source_url;
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(18rem,22rem)_minmax(0,1fr)]">
      <Card className="overflow-hidden">
        <div className="border-b border-outline-variant/15 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="font-headline text-lg font-extrabold text-on-surface">Collected jobs</h2>
              <p className="mt-1 text-xs text-on-surface-variant">{summary?.catalog_records ?? jobs.length} canonical records from the backend</p>
            </div>
            <Pill tone="green">Real</Pill>
          </div>
          <label className="mt-4 flex items-center gap-2 rounded-xl border border-outline-variant/20 bg-surface-container-low px-3 py-2">
            <span className="material-symbols-outlined text-[18px] text-on-surface-variant">search</span>
            <input className="min-w-0 flex-1 bg-transparent text-sm outline-none" onChange={(event) => setSearch(event.target.value)} placeholder="Search jobs, companies, IDs…" value={search} />
          </label>
          <div className="mt-3 flex flex-wrap gap-2">
            <Pill tone="neutral">All {summary?.catalog_records ?? "—"}</Pill>
            <Pill tone={summary?.apply_url_missing_or_invalid ? "red" : "green"}>Apply missing {summary?.apply_url_missing_or_invalid ?? "—"}</Pill>
          </div>
        </div>
        <div className="max-h-[48rem] overflow-auto p-2">
          {jobs.map((job) => (
            <button className={`flex w-full items-start gap-3 rounded-xl p-3 text-left transition ${job.canonical_job_id === selectedId ? "bg-primary/10 ring-1 ring-primary/20" : "hover:bg-surface-container-low"}`} key={job.canonical_job_id} onClick={() => { setSelectedId(job.canonical_job_id); selectTab("coverage"); }} type="button">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-xs font-extrabold text-primary">{String(job.company || "?").slice(0, 2).toUpperCase()}</span>
              <span className="min-w-0 flex-1">
                <b className="block truncate text-sm text-on-surface">{job.title || "Unknown title"}</b>
                <small className="mt-1 block truncate text-xs text-on-surface-variant">{job.company || "Unknown company"} · {job.location || "Unknown location"}</small>
                <code className="mt-1 block truncate text-[10px] text-on-surface-variant">{job.canonical_job_id}</code>
              </span>
              <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${job.apply_status === "present" ? "bg-tertiary" : "bg-error"}`} title={`Apply URL ${job.apply_status}`} />
            </button>
          ))}
          {jobs.length >= 200 ? <p className="px-3 py-3 text-xs text-on-surface-variant">Showing the first 200 records. Use search to narrow the catalog.</p> : null}
        </div>
      </Card>

      <Card className="min-w-0 overflow-hidden">
        <div className="border-b border-outline-variant/15 p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex min-w-0 items-start gap-3">
              <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-primary/10 font-headline text-lg font-extrabold text-primary">{String(inspection.company?.name || "?").slice(0, 2).toUpperCase()}</span>
              <div className="min-w-0">
                <code className="block truncate text-[10px] font-bold uppercase tracking-[0.12em] text-primary">{inspection.job?.canonical_job_id}</code>
                <h2 className="mt-1 truncate font-headline text-2xl font-extrabold text-on-surface">{inspection.job?.title || "Unknown title"}</h2>
                <p className="mt-1 text-sm text-on-surface-variant">{inspection.company?.name || "Unknown company"} · {inspection.job?.location_raw || "Unknown location"} · {selectedJob?.source || inspection.admin?.connector || "Unknown source"}</p>
              </div>
            </div>
            <div className="flex items-center gap-2"><Pill tone={inspection.admin?.publication_status === "valid" ? "green" : "amber"}>{inspection.admin?.publication_status || inspection.admin?.review_state || "Review"}</Pill><Link className="rounded-xl border border-outline-variant/20 px-3 py-2 text-xs font-bold text-primary" to="/admin">Admin home</Link></div>
          </div>
        </div>

        <section className={`mx-5 mt-5 rounded-2xl border p-4 ${apply.status === "verified" ? "border-primary/25 bg-primary/5" : "border-error/25 bg-error-container/40"}`}>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <p className={`text-[10px] font-bold uppercase tracking-[0.16em] ${apply.status === "verified" ? "text-primary" : "text-error"}`}>Direct employer / official ATS Apply URL</p>
              <h3 className="mt-1 font-headline text-lg font-extrabold text-on-surface">{apply.status === "verified" ? "Verified and ready for users" : apply.status === "missing" ? "Missing — the customer Apply button cannot work" : apply.status === "invalid" ? "Invalid — only a listing or portal fallback was found" : "Unverified — do not present as working"}</h3>
              <div className="mt-3 space-y-1 text-xs text-on-surface-variant">
                <p><b>Original listing/source URL:</b> {sourceUrl ? <a className="break-all text-primary hover:underline" href={sourceUrl} rel="noreferrer" target="_blank">{sourceUrl}</a> : "Missing"}</p>
                <p><b>Resolved URL:</b> <code className="break-all">{apply.resolved_url || "None"}</code></p>
                <p><b>Last validation:</b> {apply.verified_at ? formatDateTime(apply.verified_at) : "Unknown"}</p>
                <p><b>Classification:</b> {apply.classification || "unknown"} · <b>Evidence:</b> {(apply.evidence || []).join("; ") || "Unknown"}</p>
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2"><button className="rounded-xl border border-error/25 bg-surface-container-lowest px-3 py-2 text-xs font-bold text-error" disabled={busy} onClick={resolveApplyUrl} type="button">Resolve URL</button>{directReady ? <a className="rounded-xl bg-primary px-3 py-2 text-xs font-bold text-white" href={apply.user_facing_url} rel="noreferrer" target="_blank">Test Apply ↗</a> : <button className="cursor-not-allowed rounded-xl bg-surface-container px-3 py-2 text-xs font-bold text-on-surface-variant" disabled type="button">Test Apply disabled</button>}</div>
          </div>
          <details className="mt-3 text-xs text-on-surface-variant"><summary className="cursor-pointer font-semibold">Show all URL candidates and source evidence</summary><div className="mt-3 space-y-2">{(apply.candidate_urls || []).map((candidate) => <div className="rounded-xl bg-surface-container-lowest p-3" key={`${candidate.url}-${candidate.path}`}><code className="block break-all text-[11px]">{candidate.url}</code><span className="mt-1 block">{candidate.classification} · {candidate.source} · {(candidate.evidence || []).join(", ")}</span></div>)}{!apply.candidate_urls?.length ? <p>No URL candidates were stored.</p> : null}</div></details>
        </section>

        <div className="mt-5 flex flex-wrap gap-1 border-b border-outline-variant/15 px-5">{INSPECTOR_TABS.map(([key, label]) => <button className={`border-b-2 px-3 py-3 text-xs font-bold ${activeTab === key ? "border-primary text-primary" : "border-transparent text-on-surface-variant"}`} key={key} onClick={() => selectTab(key)} type="button">{label}</button>)}</div>

        {activeTab === "coverage" ? <div className="space-y-4 p-5"><div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between"><div><h3 className="font-headline text-xl font-extrabold text-on-surface">Is this record complete enough to publish?</h3><p className="mt-1 text-sm text-on-surface-variant">Missing, null, empty, and unknown values remain visible. Runr does not convert missing values into false.</p></div><div className="text-right"><strong className="block font-headline text-3xl font-extrabold text-on-surface">{inspection.completeness?.overall_percent ?? "—"}%</strong><small className="text-xs text-on-surface-variant">overall coverage</small></div></div><div className="grid gap-4 lg:grid-cols-3"><CoverageSection description="Normalized title, location, description, dates, requirements, and application destination." label="Job data" onInspect={() => selectTab("job")} stats={inspection.completeness?.job} /><CoverageSection description="Canonical identity and the stored authoritative company profile." label="Company data" onInspect={() => selectTab("company")} stats={inspection.completeness?.company} /><CoverageSection critical={critical} description="Source observations, posting versions, requests, review, publication, and audit." label="Admin data" onInspect={() => selectTab("admin")} stats={inspection.completeness?.admin} /></div></div> : <div className="space-y-4 p-5"><div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between"><div><h3 className="font-headline text-xl font-extrabold text-on-surface">{activeTab === "complete" ? "Complete combined record" : `${activeTab[0].toUpperCase()}${activeTab.slice(1)} data`}</h3><p className="mt-1 text-sm text-on-surface-variant">Exact authenticated backend response. Nulls, empty lists, raw payloads, errors, and provenance remain visible.</p></div><div className="flex flex-wrap gap-2"><label className="flex items-center gap-2 rounded-xl border border-outline-variant/20 bg-surface-container-low px-3 py-2"><span className="material-symbols-outlined text-[17px] text-on-surface-variant">search</span><input className="w-48 bg-transparent text-xs outline-none" onChange={(event) => setJsonSearch(event.target.value)} placeholder="Find field or value" value={jsonSearch} /></label><button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-xs font-bold text-primary" onClick={copyJson} type="button">Copy JSON</button><button className="rounded-xl bg-primary px-3 py-2 text-xs font-bold text-white" onClick={downloadJson} type="button">Download JSON</button></div></div><JsonViewer search={jsonSearch} value={activeTab === "job" ? inspection.job : activeTab === "company" ? inspection.company : activeTab === "admin" ? inspection.admin : inspection} /></div>}

        <footer className="flex flex-col gap-3 border-t border-outline-variant/15 p-5 sm:flex-row sm:items-center sm:justify-between"><div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-primary" /><div><b className="block text-xs text-on-surface">Real canonical backend record</b><small className="text-xs text-on-surface-variant">Observed {formatDateTime(inspection.job?.last_seen_at)} · Version {inspection.job?.posting_version ?? "Unknown"}</small></div></div><div className="flex flex-wrap gap-2"><button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-xs font-bold text-primary" onClick={() => setView("review")} type="button">Send to review</button><button className="rounded-xl bg-primary px-3 py-2 text-xs font-bold text-white" onClick={() => setView("publish")} type="button">Publish workflow</button></div></footer>
      </Card>
    </div>
  );
}

export default function AdminJobImportPage() {
  const { request } = useSession();
  const [view, setView] = useState("inspect");
  const [overview, setOverview] = useState(null);
  const [sources, setSources] = useState([]);
  const [imports, setImports] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [summary, setSummary] = useState(null);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [inspection, setInspection] = useState(null);
  const [activeTab, setActiveTab] = useState("coverage");
  const [jsonSearch, setJsonSearch] = useState("");
  const [selectedSources, setSelectedSources] = useState([]);
  const [scope, setScope] = useState(INITIAL_SCOPE);
  const [plan, setPlan] = useState(null);
  const [selectedImportId, setSelectedImportId] = useState("");
  const [reviewStatus, setReviewStatus] = useState("needs_review");
  const [reviewSearch, setReviewSearch] = useState("");
  const [reviewJobs, setReviewJobs] = useState([]);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadCatalog = useCallback(async (term = "") => {
    const query = new URLSearchParams({ limit: "200" });
    if (term.trim()) query.set("search", term.trim());
    const payload = await request(`/admin/job-import/jobs?${query.toString()}`);
    const nextJobs = payload.jobs || [];
    setJobs(nextJobs);
    setSummary(payload.summary || null);
    setSelectedId((current) => nextJobs.some((item) => item.canonical_job_id === current) ? current : (nextJobs[0]?.canonical_job_id || ""));
    return payload;
  }, [request]);

  const loadControlRoom = useCallback(async () => {
    const [overviewPayload, sourcePayload, importPayload] = await Promise.all([
      request("/admin/job-import/overview"),
      request("/admin/job-import/sources"),
      request("/admin/job-import/imports?limit=50"),
    ]);
    setOverview(overviewPayload);
    setSources(sourcePayload.sources || []);
    const nextImports = importPayload.imports || [];
    setImports(nextImports);
    setSelectedImportId((current) => current || nextImports[0]?.import_id || "");
  }, [request]);

  useEffect(() => {
    setLoading(true);
    Promise.all([loadControlRoom(), loadCatalog(search)]).catch((requestError) => setError(getApiErrorMessage(requestError, "Unable to load the real admin catalog."))).finally(() => setLoading(false));
  }, [loadCatalog, loadControlRoom, search]);

  useEffect(() => {
    if (!selectedId) {
      setInspection(null);
      return undefined;
    }
    let cancelled = false;
    setInspection(null);
    request(`/admin/job-import/jobs/${encodeURIComponent(selectedId)}/inspection`).then((payload) => {
      if (!cancelled) setInspection(payload);
    }).catch((requestError) => {
      if (!cancelled) setError(getApiErrorMessage(requestError, "Unable to load the complete inspection record."));
    });
    return () => { cancelled = true; };
  }, [request, selectedId]);

  const selectedJob = useMemo(() => jobs.find((item) => item.canonical_job_id === selectedId) || null, [jobs, selectedId]);
  const selectedImport = useMemo(() => imports.find((item) => item.import_id === selectedImportId) || imports[0] || null, [imports, selectedImportId]);
  const activeJson = activeTab === "job" ? inspection?.job : activeTab === "company" ? inspection?.company : activeTab === "admin" ? inspection?.admin : inspection;

  async function runAction(action, message = "Done") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(message);
      await Promise.all([loadControlRoom(), loadCatalog(search)]);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "The request could not be completed."));
    } finally {
      setBusy(false);
    }
  }

  function scopePayload() {
    return {
      ...scope,
      cities: String(scope.cities || "").split(",").map((value) => value.trim()).filter(Boolean),
      keywords: String(scope.keywords || "").split(",").map((value) => value.trim()).filter(Boolean),
      max_credits: scope.max_credits === "" ? undefined : Number(scope.max_credits),
    };
  }

  async function createPlan() {
    await runAction(async () => {
      const nextPlan = await request("/admin/job-import/plan", { method: "POST", body: { source_ids: selectedSources, scope: scopePayload() } });
      setPlan(nextPlan);
    }, "Import plan calculated from the backend.");
  }

  async function startImport() {
    await runAction(async () => {
      const result = await request("/admin/job-import/imports", { method: "POST", body: { source_ids: selectedSources, scope: scopePayload(), idempotency_key: `admin-import-${Date.now()}-${selectedSources.join("-")}` } });
      setSelectedImportId(result.import_id || "");
      setView("review");
    }, "Import queued. The worker will process it; nothing publishes automatically.");
  }

  async function loadReview() {
    if (!selectedImport?.import_id) return;
    setBusy(true);
    setError("");
    try {
      const query = new URLSearchParams({ import_id: selectedImport.import_id, status: reviewStatus, limit: "200" });
      if (reviewSearch.trim()) query.set("search", reviewSearch.trim());
      const payload = await request(`/admin/job-import/review?${query.toString()}`);
      setReviewJobs(payload.jobs || []);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to load review jobs."));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (view === "review") loadReview().catch(() => undefined);
  }, [view, reviewStatus, selectedImportId]);

  async function decide(job, decision) {
    await runAction(async () => {
      await request("/admin/job-import/review/decision", { method: "POST", body: { import_id: selectedImport.import_id, canonical_job_id: job.canonical_job_id, decision } });
      await loadReview();
    }, decision === "approve" ? "Job approved." : "Job rejected.");
  }

  async function createPreview() {
    await runAction(async () => {
      const result = await request("/admin/job-import/preview", { method: "POST", body: { import_id: selectedImport.import_id } });
      setPreview(result);
    }, "Publication preview created. The live catalog is unchanged.");
  }

  async function resolveApplyUrl() {
    if (!selectedId) return;
    await runAction(async () => {
      const result = await request(`/admin/job-import/jobs/${encodeURIComponent(selectedId)}/resolve-apply-url`, { method: "POST", body: {} });
      setInspection(result);
    }, "Apply URL resolution completed and was recorded in the audit trail.");
  }

  async function copyJson() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(activeJson ?? null, null, 2));
      setNotice("JSON copied to the clipboard.");
    } catch {
      setError("Clipboard access was unavailable. Use Download JSON instead.");
    }
  }

  function downloadJson() {
    const blob = new Blob([JSON.stringify(activeJson ?? null, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${selectedId || "runr-admin-record"}-${activeTab}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function selectTab(tab) {
    setActiveTab(tab);
    setJsonSearch("");
  }

  function renderInspector() {
    if (loading && !jobs.length) return <EmptyState title="Loading real catalog" body="Runr is loading canonical jobs from the authenticated acquisition backend." />;
    if (!jobs.length) return <EmptyState title="No canonical jobs available" body="No real canonical job records are available yet. Run an import, wait for the worker, or inspect the backend acquisition status." />;
    if (!inspection) return <EmptyState title="Loading selected record" body="The complete job, company, admin, and raw provenance payload is being loaded." />;
    return <InspectorView activeTab={activeTab} apply={inspection.apply_url || {}} busy={busy} copyJson={copyJson} critical={inspection.completeness?.critical_checks || []} downloadJson={downloadJson} inspection={inspection} jobs={jobs} jsonSearch={jsonSearch} resolveApplyUrl={resolveApplyUrl} search={search} selectedId={selectedId} selectedJob={selectedJob} selectTab={selectTab} setJsonSearch={setJsonSearch} setSearch={setSearch} setSelectedId={setSelectedId} setView={setView} summary={summary} />;
  }

  return <div className="space-y-5 pb-8"><header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between"><div><p className="text-xs font-bold uppercase tracking-[0.2em] text-primary">Admin / Jobs</p><h1 className="mt-2 font-headline text-4xl font-extrabold tracking-tight text-on-surface">Data inspector</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-on-surface-variant">Inspect the complete stored record behind every centralized job: job data, company data, acquisition provenance, raw payloads, completeness, and direct Apply URL evidence.</p></div><div className="flex items-center gap-3"><div className="text-right"><div className="flex items-center justify-end gap-2 text-sm font-bold text-primary"><span className="h-2 w-2 rounded-full bg-primary" />Real catalog</div><small className="text-xs text-on-surface-variant">{overview?.imports?.status || "Backend status loading"}</small></div><Link className="rounded-xl border border-outline-variant/20 px-4 py-3 text-sm font-bold text-primary" to="/admin">Back to Admin</Link></div></header><div className="flex flex-wrap items-center gap-1 rounded-2xl border border-outline-variant/15 bg-surface-container-low p-2">{WORKFLOW.map(([key, label], index) => <button className={`flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-bold ${view === key || (key === "live" && view === "inspect") ? "bg-surface-container-lowest text-primary shadow-soft" : "text-on-surface-variant"}`} key={key} onClick={() => key === "live" ? window.location.assign("/jobs") : setView(key)} type="button"><span className="grid h-5 w-5 place-items-center rounded-full bg-primary/10 text-[10px] text-primary">{index + 1}</span>{label}</button>)}</div><ErrorNotice message={error} />{notice ? <p className="rounded-2xl border border-primary/20 bg-primary/10 px-4 py-3 text-sm text-primary">{notice}</p> : null}<section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric hint="central canonical jobs" label="Catalog records" value={summary?.catalog_records ?? overview?.current_live_jobs} /><Metric hint="stored URL; inspect to validate" label="Apply URL stored" tone="good" value={summary?.apply_url_present} /><Metric hint="no stored URL; inspection may also report invalid" label="Apply URL missing" tone="bad" value={summary?.apply_url_missing_or_invalid} /><Metric hint={`worker ${overview?.worker?.status || "Unknown"}`} label="Review queue" value={overview?.review?.needs_review} /></section>{view === "import" ? <ImportPanel busy={busy} onPlan={createPlan} onStart={startImport} overview={overview} plan={plan} scope={scope} selectedSources={selectedSources} setScope={setScope} setSelectedSources={setSelectedSources} sources={sources} /> : view === "review" ? <ReviewPanel imports={imports} onDecision={decide} onLoad={loadReview} reviewJobs={reviewJobs} reviewSearch={reviewSearch} reviewStatus={reviewStatus} selectedImportId={selectedImportId} setReviewSearch={setReviewSearch} setReviewStatus={setReviewStatus} setSelectedImportId={setSelectedImportId} /> : view === "publish" ? <PublishPanel busy={busy} imports={imports} onPreview={createPreview} onPublish={() => runAction(() => request("/admin/job-import/publish", { method: "POST", body: { publication_id: preview.publication_id } }), "Approved records published to the live catalog.")} onUndo={() => runAction(() => request("/admin/job-import/undo", { method: "POST", body: {} }), "The last publication was undone.")} preview={preview} selectedImportId={selectedImportId} setSelectedImportId={setSelectedImportId} /> : renderInspector()}</div>;
}
