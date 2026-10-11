import { labelize } from "../../lib/formatters";
import { formatDateTime } from "./workspaceFormatters";

export function FocusedWorkspaceDocumentsPanel({
  documents,
  error,
  loading,
  resolvePath,
}) {
  return (
    <div className="rounded-xl border border-outline-variant/10 bg-surface p-4">
      <div>
        <h3 className="text-sm font-semibold text-on-surface">Workspace CVs</h3>
        <p className="mt-1 text-xs leading-6 text-on-surface-variant">
          The baseline CV for this workspace and the tailored CVs generated from it stay
          visible here, so you do not have to jump into another section to review them.
        </p>
      </div>
      {loading ? (
        <div className="mt-4 rounded-lg border border-outline-variant/10 bg-surface-container-lowest p-4 text-sm text-on-surface-variant">
          Loading workspace CVs...
        </div>
      ) : error ? (
        <div className="mt-4 rounded-lg border border-outline-variant/10 bg-surface-container-lowest p-4 text-sm text-error">
          {error}
        </div>
      ) : documents.length ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {documents.map((document) => (
            <article
              className="rounded-lg border border-outline-variant/10 bg-surface-container-lowest p-4"
              key={document.document_id}
            >
              <div className="flex flex-wrap items-center gap-2">
                <div className="text-sm font-semibold text-on-surface">
                  {document.display_name}
                </div>
                <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
                  {document.document_type}
                </span>
              </div>
              <p className="mt-2 text-sm text-on-surface-variant">
                {[document.job_title, document.company].filter(Boolean).join(" at ") ||
                  "Baseline workspace CV"}
              </p>
              <div className="mt-3 grid gap-2 text-xs leading-6 text-on-surface-variant md:grid-cols-2">
                <div>
                  <span className="font-semibold text-on-surface">Status:</span>{" "}
                  {labelize(document.display_status || document.status || "ready")}
                </div>
                <div>
                  <span className="font-semibold text-on-surface">Created:</span>{" "}
                  {formatDateTime(document.created_at)}
                </div>
              </div>
              {document.download_url ? (
                <div className="mt-4">
                  <a
                    className="inline-flex items-center rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                    href={resolvePath(document.preview_url || document.download_url)}
                    rel="noreferrer"
                    target="_blank"
                  >
                    Open Document
                  </a>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      ) : (
        <div className="mt-4 rounded-lg border border-outline-variant/10 bg-surface-container-lowest p-4 text-sm text-on-surface-variant">
          No workspace CVs are visible yet. Upload a baseline CV while editing this workspace,
          or run the workspace to generate tailored CVs here.
        </div>
      )}
    </div>
  );
}
