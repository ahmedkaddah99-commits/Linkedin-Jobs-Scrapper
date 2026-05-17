import { Link } from "react-router-dom";

export default function MemoryBuilderHeader({
  manageDocumentsTo,
  onContinueInterview,
  saveState,
}) {
  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-4xl">
          <h2 className="font-headline text-[2rem] font-extrabold tracking-tight text-on-surface">
            Career Memory Builder
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-7 text-on-surface-variant">
            Your CV shows the basics. Add the missing achievements, stories, metrics, projects,
            and motivation details Runr needs to tailor stronger applications.
          </p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <button
            className="inline-flex items-center justify-center gap-2 rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-white transition-all hover:opacity-90"
            onClick={onContinueInterview}
            type="button"
          >
            Continueguided interview
            <span className="material-symbols-outlined text-[18px]">forum</span>
          </button>
          <Link
            className="inline-flex items-center justify-center gap-2 rounded-2xl bg-surface-container-low px-5 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            to={manageDocumentsTo}
          >
            Manage documents
            <span className="material-symbols-outlined text-[18px]">folder_open</span>
          </Link>
        </div>
      </div>
      {saveState.message ? <p className="mt-4 text-sm text-primary">{saveState.message}</p> : null}
      {saveState.error ? <p className="mt-4 text-sm text-error">{saveState.error}</p> : null}
    </section>
  );
}

