import MemoryCard from "./MemoryCard";
import MemoryCardFilters from "./MemoryCardFilters";

export default function MemoryBankTab({
  autoEditCardId = "",
  cards = [],
  filters = [],
  onAddManual,
  onCardDelete,
  onCardSave,
  onChangeFilter,
  onSearchChange,
  searchValue,
  selectedFilter,
}) {
  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h3 className="font-headline text-xl font-bold text-on-surface">Career Profile</h3>
            <p className="mt-1 text-sm leading-6 text-on-surface-variant">
              A private, reusable library of real career evidence — achievements,
              projects, metrics, and stories that go beyond your baseline CV. Runr
              never invents unsupported claims.
            </p>
          </div>
          <button
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            onClick={onAddManual}
            type="button"
          >
            Add evidence
            <span className="material-symbols-outlined text-[16px]">add</span>
          </button>
        </div>
        <div className="mt-5">
          <MemoryCardFilters
            activeFilter={selectedFilter}
            filters={filters}
            onChangeFilter={onChangeFilter}
            onSearchChange={onSearchChange}
            searchValue={searchValue}
          />
        </div>
      </section>

      {cards.length ? (
        <div className="space-y-4">
          {cards.map((card) => (
            <MemoryCard
              autoEdit={card.id === autoEditCardId}
              card={card}
              key={card.id}
              onDelete={onCardDelete}
              onSave={onCardSave}
            />
          ))}
        </div>
      ) : (
        <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
          <h3 className="font-headline text-xl font-bold text-on-surface">No evidence items yet.</h3>
          <p className="mt-2 text-sm leading-7 text-on-surface-variant">
            Start the guided interview to turn your experience into reusable application evidence.
          </p>
        </section>
      )}
    </div>
  );
}

