function statusClasses(status) {
  if (status === "Ready for advanced tailoring") {
    return "bg-primary/15 text-primary";
  }
  if (status === "Basic") {
    return "bg-surface-container-low text-on-surface";
  }
  return "bg-amber-500/10 text-amber-200 dark:text-amber-100";
}

export default function ReadinessSummary({ items = [] }) {
  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="font-headline text-2xl font-bold text-on-surface">Readiness snapshot</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-on-surface-variant">
            Upload source files in the Asset Library, then use Career Memory Builder to add the
            achievements, context, and motivation your documents do not fully explain.
          </p>
        </div>
      </div>
      <div className="grid gap-4 xl:grid-cols-4">
        {items.map((item) => (
          <article
            className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft"
            key={item.title}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="text-sm font-semibold text-on-surface">{item.title}</div>
              <span
                className={[
                  "rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide",
                  statusClasses(item.status),
                ].join(" ")}
              >
                {item.status}
              </span>
            </div>
            <div className="mt-4 font-headline text-lg font-bold leading-tight text-on-surface">
              {item.value}
            </div>
            <p className="mt-3 text-sm leading-6 text-on-surface-variant">{item.description}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

