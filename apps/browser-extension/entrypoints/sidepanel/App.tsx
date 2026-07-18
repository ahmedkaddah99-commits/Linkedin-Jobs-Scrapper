import { useCallback, useEffect, useState } from "react";
import type {
  AssistedApplyTabState,
  ExtensionConnectionState,
  PanelRequest,
} from "@runr/extension-messages";
import { isPanelResponse } from "@runr/extension-messages";
import { browser } from "wxt/browser";

async function send(message: PanelRequest) {
  const response: unknown = await browser.runtime.sendMessage(message);
  if (!isPanelResponse(response) || !response.ok) {
    const error = isPanelResponse(response) ? response.error : undefined;
    throw new Error(error || "Runr could not complete the extension request.");
  }
  return response;
}

async function requestTab(message: PanelRequest): Promise<AssistedApplyTabState> {
  const response = await send(message);
  if (!response.state) throw new Error("Runr could not read the active application tab.");
  return response.state;
}

async function requestConnection(message: PanelRequest): Promise<ExtensionConnectionState> {
  const response = await send(message);
  if (!response.connection) throw new Error("Runr returned an invalid connection state.");
  return response.connection;
}

function atsLabel(ats: AssistedApplyTabState["ats"]): string {
  if (ats === "greenhouse") return "Greenhouse";
  if (ats === "lever") return "Lever";
  return "Unsupported page";
}

export default function App() {
  const testingFixtureBuild = import.meta.env.MODE === "testing";
  const [state, setState] = useState<AssistedApplyTabState | null>(null);
  const [connection, setConnection] = useState<ExtensionConnectionState | null>(null);
  const [error, setError] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [connectionBusy, setConnectionBusy] = useState(false);

  const load = useCallback(async (refresh = false) => {
    setBusy(true);
    setError("");
    try {
      setState(
        await requestTab({ type: refresh ? "REFRESH_ACTIVE_TAB_STATE" : "GET_ACTIVE_TAB_STATE" }),
      );
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load(false);
    setConnectionBusy(true);
    void requestConnection({ type: "GET_EXTENSION_CONNECTION" })
      .then(setConnection)
      .catch((nextError: unknown) => {
        setConnectionError(nextError instanceof Error ? nextError.message : String(nextError));
      })
      .finally(() => setConnectionBusy(false));
  }, [load]);

  async function updateConnection(message: PanelRequest): Promise<void> {
    setConnectionBusy(true);
    setConnectionError("");
    try {
      setConnection(await requestConnection(message));
    } catch (nextError) {
      setConnectionError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setConnectionBusy(false);
    }
  }

  async function savePreferences(
    permitSensitiveAutofill: boolean,
    permitDemographicAutofill: boolean,
  ): Promise<void> {
    await updateConnection({
      type: "UPDATE_ASSISTED_APPLY_PREFERENCES",
      permitSensitiveAutofill,
      permitDemographicAutofill,
    });
  }

  async function runFixture(): Promise<void> {
    setBusy(true);
    setError("");
    try {
      setState(await requestTab({ type: "RUN_GREENHOUSE_FIXTURE_PROOF" }));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="panel-shell">
      <header className="panel-header">
        <div className="runr-mark" aria-hidden="true">R</div>
        <div>
          <p className="eyebrow">Runr</p>
          <h1>Assisted Apply</h1>
        </div>
      </header>

      <section className="boundary" aria-label="Submission boundary">
        <strong>Review-first by design</strong>
        <p>Runr may fill supported fields. You review the form and submit it yourself.</p>
      </section>

      <section className="connection-card" aria-busy={connectionBusy}>
        <div className="status-heading">
          <div>
            <p className="eyebrow">Runr account</p>
            <h2>
              {connection?.status === "connected"
                ? connection.session?.displayName || connection.session?.email || "Connected"
                : "Connect Assisted Apply"}
            </h2>
          </div>
          <span
            className={`status-chip connection-${connection?.status || "loading"}`}
            data-testid="connection-status"
          >
            {connection?.status || "loading"}
          </span>
        </div>

        <div className="capability-disclosure">
          <p>When connected, Runr can:</p>
          <ul>
            <li>Use the reviewed profile answers and documents in your Runr account.</li>
            <li>Fill supported fields only after you launch an application from Runr.</li>
            <li>Show uncertain, sensitive, and missing answers for your review.</li>
          </ul>
          <p>
            Runr cannot submit the form, solve CAPTCHA, sign declarations, accept legal terms,
            or complete assessments.
          </p>
        </div>

        {connectionError ? <p className="error" role="alert">{connectionError}</p> : null}
        {connection?.warning ? <p className="warning" role="status">{connection.warning}</p> : null}

        {connection?.status === "connected" ? (
          <>
            {connection.session?.email && connection.session.displayName ? (
              <p className="account-detail">{connection.session.email}</p>
            ) : null}
            <fieldset className="preference-list" disabled={connectionBusy}>
              <legend>Optional sensitive-data preferences</legend>
              <label>
                <input
                  type="checkbox"
                  checked={connection.preferences.permitSensitiveAutofill}
                  onChange={(event) =>
                    void savePreferences(
                      event.currentTarget.checked,
                      connection.preferences.permitDemographicAutofill,
                    )
                  }
                />
                <span>
                  <strong>Permit sensitive-answer autofill</strong>
                  <small>Runr still applies context, scope, and review policy.</small>
                </span>
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={connection.preferences.permitDemographicAutofill}
                  onChange={(event) =>
                    void savePreferences(
                      connection.preferences.permitSensitiveAutofill,
                      event.currentTarget.checked,
                    )
                  }
                />
                <span>
                  <strong>Permit demographic-answer autofill</strong>
                  <small>Off by default and applied only when explicitly enabled.</small>
                </span>
              </label>
              <p className="locked-policy">Legal answers always require your confirmation.</p>
            </fieldset>
            <button
              className="secondary danger"
              type="button"
              onClick={() => void updateConnection({ type: "DISCONNECT_RUNR" })}
              disabled={connectionBusy}
              data-testid="disconnect-runr"
            >
              {connectionBusy ? "Disconnecting…" : "Disconnect from Runr"}
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => void updateConnection({ type: "CONNECT_RUNR" })}
            disabled={connectionBusy}
            data-testid="connect-runr"
          >
            {connectionBusy ? "Connecting…" : "Connect to Runr"}
          </button>
        )}
      </section>

      {error ? <p className="error" role="alert">{error}</p> : null}

      <section className="status-card" aria-busy={busy}>
        <div className="status-heading">
          <div>
            <p className="eyebrow">Current page</p>
            <h2 data-testid="ats-name">{state ? atsLabel(state.ats) : "Inspecting…"}</h2>
          </div>
          <span className={`status-chip status-${state?.status || "loading"}`}>
            {state?.status.replaceAll("_", " ") || "loading"}
          </span>
        </div>

        {testingFixtureBuild && state?.fixtureAvailable ? (
          <div className="fixture-proof">
            <p>
              Local AA-01 fixture found. This proof uses the non-production value
              <code>candidate@example.com</code>.
            </p>
            <button
              type="button"
              onClick={() => void runFixture()}
              disabled={busy}
              data-testid="run-fixture"
            >
              {busy ? "Checking…" : "Fill and verify fixture email"}
            </button>
          </div>
        ) : (
          <p className="muted">
            {state?.ats
              ? "Portal recognized. Real package-backed filling arrives in a later ticket."
              : "Open a supported application page, then refresh this panel."}
          </p>
        )}

        <button
          className="secondary"
          type="button"
          onClick={() => void load(true)}
          disabled={busy}
        >
          Refresh page status
        </button>
      </section>

      {state?.execution ? (
        <section className="result-card" data-testid="execution-result">
          <p className="eyebrow">Verified field result</p>
          <h2>{state.execution.fieldLabel}</h2>
          <dl>
            <div><dt>Status</dt><dd data-testid="execution-status">{state.execution.status}</dd></div>
            <div><dt>Accepted value</dt><dd>{state.execution.acceptedValue || "None"}</dd></div>
            <div><dt>Source</dt><dd>Local verified fixture package</dd></div>
          </dl>
        </section>
      ) : null}

      {state?.manualReasons.length ? (
        <section className="manual-card">
          <p className="eyebrow">Manual-only controls observed</p>
          <ul>
            {state.manualReasons.map((reason) => (
              <li key={reason}>{reason.replaceAll("_", " ")}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <footer>
        No CAPTCHA solving, declarations, assessments, signatures, terms acceptance,
        or final submission capability exists in this build.
      </footer>
    </main>
  );
}
