import { useState } from "react";
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

export default function TrackerPage() {
  const { columns, loading, error, refresh, updating, updateCard } = useTracker();
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
