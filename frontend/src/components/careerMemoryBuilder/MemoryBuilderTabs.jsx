export default function MemoryBuilderTabs({
  activeTab,
  onChangeTab,
  onSave,
  saveState,
  tabs = [],
}) {
  return (
    <section className="rounded-2xl bg-surface-container-low p-2">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <button
              className={[
                "rounded-xl px-4 py-2.5 text-sm font-medium transition-colors",
                activeTab === tab.id
                  ? "bg-surface-container-lowest text-on-surface shadow-soft"
                  : "text-on-surface-variant hover:bg-surface-container-high",
              ].join(" ")}
              key={tab.id}
              onClick={() => onChangeTab(tab.id)}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>
        <button
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-surface-container-lowest px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-60"
          disabled={saveState.saving}
          onClick={onSave}
          type="button"
        >
          {saveState.saving ? "Saving..." : "Save changes"}
          <span className="material-symbols-outlined text-[16px]">save</span>
        </button>
      </div>
    </section>
  );
}

