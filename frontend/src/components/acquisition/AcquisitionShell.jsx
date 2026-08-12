import { NavLink, useLocation } from "react-router-dom";

const NAV_ITEMS = [
  { label: "Overview", icon: "dashboard", to: "/admin/acquisition", end: true },
  { label: "Sources", icon: "lan", to: "/admin/acquisition/sources" },
  { label: "Imports", icon: "download", to: "/admin/acquisition/imports" },
  { label: "Jobs", icon: "work_history", to: "/admin/acquisition/jobs" },
  { label: "Companies", icon: "business", to: "/admin/acquisition/companies" },
  { label: "Enrichment", icon: "auto_awesome", to: "/admin/acquisition/enrichment" },
  { label: "Data Quality", icon: "fact_check", to: "/admin/acquisition/data-quality" },
  { label: "Duplicates", icon: "content_copy", to: "/admin/acquisition/duplicates" },
  { label: "Publication", icon: "publish", to: "/admin/acquisition/publication" },
  { label: "Live Catalog", icon: "language", to: "/admin/acquisition/live-catalog" },
  { label: "Audit", icon: "manage_search", to: "/admin/acquisition/audit" },
];

export default function AcquisitionShell({ title, description, children }) {
  const location = useLocation();

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6">
      {(title || description) ? <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
            Acquisition Operations
          </p>
          <h1 className="mt-2 font-headline text-2xl font-extrabold tracking-tight text-on-surface md:text-3xl">
            {title}
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-on-surface-variant">
            {description}
          </p>
        </div>
        <span className="inline-flex w-fit items-center gap-2 rounded-full border border-outline-variant/20 bg-surface-container-low px-3 py-2 text-xs font-semibold text-on-surface-variant">
          <span className="h-2 w-2 rounded-full bg-primary" />
          Manual operations · explicit confirmation
        </span>
      </header> : null}

      <nav
        aria-label="Acquisition Operations sections"
        className="flex gap-1 overflow-x-auto rounded-2xl bg-surface-container-low p-1.5"
      >
        {NAV_ITEMS.map((item) => (
          <NavLink
            aria-current={(
              item.end
                ? location.pathname === item.to
                : location.pathname === item.to || location.pathname.startsWith(`${item.to}/`)
            ) ? "page" : undefined}
            className={({ isActive }) => [
              "inline-flex shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold transition-colors",
              isActive
                ? "bg-surface-container-lowest text-on-surface shadow-soft"
                : "text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface",
            ].join(" ")}
            end={item.end}
            key={item.to}
            to={item.to}
          >
            <span className="material-symbols-outlined text-[18px]">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>

      {children}
    </div>
  );
}
