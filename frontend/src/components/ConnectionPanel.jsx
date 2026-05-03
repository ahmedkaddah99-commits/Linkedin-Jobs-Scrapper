import { useState } from "react";
import { useSession } from "../context/SessionContext";
import { resolveApiUrl } from "../lib/api";

export default function ConnectionPanel() {
  const { apiBaseUrl, accessToken, connect, status, error } = useSession();
  const [formState, setFormState] = useState({
    baseUrl: apiBaseUrl || "/v1",
    token: accessToken || "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [autoConnecting, setAutoConnecting] = useState(false);
  const [localError, setLocalError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setLocalError("");
    try {
      await connect({
        baseUrl: formState.baseUrl,
        token: formState.token,
      });
    } catch (submitError) {
      setLocalError(submitError.message || "Unable to connect.");
    } finally {
      setSubmitting(false);
    }
  }

  async function connectToLocalBackend() {
    setAutoConnecting(true);
    setLocalError("");
    try {
      const baseUrl = formState.baseUrl || "/v1";
      const response = await fetch(resolveApiUrl(baseUrl, "/dev/bootstrap-auth"));
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.error?.message || "Unable to prepare local connection.");
      }
      await connect({
        baseUrl: payload.api_base_url || baseUrl,
        token: payload.access_token,
      });
    } catch (connectError) {
      setLocalError(connectError.message || "Unable to connect to the local backend.");
    } finally {
      setAutoConnecting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
      <div className="mb-8">
        <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
          Connect Frontend To Backend
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-7 text-on-surface-variant">
          Connect to the local backend to load your saved workspaces, runs, reviews, documents, and
          settings.
        </p>
      </div>

      <div className="mb-6 rounded-xl border border-primary/20 bg-primary/10 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-bold text-on-surface">Using this app on your computer?</p>
            <p className="mt-1 text-xs leading-5 text-on-surface-variant">
              Use the local backend. No URL or token needs to be pasted.
            </p>
          </div>
          <button
            className="rounded-lg bg-primary px-5 py-3 text-sm font-bold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={autoConnecting || submitting}
            onClick={connectToLocalBackend}
            type="button"
          >
            {autoConnecting ? "Connecting..." : "Use local backend"}
          </button>
        </div>
      </div>

      <form className="space-y-6" onSubmit={handleSubmit}>
        <div>
          <label className="mb-2 block text-sm font-semibold text-on-surface">API Base URL</label>
          <input
            className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) =>
              setFormState((current) => ({ ...current, baseUrl: event.target.value }))
            }
            placeholder="/v1 or http://127.0.0.1:8000/v1"
            type="text"
            value={formState.baseUrl}
          />
        </div>

        <div>
          <label className="mb-2 block text-sm font-semibold text-on-surface">Bearer Token</label>
          <textarea
            className="min-h-32 w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) =>
              setFormState((current) => ({ ...current, token: event.target.value }))
            }
            placeholder="Paste the access token created by workspace_runner.py bootstrap-dev-auth"
            value={formState.token}
          />
        </div>

        {localError || error ? (
          <div className="rounded-lg border border-error/20 bg-error-container px-4 py-3 text-sm text-on-error-container">
            {localError || error}
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <button
            className="rounded-lg bg-gradient-to-br from-primary to-primary-container px-5 py-3 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={submitting}
            type="submit"
          >
            {submitting || status === "connecting" ? "Connecting..." : "Connect"}
          </button>
          <div className="text-sm text-on-surface-variant">
            Dev shortcut:
            {" "}
            <code className="rounded bg-surface-container-low px-2 py-1 text-xs">
              python workspace_runner.py bootstrap-dev-auth
            </code>
          </div>
        </div>
      </form>
    </div>
  );
}
