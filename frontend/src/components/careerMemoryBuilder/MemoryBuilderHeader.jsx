export default function MemoryBuilderHeader({
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
          <p className="mt-2 max-w-3xl text-sm font-medium leading-6 text-primary">
            Career Memory stores reusable facts. To edit the wording or layout of a specific CV,
            open CV Studio instead.
          </p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <button
            className="inline-flex items-center justify-center gap-2 rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-white transition-all hover:opacity-90"
            onClick={onContinueInterview}
            type="button"
          >
            Continue fact builder
            <span className="material-symbols-outlined text-[18px]">fact_check</span>
          </button>
        </div>
      </div>
      <div className="mt-5 grid gap-3 md:grid-cols-3">
        {[
          ["1. Capture one fact", "Add a sourced achievement, metric, project, or motivation detail."],
          ["2. Review provenance", "Confirm where the fact came from before it becomes reusable."],
          ["3. Save approved facts", "Runr can reuse confirmed facts across future applications."],
        ].map(([title, description]) => (
          <div className="rounded-2xl bg-surface-container-low px-4 py-3" key={title}>
            <div className="text-sm font-semibold text-on-surface">{title}</div>
            <div className="mt-1 text-xs leading-5 text-on-surface-variant">{description}</div>
          </div>
        ))}
      </div>
      {saveState.message ? <p className="mt-4 text-sm text-primary">{saveState.message}</p> : null}
      {saveState.error ? <p className="mt-4 text-sm text-error">{saveState.error}</p> : null}
    </section>
  );
}
