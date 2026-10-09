export default function MemoryCardFilters({
  activeFilter,
  filters = [],
  onChangeFilter,
  onSearchChange,
  searchValue,
}) {
  return (
    <div className="space-y-4">
      <input
        className="w-full rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface"
        onChange={(event) => onSearchChange(event.target.value)}
        placeholder="Search memories, tags, bullets, or notes"
        type="text"
        value={searchValue}
      />
      <div className="flex flex-wrap gap-2">
        {filters.map((filter) => {
          const active = filter.id === activeFilter;
          return (
            <button
              className={[
                "rounded-full px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-primary text-white"
                  : "bg-surface-container-low text-on-surface hover:bg-surface-container-high",
              ].join(" ")}
              key={filter.id}
              onClick={() => onChangeFilter(filter.id)}
              type="button"
            >
              {filter.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

