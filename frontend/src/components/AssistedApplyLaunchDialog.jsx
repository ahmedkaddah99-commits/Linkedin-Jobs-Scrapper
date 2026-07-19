import { useEffect, useMemo, useState } from "react";
import { useApiResource } from "../hooks/useApiResource";
import { bindRunrApplicationPackage } from "../lib/assistedApplyLaunch";

const SUPPORTED_MIME_TYPES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

function candidateDocuments(documents) {
  return (documents || []).filter((document) =>
    String(document?.document_id || "").startsWith("asset::")
    && SUPPORTED_MIME_TYPES.has(String(document?.content_type || "")),
  );
}

function profileSummary(profile) {
  const normalized = profile || {};
  return [
    ["Name", normalized.legal_name || normalized.full_name || normalized.name],
    ["Email", normalized.email],
    ["Phone", normalized.phone || normalized.phone_number],
  ].filter(([, value]) => String(value || "").trim());
}

export default function AssistedApplyLaunchDialog({ onClose, onLaunched, profile, request, row }) {
  const [confirmed, setConfirmed] = useState(false);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([]);
  const [state, setState] = useState({ loading: false, message: "", error: "" });
  const { data: documentsPayload, loading: documentsLoading, error: documentsError } = useApiResource(
    () => request("/documents?limit=500"),
    [request],
    { cacheKey: "assisted-apply:documents", staleMs: 30000, backgroundRefresh: true },
  );
  const documents = useMemo(
    () => candidateDocuments(documentsPayload?.documents),
    [documentsPayload],
  );
  const facts = useMemo(() => profileSummary(profile), [profile]);

  useEffect(() => {
    const primaryCv = documents.find((document) => String(document.asset_kind || "") === "workspace_cv");
    if (primaryCv) setSelectedDocumentIds([primaryCv.document_id]);
  }, [documents]);

  function toggleDocument(documentId) {
    setSelectedDocumentIds((current) =>
      current.includes(documentId)
        ? current.filter((item) => item !== documentId)
        : [...current, documentId],
    );
  }

  async function launch() {
    if (!confirmed || state.loading) return;
    const applicationUrl = String(row?.apply_link || "").trim();
    if (!applicationUrl) {
      setState({ loading: false, message: "", error: "No employer application URL is available for this role." });
      return;
    }
    // Open synchronously inside the click handler so popup protection does not
    // block the employer tab. Clear opener before navigating cross-origin.
    const applicationWindow = window.open("about:blank", "runr-assisted-apply");
    if (!applicationWindow) {
      setState({ loading: false, message: "", error: "Your browser blocked the application tab. Allow popups for Runr and try again." });
      return;
    }
    applicationWindow.opener = null;
    applicationWindow.location.replace(applicationUrl);
    setState({ loading: true, message: "Preparing your reviewed application package…", error: "" });
    try {
      const prepared = await request("/assisted-apply/packages/prepare", {
        method: "POST",
        body: {
          run_id: row.run_id,
          job_id: row.job_id,
          document_ids: selectedDocumentIds,
          confirm_standard_profile: true,
        },
      });
      const launched = await request("/assisted-apply/packages/launch", {
        method: "POST",
        body: { package_id: prepared.package_id },
      });
      await bindRunrApplicationPackage({
        bindingId: launched.binding_id,
        applicationUrl: prepared.application_url,
      });
      setState({
        loading: false,
        message: "The package is ready in the employer tab. Open the Runr side panel there to review and fill it.",
        error: "",
      });
      onLaunched?.(prepared);
    } catch (error) {
      setState({
        loading: false,
        message: "",
        error: error?.message || "Runr could not prepare this assisted application.",
      });
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4" role="presentation">
      <section aria-labelledby="assisted-apply-launch-title" className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-surface-container-lowest p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-primary">Runr Assisted Apply</p>
            <h2 className="mt-2 font-headline text-2xl font-bold text-on-surface" id="assisted-apply-launch-title">
              Review &amp; Apply
            </h2>
            <p className="mt-2 text-sm leading-6 text-on-surface-variant">
              Runr opens the employer form, prepares a one-time package, and lets you review every fill. You submit the application yourself.
            </p>
          </div>
          <button aria-label="Close" className="rounded-full p-2 text-on-surface-variant hover:bg-surface-container" disabled={state.loading} onClick={onClose} type="button">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="mt-6 rounded-2xl bg-surface-container-low p-4">
          <div className="font-semibold text-on-surface">{row.title || "Untitled role"}</div>
          <div className="mt-1 text-sm text-on-surface-variant">{[row.company, row.location].filter(Boolean).join(" | ")}</div>
        </div>

        <section className="mt-5">
          <h3 className="text-sm font-semibold text-on-surface">Standard profile facts</h3>
          {facts.length ? (
            <dl className="mt-3 grid gap-2 rounded-2xl border border-outline-variant/20 p-4 text-sm sm:grid-cols-2">
              {facts.map(([label, value]) => <div key={label}><dt className="text-on-surface-variant">{label}</dt><dd className="mt-1 font-medium text-on-surface">{value}</dd></div>)}
            </dl>
          ) : (
            <p className="mt-2 text-sm text-error">No standard profile facts are saved. You can still open the form, but complete those fields manually.</p>
          )}
          <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-2xl border border-outline-variant/20 p-4 text-sm text-on-surface">
            <input checked={confirmed} className="mt-1" onChange={(event) => setConfirmed(event.target.checked)} type="checkbox" />
            <span>I confirm that these standard profile facts are current for this application.</span>
          </label>
        </section>

        <section className="mt-5">
          <h3 className="text-sm font-semibold text-on-surface">Documents to offer</h3>
          <p className="mt-1 text-xs leading-5 text-on-surface-variant">Only selected PDF or DOCX files are made available to the employer form. You can leave this empty and upload manually.</p>
          {documentsLoading ? <p className="mt-3 text-sm text-on-surface-variant">Loading documents…</p> : null}
          {documentsError ? <p className="mt-3 text-sm text-error">{documentsError}</p> : null}
          {!documentsLoading && !documentsError && !documents.length ? <p className="mt-3 text-sm text-on-surface-variant">No supported documents are available in your Runr library.</p> : null}
          <div className="mt-3 space-y-2">
            {documents.map((document) => (
              <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-outline-variant/20 p-3 text-sm" key={document.document_id}>
                <input checked={selectedDocumentIds.includes(document.document_id)} onChange={() => toggleDocument(document.document_id)} type="checkbox" />
                <span className="min-w-0"><span className="block truncate font-medium text-on-surface">{document.display_name || document.file_name}</span><span className="text-xs text-on-surface-variant">{document.asset_kind || "document"}</span></span>
              </label>
            ))}
          </div>
        </section>

        <div className="mt-7 flex flex-wrap justify-end gap-3">
          <button className="rounded-full bg-surface-container px-4 py-2.5 text-sm font-semibold text-on-surface" disabled={state.loading} onClick={onClose} type="button">Cancel</button>
          <button className="rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60" disabled={!confirmed || state.loading} onClick={() => void launch()} type="button">
            {state.loading ? "Opening application…" : "Open reviewed application"}
          </button>
        </div>
        {state.message ? <p className="mt-4 rounded-xl bg-primary/10 p-3 text-sm text-primary" role="status">{state.message}</p> : null}
        {state.error ? <p className="mt-4 rounded-xl bg-error/10 p-3 text-sm text-error" role="alert">{state.error}</p> : null}
      </section>
    </div>
  );
}
