export default function MemoryBuilderStatusBar({ items = [] }) {
  return (
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <div
          className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-3 shadow-soft"
          key={item.id}
        >
          <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
            {item.label}
          </div>
          <div className="mt-1 text-sm font-semibold text-on-surface">{item.value}</div>
        </div>
      ))}
    </section>
  );
}

