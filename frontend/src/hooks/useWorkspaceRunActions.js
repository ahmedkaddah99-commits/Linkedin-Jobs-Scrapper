import { useCallback } from "react";
import { getApiErrorDetails, getApiErrorMessage } from "../lib/api";

const EMPTY_ACTION_STATE = {
  workspaceId: "",
  loading: false,
  message: "",
  error: "",
  details: [],
};

function buildSourceValidationPayload({ flowId, sourceIds, settings, workspaceId = "" }) {
  return {
    flow_id: flowId,
    source_ids: [...(sourceIds || [])],
    settings: { ...(settings || {}) },
    ...(workspaceId ? { workspace_id: workspaceId } : {}),
  };
}

export function useWorkspaceRunActions({
  builderCatalog,
  navigate,
  refresh,
  request,
  resolveSourceName,
  setActionState,
  settingsWithDerivedLocationDefaults,
  workspaceAutomationFlow,
  workspaceCvAssetIds,
  workspaceCvAssetsLoaded,
  workspaceSourceIds,
  workspaces,
}) {
  const buildWorkspaceValidationPayload = useCallback(
    (workspace) => {
      const flowId = workspaceAutomationFlow(workspace);
      const sourceIds = workspaceSourceIds(workspace, builderCatalog, flowId);
      return buildSourceValidationPayload({
        flowId,
        sourceIds,
        settings: settingsWithDerivedLocationDefaults(workspace.settings || {}, sourceIds),
        workspaceId: workspace.id,
      });
    },
    [
      builderCatalog,
      settingsWithDerivedLocationDefaults,
      workspaceAutomationFlow,
      workspaceSourceIds,
    ],
  );

  const triggerRun = useCallback(
    async (workspaceId, runInputOverrides = {}, runMode = "normal") => {
      const workspace = workspaces.find((item) => item.id === workspaceId);
      if (!workspace) {
        setActionState({
          ...EMPTY_ACTION_STATE,
          workspaceId,
          error: "The selected workspace is no longer available.",
        });
        return;
      }
      if (
        workspaceCvAssetsLoaded &&
        workspace.settings?.workspace_cv_asset_id &&
        !workspaceCvAssetIds.has(String(workspace.settings.workspace_cv_asset_id))
      ) {
        setActionState({
          ...EMPTY_ACTION_STATE,
          workspaceId,
          error: "Run blocked because the selected workspace CV is no longer available.",
          details: ["Open this workspace and choose or upload a new baseline CV before starting another run."],
        });
        return;
      }
      setActionState({
        ...EMPTY_ACTION_STATE,
        workspaceId,
        loading: true,
        message: "Checking workspace setup before starting the run...",
      });
      try {
        const validationPayload = buildWorkspaceValidationPayload(workspace);
        const validation = await request("/workspace-builder/source-validation", {
          method: "POST",
          body: validationPayload,
        });
        if (!validation.valid) {
          const fieldErrorDetails = (validation.field_errors || [])
            .map((item) => item?.message)
            .filter(Boolean);
          setActionState({
            ...EMPTY_ACTION_STATE,
            workspaceId,
            error: "Run blocked until the workspace source setup is fixed.",
            details: [
              ...fieldErrorDetails,
              ...(validation.source_results || [])
                .filter((result) => result.status !== "valid")
                .flatMap((result) => {
                  const prefix = resolveSourceName(result.source_id);
                  const messages = [];
                  if (result.summary) {
                    messages.push(`${prefix}: ${result.summary}`);
                  }
                  if (Array.isArray(result.field_errors)) {
                    for (const item of result.field_errors) {
                      if (item?.message) {
                        messages.push(`${prefix}: ${item.message}`);
                      }
                    }
                  }
                  if (result.details?.length) {
                    messages.push(...result.details.map((detail) => `${prefix}: ${detail}`));
                  }
                  return messages.length ? messages : [`${prefix}: Fix this source before running.`];
                }),
            ],
          });
          return;
        }
        const preRunDetails = (validation.source_results || [])
          .filter((result) => result.runner_credit_estimate)
          .map((result) => {
            const estimate = result.runner_credit_estimate || {};
            const prefix = resolveSourceName(result.source_id);
            return (
              `${prefix}: estimated ${estimate.min_runner_credits ?? 0}-` +
              `${estimate.max_runner_credits ?? 0} runner credits ` +
              `(likely ${estimate.likely_runner_credits ?? 0}).`
            );
          });
        const companyPolicy = validation.company_site_policy || {};
        if (companyPolicy.company_sites_per_run) {
          preRunDetails.push(
            `Company-site plan limit: ${
              Number(companyPolicy.company_sites_per_run) === -1
                ? "Unlimited sites per run"
                : `${companyPolicy.company_sites_per_run} site(s) per run`
            }.`,
          );
        }
        setActionState({
          ...EMPTY_ACTION_STATE,
          workspaceId,
          loading: true,
          message: "Pre-run company-site estimate calculated. Starting the run...",
          details: preRunDetails,
        });
        const run = await request("/runs", {
          method: "POST",
          body: {
            workspace_id: workspaceId,
            execution_mode: "queued",
            max_attempts: 1,
            run_mode: runMode,
            run_input_overrides: runInputOverrides,
          },
        });
        const runLabel = runMode === "test" ? "Test run" : "Run";
        setActionState({
          ...EMPTY_ACTION_STATE,
          workspaceId,
          message: `${runLabel} ${run.id} added to the queue and will start automatically.`,
          details: preRunDetails,
        });
        navigate(`/runs/${encodeURIComponent(run.id)}`, {
          state: {
            runStartedMessage: `${runLabel} ${run.id} added to the queue and will start automatically.`,
          },
        });
        refresh().catch(() => undefined);
      } catch (runError) {
        setActionState({
          ...EMPTY_ACTION_STATE,
          workspaceId,
          error: getApiErrorMessage(runError, "Unable to start run."),
          details: getApiErrorDetails(runError),
        });
      }
    },
    [
      buildWorkspaceValidationPayload,
      navigate,
      refresh,
      request,
      resolveSourceName,
      setActionState,
      workspaceCvAssetIds,
      workspaceCvAssetsLoaded,
      workspaces,
    ],
  );

  const triggerTestRun = useCallback(
    async (workspaceId) => {
      const confirmed = window.confirm(
        "Start a test run? The workspace will use minimal scraping limits, keep one job that reaches document generation, create its documents, and keep it out of Tracker.",
      );
      if (!confirmed) {
        return;
      }
      await triggerRun(workspaceId, {}, "test");
    },
    [triggerRun],
  );

  return {
    buildWorkspaceValidationPayload,
    triggerRun,
    triggerTestRun,
  };
}
