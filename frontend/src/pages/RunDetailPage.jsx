import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { formatDateTime, labelize, statusTone } from "../lib/formatters";

function StageCard({ stage, isLast }) {
  const tone = stage.status === "failed" ? "warning" : stage.status === "completed" ? "success" : "primary";
  const icon = stage.status === "failed" ? "warning" : stage.status === "completed" ? "check_circle" : "hourglass_top";

  return (
    <div className="group relative flex rounded-lg p-4 transition-colors hover:bg-surface-container-low">
      {!isLast ? (
        <div className="absolute bottom-0 left-[39px] top-12 w-px bg-outline-variant/30" />
      ) : null}
      <div className="z-10 mr-6 flex flex-col items-center">
        <div
          className={[
            "flex h-12 w-12 items-center justify-center rounded-full border-4 border-surface-container-lowest",
            tone === "warning"
              ? "bg-[#FFF3E0] text-[#E65100]"
              : tone === "success"
                ? "bg-[#E5F5E0] text-[#2E7D32]"
                : "bg-surface-container-high text-primary",
          ].join(" ")}
        >
          <span className="material-symbols-outlined text-lg" style={{ fontVariationSettings: "'FILL' 1" }}>
            {icon}
          </span>
        </div>
      </div>

      <div className="flex-1 pb-6">
        <div className="mb-2 flex items-start justify-between">
          <div>
            <h4 className="font-headline text-base font-bold text-on-surface">{labelize(stage.stage_id)}</h4>
            <p className="mt-0.5 text-xs text-on-surface-variant">{labelize(stage.stage_type)}</p>
          </div>
          <div className="text-right">
            <span className="text-xs font-medium text-on-surface-variant">
              {formatDateTime(stage.started_at)}
            </span>
            <p className="mt-1 text-[10px] uppercase tracking-widest text-on-surface-variant/60">
              {labelize(stage.status)}
            </p>
          </div>
        </div>

        {stage.error ? (
          <div className="mt-2 flex items-start gap-2 rounded border border-[#FFE0B2] bg-[#FFF3E0]/50 p-2 text-xs text-[#E65100]">
            <span className="material-symbols-outlined text-[14px]">info</span>
            <span>{stage.error}</span>
          </div>
        ) : null}

        {Object.keys(stage.metrics || {}).length ? (
          <div className="mt-3 flex flex-wrap gap-4 rounded border border-outline-variant/10 bg-surface p-3">
            {Object.entries(stage.metrics || {}).map(([key, value]) => (
              <div key={key} className="flex flex-col">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-on-surface-variant/70">
                  {labelize(key)}
                </span>
                <span className="text-lg font-bold text-on-surface">{String(value)}</span>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default function RunDetailPage() {
  const navigate = useNavigate();
  const { runId } = useParams();
  const { request } = useSession();
  const [actionMessage, setActionMessage] = useState("");
  const [actionError, setActionError] = useState("");

  const { data: run, loading, error, refresh } = useApiResource(
    () => request(`/runs/${runId}`),
    [request, runId],
  );
  const { data: artifactsPayload } = useApiResource(
    () => request(`/runs/${runId}/artifacts`),
    [request, runId],
  );

  const artifacts = useMemo(
    () =>
      (artifactsPayload?.artifacts || []).map((artifact) => ({
        ...artifact,
        file_name: artifact.path?.split(/[\\/]/).pop() || artifact.artifact_id,
        download_url: `/runs/${runId}/artifacts/${artifact.artifact_id}/download`,
      })),
    [artifactsPayload?.artifacts, runId],
  );
  const stageResults = run?.stage_results || [];

  async function performAction(action) {
    setActionMessage("");
    setActionError("");
    try {
      let updatedRun = null;
      if (action === "retry") {
        updatedRun = await request(`/runs/${runId}/retry`, { method: "POST", body: {} });
      } else if (action === "resume") {
        updatedRun = await request(`/runs/${runId}/resume`, { method: "POST", body: {} });
      } else if (action === "cancel") {
        updatedRun = await request(`/runs/${runId}/cancel`, { method: "POST", body: {} });
      } else if (action === "queue_again" && run) {
        updatedRun = await request("/runs", {
          method: "POST",
          body: {
            workspace_id: run.workspace_id,
            execution_mode: "queued",
            max_attempts: run.max_attempts || 1,
            run_input_overrides: run.run_input_overrides || {},
          },
        });
      }
      setActionMessage(`${labelize(action)} requested for ${updatedRun?.id || runId}.`);
      refresh().catch(() => undefined);
    } catch (runActionError) {
      setActionError(runActionError.message || "Unable to update run.");
    }
  }

  async function downloadArtifact(artifact) {
    const blob = await request(artifact.download_url, { responseType: "blob" });
    const objectUrl = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = artifact.file_name;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(objectUrl);
  }

  function exportRunLogs() {
    if (!run) return;
    const blob = new Blob([JSON.stringify(run, null, 2)], { type: "application/json" });
    const objectUrl = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = `${run.id}_run_log.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(objectUrl);
  }

  const primaryAction =
    run?.status === "failed" || run?.status === "cancelled"
      ? { key: "retry", label: "Retry" }
      : run?.status === "planned"
        ? { key: "resume", label: "Resume" }
        : { key: "queue_again", label: "Queue Again" };

  return (
    <div className="space-y-8">
      <section className="relative overflow-hidden rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-[0px_12px_32px_rgba(11,28,48,0.02)]">
        <div className="pointer-events-none absolute -right-24 -top-24 h-48 w-48 rounded-full bg-primary-fixed-dim/20 blur-3xl" />
        <div className="relative z-10 flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-3">
              <h2 className="font-headline text-3xl font-extrabold tracking-tighter text-on-surface">
                {run?.id || runId}
              </h2>
              {run ? (
                <StatusBadge tone={statusTone(run.status)}>{labelize(run.status)}</StatusBadge>
              ) : null}
            </div>

            <div className="flex flex-wrap items-center gap-6 text-sm text-on-surface-variant">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-sm opacity-70">calendar_today</span>
                {run ? formatDateTime(run.created_at) : "Loading..."}
              </div>
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-sm opacity-70">timer</span>
                Attempts {run?.attempt_count ?? 0}/{run?.max_attempts ?? 1}
              </div>
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-sm opacity-70">account_circle</span>
                {run?.requested_by || "Unknown initiator"}
              </div>
            </div>

            {actionMessage || actionError ? (
              <div className={actionError ? "text-sm text-error" : "text-sm text-primary"}>
                {actionError || actionMessage}
              </div>
            ) : null}
          </div>

          <div className="flex w-full items-center gap-3 md:w-auto">
            <button
              className="flex flex-1 items-center justify-center gap-2 rounded bg-surface-container-high px-5 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-variant md:flex-none"
              onClick={exportRunLogs}
              type="button"
            >
              <span className="material-symbols-outlined text-sm">download</span>
              Export Logs
            </button>
            <button
              className="flex flex-1 items-center justify-center gap-2 rounded bg-gradient-to-br from-primary to-[#0d9488] px-5 py-2.5 text-sm font-medium text-white shadow-sm shadow-primary/20 transition-all hover:opacity-90 md:flex-none"
              onClick={() => performAction(primaryAction.key)}
              type="button"
            >
              <span className="material-symbols-outlined text-sm">restart_alt</span>
              {primaryAction.label}
            </button>
            <button
              className="flex flex-1 items-center justify-center gap-2 rounded bg-surface-container-high px-5 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-variant md:flex-none"
              onClick={() => performAction("cancel")}
              type="button"
            >
              <span className="material-symbols-outlined text-sm">stop_circle</span>
              Cancel
            </button>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <h3 className="px-1 font-headline text-xl font-bold tracking-tight text-on-surface">
            Execution Stages
          </h3>
          <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-2">
            {loading ? (
              <div className="p-6 text-on-surface-variant">Loading run detail...</div>
            ) : error ? (
              <div className="p-6 text-error">{error}</div>
            ) : stageResults.length ? (
              stageResults.map((stage, index) => (
                <StageCard
                  key={`${stage.stage_id}-${index}`}
                  isLast={index === stageResults.length - 1}
                  stage={stage}
                />
              ))
            ) : (
              <div className="p-6 text-on-surface-variant">
                No stage results exist for this run yet.
              </div>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <h3 className="px-1 font-headline text-xl font-bold tracking-tight text-on-surface">
            Artifacts Output
          </h3>
          <div className="overflow-hidden rounded-xl border border-outline-variant/20 bg-surface-container-lowest">
            {artifacts.length ? (
              artifacts.map((artifact, index) => (
                <div
                  key={artifact.artifact_id}
                  className={[
                    "group flex cursor-pointer items-center justify-between p-4 transition-colors hover:bg-surface-container-low",
                    index < artifacts.length - 1 ? "border-b border-outline-variant/10" : "",
                  ].join(" ")}
                >
                  <div className="flex items-center gap-3">
                    <div className="rounded bg-surface-variant p-2 text-primary">
                      <span className="material-symbols-outlined text-lg">description</span>
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-on-surface">{artifact.file_name}</p>
                      <p className="text-xs text-on-surface-variant">{labelize(artifact.artifact_type)}</p>
                    </div>
                  </div>
                  <button
                    className="p-1 text-on-surface-variant opacity-0 transition-all group-hover:opacity-100 hover:text-primary"
                    onClick={() => downloadArtifact(artifact)}
                    type="button"
                  >
                    <span className="material-symbols-outlined">download</span>
                  </button>
                </div>
              ))
            ) : (
              <div className="p-6 text-on-surface-variant">No artifacts generated for this run yet.</div>
            )}
          </div>

          <h3 className="mt-8 px-1 font-headline text-xl font-bold tracking-tight text-on-surface">
            Run Metadata
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-4">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
                Workspace
              </p>
              <p className="font-headline text-2xl font-bold text-on-surface">{run?.workspace_id || "N/A"}</p>
            </div>
            <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-4">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
                Job Sets
              </p>
              <p className="font-headline text-2xl font-bold text-on-surface">
                {run?.final_job_set_keys?.length ?? 0}
              </p>
            </div>
          </div>
          <button
            className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
            onClick={() => navigate("/runs")}
            type="button"
          >
            Back To Runs
          </button>
        </div>
      </div>
    </div>
  );
}
