import { Link } from "react-router-dom";

export default function AdvancedMemorySettings({
  advancedFields,
  guideTo,
  onChangeField,
  workspaceScopeTo,
}) {
  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h3 className="font-headline text-xl font-bold text-on-surface">Advanced memory settings</h3>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-on-surface-variant">
              Low-frequency fields live here so the default Build tab can stay focused on one useful
              question at a time.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              className="inline-flex items-center gap-2 rounded-xl bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
              to={workspaceScopeTo}
            >
              Workspace scope
              <span className="material-symbols-outlined text-[16px]">tune</span>
            </Link>
            <Link
              className="inline-flex items-center gap-2 rounded-xl bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
              to={guideTo}
            >
              Builder guide
              <span className="material-symbols-outlined text-[16px]">help</span>
            </Link>
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        {advancedFields.map((field) => (
          <section
            className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft"
            key={field.id}
          >
            <div className="text-sm font-semibold text-on-surface">{field.label}</div>
            <p className="mt-1 text-sm leading-6 text-on-surface-variant">{field.description}</p>
            <textarea
              className="mt-4 min-h-40 w-full rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
              onChange={(event) => onChangeField(field.id, event.target.value)}
              placeholder={field.placeholder}
              value={field.value}
            />
          </section>
        ))}
      </div>
    </div>
  );
}

