import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import {
  ASSISTED_APPLY_BOUNDARIES,
  ASSISTED_APPLY_CAPABILITIES,
  DEFAULT_ASSISTED_APPLY_PREFERENCES,
  assistedApplyConnectionPath,
  assistedApplyConnectionRequestActionPath,
  buildAssistedApplyPreferencesPayload,
  normalizeAssistedApplyConnectionPayload,
  normalizeBackendCompletionUrl,
  parseAssistedApplyConnectionSearch,
} from "../lib/assistedApplyConnection";

function StatusBadge({ state }) {
  const labels = {
    connected: "Connected",
    disconnected: "Not connected",
    expired: "Request expired",
    not_found: "Request unavailable",
    pending: "Connection requested",
    rejected: "Request rejected",
    revoked: "Request revoked",
  };
  const connected = state === "connected";
  const pending = state === "pending";
  return (
    <span
      className={[
        "inline-flex rounded-full px-3 py-1 text-xs font-bold uppercase tracking-[0.14em]",
        connected
          ? "bg-primary/10 text-primary"
          : pending
            ? "bg-amber-500/10 text-amber-700"
            : "bg-surface-container-high text-on-surface-variant",
      ].join(" ")}
    >
      {labels[state] || "Not connected"}
    </span>
  );
}

function InformationList({ items, icon }) {
  return (
    <ul className="mt-4 space-y-3">
      {items.map((item) => (
        <li className="flex items-start gap-3 text-sm leading-6 text-on-surface-variant" key={item}>
          <span className="material-symbols-outlined mt-0.5 text-[18px] text-primary" aria-hidden="true">
            {icon}
          </span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function PreferencesForm({ disabled, onChange, preferences }) {
  function updatePreference(key, checked) {
    onChange({
      ...preferences,
      [key]: checked,
      require_legal_answer_confirmation: true,
    });
  }

  return (
    <div className="space-y-3">
      <label className="flex gap-3 rounded-2xl border border-outline-variant/20 bg-surface p-4">
        <input
          checked={preferences.permit_sensitive_autofill}
          className="mt-1 h-4 w-4 accent-primary"
          disabled={disabled}
          onChange={(event) => updatePreference("permit_sensitive_autofill", event.target.checked)}
          type="checkbox"
        />
        <span>
          <span className="block text-sm font-semibold text-on-surface">Allow sensitive-data autofill</span>
          <span className="mt-1 block text-xs leading-5 text-on-surface-variant">
            Context-dependent personal answers may be proposed only when their scope and freshness match.
          </span>
        </span>
      </label>

      <label className="flex gap-3 rounded-2xl border border-outline-variant/20 bg-surface p-4">
        <input
          checked={preferences.permit_demographic_autofill}
          className="mt-1 h-4 w-4 accent-primary"
          disabled={disabled}
          onChange={(event) => updatePreference("permit_demographic_autofill", event.target.checked)}
          type="checkbox"
        />
        <span>
          <span className="block text-sm font-semibold text-on-surface">Allow demographic autofill</span>
          <span className="mt-1 block text-xs leading-5 text-on-surface-variant">
            Demographic answers remain manual unless you explicitly enable this preference.
          </span>
        </span>
      </label>

      <div className="flex gap-3 rounded-2xl border border-primary/20 bg-primary/5 p-4">
        <span className="material-symbols-outlined mt-0.5 text-[20px] text-primary" aria-hidden="true">
          lock
        </span>
        <span>
          <span className="block text-sm font-semibold text-on-surface">Legal confirmation is always required</span>
          <span className="mt-1 block text-xs leading-5 text-on-surface-variant">
            This safeguard is fixed and cannot be disabled.
          </span>
        </span>
      </div>
    </div>
  );
}

export default function AssistedApplyConnectionPage() {
  const { request } = useSession();
  const [searchParams] = useSearchParams();
  const parsedSearch = useMemo(
    () => parseAssistedApplyConnectionSearch(searchParams),
    [searchParams],
  );
  const requestId = parsedSearch.requestId;
  const [preferences, setPreferences] = useState(DEFAULT_ASSISTED_APPLY_PREFERENCES);
  const [busy, setBusy] = useState("");
  const [feedback, setFeedback] = useState({ message: "", error: "" });
  const {
    data,
    loading,
    error,
    refresh,
  } = useApiResource(
    () => request(assistedApplyConnectionPath(requestId)),
    [request, requestId],
    { backgroundRefresh: false },
  );
  const connection = useMemo(
    () => normalizeAssistedApplyConnectionPayload(data || {}, { requestId }),
    [data, requestId],
  );

  useEffect(() => {
    if (data) setPreferences(connection.preferences);
  }, [connection.preferences, data]);

  async function approveConnection() {
    if (!requestId || !connection.pending_request) return;
    setBusy("approve");
    setFeedback({ message: "", error: "" });
    try {
      const payload = await request(
        assistedApplyConnectionRequestActionPath(requestId, "approve"),
        {
          method: "POST",
          body: { preferences: buildAssistedApplyPreferencesPayload(preferences) },
        },
      );
      const completionUrl = normalizeBackendCompletionUrl(payload?.completion_url);
      if (!completionUrl) throw new Error("Runr did not return a secure extension completion URL.");
      window.location.replace(completionUrl);
    } catch (approveError) {
      setBusy("");
      setFeedback({
        message: "",
        error: approveError.message || "Unable to connect this extension.",
      });
    }
  }

  async function rejectConnection() {
    if (!requestId || !connection.pending_request) return;
    setBusy("reject");
    setFeedback({ message: "", error: "" });
    try {
      await request(assistedApplyConnectionRequestActionPath(requestId, "reject"), {
        method: "POST",
        body: {},
      });
      setFeedback({ message: "Connection request rejected.", error: "" });
      await refresh({ showLoading: false });
    } catch (rejectError) {
      setFeedback({
        message: "",
        error: rejectError.message || "Unable to reject this connection request.",
      });
    } finally {
      setBusy("");
    }
  }

  async function savePreferences() {
    setBusy("preferences");
    setFeedback({ message: "", error: "" });
    try {
      await request("/assisted-apply/preferences", {
        method: "PUT",
        body: buildAssistedApplyPreferencesPayload(preferences),
      });
      setFeedback({ message: "Assisted Apply preferences saved.", error: "" });
      await refresh({ showLoading: false });
    } catch (saveError) {
      setFeedback({
        message: "",
        error: saveError.message || "Unable to save Assisted Apply preferences.",
      });
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.24em] text-primary">Account connection</p>
          <h1 className="mt-3 font-headline text-[2rem] font-extrabold leading-tight tracking-tight text-on-surface">
            Assisted Apply connection
          </h1>
          <p className="mt-3 max-w-3xl text-sm leading-7 text-on-surface-variant">
            Review what the Runr extension can do and manage its privacy preferences.
          </p>
        </div>
        <Link
          className="inline-flex w-fit items-center gap-2 rounded-full border border-outline-variant/20 bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
          to="/settings"
        >
          <span className="material-symbols-outlined text-[18px]" aria-hidden="true">arrow_back</span>
          Account settings
        </Link>
      </header>

      {parsedSearch.invalidRequestId ? (
        <p className="rounded-2xl border border-error/20 bg-error/5 px-5 py-4 text-sm text-error" role="alert">
          This extension connection request is invalid. Return to the extension and start again.
        </p>
      ) : null}

      {loading && !data ? (
        <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-8 text-on-surface-variant">
          Loading extension connection...
        </div>
      ) : error && !data ? (
        <section className="rounded-2xl border border-error/20 bg-error/5 p-6">
          <p className="text-sm text-error">{error}</p>
          <button
            className="mt-4 rounded-lg bg-surface px-4 py-2 text-sm font-semibold text-primary"
            onClick={() => refresh().catch(() => undefined)}
            type="button"
          >
            Retry
          </button>
        </section>
      ) : (
        <>
          <section className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-primary/80">Connection status</p>
                <h2 className="mt-2 font-headline text-2xl font-bold text-on-surface">
                  {connection.state === "pending"
                    ? `Connect ${connection.pending_request?.client_label || "Runr browser extension"}`
                    : "Browser extension connection"}
                </h2>
              </div>
              <StatusBadge state={connection.state} />
            </div>

            {connection.state !== "pending" ? (
              <p className="mt-6 rounded-2xl border border-outline-variant/20 bg-surface p-5 text-sm leading-6 text-on-surface-variant">
                {connection.state === "connected"
                  ? "This connection request has already been authorized. Return to the extension to continue."
                  : connection.state === "expired"
                    ? "This connection request expired. Return to the extension and start again."
                    : connection.state === "rejected"
                      ? "This connection request was rejected. Return to the extension to start a new request."
                      : connection.state === "revoked"
                        ? "This connection is no longer active. Return to the extension to reconnect."
                        : "No connection request is open. Start the connection from the Runr extension."}
              </p>
            ) : null}
          </section>

          <div className="grid gap-6 xl:grid-cols-2">
            <section className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-primary/80">Capabilities</p>
              <h2 className="mt-2 font-headline text-xl font-bold text-on-surface">What the extension may do</h2>
              <InformationList icon="check_circle" items={ASSISTED_APPLY_CAPABILITIES} />
            </section>

            <section className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-primary/80">Review-first boundary</p>
              <h2 className="mt-2 font-headline text-xl font-bold text-on-surface">What remains yours to do</h2>
              <InformationList icon="shield" items={ASSISTED_APPLY_BOUNDARIES} />
            </section>
          </div>

          <section className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-primary/80">Privacy preferences</p>
            <h2 className="mt-2 font-headline text-xl font-bold text-on-surface">Optional autofill categories</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-on-surface-variant">
              Both optional categories start off. You can change them later without reconnecting the extension.
            </p>
            <div className="mt-5">
              <PreferencesForm
                disabled={Boolean(busy)}
                onChange={setPreferences}
                preferences={preferences}
              />
            </div>

            {feedback.message || feedback.error ? (
              <p
                className={[
                  "mt-5 rounded-2xl px-4 py-3 text-sm",
                  feedback.error ? "bg-error/5 text-error" : "bg-primary/5 text-primary",
                ].join(" ")}
                role={feedback.error ? "alert" : "status"}
              >
                {feedback.error || feedback.message}
              </p>
            ) : null}

            <div className="mt-6 flex flex-wrap gap-3">
              {connection.state === "pending" ? (
                <>
                  <button
                    className="rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={Boolean(busy)}
                    onClick={approveConnection}
                    type="button"
                  >
                    {busy === "approve" ? "Connecting..." : "Connect this extension"}
                  </button>
                  <button
                    className="rounded-lg border border-outline-variant/20 px-5 py-2.5 text-sm font-semibold text-on-surface-variant transition-colors hover:bg-surface-container-low disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={Boolean(busy)}
                    onClick={rejectConnection}
                    type="button"
                  >
                    {busy === "reject" ? "Rejecting..." : "Reject request"}
                  </button>
                </>
              ) : (
                <button
                  className="rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={Boolean(busy)}
                  onClick={savePreferences}
                  type="button"
                >
                  {busy === "preferences" ? "Saving..." : "Save preferences"}
                </button>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
