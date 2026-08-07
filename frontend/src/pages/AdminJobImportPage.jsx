import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { getApiErrorMessage } from "../lib/api";
import { formatDateTime, statusTone } from "../lib/formatters";

const tabs = [
  ["overview", "Overview"],
  ["import", "Import jobs"],
  ["review", "Review jobs"],
  ["publish", "Publish"],
  ["history", "History"],
];

const initialScope = {
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
  return <section className={`rounded-[1.5rem] border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft ${className}`}>{children}</section>;
}

function Metric({ label, value, tone = "neutral" }) {
  return (
    <Card>
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-on-surface-variant">{label}</p>
      <p className={`mt-3 font-headline text-3xl font-extrabold ${tone === "warning" ? "text-error" : "text-on-surface"}`}>{value}</p>
    </Card>
  );
}

function SourceDetails({ source }) {
  return (
    <details className="mt-3 text-xs text-on-surface-variant">
      <summary className="cursor-pointer font-semibold">Advanced details</summary>
      <dl className="mt-2 space-y-1 rounded-xl bg-surface-container-low p-3">
        <div><dt className="inline font-semibold">Request hosts: </dt><dd className="inline font-mono">{(source.request_hosts || []).join(", ") || "None"}</dd></div>
        <div><dt className="inline font-semibold">Connector: </dt><dd className="inline font-mono">{source.advanced?.target_id || source.id}</dd></div>
        <div><dt className="inline font-semibold">Policy: </dt><dd className="inline font-mono">{source.advanced?.policy_version || "Unknown"}</dd></div>
      </dl>
    </details>
  );
}

function ErrorNotice({ message }) {
  if (!message) return null;
  return <p className="rounded-2xl bg-error-container px-4 py-3 text-sm text-on-error-container">{message}</p>;
}

export default function AdminJobImportPage() {
  const { request } = useSession();
  const [tab, setTab] = useState("overview");
  const [overview, setOverview] = useState(null);
  const [sources, setSources] = useState([]);
  const [imports, setImports] = useState([]);
  const [selectedSources, setSelectedSources] = useState([]);
  const [scope, setScope] = useState(initialScope);
  const [plan, setPlan] = useState(null);
  const [selectedImportId, setSelectedImportId] = useState("");
  const [reviewStatus, setReviewStatus] = useState("needs_review");
  const [reviewSearch, setReviewSearch] = useState("");
  const [reviewJobs, setReviewJobs] = useState([]);
  const [preview, setPreview] = useState(null);
  const [events, setEvents] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadOverview = useCallback(async () => {
    const [overviewPayload, sourcePayload, importPayload] = await Promise.all([
      request("/admin/job-import/overview"),
      request("/admin/job-import/sources"),
      request("/admin/job-import/imports?limit=50"),
    ]);
    setOverview(overviewPayload);
    setSources(sourcePayload.sources || []);
    const nextImports = importPayload.imports || [];
    setImports(nextImports);
    if (!selectedImportId && nextImports[0]?.import_id) setSelectedImportId(nextImports[0].import_id);
  }, [request, selectedImportId]);

  useEffect(() => {
    loadOverview().catch((requestError) => setError(getApiErrorMessage(requestError, "Unable to load the import dashboard.")));
  }, [loadOverview]);

  const selectedImport = useMemo(() => imports.find((item) => item.import_id === selectedImportId) || imports[0], [imports, selectedImportId]);

  async function runAction(action, successMessage = "Done") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(successMessage);
      await loadOverview();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "The request could not be completed."));
    } finally {
      setBusy(false);
    }
  }

  function updateScope(key, value) {
    setScope((current) => ({ ...current, [key]: value }));
  }

  function scopePayload() {
    return {
      ...scope,
      cities: scope.cities.split(",").map((value) => value.trim()).filter(Boolean),
      keywords: scope.keywords.split(",").map((value) => value.trim()).filter(Boolean),
      max_credits: scope.max_credits === "" ? undefined : Number(scope.max_credits),
    };
  }

  async function createPlan() {
    await runAction(async () => {
      const nextPlan = await request("/admin/job-import/plan", {
        method: "POST",
        body: { source_ids: selectedSources, scope: scopePayload() },
      });
      setPlan(nextPlan);
    }, "Import plan calculated.");
  }

  async function startImport() {
    await runAction(async () => {
      const result = await request("/admin/job-import/imports", {
        method: "POST",
        body: {
          source_ids: selectedSources,
          scope: scopePayload(),
          idempotency_key: `admin-import-${Date.now()}-${selectedSources.join("-")}`,
        },
      });
      setSelectedImportId(result.import_id);
      setTab("review");
    }, "Import queued. The worker will run it once; nothing publishes automatically.");
  }

  async function loadReview() {
    if (!selectedImport?.import_id) return;
    setBusy(true);
    setError("");
    try {
      const params = new URLSearchParams({ import_id: selectedImport.import_id, status: reviewStatus, limit: "200" });
      if (reviewSearch.trim()) params.set("search", reviewSearch.trim());
      const result = await request(`/admin/job-import/review?${params.toString()}`);
      setReviewJobs(result.jobs || []);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to load review jobs."));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (tab !== "review") return;
    loadReview().catch(() => undefined);
  }, [tab, reviewStatus, selectedImportId]);

  async function decide(job, decision) {
    await runAction(async () => {
      await request("/admin/job-import/review/decision", {
        method: "POST",
        body: { import_id: selectedImport.import_id, canonical_job_id: job.canonical_job_id, decision },
      });
      await loadReview();
    }, decision === "approve" ? "Job approved." : "Job not accepted.");
  }

  async function createPreview() {
    await runAction(async () => {
      const result = await request("/admin/job-import/preview", { method: "POST", body: { import_id: selectedImport.import_id } });
      setPreview(result);
    }, "Preview created. The live catalog has not changed.");
  }

  async function loadHistory() {
    try {
      const result = await request(`/admin/job-import/history${selectedImport?.import_id ? `?import_id=${selectedImport.import_id}` : ""}`);
      setEvents(result.events || []);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to load history."));
    }
  }

  useEffect(() => {
    if (tab === "history") loadHistory().catch(() => undefined);
  }, [tab, selectedImportId]);

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">Admin control room</p>
          <h1 className="mt-2 font-headline text-4xl font-extrabold tracking-tight text-on-surface">Job Import</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-on-surface-variant">Import jobs, review every result, publish approved jobs, and undo the last publication when necessary.</p>
        </div>
        <Link className="rounded-2xl border border-outline-variant/20 px-4 py-3 text-sm font-semibold text-primary" to="/admin">Back to Admin</Link>
      </header>

      <ErrorNotice message={error} />
      {notice ? <p className="rounded-2xl bg-primary/10 px-4 py-3 text-sm text-primary">{notice}</p> : null}

      <nav className="flex flex-wrap gap-2 rounded-2xl bg-surface-container-low p-2">
        {tabs.map(([key, label]) => <button key={key} className={`rounded-xl px-4 py-2 text-sm font-semibold ${tab === key ? "bg-surface-container-lowest text-on-surface shadow-soft" : "text-on-surface-variant"}`} onClick={() => setTab(key)} type="button">{label}</button>)}
      </nav>

      {tab === "overview" ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Metric label="Imports" value={overview?.imports?.status || "Loading"} tone={overview?.imports?.paused ? "warning" : "neutral"} />
            <Metric label="Jobs waiting for review" value={overview?.review?.needs_review ?? "—"} />
            <Metric label="Approved jobs" value={overview?.review?.approved ?? "—"} />
            <Metric label="Current live jobs" value={overview?.current_live_jobs ?? "—"} />
          </div>
          <Card>
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div><h2 className="font-headline text-2xl font-bold text-on-surface">Import jobs → Review jobs → Publish</h2><p className="mt-1 text-sm text-on-surface-variant">The worker is {overview?.worker?.status || "checking"}. Imports are {overview?.imports?.paused ? "paused" : "ready"}; publication is always a separate action.</p></div>
              <div className="flex flex-wrap gap-3"><button className="rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-white" onClick={() => setTab("import")} type="button">Import jobs</button><button className="rounded-xl border border-primary/20 px-4 py-3 text-sm font-semibold text-primary" onClick={() => setTab("review")} type="button">Review jobs</button><button className="rounded-xl border border-error/20 px-4 py-3 text-sm font-semibold text-error" onClick={() => runAction(() => request("/admin/job-import/pause", { method: "POST", body: { paused: true } }), "All imports paused.")} type="button">Pause all imports</button></div>
            </div>
          </Card>
          <Card><h2 className="font-headline text-xl font-bold text-on-surface">Important warnings</h2><div className="mt-3 space-y-2">{(overview?.warnings || ["No warnings."]).map((warning) => <p className="rounded-xl bg-surface-container-low px-4 py-3 text-sm text-on-surface-variant" key={warning}>{warning}</p>)}</div></Card>
        </>
      ) : null}

      {tab === "import" ? (
        <div className="space-y-5">
          <Card><div className="flex items-center justify-between"><div><h2 className="font-headline text-2xl font-bold text-on-surface">Choose sources</h2><p className="mt-1 text-sm text-on-surface-variant">Official source requests stay direct. Web imports use the existing server-side ScrapeOps path where a source is approved for it.</p></div><StatusBadge tone={overview?.imports?.paused ? "error" : "success"}>{overview?.imports?.paused ? "Paused" : "Ready"}</StatusBadge></div><div className="mt-5 grid gap-3 md:grid-cols-2">{sources.map((source) => <label className={`cursor-pointer rounded-2xl border p-4 ${selectedSources.includes(source.id) ? "border-primary bg-primary/5" : "border-outline-variant/20"}`} key={source.id}><div className="flex gap-3"><input checked={selectedSources.includes(source.id)} onChange={(event) => setSelectedSources((current) => event.target.checked ? [...current, source.id] : current.filter((item) => item !== source.id))} type="checkbox" /><span className="min-w-0"><span className="block font-semibold text-on-surface">{source.company || source.name}</span><span className="mt-1 block text-sm text-on-surface-variant">{source.source_type} · {source.status === "ready" ? "Ready" : "Source paused"}</span><span className="mt-1 block text-xs text-on-surface-variant">Locations: {(source.supported_locations || []).join(", ")}</span><SourceDetails source={source} /></span></div></label>)}</div></Card>
          <Card><h2 className="font-headline text-2xl font-bold text-on-surface">Choose scope</h2><p className="mt-1 text-sm text-on-surface-variant">Runr collects the selected source scope and keeps all collected results in review. Filters never publish automatically.</p><div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{[["country", "Country"], ["cities", "City or region"], ["department", "Department"], ["category", "Category"], ["keywords", "Keywords"]].map(([key, label]) => <label className="space-y-2 text-sm text-on-surface-variant" key={key}><span className="font-semibold text-on-surface">{label}</span><input className="w-full rounded-xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 text-on-surface" disabled={scope.full_source_import} onChange={(event) => updateScope(key, event.target.value)} placeholder={key === "cities" || key === "keywords" ? "Comma separated" : "Optional"} value={scope[key]} /></label>)}<label className="flex items-center gap-2 pt-7 text-sm font-semibold text-on-surface"><input checked={scope.remote} disabled={scope.full_source_import} onChange={(event) => updateScope("remote", event.target.checked)} type="checkbox" /> Remote jobs</label><label className="flex items-center gap-2 pt-7 text-sm font-semibold text-on-surface"><input checked={scope.full_source_import} onChange={(event) => updateScope("full_source_import", event.target.checked)} type="checkbox" /> Full source import</label></div><details className="mt-5 text-sm text-on-surface-variant"><summary className="cursor-pointer font-semibold">Advanced limits</summary><div className="mt-3 grid gap-4 md:grid-cols-3"><label>Maximum pages<input className="mt-2 w-full rounded-xl border border-outline-variant/20 bg-surface-container-low px-3 py-2" min="1" max="20" onChange={(event) => updateScope("max_pages", event.target.value)} type="number" value={scope.max_pages} /></label><label>Maximum requests<input className="mt-2 w-full rounded-xl border border-outline-variant/20 bg-surface-container-low px-3 py-2" min="1" max="100" onChange={(event) => updateScope("max_requests", event.target.value)} type="number" value={scope.max_requests} /></label><label>Maximum ScrapeOps credits<input className="mt-2 w-full rounded-xl border border-outline-variant/20 bg-surface-container-low px-3 py-2" min="0" max="10000" onChange={(event) => updateScope("max_credits", event.target.value)} placeholder="Required for paid sources" type="number" value={scope.max_credits} /></label></div></details></Card>
          <Card><h2 className="font-headline text-2xl font-bold text-on-surface">Confirm</h2>{plan ? <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric label="Maximum requests" value={plan.maximum_requests} /><Metric label="Maximum pages" value={plan.maximum_pages} /><Metric label="Maximum credits" value={plan.maximum_credits || 0} /><Metric label="Estimated cost" value={plan.estimated_cost?.known ? `${plan.estimated_cost.maximum} USD` : "Needs server limit"} tone={!plan.estimated_cost?.known ? "warning" : "neutral"} /></div> : <p className="mt-3 text-sm text-on-surface-variant">Choose a source and calculate a bounded plan before starting.</p>}<div className="mt-5 flex flex-wrap gap-3"><button className="rounded-xl border border-primary/20 px-4 py-3 text-sm font-semibold text-primary disabled:opacity-50" disabled={busy || !selectedSources.length} onClick={createPlan} type="button">Calculate plan</button><button className="rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-white disabled:opacity-50" disabled={busy || !plan?.can_start || overview?.imports?.paused} onClick={startImport} type="button">{busy ? "Working..." : "Start import"}</button></div><p className="mt-4 text-sm text-on-surface-variant">All jobs go to review. Nothing publishes automatically.</p><details className="mt-4 text-xs text-on-surface-variant"><summary className="cursor-pointer font-semibold">Advanced details</summary><pre className="mt-2 overflow-auto rounded-xl bg-surface-container-low p-3">{JSON.stringify(plan || {}, null, 2)}</pre></details></Card>
        </div>
      ) : null}

      {tab === "review" ? (
        <div className="space-y-5"><Card><div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between"><div><h2 className="font-headline text-2xl font-bold text-on-surface">Review jobs</h2><p className="mt-1 text-sm text-on-surface-variant">Every normalized result stays visible, including automatically rejected jobs.</p></div><select className="rounded-xl border border-outline-variant/20 bg-surface-container-low px-3 py-2 text-sm" onChange={(event) => setSelectedImportId(event.target.value)} value={selectedImport?.import_id || ""}>{imports.map((item) => <option key={item.import_id} value={item.import_id}>{item.import_id} · {item.status}</option>)}</select></div><div className="mt-5 flex flex-wrap gap-2">{[["needs_review", "Needs review"], ["approved", "Approved"], ["not_accepted", "Not accepted"], ["already_live", "Already live"], ["all", "All results"]].map(([key, label]) => <button className={`rounded-full px-3 py-2 text-xs font-semibold ${reviewStatus === key ? "bg-primary text-white" : "bg-surface-container-low text-on-surface-variant"}`} key={key} onClick={() => setReviewStatus(key)} type="button">{label}</button>)}<input className="min-w-[16rem] flex-1 rounded-xl border border-outline-variant/20 bg-surface-container-low px-3 py-2 text-sm" onChange={(event) => setReviewSearch(event.target.value)} onKeyDown={(event) => event.key === "Enter" && loadReview()} placeholder="Search company, title, location" value={reviewSearch} /><button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-sm font-semibold" onClick={loadReview} type="button">Filter</button></div></Card><Card className="overflow-x-auto p-0"><table className="w-full min-w-[64rem] text-left text-sm"><thead className="bg-surface-container-low text-xs uppercase tracking-wider text-on-surface-variant"><tr>{["Company", "Title", "Location", "Apply", "Quality", "Review"].map((label) => <th className="px-5 py-4" key={label}>{label}</th>)}<th className="px-5 py-4">Actions</th></tr></thead><tbody className="divide-y divide-outline-variant/10">{reviewJobs.map((job) => <tr className="hover:bg-surface-container-low" key={`${job.canonical_job_id || job.external_job_id}-${job.source_id}`}><td className="px-5 py-4 font-semibold text-on-surface">{job.company || "Unknown"}<span className="block text-xs font-normal text-on-surface-variant">{job.source_id}</span></td><td className="px-5 py-4 text-on-surface">{job.title || "Unknown"}<details className="mt-1 text-xs text-on-surface-variant"><summary className="cursor-pointer">Description and details</summary><p className="mt-2 max-w-xl whitespace-pre-wrap">{job.description || "Not available"}</p><pre className="mt-2 max-w-xl overflow-auto rounded bg-surface-container-low p-2">{JSON.stringify(job.source_payload || {}, null, 2)}</pre></details></td><td className="px-5 py-4 text-on-surface-variant">{job.location || "Unknown"}</td><td className="px-5 py-4">{job.apply_url ? <a className="font-semibold text-primary" href={job.apply_url} rel="noreferrer" target="_blank">Open Apply</a> : <span className="text-error">Missing</span>}</td><td className="px-5 py-4 text-xs text-on-surface-variant">{(job.quality_warnings || []).join(", ") || "Checks passed"}</td><td className="px-5 py-4"><StatusBadge tone={statusTone(job.review_state)}>{job.review_state}</StatusBadge></td><td className="px-5 py-4"><div className="flex gap-2">{job.canonical_job_id && job.review_state === "needs_review" ? <><button className="rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-white" onClick={() => decide(job, "approve")} type="button">Approve</button><button className="rounded-lg border border-error/20 px-3 py-2 text-xs font-semibold text-error" onClick={() => decide(job, "reject")} type="button">Reject</button></> : null}</div></td></tr>)}</tbody></table>{!reviewJobs.length ? <p className="p-8 text-sm text-on-surface-variant">No results in this view yet. The worker may still be processing the import.</p> : null}</Card></div>
      ) : null}

      {tab === "publish" ? (
        <div className="space-y-5"><Card><h2 className="font-headline text-2xl font-bold text-on-surface">Publish approved jobs</h2><p className="mt-1 text-sm text-on-surface-variant">Preview the customer-facing catalog change before moving the live publication head.</p><div className="mt-5 flex flex-wrap gap-3"><select className="rounded-xl border border-outline-variant/20 bg-surface-container-low px-3 py-2 text-sm" onChange={(event) => setSelectedImportId(event.target.value)} value={selectedImport?.import_id || ""}>{imports.map((item) => <option key={item.import_id} value={item.import_id}>{item.import_id} · {item.status}</option>)}</select><button className="rounded-xl border border-primary/20 px-4 py-3 text-sm font-semibold text-primary" disabled={!selectedImport?.import_id || busy} onClick={createPreview} type="button">Create preview</button></div>{preview ? <div className="mt-5 rounded-2xl bg-surface-container-low p-4"><p className="font-semibold text-on-surface">Preview: {preview.total} jobs</p><p className="mt-1 text-sm text-on-surface-variant">The live catalog is unchanged until you publish.</p><details className="mt-3 text-xs text-on-surface-variant"><summary className="cursor-pointer font-semibold">Advanced details</summary><pre className="mt-2 max-h-64 overflow-auto">{JSON.stringify(preview, null, 2)}</pre></details><div className="mt-4 flex flex-wrap gap-3"><button className="rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-white" disabled={busy} onClick={() => runAction(() => request("/admin/job-import/publish", { method: "POST", body: { publication_id: preview.publication_id } }), "Approved jobs published.")} type="button">Publish approved jobs</button><button className="rounded-xl border border-error/20 px-4 py-3 text-sm font-semibold text-error" disabled={busy} onClick={() => runAction(() => request("/admin/job-import/undo", { method: "POST", body: {} }), "Last publication undone.")} type="button">Undo last publish</button><Link className="rounded-xl border border-outline-variant/20 px-4 py-3 text-sm font-semibold text-primary" to="/jobs">View in Jobs</Link></div></div> : null}</Card></div>
      ) : null}

      {tab === "history" ? <Card><div className="flex items-center justify-between"><div><h2 className="font-headline text-2xl font-bold text-on-surface">History</h2><p className="mt-1 text-sm text-on-surface-variant">Plain-language import, review and publication events.</p></div><button className="rounded-xl border border-outline-variant/20 px-3 py-2 text-sm font-semibold" onClick={loadHistory} type="button">Refresh</button></div><div className="mt-5 space-y-3">{events.map((event) => <div className="rounded-2xl bg-surface-container-low p-4" key={event.event_id}><div className="flex flex-wrap items-center justify-between gap-3"><span className="font-semibold text-on-surface">{String(event.event_type || "event").replaceAll("_", " ")}</span><span className="text-xs text-on-surface-variant">{formatDateTime(event.created_at)}</span></div><details className="mt-2 text-xs text-on-surface-variant"><summary className="cursor-pointer">Advanced details</summary><pre className="mt-2 overflow-auto">{JSON.stringify(event.payload || {}, null, 2)}</pre></details></div>)}{!events.length ? <p className="text-sm text-on-surface-variant">No import history yet.</p> : null}</div></Card> : null}
    </div>
  );
}
