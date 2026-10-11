export default function MemoryTriggerChips({ activeTrigger, triggers = [], onSelectTrigger }) {
  return (
    <div className="flex flex-wrap gap-2">
      {triggers.map((trigger) => {
        const active = trigger.id === activeTrigger;
        return (
          <button
            className={[
              "rounded-full px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-primary text-white"
                : "bg-surface-container-low text-on-surface hover:bg-surface-container-high",
            ].join(" ")}
            key={trigger.id}
            onClick={() => onSelectTrigger(trigger.id)}
            type="button"
          >
            {trigger.label}
          </button>
        );
      })}
    </div>
  );
}

