export default function TailoringProgressPanel({ checklist }) {
  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
      <div>
        <h3 className="font-headline text-lg font-bold text-on-surface">Tailoring readiness</h3>
        <p className="mt-2 text-sm leading-6 text-on-surface-variant">{checklist.summary}</p>
      </div>
      <div className="mt-4 rounded-2xl border border-outline-variant/15 bg-surface p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="text-sm font-semibold text-on-surface">Progress</div>
          <div className="text-sm font-semibold text-on-surface">
            {checklist.completedCount} / {checklist.totalCount} complete
          </div>
        </div>
        <div className="mt-3 h-2 rounded-full bg-surface-container-low">
          <div
            className="h-2 rounded-full bg-primary transition-all"
            style={{ width: `${(checklist.completedCount / checklist.totalCount) * 100}%` }}
          />
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

