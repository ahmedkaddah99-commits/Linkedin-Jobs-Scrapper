import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { getApiErrorDetails, getApiErrorMessage } from "../lib/api";

function parseDelimitedList(value) {
  const rawValues = Array.isArray(value) ? value : [value];
  const tokens = [];
  const seen = new Set();
  for (const rawValue of rawValues) {
    for (const item of String(rawValue || "").split(/[\r\n,]+/)) {
      const normalized = item.trim();
      if (!normalized) continue;
      const dedupeKey = normalized.toLowerCase();
      if (seen.has(dedupeKey)) continue;
      tokens.push(normalized);
      seen.add(dedupeKey);
      if (tokens.length >= 50) {
        return tokens;
      }
    }
  }
  return tokens;
}

function workspaceAutomationFlow(workspace) {
  return String(
    workspace?.automation_flow ||
      workspace?.metadata?.automation_flow ||
      workspace?.settings?.automation_flow ||
      "",
  ).trim();
}

function formatInvalidEntry(entry) {
  const url = String(entry?.url || "").trim();
  const lineNumber = Number(entry?.line_number || 0);
  const reason = String(entry?.error || entry?.stage || "invalid_entry")
    .replace(/_/g, " ")
    .trim();
  const prefix = lineNumber > 0 ? `Line ${lineNumber}` : "Entry";
  return [prefix, url, reason].filter(Boolean).join(" | ");
}

function TogglePill({ checked, label, onClick }) {
  return (
    <button
      className={[
        "rounded-full border px-3 py-1.5 text-sm font-medium transition-colors",
        checked
          ? "border-primary/30 bg-primary/10 text-primary"
          : "border-outline-variant/20 bg-surface-container-low text-on-surface-variant hover:bg-surface-container-high",
      ].join(" ")}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  );
}

function TokenListInput({ value, onChange, placeholder }) {
  const tokens = useMemo(() => parseDelimitedList(value), [value]);
  const [draft, setDraft] = useState("");

  function commit(rawValue) {
    onChange(parseDelimitedList([tokens, rawValue]));
    setDraft("");
  }

  return (
    <div className="space-y-2">
      <div className="rounded-xl border border-outline-variant/20 bg-surface px-3 py-3">
        <div className="flex flex-wrap gap-2">
          {tokens.map((token) => (
            <span
              className="inline-flex items-center gap-2 rounded-full bg-surface-container-low px-3 py-1.5 text-sm text-on-surface"
              key={token}
            >
              <span>{token}</span>
              <button
                aria-label={`Remove ${token}`}
                className="text-on-surface-variant transition-colors hover:text-error"
                onClick={() => onChange(tokens.filter((item) => item !== token))}
                type="button"
              >
                x
              </button>
            </span>
          ))}
          {tokens.length < 50 ? (
            <input
              className="min-w-[18rem] flex-1 bg-transparent py-1 text-sm text-on-surface outline-none placeholder:text-on-surface-variant"
              onBlur={() => {
                if (draft.trim()) {
                  commit(draft);
                }
              }}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === ",") {
                  event.preventDefault();
                  if (draft.trim()) {
                    commit(draft);
                  }
                }
              }}
              onPaste={(event) => {
                const pastedText = event.clipboardData.getData("text");
                if (/[\r\n,]/.test(pastedText)) {
                  event.preventDefault();
                  commit(pastedText);
                }
              }}
              placeholder={placeholder}
              value={draft}
            />
          ) : null}
        </div>
      </div>
      <div className="flex items-center justify-between gap-3 text-xs text-on-surface-variant">
        <span>Separate each exact job URL with Enter or a comma.</span>
        <span>
          {tokens.length}/50
        </span>
      </div>
    </div>
  );
}

export default function QuickApplyPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { request } = useSession();
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [manualUrls, setManualUrls] = useState([]);
  const [executionMode, setExecutionMode] = useState("sync");
  const [submitState, setSubmitState] = useState({
    submitting: false,
    message: "",
    error: "",
    details: [],
    invalidEntries: [],
    acceptedUrlCount: 0,
    runId: "",
  });

  const {
    data: workspacesPayload,
    loading,
    error,
  } = useApiResource(() => request("/workspaces?limit=100"), [request]);
  const { data: settingsPayload } = useApiResource(() => request("/settings"), [request]);

  const eligibleWorkspaces = useMemo(
    () =>
      (workspacesPayload?.workspaces || []).filter(
        (workspace) => workspaceAutomationFlow(workspace) === "tailored_documents",
      ),
    [workspacesPayload?.workspaces],
  );
  const selectedWorkspace = useMemo(
    () => eligibleWorkspaces.find((workspace) => workspace.id === selectedWorkspaceId) || null,
    [eligibleWorkspaces, selectedWorkspaceId],
  );

  useEffect(() => {
    if (selectedWorkspaceId || !eligibleWorkspaces.length) {
      return;
    }
    const requestedWorkspaceId = searchParams.get("workspace_id") || "";
    const defaultWorkspaceId = settingsPayload?.defaults?.default_workspace_id || "";
    const preferredWorkspaceId = [requestedWorkspaceId, defaultWorkspaceId].find((workspaceId) =>
      eligibleWorkspaces.some((workspace) => workspace.id === workspaceId),
    );
    setSelectedWorkspaceId(preferredWorkspaceId || eligibleWorkspaces[0].id);
  }, [eligibleWorkspaces, searchParams, selectedWorkspaceId, settingsPayload?.defaults?.default_workspace_id]);

  useEffect(() => {
    const defaultExecutionMode = String(settingsPayload?.defaults?.default_execution_mode || "").trim();
    if (defaultExecutionMode === "queued" || defaultExecutionMode === "sync") {
      setExecutionMode(defaultExecutionMode);
    }
  }, [settingsPayload?.defaults?.default_execution_mode]);

  function resetSubmitFeedback() {
    setSubmitState((current) => {
      if (
        !current.message &&
        !current.error &&
        !current.details.length &&
        !current.invalidEntries.length &&
        !current.runId
      ) {
        return current;
      }
      return {
        ...current,
        message: "",
        error: "",
        details: [],
        invalidEntries: [],
        acceptedUrlCount: 0,
        runId: "",
      };
    });
  }

  async function submitQuickApply() {
    if (!selectedWorkspaceId || !manualUrls.length) {
      return;
    }
    setSubmitState({
      submitting: true,
      message: "",
      error: "",
      details: [],
      invalidEntries: [],
      acceptedUrlCount: 0,
      runId: "",
    });
    try {
      const payload = await request("/quick-apply/runs", {
        method: "POST",
        body: {
          workspace_id: selectedWorkspaceId,
          execution_mode: executionMode,
          manual_urls: manualUrls,
        },
      });
      const run = payload.run || {};
      const invalidEntries = payload.invalid_entries || [];
      const acceptedUrlCount = Number(payload.accepted_url_count || run.metadata?.accepted_url_count || 0);
      setSubmitState({
        submitting: false,
        message:
          executionMode === "sync"
            ? `Quick application ${run.id} finished with status ${run.status}. Accepted ${acceptedUrlCount} exact job URL${acceptedUrlCount === 1 ? "" : "s"}.`
            : `Queued quick application ${run.id}. Accepted ${acceptedUrlCount} exact job URL${acceptedUrlCount === 1 ? "" : "s"}.`,
        error: "",
        details: [],
        invalidEntries,
        acceptedUrlCount,
        runId: run.id || "",
      });
      if (executionMode === "sync" && run.id && !invalidEntries.length) {
        navigate(`/runs/${run.id}`);
      }
    } catch (submitError) {
      setSubmitState({
        submitting: false,
        message: "",
        error: getApiErrorMessage(submitError, "Unable to start the quick application."),
        details: getApiErrorDetails(submitError),
        invalidEntries: [],
        acceptedUrlCount: 0,
        runId: "",
      });
    }
  }

  if (loading) {
    return (
      <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 text-on-surface-variant shadow-soft">
        Loading quick-apply options...
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        <p className="text-error">{error}</p>
      </div>
    );
  }

  if (!eligibleWorkspaces.length) {
    return (
      <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
        <h1 className="font-headline text-2xl font-bold text-on-surface">Quick Apply</h1>
        <p className="mt-3 max-w-2xl text-sm leading-7 text-on-surface-variant">
          Quick Apply needs one tailored-documents workspace first so the app knows which CV baseline and document defaults to use.
        </p>
        <Link
          className="mt-5 inline-flex rounded bg-gradient-to-br from-primary to-primary-container px-5 py-3 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90"
          to="/workspaces"
        >
          Create a Workspace
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
          Quick Apply
        </h1>
        <p className="max-w-3xl text-sm leading-7 text-on-surface-variant">
          Use this when you already found an exact job posting link yourself. Pick the workspace that should provide the baseline CV and document defaults, then paste the job URL and generate the application package.
        </p>
        <p className="text-xs uppercase tracking-wider text-on-surface-variant/80">
          Exact job links only. This page does not crawl company sites and does not generate motivation letters.
        </p>
      </header>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
        <div className="space-y-6 rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
          <label className="space-y-2">
            <span className="block text-sm font-semibold text-on-surface">Baseline Workspace</span>
            <select
              className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
              onChange={(event) => {
                resetSubmitFeedback();
                setSelectedWorkspaceId(event.target.value);
              }}
              value={selectedWorkspaceId}
            >
              {eligibleWorkspaces.map((workspace) => (
                <option key={workspace.id} value={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </select>
            <span className="block text-xs leading-6 text-on-surface-variant">
              This workspace supplies the CV baseline, targeting defaults, and document styling.
            </span>
          </label>

          <label className="space-y-2">
            <span className="block text-sm font-semibold text-on-surface">Exact Job URLs</span>
            <TokenListInput
              onChange={(nextManualUrls) => {
                resetSubmitFeedback();
                setManualUrls(nextManualUrls);
              }}
              placeholder="https://company.example/jobs/123"
              value={manualUrls}
            />
            <span className="block text-xs leading-6 text-on-surface-variant">
              Paste one or more exact job posting links. Up to 50 URLs.
            </span>
          </label>

          <div className="space-y-2">
            <span className="block text-sm font-semibold text-on-surface">Execution Mode</span>
            <div className="flex flex-wrap gap-3">
              <TogglePill
                checked={executionMode === "sync"}
                label="Run Now"
                onClick={() => {
                  resetSubmitFeedback();
                  setExecutionMode("sync");
                }}
              />
              <TogglePill
                checked={executionMode === "queued"}
                label="Queue Run"
                onClick={() => {
                  resetSubmitFeedback();
                  setExecutionMode("queued");
                }}
              />
            </div>
          </div>

          {submitState.error ? (
            <div className="rounded-lg bg-error-container px-4 py-3 text-sm text-on-error-container">
              <div>{submitState.error}</div>
              {submitState.details.length ? (
                <div className="mt-2 space-y-1 text-xs leading-6">
                  {submitState.details.map((detail) => (
                    <div key={detail}>{detail}</div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
          {submitState.message ? (
            <div className="rounded-lg bg-surface-container-low px-4 py-3 text-sm text-on-surface">
              <div>{submitState.message}</div>
              {submitState.runId && submitState.invalidEntries.length ? (
                <Link
                  className="mt-3 inline-flex rounded bg-surface px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                  to={`/runs/${submitState.runId}`}
                >
                  Open Run
                </Link>
              ) : null}
            </div>
          ) : null}
          {submitState.invalidEntries.length ? (
            <div className="rounded-lg border border-error/20 bg-error/5 px-4 py-3 text-sm text-on-surface">
              <div className="font-semibold text-on-surface">
                Ignored {submitState.invalidEntries.length} invalid URL entr{submitState.invalidEntries.length === 1 ? "y" : "ies"}
              </div>
              <div className="mt-2 space-y-1 text-xs leading-6 text-on-surface-variant">
                {submitState.invalidEntries.map((entry, index) => (
                  <div key={`${formatInvalidEntry(entry)}-${index}`}>{formatInvalidEntry(entry)}</div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="flex flex-wrap gap-3">
            <button
              className="rounded bg-gradient-to-br from-primary to-primary-container px-5 py-3 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={submitState.submitting || !selectedWorkspaceId || !manualUrls.length}
              onClick={submitQuickApply}
              type="button"
            >
              {submitState.submitting
                ? executionMode === "sync"
                  ? "Running..."
                  : "Queueing..."
                : executionMode === "sync"
                  ? "Create Quick Application"
                  : "Queue Quick Application"}
            </button>
            <Link
              className="rounded bg-surface-container-low px-5 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
              to="/workspaces"
            >
              Back to Workspaces
            </Link>
          </div>
        </div>

        <aside className="space-y-4 rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
          <div>
            <div className="text-sm font-semibold text-on-surface">Selected workspace</div>
            <div className="mt-1 text-lg font-bold text-on-surface">
              {selectedWorkspace?.name || "Choose a workspace"}
            </div>
            <p className="mt-2 text-sm leading-6 text-on-surface-variant">
              {selectedWorkspace?.description || "The selected workspace description will appear here."}
            </p>
          </div>

          <div className="rounded-lg border border-outline-variant/10 bg-surface p-4">
            <div className="text-sm font-semibold text-on-surface">What this does</div>
            <p className="mt-2 text-sm leading-6 text-on-surface-variant">
              The app ingests the exact job links you pasted, removes duplicates, and generates application documents using the baseline workspace you selected.
            </p>
          </div>

          <div className="rounded-lg border border-outline-variant/10 bg-surface p-4">
            <div className="text-sm font-semibold text-on-surface">What this does not do</div>
            <p className="mt-2 text-sm leading-6 text-on-surface-variant">
              It does not crawl company sites, it does not search job boards, and it does not create a motivation letter.
            </p>
          </div>
        </aside>
      </section>
    </div>
  );
}
