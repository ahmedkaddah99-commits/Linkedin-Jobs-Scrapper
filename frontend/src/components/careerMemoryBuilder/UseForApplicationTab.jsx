export default function UseForApplicationTab({
  baselineCvAssetId = "",
  boundWorkspaceId = "",
  boundWorkspaceName = "",
  cards = [],
  onBindWorkspace,
  onManageDocuments,
  onReplaceBaselineCv,
  onToggleUseInCv,
  onToggleUseInLetter,
  onUnbindWorkspace,
  workspaceTo,
}) {
  const isBound = Boolean(boundWorkspaceId);
  const newBaselineCvLinked = Boolean(baselineCvAssetId);

  const cvMappedCards = (cards || []).filter((card) => card.useInCv);
  const letterMappedCards = (cards || []).filter((card) => card.useInLetter);

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        <h2 className="font-headline text-xl font-bold text-on-surface">Use for Application</h2>
        <p className="mt-1 text-sm leading-6 text-on-surface-variant">
          Connect your career profile to a workspace and map evidence to CV/letter usage so Runr can tailor applications.
        </p>
      </section>

      {/* Workspace binding */}
      <section className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
        <h3 className="font-headline text-lg font-bold text-on-surface">Workspace Binding</h3>
        <p className="mt-1 text-sm leading-6 text-on-surface-variant">
          Bind this profile to a workspace to enable CV tailoring, letters, answers, and interview preparation.
        </p>
        <div className="mt-4 space-y-3">
          <div className="rounded-xl border border-outline-variant/15 bg-surface p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-on-surface">Current binding</div>
                <div className="mt-0.5 text-xs text-on-surface-variant">
                  {isBound
                    ? `Bound to ${boundWorkspaceName || boundWorkspaceId}`
                    : "Not bound to any workspace"}
                </div>
              </div>
              <div className="flex gap-2">
                {isBound ? (
                  <>
                    <button
                      className="rounded-xl bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                      onClick={onBindWorkspace}
                      type="button"
                    >
                      Rebind
                    </button>
                    <button
                      className="rounded-xl bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-error-container hover:text-on-error-container"
                      onClick={onUnbindWorkspace}
                      type="button"
                    >
                      Unbind
                    </button>
                  </>
                ) : (
                  <button
                    className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90"
                    onClick={onBindWorkspace}
                    type="button"
                  >
                    Bind to workspace
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>


      {/* Baseline CV */}
      <section className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
        <h3 className="font-headline text-lg font-bold text-on-surface">Baseline CV</h3>
        <p className="mt-1 text-sm leading-6 text-on-surface-variant">
          Your baseline CV provides the foundation for tailored applications.
        </p>
        <div className="mt-4 rounded-xl border border-outline-variant/15 bg-surface p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-on-surface">Linked baseline CV</div>
              <div className="mt-0.5 text-xs text-on-surface-variant">
                {newBaselineCvLinked ? "Baseline CV is linked" : "No baseline CV linked"}
              </div>
            </div>
            <div className="flex gap-2">
              {onReplaceBaselineCv ? (
                <button
                  className="rounded-xl bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                  onClick={onReplaceBaselineCv}
                  type="button"
                >
                  Replace
                </button>
              ) : null}
              {onManageDocuments ? (
                <button
                  className="rounded-xl bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                  onClick={onManageDocuments}
                  type="button"
                >
                  Manage documents
                </button>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      {/* Evidence mapping */}
      <section className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
        <h3 className="font-headline text-lg font-bold text-on-surface">Evidence Mapping</h3>
        <p className="mt-1 text-sm leading-6 text-on-surface-variant">
          Map evidence items to CV bullets or cover letter angles to strengthen tailored applications.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-outline-variant/15 bg-surface p-4">
            <div className="text-sm font-semibold text-on-surface">CV Mapped</div>
            <div className="mt-2 font-headline text-2xl font-bold text-on-surface">
              {cvMappedCards.length}
            </div>
            <div className="mt-0.5 text-xs text-on-surface-variant">
              evidence items mapped to CV usage
            </div>
          </div>
          <div className="rounded-xl border border-outline-variant/15 bg-surface p-4">
            <div className="text-sm font-semibold text-on-surface">Letter Mapped</div>
            <div className="mt-2 font-headline text-2xl font-bold text-on-surface">
              {letterMappedCards.length}
            </div>
            <div className="mt-0.5 text-xs text-on-surface-variant">
              evidence items mapped to letter usage
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
