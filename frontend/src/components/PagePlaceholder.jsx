import { placeholderCards } from "../data/mockData";

export default function PagePlaceholder({ title, subtitle }) {
  const cards = placeholderCards[title] || [];

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-2">
        <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
          {title}
        </h1>
        <p className="text-sm text-on-surface-variant">{subtitle}</p>
      </header>

      <div className="grid gap-6 md:grid-cols-3">
        {cards.map((card) => (
          <section
            key={card.label}
            className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft"
          >
            <p className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
              {card.label}
            </p>
            <p className="mt-3 font-headline text-4xl font-extrabold tracking-tight text-on-surface">
              {card.value}
            </p>
          </section>
        ))}
      </div>

      <section className="rounded-xl border border-dashed border-outline-variant bg-surface-container-low p-10 text-center">
        <h2 className="font-headline text-2xl font-bold text-on-surface">{title} screen stub</h2>
        <p className="mx-auto mt-3 max-w-2xl text-sm leading-7 text-on-surface-variant">
          The routed React shell is ready. This page can now be replaced with the next Figma
          screen or wired to the real backend API once the design is finalized.
        </p>
      </section>
    </div>
  );
}
