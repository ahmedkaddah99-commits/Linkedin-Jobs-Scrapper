export default function MissingContextCards({ items = [], onHelp }) {
  const missingItems = items.filter((item) => !item.isComplete);

  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="font-headline text-xl font-bold text-on-surface">
            What Runr still needs from you
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-on-surface-variant">
            Stronger tailoring comes from the extra proof points your uploaded documents do not
            fully spell out yet.
          </p>
        </div>
      </div>

      {missingItems.length ? (
        <div className="mt-5 grid gap-4 xl:grid-cols-2">
          {missingItems.map((item) => (
            <article
              className="rounded-2xl border border-outline-variant/15 bg-surface p-5"
              key={item.id}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="font-semibold text-on-surface">{item.title}</div>
                <span className="rounded-full bg-surface-container-low px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-on-surface-variant">
                  {item.targetLabel}
                </span>
              </div>
              <p className="mt-3 text-sm leading-6 text-on-surface-variant">{item.why}</p>
              <button
                className="mt-4 inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90"
                onClick={() => onHelp(item)}
                type="button"
              >
                Help me fill this
                <span className="material-symbols-outlined text-[16px]">chat</span>
              </button>
            </article>
          ))}
        </div>
      ) : (
        <div className="mt-5 rounded-2xl border border-primary/20 bg-primary/10 p-5">
          <div className="font-semibold text-on-surface">Your high-impact context is in good shape.</div>
          <p className="mt-2 text-sm leading-6 text-on-surface-variant">
            Documents, achievements, metrics, stakeholder examples, and motivation notes are all
            present. Save this builder and use full personalization where it fits.
          </p>
        </div>
      )}
    </section>
  );
}

