import { useEffect, useState } from "react";
import { useTracker } from "../hooks/useTracker";

const COLUMNS = [
  {
    key: "applied",
    label: "Applied",
    icon: "send",
    accent: "text-primary",
    badge: "bg-primary/10 text-primary",
    border: "border-primary/30",
    glow: "shadow-primary/10",
  },
  {
    key: "email_confirmed",
    label: "Email Confirmed",
    icon: "mark_email_read",
    accent: "text-teal-500",
    badge: "bg-teal-500/10 text-teal-500",
    border: "border-teal-500/30",
    glow: "shadow-teal-500/10",
  },
  {
    key: "interview_invited",
    label: "Interview Invited",
    icon: "calendar_month",
    accent: "text-amber-500",
    badge: "bg-amber-500/10 text-amber-500",
    border: "border-amber-500/30",
    glow: "shadow-amber-500/10",
  },
  {
    key: "rejected",
    label: "Rejected",
    icon: "cancel",
    accent: "text-error",
    badge: "bg-error/10 text-error",
    border: "border-error/30",
    glow: "shadow-error/10",
  },
];

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

function StatusDropdown({ current, onSelect, disabled }) {
  const [open, setOpen] = useState(false);
  const currentCol = COLUMNS.find((c) => c.key === current) || COLUMNS[0];

  return (
    <div className="relative">
      <button
        className={[
          "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold transition-all",
          currentCol.badge,
          disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:opacity-80",
        ].join(" ")}
        disabled={disabled}
        onClick={() => !disabled && setOpen((v) => !v)}
        type="button"
      >
        <span className="material-symbols-outlined text-[14px]">{currentCol.icon}</span>
        {currentCol.label}
        <span className="material-symbols-outlined text-[12px]">expand_more</span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-full z-20 mt-1 w-52 overflow-hidden rounded-xl border border-outline-variant/20 bg-surface-container-lowest shadow-xl">
            {COLUMNS.map((col) => (
              <button
                className={[
                  "flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors hover:bg-surface-container-low",
                  col.key === current ? "font-semibold " + col.accent : "text-on-surface",
                ].join(" ")}
                key={col.key}
                onClick={() => {
                  setOpen(false);
                  if (col.key !== current) onSelect(col.key);
                }}
                type="button"
              >
                <span className={["material-symbols-outlined text-[16px]", col.accent].join(" ")}>
                  {col.icon}
                </span>
                {col.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function TrackerCard({ item, onUpdate, updating }) {
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState(item.rejection_note || "");
  const isBusy = updating === item.review_id;
  const isRejected = item.tracker_status === "rejected";

  async function handleStatusChange(newStatus) {
    await onUpdate(item.review_id, { tracker_status: newStatus });
    if (newStatus === "rejected") setNoteOpen(true);
  }

  async function handleEmailToggle() {
    await onUpdate(item.review_id, { email_confirmed: !item.email_confirmed });
  }

  async function saveNote() {
    await onUpdate(item.review_id, { rejection_note: note });
    setNoteOpen(false);
  }

  const col = COLUMNS.find((c) => c.key === item.tracker_status) || COLUMNS[0];

  return (
    <div
      className={[
        "group relative overflow-hidden rounded-2xl border bg-surface-container-lowest p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md",
        col.border,
        col.glow,
      ].join(" ")}
    >
      {/* Loading overlay */}
      {isBusy && (
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-2xl bg-surface-container-lowest/70 backdrop-blur-sm">
          <span className="material-symbols-outlined animate-spin text-2xl text-primary">
            progress_activity
          </span>
        </div>
      )}

      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-on-surface leading-tight">
            {item.title}
          </h3>
          <div className="mt-0.5 flex items-center gap-1.5 text-xs text-on-surface-variant">
            <span className="material-symbols-outlined text-[13px]">business</span>
            <span className="truncate">{item.company || "Unknown Company"}</span>
          </div>
        </div>
        <StatusDropdown
          current={item.tracker_status || "applied"}
          disabled={isBusy}
          onSelect={handleStatusChange}
        />
      </div>

      <div className="mb-3 flex flex-wrap gap-2 text-xs text-on-surface-variant">
        {item.workspace_name && (
          <span className="flex items-center gap-1">
            <span className="material-symbols-outlined text-[12px]">workspaces</span>
            {item.workspace_name}
          </span>
        )}
        {item.run_finished_at && (
          <span className="flex items-center gap-1">
            <span className="material-symbols-outlined text-[12px]">event</span>
            {formatDate(item.run_finished_at)}
          </span>
        )}
        {item.location && (
          <span className="flex items-center gap-1">
            <span className="material-symbols-outlined text-[12px]">location_on</span>
            {item.location}
          </span>
        )}
      </div>

      <div className="flex items-center justify-between gap-2">
        {/* Email confirmed toggle (REQ-10) */}
        <button
          className={[
            "flex items-center gap-1.5 rounded-full px-2 py-1 text-xs font-medium transition-all",
            item.email_confirmed
              ? "bg-teal-500/10 text-teal-600"
              : "bg-surface-container text-on-surface-variant hover:bg-teal-500/10 hover:text-teal-600",
          ].join(" ")}
          disabled={isBusy}
          onClick={handleEmailToggle}
          title={item.email_confirmed ? "Email confirmed — click to unmark" : "Mark email as confirmed"}
          type="button"
        >
          <span className="material-symbols-outlined text-[14px]">
            {item.email_confirmed ? "mark_email_read" : "mail"}
          </span>
          {item.email_confirmed ? "Email confirmed" : "Confirm email"}
        </button>

        <div className="flex items-center gap-1.5">
          {isRejected && (
            <button
              className="flex h-7 w-7 items-center justify-center rounded-full text-on-surface-variant transition-colors hover:bg-surface-container hover:text-primary"
              onClick={() => setNoteOpen((v) => !v)}
              title="Add rejection note"
              type="button"
            >
              <span className="material-symbols-outlined text-[16px]">note_add</span>
            </button>
          )}
          {item.apply_link && (
            <a
              className="flex h-7 w-7 items-center justify-center rounded-full text-on-surface-variant transition-colors hover:bg-surface-container hover:text-primary"
              href={item.apply_link}
              rel="noreferrer"
              target="_blank"
              title="Open job posting"
            >
              <span className="material-symbols-outlined text-[16px]">open_in_new</span>
            </a>
          )}
        </div>
      </div>

      {/* Rejection note area */}
      {noteOpen && (
        <div className="mt-3 border-t border-outline-variant/10 pt-3">
          <textarea
            className="w-full rounded-lg border border-outline-variant/20 bg-surface-container p-2 text-xs text-on-surface placeholder-on-surface-variant/50 focus:border-primary/30 focus:outline-none focus:ring-1 focus:ring-primary/20"
            onChange={(e) => setNote(e.target.value)}
            placeholder="Optional rejection note…"
            rows={2}
            value={note}
          />
          <div className="mt-1.5 flex justify-end gap-2">
            <button
              className="rounded px-2 py-1 text-xs text-on-surface-variant hover:text-on-surface"
              onClick={() => setNoteOpen(false)}
              type="button"
            >
              Cancel
            </button>
            <button
              className="rounded bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/20"
              onClick={saveNote}
              type="button"
            >
              Save note
            </button>
          </div>
        </div>
      )}

      {item.rejection_note && !noteOpen && (
        <div className="mt-2 border-t border-outline-variant/10 pt-2 text-xs italic text-on-surface-variant">
          {item.rejection_note}
        </div>
      )}
    </div>
  );
}

function KanbanColumn({ colDef, cards, onUpdate, updating }) {
  return (
    <div className="flex min-w-[280px] flex-1 flex-col">
      {/* Column header */}
      <div
        className={[
          "mb-4 flex items-center justify-between rounded-xl border px-4 py-3",
          colDef.border,
        ].join(" ")}
      >
        <div className="flex items-center gap-2">
          <span
            className={["material-symbols-outlined text-xl", colDef.accent].join(" ")}
            style={{ fontVariationSettings: "'FILL' 1" }}
          >
            {colDef.icon}
          </span>
          <span className="font-semibold text-on-surface">{colDef.label}</span>
        </div>
        <span
          className={[
            "min-w-[24px] rounded-full px-2 py-0.5 text-center text-xs font-bold",
            colDef.badge,
          ].join(" ")}
        >
          {cards.length}
        </span>
      </div>

      {/* Cards */}
      <div className="flex flex-col gap-3">
        {cards.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-outline-variant/20 py-10 text-center text-sm text-on-surface-variant/50">
            <span
              className="material-symbols-outlined mb-2 text-3xl opacity-30"
              style={{ fontVariationSettings: "'FILL' 1" }}
            >
              {colDef.icon}
            </span>
            No jobs here yet
          </div>
        ) : (
          cards.map((item) => (
            <TrackerCard
              item={item}
              key={item.review_id}
              onUpdate={onUpdate}
              updating={updating}
            />
          ))
        )}
      </div>
    </div>
  );
}

function buildEmailFormState(integration) {
  const config = integration?.config || {};
  return {
    folder: config.folder || "INBOX",
    max_messages: String(config.max_messages || 40),
  };
}

function EmailIntegrationPanel({
  integration,
  busy,
  onStartGoogle,
  onRefreshIntegration,
  onSaveSettings,
  onSync,
  onDelete,
  lastSyncResult,
}) {
  const config = integration?.config || {};
  const [form, setForm] = useState(() => buildEmailFormState(integration));
  const [feedback, setFeedback] = useState({ message: "", error: "" });

  useEffect(() => {
    setForm(buildEmailFormState(integration));
  }, [integration]);

  const syncSummary = lastSyncResult?.summary || config.last_sync_summary || null;

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function handleSaveSettings(event) {
    event.preventDefault();
    setFeedback({ message: "", error: "" });
    try {
      await onSaveSettings({
        provider_id: "gmail",
        auth_strategy: "google_oauth",
        folder: form.folder,
        max_messages: Number(form.max_messages || 40),
      });
      setFeedback({ message: "Sync settings updated.", error: "" });
    } catch (saveError) {
      setFeedback({ message: "", error: saveError.message || "Unable to update sync settings." });
    }
  }

  async function handleGoogleConnect() {
    setFeedback({ message: "", error: "" });
    try {
      const startPayload = await onStartGoogle({
        folder: form.folder,
        max_messages: Number(form.max_messages || 40),
      });
      const authorizationUrl = startPayload?.authorization_url || "";
      if (!authorizationUrl) {
        throw new Error("Google authorization could not be started.");
      }
      const popup = window.open(
        authorizationUrl,
        "tracker-google-oauth",
        "popup=yes,width=520,height=720",
      );
      if (!popup) {
        window.location.assign(authorizationUrl);
        return;
      }
      setFeedback({
        message: "Finish Google sign-in in the popup. The tracker will refresh automatically once access is granted.",
        error: "",
      });
      const timeoutAt = Date.now() + 90_000;
      while (Date.now() < timeoutAt) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        const refreshed = await onRefreshIntegration();
        const refreshedConfig = refreshed?.config || {};
        if (refreshedConfig.connected) {
          try {
            popup.close();
          } catch {
            // Ignore popup close issues.
          }
          setFeedback({
            message: `${refreshedConfig.email_address || "Your Gmail inbox"} is now connected.`,
            error: "",
          });
          return;
        }
        if (refreshedConfig.last_error) {
          throw new Error(refreshedConfig.last_error);
        }
        if (popup.closed && refreshedConfig.authorization_state !== "authorization_url_created") {
          break;
        }
      }
      setFeedback({
        message: "Waiting for Google authorization to finish. If you already approved access, refresh once.",
        error: "",
      });
    } catch (connectError) {
      setFeedback({
        message: "",
        error: connectError.message || "Unable to start Google authorization.",
      });
    }
  }

  async function handleSync() {
    setFeedback({ message: "", error: "" });
    try {
      const result = await onSync();
      const summary = result?.result?.summary || {};
      setFeedback({
        message: `Sync complete. ${summary.updated_reviews || 0} tracker card${summary.updated_reviews === 1 ? "" : "s"} updated.`,
        error: "",
      });
    } catch (syncError) {
      setFeedback({ message: "", error: syncError.message || "Unable to sync inbox." });
    }
  }

  async function handleDelete() {
    setFeedback({ message: "", error: "" });
    try {
      await onDelete();
      setForm(buildEmailFormState({ providers }));
      setFeedback({ message: "Inbox connection removed.", error: "" });
    } catch (deleteError) {
      setFeedback({ message: "", error: deleteError.message || "Unable to disconnect inbox." });
    }
  }

  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-sm">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-2xl">
          <h2 className="font-headline text-2xl font-bold tracking-tight text-on-surface">
            Email Inbox Sync
          </h2>
          <p className="mt-2 text-sm leading-7 text-on-surface-variant">
            Connect Gmail with Google authorization so the tracker can pull confirmations,
            interview invites, and rejections into the board automatically without asking for your password.
          </p>
          <p className="mt-3 rounded-2xl bg-surface-container px-4 py-3 text-xs leading-6 text-on-surface-variant">
            <span className="font-semibold text-on-surface">Secure access:</span>
            {" "}
            the tracker stores OAuth tokens and reads Gmail in read-only mode. It does not ask
            for your account password.
          </p>
          {config.email_address ? (
            <p className="mt-3 rounded-2xl bg-surface-container px-4 py-3 text-xs leading-6 text-on-surface-variant">
              <span className="font-semibold text-on-surface">Connected account:</span>
              {" "}
              {config.email_address}
            </p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!config.oauth_available || busy === "authorize"}
            onClick={handleGoogleConnect}
            type="button"
          >
            <span className="material-symbols-outlined text-[18px]">
              {busy === "authorize" ? "progress_activity" : "login"}
            </span>
            {busy === "authorize"
              ? "Opening Google..."
              : config.connected
                ? "Reconnect Google"
                : "Connect with Google"}
          </button>
          <button
            className="flex items-center gap-2 rounded-lg bg-primary/10 px-4 py-2.5 text-sm font-medium text-primary transition-colors hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!config.connected || busy === "sync"}
            onClick={handleSync}
            type="button"
          >
            <span className="material-symbols-outlined text-[18px]">
              {busy === "sync" ? "progress_activity" : "mark_email_read"}
            </span>
            {busy === "sync" ? "Syncing..." : "Sync Inbox"}
          </button>
          <button
            className="rounded-lg border border-outline-variant/20 px-4 py-2.5 text-sm font-medium text-on-surface-variant transition-colors hover:bg-surface-container-low disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!config.connected || busy === "delete"}
            onClick={handleDelete}
            type="button"
          >
            Disconnect
          </button>
        </div>
      </div>

      <form className="mt-6 grid gap-4 lg:grid-cols-2" onSubmit={handleSaveSettings}>
        <label className="block">
          <span className="mb-2 block text-sm font-semibold text-on-surface">Scan Depth</span>
          <input
            className="w-full rounded-xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            max="100"
            min="1"
            onChange={(event) => updateField("max_messages", event.target.value)}
            type="number"
            value={form.max_messages}
          />
        </label>

        <label className="block">
          <span className="mb-2 block text-sm font-semibold text-on-surface">Folder</span>
          <input
            className="w-full rounded-xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface"
            onChange={(event) => updateField("folder", event.target.value)}
            placeholder="INBOX"
            type="text"
            value={form.folder}
          />
        </label>

        <div className="lg:col-span-2">
          {feedback.error ? (
            <div className="rounded-2xl border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">
              {feedback.error}
            </div>
          ) : null}
          {feedback.message ? (
            <div className="rounded-2xl border border-primary/20 bg-primary/5 px-4 py-3 text-sm text-primary">
              {feedback.message}
            </div>
          ) : null}
          {config.last_error && !feedback.error ? (
            <div className="rounded-2xl border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">
              Last sync error: {config.last_error}
            </div>
          ) : null}
          {!config.oauth_available ? (
            <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm text-amber-600">
              Google OAuth is not configured on the backend yet. Set the tracker Google client ID and secret first.
            </div>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-3 lg:col-span-2">
          <button
            className="rounded-lg bg-surface-container-high px-5 py-3 text-sm font-medium text-on-surface shadow-sm transition-all hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-60"
            disabled={busy === "save"}
            type="submit"
          >
            {busy === "save" ? "Saving..." : "Save Sync Settings"}
          </button>
          {config.connected_at ? (
            <span className="text-sm text-on-surface-variant">
              Connected {formatDate(config.connected_at)}
            </span>
          ) : null}
          {config.last_sync_at ? (
            <span className="text-sm text-on-surface-variant">
              Last sync {formatDate(config.last_sync_at)}
            </span>
          ) : null}
          {config.authorization_state === "authorization_url_created" && !config.connected ? (
            <span className="text-sm text-primary">Awaiting Google authorization</span>
          ) : null}
        </div>
      </form>

      {syncSummary ? (
        <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[
            { label: "Checked", value: syncSummary.checked_messages || 0 },
            { label: "Processed", value: syncSummary.processed_messages || 0 },
            { label: "Updated", value: syncSummary.updated_reviews || 0 },
            { label: "Unmatched", value: syncSummary.unmatched_messages || 0 },
          ].map((item) => (
            <div
              className="rounded-2xl border border-outline-variant/20 bg-surface-container p-4"
              key={item.label}
            >
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">
                {item.label}
              </div>
              <div className="mt-2 text-2xl font-bold text-on-surface">{item.value}</div>
            </div>
          ))}
        </div>
      ) : null}

      {lastSyncResult?.matched_updates?.length ? (
        <div className="mt-6 rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4">
          <h3 className="text-sm font-semibold text-on-surface">Latest Matches</h3>
          <div className="mt-3 space-y-2">
            {lastSyncResult.matched_updates.slice(0, 5).map((match) => (
              <div
                className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-surface px-3 py-2 text-sm"
                key={`${match.review_id}-${match.message_id}`}
              >
                <div>
                  <span className="font-medium text-on-surface">{match.company || "Unknown Company"}</span>
                  {" "}
                  <span className="text-on-surface-variant">- {match.title || "Untitled role"}</span>
                </div>
                <div className="text-on-surface-variant">
                  {match.from_status || "applied"} → {match.to_status}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default function TrackerPage() {
  const {
    columns,
    loading,
    error,
    refresh,
    updating,
    updateCard,
    emailIntegration,
    integrationBusy,
    lastSyncResult,
    refreshEmailIntegration,
    startGoogleEmailIntegration,
    updateEmailIntegrationSettings,
    syncEmailIntegration,
    deleteEmailIntegration,
  } = useTracker();
  const totalCards = COLUMNS.reduce((acc, c) => acc + (columns[c.key]?.length || 0), 0);

  return (
    <div className="space-y-8">
      {/* Page header */}
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="font-headline text-[2.25rem] font-extrabold leading-tight tracking-tight text-on-surface">
            Application Tracker
          </h1>
          <p className="mt-1 text-sm text-on-surface-variant">
            {totalCards > 0
              ? `Tracking ${totalCards} application${totalCards === 1 ? "" : "s"} across all stages.`
              : "Applications you've approved in the Review Queue will appear here."}
          </p>
        </div>
        <button
          className="flex items-center gap-2 rounded bg-surface-container-high px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-surface-container-low active:scale-[0.98]"
          onClick={() => refresh().catch(() => undefined)}
          type="button"
        >
          <span className="material-symbols-outlined text-sm">refresh</span>
          Refresh
        </button>
      </header>

      {/* State feedback */}
      {loading && (
        <div className="flex items-center gap-3 rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-6 py-4 text-sm text-on-surface-variant">
          <span className="material-symbols-outlined animate-spin">progress_activity</span>
          Loading tracker…
        </div>
      )}
      {error && !loading && (
        <div className="flex items-center gap-3 rounded-xl border border-error/20 bg-error/5 px-6 py-4 text-sm text-error">
          <span className="material-symbols-outlined">error</span>
          {error}
        </div>
      )}

      {!loading && !error ? (
        <EmailIntegrationPanel
          busy={integrationBusy}
          integration={emailIntegration}
          lastSyncResult={lastSyncResult}
          onDelete={deleteEmailIntegration}
          onRefreshIntegration={refreshEmailIntegration}
          onSaveSettings={updateEmailIntegrationSettings}
          onStartGoogle={startGoogleEmailIntegration}
          onSync={syncEmailIntegration}
        />
      ) : null}

      {/* Kanban board */}
      {!loading && !error && (
        <div className="flex gap-5 overflow-x-auto pb-4">
          {COLUMNS.map((colDef) => (
            <KanbanColumn
              cards={columns[colDef.key] || []}
              colDef={colDef}
              key={colDef.key}
              onUpdate={updateCard}
              updating={updating}
            />
          ))}
        </div>
      )}
    </div>
  );
}
