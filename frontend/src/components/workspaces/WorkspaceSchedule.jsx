import { useState } from "react";
import { Link } from "react-router-dom";
import { getApiErrorMessage } from "../../lib/api";
import {
  formatDateTime,
  scheduleIntervalLabel,
  workspaceRunSchedule,
} from "./workspaceFormatters";

export const EMPTY_SCHEDULE_EDITOR_STATE = {
  workspaceId: "",
  enabled: false,
  intervalDays: "7",
  saving: false,
  error: "",
};

export function useWorkspaceScheduleEditor({ request, refresh, setActionState }) {
  const [scheduleEditorState, setScheduleEditorState] = useState(EMPTY_SCHEDULE_EDITOR_STATE);

  function openScheduleEditor(workspace) {
    const schedule = workspaceRunSchedule(workspace);
    setScheduleEditorState({
      workspaceId: workspace.id,
      enabled: schedule.enabled,
      intervalDays: schedule.intervalDays ? String(schedule.intervalDays) : "7",
      saving: false,
      error: "",
    });
  }

  function closeScheduleEditor() {
    setScheduleEditorState(EMPTY_SCHEDULE_EDITOR_STATE);
  }

  async function saveWorkspaceSchedule(workspace) {
    const enabled = Boolean(scheduleEditorState.enabled);
    const parsedIntervalDays = Number.parseInt(scheduleEditorState.intervalDays, 10);
    if (enabled && (!Number.isInteger(parsedIntervalDays) || parsedIntervalDays < 1)) {
      setScheduleEditorState((current) => ({
        ...current,
        error: "Enter a whole number of days greater than 0.",
      }));
      return;
    }

    setScheduleEditorState((current) => ({
      ...current,
      saving: true,
      error: "",
    }));

    try {
      const updatedWorkspace = await request(`/workspaces/${workspace.id}/schedule`, {
        method: "PUT",
        body: {
          enabled,
          interval_days: enabled ? parsedIntervalDays : 0,
        },
      });
      const schedule = workspaceRunSchedule(updatedWorkspace);
      setActionState({
        workspaceId: workspace.id,
        loading: false,
        error: "",
        details: [],
        message: schedule.enabled
          ? `Recurring schedule saved. Next queued run: ${
              schedule.nextRunAt ? formatDateTime(schedule.nextRunAt) : "Pending"
            }`
          : "Recurring schedule turned off.",
      });
      setScheduleEditorState(EMPTY_SCHEDULE_EDITOR_STATE);
      await refresh();
    } catch (scheduleError) {
      setScheduleEditorState((current) => ({
        ...current,
        saving: false,
        error: getApiErrorMessage(scheduleError, "Unable to save recurring schedule."),
      }));
    }
  }

  return {
    scheduleEditorState,
    setScheduleEditorState,
    openScheduleEditor,
    closeScheduleEditor,
    saveWorkspaceSchedule,
  };
}

export function WorkspaceScheduleBadges({ workspace }) {
  const schedule = workspaceRunSchedule(workspace);
  return (
    <div className="mt-3 flex flex-wrap gap-2 text-xs">
      <span
        className={[
          "rounded-full px-3 py-1 font-medium",
          schedule.enabled
            ? "bg-primary/10 text-primary"
            : "bg-surface-container-low text-on-surface-variant",
        ].join(" ")}
      >
        {schedule.enabled ? scheduleIntervalLabel(schedule.intervalDays) : "Manual only"}
      </span>
      {schedule.enabled && schedule.nextRunAt ? (
        <span className="rounded-full bg-surface-container-low px-3 py-1 text-on-surface-variant">
          Next run {formatDateTime(schedule.nextRunAt)}
        </span>
      ) : null}
      {schedule.lastError ? (
        <span className="rounded-full bg-error/10 px-3 py-1 text-error">
          Scheduler issue saved on {formatDateTime(schedule.lastErrorAt)}
        </span>
      ) : null}
    </div>
  );
}

export function WorkspaceScheduleEditor({
  workspace,
  scheduleEditorState,
  setScheduleEditorState,
  closeScheduleEditor,
  saveWorkspaceSchedule,
}) {
  if (scheduleEditorState.workspaceId !== workspace.id) {
    return null;
  }

  return (
    <div className="rounded-xl border border-outline-variant/10 bg-surface p-4">
      <div className="grid gap-4 xl:grid-cols-[minmax(180px,0.55fr)_minmax(220px,0.75fr)_auto] xl:items-end">
        <label className="space-y-2">
          <span className="block text-sm font-semibold text-on-surface">Run mode</span>
          <select
            className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            disabled={scheduleEditorState.saving}
            onChange={(event) =>
              setScheduleEditorState((current) => ({
                ...current,
                enabled: event.target.value === "scheduled",
                error: "",
              }))
            }
            value={scheduleEditorState.enabled ? "scheduled" : "manual"}
          >
            <option value="manual">Manual only</option>
            <option value="scheduled">Every N days</option>
          </select>
        </label>

        <label className="space-y-2">
          <span className="block text-sm font-semibold text-on-surface">Interval</span>
          <div className="flex items-center gap-3">
            <input
              className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface disabled:cursor-not-allowed disabled:text-on-surface-variant"
              disabled={!scheduleEditorState.enabled || scheduleEditorState.saving}
              min="1"
              onChange={(event) =>
                setScheduleEditorState((current) => ({
                  ...current,
                  intervalDays: event.target.value,
                  error: "",
                }))
              }
              step="1"
              type="number"
              value={scheduleEditorState.intervalDays}
            />
            <span className="text-sm text-on-surface-variant">days</span>
          </div>
          <span className="block text-xs leading-6 text-on-surface-variant">
            Runr adds a queued run automatically when the interval elapses and a worker is polling.
          </span>
        </label>

        <div className="flex flex-wrap gap-2 xl:justify-end">
          <button
            className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            disabled={scheduleEditorState.saving}
            onClick={closeScheduleEditor}
            type="button"
          >
            Cancel
          </button>
          <button
            className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={scheduleEditorState.saving}
            onClick={() => saveWorkspaceSchedule(workspace)}
            type="button"
          >
            {scheduleEditorState.saving ? "Saving..." : "Save schedule"}
          </button>
        </div>
      </div>

      {scheduleEditorState.error ? (
        <p className="mt-3 text-sm text-error">{scheduleEditorState.error}</p>
      ) : null}
    </div>
  );
}

export function WorkspaceSchedulePanel({
  workspace,
  scheduleEditorState,
  setScheduleEditorState,
  openScheduleEditor,
  closeScheduleEditor,
  saveWorkspaceSchedule,
}) {
  const schedule = workspaceRunSchedule(workspace);
  const scheduleEditorOpen = scheduleEditorState.workspaceId === workspace.id;

  return (
    <div className="rounded-xl border border-outline-variant/10 bg-surface p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-on-surface">Recurring Run Schedule</h3>
          <p className="mt-1 text-xs leading-6 text-on-surface-variant">
            {schedule.enabled
              ? `This workspace will be added to the queue every ${schedule.intervalDays} day${
                  schedule.intervalDays === 1 ? "" : "s"
                }.`
              : "This workspace only runs when you start it manually."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span
            className={[
              "rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide",
              schedule.enabled
                ? "bg-primary/10 text-primary"
                : "bg-surface-container-low text-on-surface-variant",
            ].join(" ")}
          >
            {schedule.enabled ? scheduleIntervalLabel(schedule.intervalDays) : "Manual only"}
          </span>
          <button
            className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            onClick={() =>
              scheduleEditorOpen ? closeScheduleEditor() : openScheduleEditor(workspace)
            }
            type="button"
          >
            {scheduleEditorOpen ? "Close" : schedule.enabled ? "Edit schedule" : "Set schedule"}
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <div className="rounded-lg border border-outline-variant/10 bg-surface-container-lowest p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant">
            Next queued run
          </div>
          <div className="mt-1 text-sm text-on-surface">
            {schedule.enabled && schedule.nextRunAt
              ? formatDateTime(schedule.nextRunAt)
              : "Not scheduled"}
          </div>
        </div>
        <div className="rounded-lg border border-outline-variant/10 bg-surface-container-lowest p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant">
            Last queued
          </div>
          <div className="mt-1 text-sm text-on-surface">
            {schedule.lastEnqueuedAt ? formatDateTime(schedule.lastEnqueuedAt) : "Not queued yet"}
          </div>
        </div>
        <div className="rounded-lg border border-outline-variant/10 bg-surface-container-lowest p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant">
            Last scheduled run
          </div>
          <div className="mt-1 text-sm text-on-surface">
            {schedule.lastRunId ? (
              <Link className="text-primary hover:underline" to={`/runs/${schedule.lastRunId}`}>
                Open run
              </Link>
            ) : (
              "No scheduled runs yet"
            )}
          </div>
        </div>
      </div>

      {schedule.lastError ? (
        <div className="mt-4 rounded-lg border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">
          Last scheduler issue: {schedule.lastError}
        </div>
      ) : null}

      {scheduleEditorOpen ? (
        <div className="mt-4">
          <WorkspaceScheduleEditor
            closeScheduleEditor={closeScheduleEditor}
            saveWorkspaceSchedule={saveWorkspaceSchedule}
            scheduleEditorState={scheduleEditorState}
            setScheduleEditorState={setScheduleEditorState}
            workspace={workspace}
          />
        </div>
      ) : null}
    </div>
  );
}
