import MemoryBuilderStatusBar from "./MemoryBuilderStatusBar";
import NextBestActions from "./NextBestActions";
import ReadinessSummary from "./ReadinessSummary";
import TailoringProgressPanel from "./TailoringProgressPanel";

export default function OverviewTab({
  baselineCvAssetId = "",
  boundWorkspaceId = "",
  boundWorkspaceName = "",
  nextBestActions = [],
  onContinueInterview,
  onStartAction,
  profileName = "Career Profile",
  profileStatus = "",
  readinessItems = [],
  statusBarItems = [],
  tailoringChecklist,
  workspaceBindingLabel = "",
  workspaceTo,
}) {
  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-primary">
              Career Profile
            </div>
            <h2 className="mt-3 font-headline text-2xl font-bold text-on-surface">
              {profileName}
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-7 text-on-surface-variant">
              Your evidence lifecycle workspace. Add sources, review evidence, build a timeline, and
              use your profile to tailor applications.
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <button
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-white transition-all hover:opacity-90"
              onClick={onContinueInterview}
              type="button"
            >
              Continue evidence builder
              <span className="material-symbols-outlined text-[18px]">fact_check</span>
            </button>
          </div>
        </div>

        {/* Identity and workspace binding */}
        <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <div className="rounded-2xl border border-outline-variant/15 bg-surface p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
              Workspace
            </div>
            <div className="mt-1 text-sm font-semibold text-on-surface">
              {workspaceBindingLabel || "Not bound"}
            </div>
            {workspaceTo ? (
              <a
                className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                href={workspaceTo}
              >
                <span className="material-symbols-outlined text-[14px]">workspaces</span>
                {boundWorkspaceName ? "View workspace" : "Bind workspace"}
              </a>
            ) : null}
          </div>
          <div className="rounded-2xl border border-outline-variant/15 bg-surface p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
              Baseline CV
            </div>
            <div className="mt-1 text-sm font-semibold text-on-surface">
              {baselineCvAssetId ? "Bound" : "Not bound"}
            </div>
          </div>
          <div className="rounded-2xl border border-outline-variant/15 bg-surface p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
              Status
            </div>
            <div className="mt-1 text-sm font-semibold text-on-surface">
              {profileStatus || "Not started"}
            </div>
          </div>
        </div>
      </section>

      <MemoryBuilderStatusBar items={statusBarItems} />
      <ReadinessSummary items={readinessItems} />

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <TailoringProgressPanel checklist={tailoringChecklist} />
        <NextBestActions items={nextBestActions} onStart={onStartAction} />
      </div>
    </div>
  );
}
