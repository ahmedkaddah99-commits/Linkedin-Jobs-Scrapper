import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useTracker } from "../hooks/useTracker";

const BOARD_COLUMNS = [
  {
    key: "saved",
    label: "Saved",
    statuses: ["not_applied", "unknown"],
    icon: "bookmark_border",
    color: "#7a8799",
  },
  {
    key: "applied",
    label: "Applied",
    statuses: ["applied"],
    icon: "send",
    color: "#159fbd",
  },
  {
    key: "interviewing",
    label: "Interviewing",
    statuses: ["interview_invited"],
    icon: "forum",
    color: "#b17a17",
  },
  {
    key: "offer",
    label: "Offer",
    statuses: ["offer"],
    icon: "workspace_premium",
    color: "#1b9a68",
  },
  {
    key: "rejected",
    label: "Rejected",
    statuses: ["rejected"],
    icon: "cancel",
    color: "#d75b67",
  },
];

const STATUS_OPTIONS = [
  { value: "not_applied", label: "Saved" },
  { value: "applied", label: "Applied" },
  { value: "interview_invited", label: "Interviewing" },
  { value: "offer", label: "Offer" },
  { value: "rejected", label: "Rejected" },
  { value: "withdrawn", label: "Withdrawn" },
  { value: "unknown", label: "Unknown" },
];

const EMPTY_FORM = {
  title: "",
  company: "",
  location: "",
  application_date: "",
  apply_link: "",
  notes: "",
};

function icon(name, className = "") {
  return (
    <span
      aria-hidden="true"
      className={`material-symbols-outlined ${className}`}
    >
      {name}
    </span>
  );
}

function statusFor(item) {
  const value =
    item?.tracker_status === "email_confirmed"
      ? "applied"
      : item?.tracker_status;
  return STATUS_OPTIONS.some((option) => option.value === value)
    ? value
    : "unknown";
}

function statusLabel(value) {
  return (
    STATUS_OPTIONS.find((option) => option.value === value)?.label || "Unknown"
  );
}

function columnFor(item) {
  const value = statusFor(item);
  return (
    BOARD_COLUMNS.find((column) => column.statuses.includes(value)) ||
    BOARD_COLUMNS[0]
  );
}

function formatDate(value, fallback = "") {
  if (!value) return fallback;
  try {
    return new Date(value).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return value;
  }
}

function shortDate(value) {
  if (!value) return "";
  try {
    return new Date(value).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  } catch {
    return String(value).slice(0, 10);
  }
}

function companyInitials(company) {
  const parts = String(company || "?")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  return (
    parts.length > 1
      ? `${parts[0][0]}${parts[1][0]}`
      : parts[0]?.slice(0, 2) || "?"
  ).toUpperCase();
}

function companyColor(company) {
  const palette = [
    "#22b9d6",
    "#7967d8",
    "#e27e49",
    "#198b72",
    "#d15f85",
    "#4778bb",
  ];
  const hash = [...String(company || "")].reduce(
    (sum, character) => sum + character.charCodeAt(0),
    0,
  );
  return palette[hash % palette.length];
}

function sourceLabel(item) {
  if (item?.source_label) return item.source_label;
  if (item?.tracker_source_type === "external") return "External";
  if (item?.is_test_run) return "Test run";
  return "Runr run";
}

function matchesDateRange(item, from, until) {
  const date = String(
    item?.application_date ||
      item?.placed_in_tracker_at ||
      item?.run_finished_at ||
      "",
  ).slice(0, 10);
  return (
    (!from || (date && date >= from)) && (!until || (date && date <= until))
  );
}

function splitDescription(value) {
  return String(value || "")
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function Button({ children, className = "", variant = "outline", ...props }) {
  const variants = {
    outline:
      "border-[#b8c9d7] bg-white text-[#087ea7] hover:border-[#16aeca] hover:bg-[#f0fbfd]",
    primary: "border-[#159fbd] bg-[#159fbd] text-white hover:bg-[#128eaa]",
    quiet:
      "border-transparent bg-transparent text-[#5d7185] hover:bg-[#eef5f8] hover:text-[#12304a]",
    danger: "border-[#e99aa3] bg-white text-[#d02e47] hover:bg-[#fff1f2]",
  };
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
      type="button"
      {...props}
    >
      {children}
    </button>
  );
}

function Logo({ company, large = false }) {
  return (
    <div
      className={`flex shrink-0 items-center justify-center rounded-md font-bold text-white ${large ? "h-16 w-16 text-xl" : "h-12 w-12 text-sm"}`}
      style={{ background: companyColor(company) }}
    >
      {companyInitials(company)}
    </div>
  );
}

function FilterSelect({ label, value, onChange, children }) {
  return (
    <label className="relative flex min-w-[145px] items-center gap-2 rounded-md border border-[#c5d1dc] bg-white px-3 py-2 text-sm text-[#567087]">
      <span className="sr-only">{label}</span>
      <select
        aria-label={label}
        className="w-full appearance-none bg-transparent pr-5 outline-none"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        {children}
      </select>
      {icon("expand_more", "pointer-events-none absolute right-2 text-[18px]")}
    </label>
  );
}

function SearchAndFilters({ filters, onChange, jobTypes, onReset }) {
  const hasFilters = Object.values(filters).some(Boolean);
  return (
    <div className="border-b border-[#d6e0e8] bg-[#f8fafc] px-4 py-4 md:px-8">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
        <label className="flex min-w-0 flex-1 items-center gap-2 rounded-md border border-[#d1dce6] bg-white px-3 py-2.5 text-sm text-[#718398] shadow-sm">
          {icon("search", "text-[20px]")}
          <span className="sr-only">Search roles or companies</span>
          <input
            className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-[#8292a3]"
            onChange={(event) => onChange({ query: event.target.value })}
            placeholder="Search for roles or companies"
            type="search"
            value={filters.query}
          />
          {filters.query ? (
            <button
              aria-label="Clear search"
              className="text-[#8796a7] hover:text-[#12304a]"
              onClick={() => onChange({ query: "" })}
              type="button"
            >
              {icon("close", "text-[17px]")}
            </button>
          ) : null}
        </label>
        <div className="flex flex-wrap gap-2">
          <label className="flex items-center gap-2 rounded-md border border-[#c5d1dc] bg-white px-3 py-2 text-sm text-[#567087]">
            {icon("calendar_month", "text-[17px]")}
            <span className="sr-only">Applied from</span>
            <input
              aria-label="Applied from"
              className="w-[125px] bg-transparent outline-none"
              onChange={(event) => onChange({ from: event.target.value })}
              type="date"
              value={filters.from}
            />
          </label>
          <label className="flex items-center gap-2 rounded-md border border-[#c5d1dc] bg-white px-3 py-2 text-sm text-[#567087]">
            {icon("event", "text-[17px]")}
            <span className="sr-only">Applied until</span>
            <input
              aria-label="Applied until"
              className="w-[125px] bg-transparent outline-none"
              onChange={(event) => onChange({ until: event.target.value })}
              type="date"
              value={filters.until}
            />
          </label>
          <FilterSelect
            label="Job type"
            onChange={(value) => onChange({ jobType: value })}
            value={filters.jobType}
          >
            <option value="">Job Type</option>
            {jobTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </FilterSelect>
          <FilterSelect
            label="Status"
            onChange={(value) => onChange({ status: value })}
            value={filters.status}
          >
            <option value="">Status</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </FilterSelect>
          {hasFilters ? (
            <Button className="px-3" onClick={onReset} variant="quiet">
              {icon("filter_alt_off", "text-[18px]")} Clear
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function TrackerCard({ item, onOpen, onStatusChange, busy }) {
  const currentStatus = statusFor(item);
  const column = columnFor(item);
  const jobType =
    item.job_type ||
    item.tracker_table_row?.job_type ||
    item.tracker_table_row?.type ||
    "";
  return (
    <article className="group relative rounded-md border border-[#d6e0e8] bg-white p-3 shadow-[0_2px_4px_rgba(23,53,79,0.06)] transition hover:-translate-y-0.5 hover:border-[#94cddd] hover:shadow-[0_8px_20px_rgba(23,53,79,0.1)]">
      {busy ? (
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-md bg-white/75">
          {icon("progress_activity", "animate-spin text-[#159fbd]")}
        </div>
      ) : null}
      <button
        className="w-full text-left"
        onClick={() => onOpen(item)}
        type="button"
      >
        <div className="flex gap-3">
          <Logo company={item.company} />
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <h3 className="line-clamp-2 text-[14px] font-bold leading-5 text-[#18314b]">
                {item.title || "Untitled role"}
              </h3>
              {icon("favorite_border", "shrink-0 text-[19px] text-[#7a8999]")}
            </div>
            <p className="mt-1 truncate text-xs font-medium text-[#536b80]">
              {item.company || "Unknown company"}
            </p>
          </div>
        </div>
        <div className="mt-3 space-y-1 text-xs text-[#60768a]">
          {item.location ? (
            <p className="flex items-center gap-1.5 truncate">
              {icon("location_on", "text-[15px]")}
              {item.location}
            </p>
          ) : null}
          <p className="flex items-center gap-1.5">
            {icon("calendar_today", "text-[14px]")}
            {shortDate(
              item.application_date ||
                item.placed_in_tracker_at ||
                item.run_finished_at,
            ) || "Added recently"}
          </p>
          {jobType ? (
            <p className="flex items-center gap-1.5">
              {icon("work_outline", "text-[14px]")}
              {jobType}
            </p>
          ) : null}
        </div>
      </button>
      <div className="mt-3 flex items-center justify-between gap-2 border-t border-[#edf1f4] pt-2">
        <span className="truncate text-[11px] font-semibold uppercase tracking-[0.06em] text-[#8a99a8]">
          {sourceLabel(item)}
        </span>
        <label
          className="relative"
          onClick={(event) => event.stopPropagation()}
        >
          <span className="sr-only">Change status</span>
          <select
            aria-label={`Change status for ${item.title || "job"}`}
            className="max-w-[112px] appearance-none bg-transparent pr-4 text-xs font-bold outline-none"
            onChange={(event) => onStatusChange(item, event.target.value)}
            value={currentStatus}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {icon(
            "expand_more",
            "pointer-events-none absolute right-0 top-0 text-[15px] text-[#7c8d9d]",
          )}
        </label>
      </div>
      <div
        aria-hidden="true"
        className="absolute bottom-0 left-0 h-0.5 w-full rounded-b-md opacity-0 transition group-hover:opacity-100"
        style={{ background: column.color }}
      />
    </article>
  );
}

function BoardColumn({ column, items, onOpen, onStatusChange, updating }) {
  return (
    <section
      className="flex min-h-[470px] min-w-[255px] flex-1 flex-col border-r border-[#d9e3eb] last:border-r-0"
      data-column={column.key}
    >
      <div className="flex items-center justify-between px-4 pb-3 pt-4">
        <div className="flex items-center gap-2 text-sm font-bold uppercase tracking-[0.05em] text-[#2d4358]">
          {icon(column.icon, "text-[18px]")}
          {column.label}
          <span className="font-semibold text-[#8090a0]">({items.length})</span>
        </div>
        {icon("visibility_off", "text-[17px] text-[#7c8c9d]")}
      </div>
      <div className="flex flex-1 flex-col gap-3 bg-[#f5f8fb] px-3 pb-4">
        {items.length ? (
          items.map((item) => (
            <TrackerCard
              busy={updating === item.review_id}
              item={item}
              key={item.review_id}
              onOpen={onOpen}
              onStatusChange={onStatusChange}
            />
          ))
        ) : (
          <div className="flex flex-1 items-center justify-center rounded-md border border-dashed border-[#d6e0e8] text-center text-xs text-[#8a9aaa]">
            No jobs here yet
          </div>
        )}
      </div>
    </section>
  );
}

function TrackerBoard({ items, onOpen, onStatusChange, updating }) {
  return (
    <div className="overflow-x-auto rounded-md border border-[#d7e1e9] shadow-sm">
      <div className="flex min-w-[1280px]">
        {BOARD_COLUMNS.map((column) => (
          <BoardColumn
            column={column}
            items={items.filter((item) =>
              column.statuses.includes(statusFor(item)),
            )}
            key={column.key}
            onOpen={onOpen}
            onStatusChange={onStatusChange}
            updating={updating}
          />
        ))}
      </div>
    </div>
  );
}

function Insights({ items }) {
  const counts = Object.fromEntries(
    STATUS_OPTIONS.map((option) => [
      option.value,
      items.filter((item) => statusFor(item) === option.value).length,
    ]),
  );
  const active = items.filter((item) => statusFor(item) !== "withdrawn").length;
  const responseRate = counts.applied
    ? Math.round(
        ((counts.interview_invited + counts.offer) / counts.applied) * 100,
      )
    : 0;
  const metrics = [
    ["Total applications", items.length, "inventory_2", "#159fbd"],
    ["Active applications", active, "bolt", "#1b9a68"],
    ["Interview rate", `${responseRate}%`, "forum", "#b17a17"],
    ["Offers", counts.offer || 0, "workspace_premium", "#765fcd"],
  ];
  return (
    <div className="rounded-md border border-[#d7e1e9] bg-white p-5 shadow-sm md:p-7">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#159fbd]">
            Flow chart
          </p>
          <h2 className="mt-1 text-xl font-bold text-[#18314b]">
            Application insights
          </h2>
        </div>
        <p className="text-sm text-[#6e8294]">
          Calculated from the applications currently in view
        </p>
      </div>
      <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map(([label, value, metricIcon, color]) => (
          <div
            className="rounded-md border border-[#e0e7ed] bg-[#f9fbfd] p-4"
            key={label}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm text-[#62788c]">{label}</span>
              <span className="rounded-md bg-white p-2" style={{ color }}>
                {icon(metricIcon, "text-[19px]")}
              </span>
            </div>
            <p className="mt-4 text-3xl font-bold text-[#18314b]">{value}</p>
          </div>
        ))}
      </div>
      <div className="mt-7 grid gap-5 lg:grid-cols-[1.2fr_1fr]">
        <div className="rounded-md border border-[#e0e7ed] p-5">
          <h3 className="font-bold text-[#18314b]">Pipeline</h3>
          <div className="mt-5 space-y-4">
            {BOARD_COLUMNS.map((column) => {
              const count = items.filter((item) =>
                column.statuses.includes(statusFor(item)),
              ).length;
              const width = items.length
                ? Math.max(4, Math.round((count / items.length) * 100))
                : 4;
              return (
                <div key={column.key}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="text-[#536b80]">{column.label}</span>
                    <b className="text-[#18314b]">{count}</b>
                  </div>
                  <div className="h-2 rounded-full bg-[#edf2f6]">
                    <div
                      className="h-2 rounded-full"
                      style={{ background: column.color, width: `${width}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <div className="rounded-md border border-[#e0e7ed] p-5">
          <h3 className="font-bold text-[#18314b]">Next actions</h3>
          <div className="mt-4 space-y-3 text-sm text-[#536b80]">
            <p className="flex items-center gap-2">
              {icon("schedule", "text-[#b17a17]")}Follow up on{" "}
              {counts.applied || 0} applied job{counts.applied === 1 ? "" : "s"}
              .
            </p>
            <p className="flex items-center gap-2">
              {icon("event_available", "text-[#1b9a68]")}
              {counts.interview_invited || 0} interview
              {counts.interview_invited === 1 ? "" : "s"} in progress.
            </p>
            <p className="flex items-center gap-2">
              {icon("mail", "text-[#159fbd]")}Keep your application notes up to
              date.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatusTimeline({ item, onChange, busy }) {
  const steps = ["not_applied", "applied", "interview_invited", "offer"];
  const current = statusFor(item);
  const currentIndex = steps.indexOf(current);
  return (
    <div className="rounded-md border border-[#d2dee7] bg-[#f8fafc] p-4">
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-[#18314b]">Application status</h3>
        <FilterSelect
          label="Application status"
          onChange={onChange}
          value={current}
        >
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </FilterSelect>
      </div>
      <div className="mt-5 space-y-3">
        {steps.map((step, index) => (
          <button
            className="flex w-full items-center gap-3 text-left text-sm"
            disabled={busy}
            key={step}
            onClick={() => onChange(step)}
            type="button"
          >
            <span
              className={`flex h-5 w-5 items-center justify-center rounded-full border-2 ${index <= currentIndex && current !== "rejected" && current !== "withdrawn" ? "border-[#159fbd] bg-[#159fbd] text-white" : "border-[#cbd7e1] bg-white text-transparent"}`}
            >
              {icon("check", "text-[13px]")}
            </span>
            <span
              className={
                index === currentIndex
                  ? "font-bold text-[#18314b]"
                  : "text-[#6e8294]"
              }
            >
              {statusLabel(step)}
            </span>
            {index === currentIndex ? (
              <span className="text-xs text-[#7f91a1]">
                {formatDate(item.application_date || item.placed_in_tracker_at)}
              </span>
            ) : null}
          </button>
        ))}
      </div>
      {current === "rejected" || current === "withdrawn" ? (
        <p className="mt-4 rounded-md bg-[#fff2f3] px-3 py-2 text-xs font-semibold text-[#c43e50]">
          {statusLabel(current)} — this application is outside the active
          pipeline.
        </p>
      ) : null}
    </div>
  );
}

function DetailDrawer({
  item,
  onClose,
  onStatusChange,
  onDelete,
  onArchive,
  onApply,
  onSaveNotes,
  request,
  updating,
}) {
  const [detail, setDetail] = useState(item);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("overview");
  const [notes, setNotes] = useState(item.notes || "");
  const [favorite, setFavorite] = useState(false);
  const [ats, setAts] = useState(null);
  const [atsLoading, setAtsLoading] = useState(false);
  const bodyRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    setDetail(item);
    setNotes(item.notes || "");
    setLoading(true);
    setError("");
    setTab("overview");
    setAts(null);
    request(`/tracker/${encodeURIComponent(item.review_id)}/details`)
      .then((payload) => {
        if (!cancelled) {
          setDetail(payload);
          setNotes(payload.notes || "");
        }
      })
      .catch((requestError) => {
        if (!cancelled)
          setError(requestError.message || "Unable to load this application.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [item, request]);

  useEffect(() => {
    if (tab !== "score" || ats || atsLoading) return;
    let cancelled = false;
    setAtsLoading(true);
    request(`/tracker/${encodeURIComponent(item.review_id)}/ats`)
      .then((payload) => {
        if (!cancelled) setAts(payload);
      })
      .catch(() => {
        if (!cancelled)
          setAts({ error: "Resume score is not available for this job yet." });
      })
      .finally(() => {
        if (!cancelled) setAtsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ats, atsLoading, item.review_id, request, tab]);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: 0 });
  }, [tab]);

  const effectiveItem = { ...item, ...detail };
  const documents = Array.isArray(detail.documents) ? detail.documents : [];
  async function saveNotes() {
    await onSaveNotes(effectiveItem, notes);
    setDetail((current) => ({ ...current, notes }));
  }
  function updateStatus(value) {
    onStatusChange(effectiveItem, value)
      .then(() =>
        setDetail((current) => ({
          ...current,
          tracker_status: value,
          application_status: statusLabel(value),
        })),
      )
      .catch(() => undefined);
  }

  return (
    <div
      aria-label="Application details"
      className="fixed inset-0 z-50 flex justify-end bg-[#10263b]/45"
      role="dialog"
    >
      <button
        aria-label="Close application details"
        className="absolute inset-0 cursor-default"
        onClick={onClose}
        type="button"
      />
      <aside className="relative flex h-full w-full max-w-[1120px] flex-col overflow-hidden bg-white shadow-2xl">
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-4 border-b border-[#d9e2e9] px-6 py-5 md:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <Logo company={effectiveItem.company} large />
            <div className="min-w-0">
              <h2 className="text-xl font-bold leading-7 text-[#18314b] md:text-2xl">
                {effectiveItem.title || "Untitled role"}
              </h2>
              <p className="mt-1 text-sm text-[#536b80]">
                {effectiveItem.company || "Unknown company"}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              disabled={loading}
              onClick={() => onApply(effectiveItem)}
              variant="outline"
            >
              {icon("bolt", "text-[18px]")} Apply
            </Button>
            <Button
              onClick={() => setFavorite((current) => !current)}
              variant="outline"
            >
              {icon(favorite ? "favorite" : "favorite_border", "text-[18px]")}{" "}
              {favorite ? "Favorited" : "Favorite"}
            </Button>
            <Button
              disabled={updating === effectiveItem.review_id}
              onClick={() => onArchive(effectiveItem)}
              variant="outline"
            >
              {icon("archive", "text-[18px]")} Archive
            </Button>
            <Button
              disabled={updating === effectiveItem.review_id}
              onClick={() => onDelete(effectiveItem)}
              variant="danger"
            >
              {icon("delete", "text-[18px]")} Delete
            </Button>
            <button
              aria-label="Close"
              className="ml-1 rounded p-2 text-[#65798c] hover:bg-[#eef5f8]"
              onClick={onClose}
              type="button"
            >
              {icon("close")}
            </button>
          </div>
        </header>
        <nav className="flex shrink-0 gap-1 overflow-x-auto border-b border-[#d9e2e9] px-6 md:px-8">
          {[
            ["overview", "Overview", "work"],
            ["documents", "Documents", "description"],
            ["score", "Resume Score", "emoji_events"],
            ["email", "AI Email", "mail"],
            ["questions", "Questions", "quiz"],
          ].map(([key, label, tabIcon]) => (
            <button
              className={`flex shrink-0 items-center gap-2 border-b-2 px-3 py-3 text-sm font-semibold ${tab === key ? "border-[#159fbd] bg-[#effafd] text-[#0783a9]" : "border-transparent text-[#62778a] hover:bg-[#f6f9fb]"}`}
              key={key}
              onClick={() => setTab(key)}
              type="button"
            >
              {icon(tabIcon, "text-[17px]")}
              {label}
            </button>
          ))}
        </nav>
        <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_330px]">
          <main
            className="min-h-0 overflow-y-auto px-6 py-6 md:px-8"
            ref={bodyRef}
          >
            {loading ? (
              <div className="space-y-4">
                <div className="h-7 w-1/3 animate-pulse rounded bg-[#edf2f6]" />
                <div className="h-32 animate-pulse rounded bg-[#edf2f6]" />
                <div className="h-48 animate-pulse rounded bg-[#edf2f6]" />
              </div>
            ) : error ? (
              <div className="rounded-md border border-[#f0b3ba] bg-[#fff3f4] p-4 text-sm text-[#c43e50]">
                {error}
              </div>
            ) : tab === "overview" ? (
              <Overview detail={detail} />
            ) : tab === "documents" ? (
              <Documents documents={documents} />
            ) : tab === "score" ? (
              <ResumeScore ats={ats} loading={atsLoading} />
            ) : tab === "email" ? (
              <EmailTab item={effectiveItem} />
            ) : (
              <Questions />
            )}
          </main>
          <aside className="min-h-0 overflow-y-auto border-t border-[#d9e2e9] bg-[#fbfcfd] px-5 py-6 lg:border-l lg:border-t-0">
            <StatusTimeline
              busy={updating === effectiveItem.review_id}
              item={effectiveItem}
              onChange={updateStatus}
            />
            <section className="mt-5">
              <div className="flex items-center justify-between">
                <h3 className="font-bold text-[#18314b]">Notes</h3>
                <Button
                  className="px-2 py-1 text-xs"
                  disabled={
                    updating === effectiveItem.review_id ||
                    notes === (effectiveItem.notes || "")
                  }
                  onClick={saveNotes}
                  variant="quiet"
                >
                  Save
                </Button>
              </div>
              <textarea
                className="mt-3 min-h-[220px] w-full resize-y rounded-md border border-[#d2dee7] bg-white p-3 text-sm leading-6 text-[#30485e] outline-none placeholder:text-[#91a0ae] focus:border-[#159fbd]"
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Add notes, reminders, or contacts for this job"
                value={notes}
              />
            </section>
          </aside>
        </div>
      </aside>
    </div>
  );
}

function Overview({ detail }) {
  const paragraphs = splitDescription(detail.full_description);
  return (
    <div>
      <div className="flex flex-wrap gap-2 text-xs font-semibold text-[#61768a]">
        <span className="rounded-full bg-[#eef5f8] px-3 py-1.5">
          {sourceLabel(detail)}
        </span>
        {detail.application_date ? (
          <span className="rounded-full bg-[#eef5f8] px-3 py-1.5">
            Applied {formatDate(detail.application_date)}
          </span>
        ) : null}
      </div>
      <div className="mt-6 grid gap-5 sm:grid-cols-2">
        <Info
          label="Location"
          value={detail.location || "Not set"}
          iconName="location_on"
        />
        <Info
          label="Job type"
          value={
            detail.job_type ||
            detail.tracker_table_row?.job_type ||
            detail.tracker_table_row?.type ||
            "Not set"
          }
          iconName="work_outline"
        />
        <Info
          label="URL"
          value={detail.apply_link ? "View job posting" : "Not available"}
          iconName="open_in_new"
          href={detail.apply_link}
        />
        <Info
          label="Workspace"
          value={detail.workspace_name || "External application"}
          iconName="folder_open"
        />
      </div>
      <div className="mt-7 border-t border-[#e0e7ed] pt-6">
        <h3 className="text-lg font-bold text-[#18314b]">Job description</h3>
        {paragraphs.length ? (
          <div className="mt-4 space-y-4 text-sm leading-7 text-[#3f566b]">
            {paragraphs.map((paragraph, index) => (
              <p key={`${index}-${paragraph.slice(0, 12)}`}>{paragraph}</p>
            ))}
          </div>
        ) : (
          <p className="mt-4 text-sm text-[#74889a]">
            Open the original posting for the full job description.
          </p>
        )}
      </div>
    </div>
  );
}

function Info({ label, value, iconName, href }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[#8a99a8]">
        {label}
      </p>
      <p className="mt-1 flex items-center gap-1.5 text-sm font-semibold text-[#18314b]">
        {icon(iconName, "text-[16px] text-[#159fbd]")}
        {href ? (
          <a
            className="text-[#0783a9] hover:underline"
            href={href}
            rel="noreferrer"
            target="_blank"
          >
            {value}
          </a>
        ) : (
          value
        )}
      </p>
    </div>
  );
}

function Documents({ documents }) {
  return (
    <div>
      <h3 className="text-xl font-bold text-[#18314b]">Documents</h3>
      <p className="mt-2 text-sm text-[#6e8294]">
        Only this job's document list was loaded when you opened the
        application.
      </p>
      {documents.length ? (
        <div className="mt-5 space-y-3">
          {documents.map((document, index) => (
            <div
              className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-[#dce5ec] p-4"
              key={document.document_id || `${document.label}-${index}`}
            >
              <div className="flex items-center gap-3">
                {icon(
                  document.file_extension === "pdf"
                    ? "picture_as_pdf"
                    : "description",
                  "text-[23px] text-[#159fbd]",
                )}
                <div>
                  <p className="font-semibold text-[#18314b]">
                    {document.label || document.document_type || "Document"}
                  </p>
                  <p className="mt-1 text-xs text-[#74889a]">
                    {document.file_extension?.toUpperCase() || "FILE"}
                  </p>
                </div>
              </div>
              {document.download_url ? (
                <a
                  className="text-sm font-semibold text-[#0783a9] hover:underline"
                  href={document.download_url}
                  rel="noreferrer"
                  target="_blank"
                >
                  Open
                </a>
              ) : (
                <span className="text-xs text-[#8a99a8]">Stored locally</span>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-6 rounded-md border border-dashed border-[#d2dee7] p-8 text-center text-sm text-[#74889a]">
          No application documents are linked to this job yet.
        </div>
      )}
    </div>
  );
}

function ResumeScore({ ats, loading }) {
  if (loading)
    return (
      <div className="flex items-center gap-2 text-sm text-[#6e8294]">
        {icon("progress_activity", "animate-spin text-[#159fbd]")}Loading resume
        score…
      </div>
    );
  if (!ats || ats.error)
    return (
      <div className="rounded-md border border-dashed border-[#d2dee7] p-8 text-center text-sm text-[#74889a]">
        {ats?.error || "Resume score is not available for this job yet."}
      </div>
    );
  const score = ats.score?.best || 0;
  return (
    <div className="max-w-xl">
      <div className="flex items-center gap-5">
        <div
          className="flex h-24 w-24 items-center justify-center rounded-full border-[10px] border-[#e8eef4] text-3xl font-bold text-[#18314b]"
          style={{ borderLeftColor: score < 70 ? "#e83f68" : "#1b9a68" }}
        >
          {score}
        </div>
        <div>
          <p className="font-bold text-[#18314b]">
            {ats.score?.gate_state === "passed" ? "Good match" : "Needs review"}
          </p>
        </div>
      </div>
      {ats.criteria?.missing?.length ? (
        <div className="mt-5 rounded-md border border-[#f0dfe3] bg-[#fff8f9] p-3 text-sm text-[#b53c4c]">
          <b>{ats.criteria.missing.length} missing {ats.criteria.missing.length === 1 ? "keyword" : "keywords"}</b>
          <ul className="mt-2 flex flex-wrap gap-2">
            {ats.criteria.missing.map((value) => (
              <li className="rounded-full bg-[#fdecef] px-2.5 py-1 text-xs" key={value}>{value}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function EmailTab({ item }) {
  return (
    <div>
      <h3 className="text-xl font-bold text-[#18314b]">AI email</h3>
      <p className="mt-2 text-sm leading-6 text-[#6e8294]">
        Generate a follow-up message for {item.company || "this employer"} from
        the tracker email tools.
      </p>
      <div className="mt-6 rounded-md border border-[#dce5ec] bg-[#f8fafc] p-5">
        <p className="font-semibold text-[#18314b]">
          Follow up after application
        </p>
        <p className="mt-2 text-sm leading-6 text-[#60768a]">
          A concise check-in that reiterates your interest and asks about next
          steps.
        </p>
        <Button
          className="mt-4"
          onClick={() =>
            window.alert(
              "Email generation is available after selecting an email template.",
            )
          }
          variant="primary"
        >
          {icon("auto_awesome", "text-[17px]")} Select template
        </Button>
      </div>
    </div>
  );
}

function Questions() {
  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-xl font-bold text-[#18314b]">
          Application questions
        </h3>
        <Button variant="primary">
          {icon("add", "text-[17px]")} Add question
        </Button>
      </div>
      <p className="mt-4 text-sm text-[#6e8294]">
        No application questions found for this job.
      </p>
    </div>
  );
}

function AddApplicationModal({ onClose, onCreate, busy }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState("");
  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }
  async function submit(event) {
    event.preventDefault();
    if (!form.title.trim() || !form.company.trim()) {
      setError("Role and company are required.");
      return;
    }
    try {
      await onCreate(form);
    } catch (requestError) {
      setError(requestError.message || "Unable to add application.");
    }
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#10263b]/45 px-4">
      <div
        aria-label="Add application"
        className="w-full max-w-xl rounded-md bg-white p-6 shadow-2xl"
        role="dialog"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#159fbd]">
              New tracker item
            </p>
            <h2 className="mt-1 text-2xl font-bold text-[#18314b]">
              Add application
            </h2>
          </div>
          <button
            aria-label="Close"
            className="rounded p-2 text-[#65798c] hover:bg-[#eef5f8]"
            onClick={onClose}
            type="button"
          >
            {icon("close")}
          </button>
        </div>
        <form className="mt-6 space-y-4" onSubmit={submit}>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="sm:col-span-2">
              <span className="mb-1 block text-xs font-bold uppercase tracking-[0.06em] text-[#6b8093]">
                Role *
              </span>
              <input
                autoFocus
                className="w-full rounded-md border border-[#cbd8e2] px-3 py-2.5 text-sm outline-none focus:border-[#159fbd]"
                onChange={(event) => update("title", event.target.value)}
                placeholder="e.g. Product Manager"
                value={form.title}
              />
            </label>
            <label>
              <span className="mb-1 block text-xs font-bold uppercase tracking-[0.06em] text-[#6b8093]">
                Company *
              </span>
              <input
                className="w-full rounded-md border border-[#cbd8e2] px-3 py-2.5 text-sm outline-none focus:border-[#159fbd]"
                onChange={(event) => update("company", event.target.value)}
                placeholder="e.g. Tesla"
                value={form.company}
              />
            </label>
            <label>
              <span className="mb-1 block text-xs font-bold uppercase tracking-[0.06em] text-[#6b8093]">
                Location
              </span>
              <input
                className="w-full rounded-md border border-[#cbd8e2] px-3 py-2.5 text-sm outline-none focus:border-[#159fbd]"
                onChange={(event) => update("location", event.target.value)}
                placeholder="City or remote"
                value={form.location}
              />
            </label>
            <label>
              <span className="mb-1 block text-xs font-bold uppercase tracking-[0.06em] text-[#6b8093]">
                Applied on
              </span>
              <input
                className="w-full rounded-md border border-[#cbd8e2] px-3 py-2.5 text-sm outline-none focus:border-[#159fbd]"
                onChange={(event) =>
                  update("application_date", event.target.value)
                }
                type="date"
                value={form.application_date}
              />
            </label>
            <label>
              <span className="mb-1 block text-xs font-bold uppercase tracking-[0.06em] text-[#6b8093]">
                Posting URL
              </span>
              <input
                className="w-full rounded-md border border-[#cbd8e2] px-3 py-2.5 text-sm outline-none focus:border-[#159fbd]"
                onChange={(event) => update("apply_link", event.target.value)}
                placeholder="https://…"
                type="url"
                value={form.apply_link}
              />
            </label>
          </div>
          <label>
            <span className="mb-1 block text-xs font-bold uppercase tracking-[0.06em] text-[#6b8093]">
              Notes
            </span>
            <textarea
              className="min-h-24 w-full rounded-md border border-[#cbd8e2] px-3 py-2.5 text-sm outline-none focus:border-[#159fbd]"
              onChange={(event) => update("notes", event.target.value)}
              placeholder="Anything worth remembering?"
              value={form.notes}
            />
          </label>
          {error ? (
            <p className="rounded-md bg-[#fff2f3] px-3 py-2 text-sm text-[#c43e50]">
              {error}
            </p>
          ) : null}
          <div className="flex justify-end gap-2 pt-2">
            <Button onClick={onClose} variant="quiet">
              Cancel
            </Button>
            <Button disabled={busy} type="submit" variant="primary">
              {busy
                ? icon("progress_activity", "animate-spin text-[17px]")
                : icon("add", "text-[17px]")}{" "}
              {busy ? "Adding…" : "Add application"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function EmailSyncPopover({
  integration,
  busy,
  onConnect,
  onSync,
  onApprove,
  onDismiss,
  onClose,
}) {
  const config = integration?.config || {};
  const detections = config.pending_detections || [];
  return (
    <div className="absolute right-0 top-12 z-30 w-[min(390px,calc(100vw-2rem))] rounded-md border border-[#cbd9e3] bg-white p-5 text-left shadow-2xl">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-bold text-[#18314b]">Connect Email</h3>
          <p className="mt-1 text-xs leading-5 text-[#6e8294]">
            Connect Gmail to automatically update your applications when your status changes and notify you when you reach the interview stage.
          </p>
        </div>
        <button
          aria-label="Close email connection"
          className="text-[#75899a]"
          onClick={onClose}
          type="button"
        >
          {icon("close", "text-[18px]")}
        </button>
      </div>
      {!integration ? (
        <div className="mt-5 flex items-center gap-2 text-sm text-[#6e8294]">
          {icon("progress_activity", "animate-spin text-[#159fbd]")}Loading
          connection…
        </div>
      ) : (
        <>
          <div className="mt-5 rounded-md bg-[#f4f9fb] p-3 text-sm text-[#536b80]">
            {config.connected ? (
              <>
                <b className="text-[#18314b]">Connected</b>
                <br />
                {config.email_address || "Google inbox"}
              </>
            ) : (
              "No email connected yet."
            )}
          </div>
          <div className="mt-4 flex gap-2">
            {!config.connected ? (
              <Button
                disabled={busy === "authorize"}
                onClick={onConnect}
                variant="primary"
              >
                {icon("login", "text-[17px]")} Connect Google
              </Button>
            ) : (
              <Button
                disabled={busy === "sync"}
                onClick={onSync}
                variant="primary"
              >
                {icon("sync", "text-[17px]")}{" "}
                {busy === "sync" ? "Syncing…" : "Sync email"}
              </Button>
            )}
          </div>
          {detections.length ? (
            <div className="mt-5 border-t border-[#e1e8ee] pt-4">
              <p className="text-xs font-bold uppercase tracking-[0.1em] text-[#6e8294]">
                Needs review ({detections.length})
              </p>
              <div className="mt-3 max-h-44 space-y-2 overflow-y-auto">
                {detections.slice(0, 6).map((detection) => (
                  <div
                    className="rounded-md border border-[#dde6ed] p-3"
                    key={
                      detection.detection_id ||
                      detection.source_email?.message_id
                    }
                  >
                    <p className="text-sm font-semibold text-[#18314b]">
                      {detection.detected_application?.company ||
                        "Unknown company"}
                    </p>
                    <p className="mt-1 truncate text-xs text-[#6e8294]">
                      {detection.detected_application?.title ||
                        detection.source_email?.subject ||
                        "Application update"}
                    </p>
                    <div className="mt-2 flex gap-2">
                      <button
                        className="text-xs font-bold text-[#0783a9]"
                        disabled={busy === "approve-detections"}
                        onClick={() => onApprove(detection)}
                        type="button"
                      >
                        Import
                      </button>
                      <button
                        className="text-xs text-[#6e8294]"
                        disabled={busy === "dismiss-detections"}
                        onClick={() => onDismiss(detection)}
                        type="button"
                      >
                        Dismiss
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function parseCsv(text) {
  const rows = String(text || "")
    .trim()
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) =>
      line
        .split(/,(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)/)
        .map((cell) => cell.trim().replace(/^\"|\"$/g, "")),
    );
  if (rows.length < 2) return [];
  const headers = rows
    .shift()
    .map((header) => header.toLowerCase().replace(/[^a-z0-9]+/g, "_"));
  return rows
    .map((row) =>
      Object.fromEntries(
        headers.map((header, index) => [header, row[index] || ""]),
      ),
    )
    .map((row) => ({
      title: row.title || row.role || row.job_title || "",
      company: row.company || row.employer || "",
      location: row.location || "",
      application_date:
        row.application_date || row.applied_on || row.date || "",
      apply_link: row.apply_link || row.url || row.job_url || "",
      notes: row.notes || "",
    }))
    .filter((row) => row.title && row.company);
}

function downloadCsv(items) {
  const header = [
    "title",
    "company",
    "location",
    "application_date",
    "status",
    "apply_link",
    "notes",
  ];
  const rows = items.map((item) =>
    [
      item.title,
      item.company,
      item.location,
      item.application_date,
      statusLabel(statusFor(item)),
      item.apply_link,
      item.notes,
    ]
      .map((value) => `"${String(value || "").replace(/"/g, '""')}"`)
      .join(","),
  );
  const blob = new Blob([[header.join(","), ...rows].join("\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "runr-job-tracker.csv";
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function TrackerPage() {
  const { request } = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState({
    query: searchParams.get("query") || "",
    from: "",
    until: "",
    jobType: "",
    status: "",
  });
  const [tab, setTab] = useState("active");
  const [view, setView] = useState("board");
  const [selectedItem, setSelectedItem] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [addBusy, setAddBusy] = useState(false);
  const [, setImportRef] = useState(null);
  const [emailOpen, setEmailOpen] = useState(false);
  const [feedback, setFeedback] = useState("");
  const {
    items,
    loading,
    error,
    refresh,
    updating,
    updateCard,
    deleteCard,
    emailIntegration,
    integrationBusy,
    loadEmailIntegration,
    refreshEmailIntegration,
    startGoogleEmailIntegration,
    syncEmailIntegration,
    approveEmailDetections,
    dismissEmailDetections,
  } = useTracker();

  const jobTypes = useMemo(
    () =>
      [
        ...new Set(
          items
            .map(
              (item) =>
                item.job_type ||
                item.tracker_table_row?.job_type ||
                item.tracker_table_row?.type,
            )
            .filter(Boolean),
        ),
      ].sort(),
    [items],
  );
  const visibleItems = useMemo(
    () =>
      items.filter((item) => {
        const currentStatus = statusFor(item);
        const archived = currentStatus === "withdrawn";
        const text =
          `${item.title || ""} ${item.company || ""} ${item.location || ""}`.toLocaleLowerCase();
        const jobType =
          item.job_type ||
          item.tracker_table_row?.job_type ||
          item.tracker_table_row?.type ||
          "";
        return (
          (tab === "archived"
            ? archived
            : tab === "active"
              ? !archived
              : false) &&
          (!filters.query ||
            text.includes(filters.query.toLocaleLowerCase())) &&
          (!filters.status || currentStatus === filters.status) &&
          (!filters.jobType || jobType === filters.jobType) &&
          matchesDateRange(item, filters.from, filters.until)
        );
      }),
    [filters, items, tab],
  );
  const totalActive = items.filter(
    (item) => statusFor(item) !== "withdrawn",
  ).length;
  const activeCounts = Object.fromEntries(
    BOARD_COLUMNS.map((column) => [
      column.key,
      items.filter(
        (item) =>
          statusFor(item) !== "withdrawn" &&
          column.statuses.includes(statusFor(item)),
      ).length,
    ]),
  );

  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    if (filters.query) next.set("query", filters.query);
    else next.delete("query");
    setSearchParams(next, { replace: true });
  }, [filters.query, searchParams, setSearchParams]);

  function changeFilters(next) {
    setFilters((current) => ({ ...current, ...next }));
  }
  async function handleStatusChange(item, nextStatus) {
    setFeedback("");
    await updateCard(item.review_id, { tracker_status: nextStatus });
    setSelectedItem((current) =>
      current?.review_id === item.review_id
        ? {
            ...current,
            tracker_status: nextStatus,
            application_status: statusLabel(nextStatus),
          }
        : current,
    );
  }
  async function handleDelete(item) {
    if (!window.confirm(`Delete ${item.title || "this application"}?`)) return;
    await deleteCard(item);
    setSelectedItem(null);
    setFeedback("Application deleted.");
  }
  async function handleArchive(item) {
    await handleStatusChange(item, "withdrawn");
    setSelectedItem(null);
    setTab("archived");
    setFeedback("Application archived.");
  }
  function handleApply(item) {
    if (item.apply_link)
      window.open(item.apply_link, "_blank", "noopener,noreferrer");
    handleStatusChange(item, "applied").catch(() => undefined);
  }
  async function createApplication(form) {
    setAddBusy(true);
    try {
      await request("/tracker/manual", { method: "POST", body: form });
      await refresh({ showLoading: false });
      setAddOpen(false);
      setFeedback("Application added.");
    } finally {
      setAddBusy(false);
    }
  }
  async function importApplications(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const rows = parseCsv(await file.text());
    if (!rows.length) {
      setFeedback("No valid rows found. Include title and company columns.");
      return;
    }
    setAddBusy(true);
    try {
      for (const row of rows)
        await request("/tracker/manual", { method: "POST", body: row });
      await refresh({ showLoading: false });
      setFeedback(
        `Imported ${rows.length} application${rows.length === 1 ? "" : "s"}.`,
      );
    } catch (requestError) {
      setFeedback(requestError.message || "Unable to import CSV.");
    } finally {
      setAddBusy(false);
    }
  }
  async function openEmailSync() {
    setEmailOpen((current) => !current);
    if (!emailIntegration) await loadEmailIntegration({ showLoading: true });
  }
  async function connectGoogle() {
    const result = await startGoogleEmailIntegration({
      folder: "INBOX",
      email_sync_start_date: new Date().toISOString().slice(0, 10),
    });
    if (result?.authorization_url)
      window.open(
        result.authorization_url,
        "tracker-google-oauth",
        "popup=yes,width=520,height=720",
      );
  }
  async function approveDetection(detection) {
    await approveEmailDetections([detection]);
    await refresh({ showLoading: false });
  }
  async function dismissDetection(detection) {
    await dismissEmailDetections([detection]);
  }

  return (
    <div className="-mx-4 -mt-6 min-h-[calc(100vh-4rem)] bg-[#f8fafc] text-[#18314b] md:-mx-8">
      <header className="border-b border-[#d6e0e8] bg-white px-4 pb-0 pt-8 md:px-8">
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div>
            <h1 className="text-[2rem] font-extrabold tracking-[-0.04em] text-[#173451]">
              Your Job Tracker
            </h1>
            <div className="mt-5 flex flex-wrap items-center gap-5 text-sm font-semibold">
              <span className="text-[#263d54]">
                <b className="mr-2 text-lg">{items.length}</b>TOTAL JOBS
              </span>
              <button
                className={`border-b-2 px-0 pb-4 ${tab === "active" ? "border-[#159fbd] text-[#159fbd]" : "border-transparent text-[#657b8e]"}`}
                onClick={() => setTab("active")}
                type="button"
              >
                Active
              </button>
              <button
                className={`border-b-2 px-0 pb-4 ${tab === "archived" ? "border-[#159fbd] text-[#159fbd]" : "border-transparent text-[#657b8e]"}`}
                onClick={() => setTab("archived")}
                type="button"
              >
                Archived
              </button>
            </div>
          </div>
          <div className="relative flex flex-wrap items-center gap-2 pb-4">
            <div className="flex rounded-md border border-[#cbd8e2] bg-white p-0.5">
              <button
                className={`rounded px-3 py-2 text-sm font-semibold ${view === "board" ? "bg-[#effafd] text-[#0783a9]" : "text-[#718398]"}`}
                onClick={() => setView("board")}
                type="button"
              >
                {icon("table_rows", "mr-1 text-[17px] align-middle")} Tracked
                Jobs
              </button>
              <button
                className={`rounded px-3 py-2 text-sm font-semibold ${view === "insights" ? "bg-[#effafd] text-[#0783a9]" : "text-[#718398]"}`}
                onClick={() => setView("insights")}
                type="button"
              >
                {icon("query_stats", "mr-1 text-[17px] align-middle")} Flow
                Chart
              </button>
            </div>
            <Button onClick={() => downloadCsv(visibleItems)}>
              {icon("upload", "rotate-180 text-[17px]")} Export CSV
            </Button>
            <label className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-md border border-[#b8c9d7] bg-white px-3 py-2 text-sm font-semibold text-[#087ea7] hover:bg-[#f0fbfd]">
              {icon("download", "text-[17px]")} Import CSV
              <input
                accept=".csv,text/csv"
                className="hidden"
                onChange={importApplications}
                ref={setImportRef}
                type="file"
              />
            </label>
            <Button onClick={() => setAddOpen(true)} variant="primary">
              {icon("add", "text-[18px]")} Add Application
            </Button>
            <div className="relative">
              <Button
                aria-expanded={emailOpen}
                onClick={openEmailSync}
                variant="quiet"
              >
                {icon("mail", "text-[18px]")} Connect Email
              </Button>
              {emailOpen ? (
                <EmailSyncPopover
                  busy={integrationBusy}
                  integration={emailIntegration}
                  onApprove={approveDetection}
                  onClose={() => setEmailOpen(false)}
                  onConnect={connectGoogle}
                  onDismiss={dismissDetection}
                  onSync={async () => {
                    await syncEmailIntegration();
                    await refresh({ showLoading: false });
                  }}
                />
              ) : null}
            </div>
          </div>
        </div>
      </header>
      {feedback ? (
        <div className="mx-4 mt-4 rounded-md border border-[#b8dfd3] bg-[#effbf7] px-4 py-3 text-sm font-semibold text-[#18775a] md:mx-8">
          {feedback}
        </div>
      ) : null}
      {loading ? (
        <div className="mx-4 mt-5 flex items-center gap-3 rounded-md border border-[#d7e1e9] bg-white px-5 py-5 text-sm text-[#6e8294] md:mx-8">
          {icon("progress_activity", "animate-spin text-[#159fbd]")}Loading your
          tracker…
        </div>
      ) : error ? (
        <div className="mx-4 mt-5 rounded-md border border-[#efb8be] bg-[#fff3f4] px-5 py-5 text-sm text-[#c43e50] md:mx-8">
          {error}
        </div>
      ) : (
        <>
          <SearchAndFilters
            filters={filters}
            jobTypes={jobTypes}
            onChange={changeFilters}
            onReset={() =>
              setFilters({
                query: "",
                from: "",
                until: "",
                jobType: "",
                status: "",
              })
            }
          />
          <div className="px-4 pt-4 md:px-8">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-4 text-sm text-[#62788c]">
                  <span>
                    <b className="text-[#18314b]">{visibleItems.length}</b>{" "}
                    visible
                  </span>
                  {BOARD_COLUMNS.map((column) => (
                    <button
                      className={`flex items-center gap-1.5 ${filters.status === column.statuses[0] ? "font-bold text-[#159fbd]" : ""}`}
                      key={column.key}
                      onClick={() =>
                        changeFilters({
                          status:
                            filters.status === column.statuses[0]
                              ? ""
                              : column.statuses[0],
                        })
                      }
                      type="button"
                    >
                      {icon(column.icon, "text-[16px]")}
                      {activeCounts[column.key]}
                    </button>
                  ))}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    onClick={() => refresh({ showLoading: false })}
                    variant="quiet"
                  >
                    {icon("refresh", "text-[17px]")} Refresh
                  </Button>
                  <span className="hidden text-sm text-[#62788c] sm:inline">
                    Visible columns (5)
                  </span>
                </div>
              </div>
              {view === "board" ? (
                <TrackerBoard
                  items={visibleItems}
                  onOpen={setSelectedItem}
                  onStatusChange={handleStatusChange}
                  updating={updating}
                />
              ) : (
                <Insights items={visibleItems} />
              )}
          </div>
        </>
      )}
      {selectedItem ? (
        <DetailDrawer
          item={selectedItem}
          onApply={handleApply}
          onArchive={handleArchive}
          onClose={() => setSelectedItem(null)}
          onDelete={handleDelete}
          onSaveNotes={(item, notes) => updateCard(item.review_id, { notes })}
          onStatusChange={handleStatusChange}
          request={request}
          updating={updating}
        />
      ) : null}
      {addOpen ? (
        <AddApplicationModal
          busy={addBusy}
          onClose={() => setAddOpen(false)}
          onCreate={createApplication}
        />
      ) : null}
    </div>
  );
}
