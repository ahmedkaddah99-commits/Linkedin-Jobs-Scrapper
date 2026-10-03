export default function NextBestActions({ items = [], onStart }) {
  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="font-headline text-lg font-bold text-on-surface">Quick actions</h3>
          <p className="mt-1 text-sm leading-6 text-on-surface-variant">
            Add career evidence one step at a time. Each prompt helps you capture a reusable achievement or story for your Career Profile.
          </p>
        </div>
      </div>
      <div className="mt-5 space-y-3">
        {items.map((item) => (
          <div
            className="flex flex-col gap-3 rounded-2xl border border-outline-variant/15 bg-surface p-4 lg:flex-row lg:items-center lg:justify-between"
            key={item.id}
          >
            <div>
              <div className="font-semibold text-on-surface">{item.label}</div>
              <div className="mt-1 text-sm leading-6 text-on-surface-variant">{item.reason}</div>
            </div>
            <div className="flex items-center gap-3">
              <div className="text-sm font-medium text-on-surface-variant">{item.progress}</div>
              <button
                className="rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90"
                onClick={() => onStart(item.questionSetType)}
                type="button"
              >
                Start
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
