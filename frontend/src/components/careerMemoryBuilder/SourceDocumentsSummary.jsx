export default function SourceDocumentsSummary({ summary }) {
  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
      <h3 className="font-headline text-lg font-bold text-on-surface">Source documents summary</h3>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-outline-variant/15 bg-surface p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
            Documents available
          </div>
          <div className="mt-1 text-sm font-semibold text-on-surface">{summary.documentsAvailable}</div>
        </div>
        <div className="rounded-2xl border border-outline-variant/15 bg-surface p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
            Selected for tailoring
          </div>
          <div className="mt-1 text-sm font-semibold text-on-surface">{summary.selectedForTailoring}</div>
        </div>
        <div className="rounded-2xl border border-outline-variant/15 bg-surface p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
            Master profile
          </div>
          <div className="mt-1 text-sm font-semibold text-on-surface">
            {summary.masterProfileLinked ? "Linked" : "Missing"}
          </div>
        </div>
      </div>
    </section>
  );
}

