export default function TailoringProgressPanel({ checklist }) {
  const ready = checklist.readyForTailoring;

  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
      <div>
        <h3 className="font-headline text-lg font-bold text-on-surface">Tailoring readiness</h3>
        <p className="mt-2 text-sm leading-6 text-on-surface-variant">{checklist.summary}</p>
      </div>
      <div className="mt-4 rounded-2xl border border-outline-variant/15 bg-surface p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="text-sm font-semibold text-on-surface">State</div>
          <div
            className={[
              "rounded-full px-3 py-1 text-sm font-semibold",
              ready
                ? "bg-primary/15 text-primary"
                : "bg-amber-500/10 text-amber-200 dark:text-amber-100",
            ].join(" ")}
          >
            {checklist.level}
          </div>
        </div>
      </div>
      <div className="mt-4 space-y-3">
        {checklist.items.map((item) => (
          <div
            className="flex items-center justify-between gap-3 rounded-2xl border border-outline-variant/15 bg-surface px-4 py-3"
            key={item.id}
          >
            <div className="text-sm text-on-surface">{item.label}</div>
            <div className="text-sm font-medium text-on-surface-variant">{item.progressLabel}</div>
          </div>
        ))}
      </div>
    </section>
  );
}