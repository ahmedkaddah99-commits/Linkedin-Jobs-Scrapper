import { useEffect, useState } from "react";
import { matchPath, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useTheme } from "../context/ThemeContext";

const DESKTOP_SIDEBAR_STORAGE_KEY = "runr.sidebarCollapsed";

const navItems = [
  {
    label: "Dashboard",
    icon: "dashboard",
    to: "/",
    matchers: [
      { path: "/", end: true },
      { path: "/dashboard", end: true },
    ],
  },
  {
    label: "Workspaces",
    icon: "workspaces",
    to: "/workspaces",
    matchers: [{ path: "/workspaces", end: false }],
  },
  {
    label: "Quick Apply",
    icon: "bolt",
    to: "/quick-apply",
    matchers: [{ path: "/quick-apply", end: false }],
  },
  {
    label: "Runs",
    icon: "speed",
    to: "/runs",
    matchers: [
      { path: "/runs", end: false },
      { path: "/runs/:runId", end: true },
    ],
  },
  {
    label: "Review Queue",
    icon: "fact_check",
    to: "/review-queue",
    matchers: [{ path: "/review-queue", end: false }],
  },
  {
    label: "Tracker",
    icon: "table_rows",
    to: "/tracker",
    matchers: [{ path: "/tracker", end: false }],
  },
  {
    label: "Documents",
    icon: "inventory_2",
    to: "/documents",
    matchers: [
      { path: "/documents", end: false },
      { path: "/artifacts", end: false },
    ],
  },
  {
    label: "Referrals",
    icon: "group_add",
    to: "/referrals",
    matchers: [{ path: "/referrals", end: false }],
  },
  {
    label: "Settings",
    icon: "settings",
    to: "/settings",
    matchers: [
      { path: "/settings", end: false },
      { path: "/cv-studio", end: false },
    ],
  },
];

const topRibbonItems = [
  { label: "Support", icon: "contact_support" },
  { label: "Documentation", icon: "menu_book" },
  {
    label: "Admin",
    icon: "admin_panel_settings",
    to: "/admin",
    matchers: [{ path: "/admin", end: false }],
  },
];

function isNavItemActive(pathname, item) {
  return (item.matchers || []).some((matcher) => Boolean(matchPath(matcher, pathname)));
}

function BrandMark() {
  return (
    <div aria-hidden="true" className="shell-brand-mark">
      <span />
      <span />
      <span />
    </div>
  );
}

function HoverLabel({ label }) {
  return <span className="shell-sidebar__tooltip">{label}</span>;
}

function SidebarLink({ collapsed = false, item, onNavigate }) {
  const location = useLocation();
  const isActive = isNavItemActive(location.pathname, item);

  return (
    <NavLink
      aria-current={isActive ? "page" : undefined}
      aria-label={collapsed ? item.label : undefined}
      className={["shell-nav-link", isActive ? "is-active" : "", collapsed ? "is-collapsed" : ""].join(" ")}
      onClick={onNavigate}
      title={collapsed ? item.label : undefined}
      to={item.to}
    >
      <span
        className="material-symbols-outlined shell-nav-link__icon"
        style={isActive ? { fontVariationSettings: "'FILL' 1" } : undefined}
      >
        {item.icon}
      </span>
      {!collapsed ? <span className="shell-nav-link__label">{item.label}</span> : null}
      {collapsed ? <HoverLabel label={item.label} /> : null}
    </NavLink>
  );
}

function SidebarActionButton({ collapsed = false, icon, label, onClick, type = "button" }) {
  return (
    <button
      aria-label={collapsed ? label : undefined}
      className={["shell-utility-link", collapsed ? "is-collapsed" : ""].join(" ")}
      onClick={onClick}
      title={collapsed ? label : undefined}
      type={type}
    >
      <span className="material-symbols-outlined shell-utility-link__icon">{icon}</span>
      {!collapsed ? <span>{label}</span> : null}
      {collapsed ? <HoverLabel label={label} /> : null}
    </button>
  );
}

function TopRibbonAction({ item }) {
  const location = useLocation();
  const isActive = item.to ? isNavItemActive(location.pathname, item) : false;
  const className = [
    "inline-flex items-center gap-2 rounded-full border px-3 py-2 text-sm font-medium transition-colors",
    isActive
      ? "border-primary/30 bg-primary/10 text-primary"
      : "border-outline-variant/20 bg-surface-container-low text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface",
  ].join(" ");

  const content = (
    <>
      <span
        className="material-symbols-outlined text-[20px]"
        style={isActive ? { fontVariationSettings: "'FILL' 1" } : undefined}
      >
        {item.icon}
      </span>
      <span className="hidden lg:inline">{item.label}</span>
    </>
  );

  if (item.to) {
    return (
      <NavLink aria-label={item.label} className={className} title={item.label} to={item.to}>
        {content}
      </NavLink>
    );
  }

  return (
    <button aria-label={item.label} className={className} title={item.label} type="button">
      {content}
    </button>
  );
}

function SidebarContents({
  collapsed = false,
  isDesktop = false,
  onClose,
  onStartRun,
  onToggleCollapse,
}) {
  const isCollapsedRail = isDesktop && collapsed;

  function handleStartRun() {
    onStartRun();
    onClose?.();
  }

  return (
    <>
      <div className={["shell-sidebar__header", isCollapsedRail ? "is-collapsed" : ""].join(" ")}>
        <div className={["shell-sidebar__brand-row", isCollapsedRail ? "is-collapsed" : ""].join(" ")}>
          <div className={["shell-sidebar__brand", isCollapsedRail ? "is-collapsed" : ""].join(" ")}>
            <BrandMark />
            {!isCollapsedRail ? (
              <div className="shell-sidebar__brand-copy">
                <h1 className="shell-sidebar__title">runr.</h1>
                <p className="shell-sidebar__subtitle">High Performance Ops</p>
              </div>
            ) : null}
          </div>
          {onClose ? (
            <button
              aria-label="Close navigation"
              className="rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-primary"
              onClick={onClose}
              type="button"
            >
              <span className="material-symbols-outlined">close</span>
            </button>
          ) : null}
        </div>

        <button
          aria-label={isCollapsedRail ? "Start New Run" : undefined}
          className={["shell-primary-action", isCollapsedRail ? "is-collapsed" : ""].join(" ")}
          onClick={handleStartRun}
          title={isCollapsedRail ? "Start New Run" : undefined}
          type="button"
        >
          <span className="material-symbols-outlined shell-primary-action__icon">add</span>
          {!isCollapsedRail ? <span>Start New Run</span> : null}
          {isCollapsedRail ? <HoverLabel label="Start New Run" /> : null}
        </button>
      </div>

      <nav className="shell-sidebar__nav">
        {navItems.map((item) => (
          <SidebarLink collapsed={isCollapsedRail} item={item} key={item.label} onNavigate={onClose} />
        ))}
      </nav>

      {isDesktop ? (
        <div className="shell-sidebar__footer">
          <SidebarActionButton
            collapsed={isCollapsedRail}
            icon={isCollapsedRail ? "keyboard_double_arrow_right" : "keyboard_double_arrow_left"}
            label={isCollapsedRail ? "Expand Menu" : "Collapse Menu"}
            onClick={onToggleCollapse}
          />
        </div>
      ) : null}
    </>
  );
}

export default function AppShell({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const runMatch = matchPath({ path: "/runs/:runId", end: true }, location.pathname);
  const isRunDetail = Boolean(runMatch);
  const { disconnect, status, user } = useSession();
  const { isDark, toggleTheme } = useTheme();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [desktopSidebarCollapsed, setDesktopSidebarCollapsed] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.localStorage.getItem(DESKTOP_SIDEBAR_STORAGE_KEY) === "true";
  });

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname, location.search]);

  useEffect(() => {
    window.localStorage.setItem(
      DESKTOP_SIDEBAR_STORAGE_KEY,
      desktopSidebarCollapsed ? "true" : "false",
    );
  }, [desktopSidebarCollapsed]);

  const shellUser = {
    name: user?.display_name || user?.email || "Disconnected",
    subtitle: user?.email || (status === "connected" ? "" : "Backend not connected"),
    avatar:
      "https://lh3.googleusercontent.com/aida-public/AB6AXuDeh_GwQ1tyaiUiDvT71g8HFsHEJ5gVS679pFkoWXtNfLFzoFMzeRd4HMomF0XAuq8mfaec3nzeharFzxat1NNtR0s1NGQ8OmsZwjVfuKfX6PFUGr0duTgyC5ItHvMrLbUKmVICPFeD-iyiVRX9E4uWBHxGmGTQWtgvLOpUORp77hhc30XrStvTwhM64ft7fw0EhK8zMcSjQubBgd6isZ-HmuKrN7-OkTq3cDe4ub5eT-F6nWziFtgteycj_e7n3xQafjsJUdJbHiU",
  };

  return (
    <div
      className="app-shell min-h-screen bg-background text-on-surface"
      data-sidebar-collapsed={desktopSidebarCollapsed ? "true" : "false"}
    >
      <div
        aria-hidden={!mobileNavOpen}
        className={[
          "fixed inset-0 z-40 bg-[#07111f]/45 transition-opacity duration-300 md:hidden",
          mobileNavOpen ? "opacity-100" : "pointer-events-none opacity-0",
        ].join(" ")}
        onClick={() => setMobileNavOpen(false)}
      />

      <aside
        className={[
          "shell-sidebar shell-sidebar--mobile fixed inset-y-0 left-0 z-50 flex flex-col shadow-soft transition-transform duration-300 md:hidden",
          mobileNavOpen ? "translate-x-0" : "-translate-x-full",
        ].join(" ")}
      >
        <SidebarContents
          onClose={() => setMobileNavOpen(false)}
          onStartRun={() => navigate("/workspaces")}
        />
      </aside>

      <aside className="app-shell__desktop-sidebar shell-sidebar hidden flex-col md:flex">
        <SidebarContents
          collapsed={desktopSidebarCollapsed}
          isDesktop
          onStartRun={() => navigate("/workspaces")}
          onToggleCollapse={() => setDesktopSidebarCollapsed((currentValue) => !currentValue)}
        />
      </aside>

      <div className="app-shell__main">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-outline-variant/10 bg-background/95 px-4 py-4 backdrop-blur-[20px] md:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <button
              aria-label="Open navigation"
              className="rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container-low hover:text-primary md:hidden"
              onClick={() => setMobileNavOpen(true)}
              type="button"
            >
              <span className="material-symbols-outlined">menu</span>
            </button>
            {isRunDetail ? (
              <>
                <button
                  className="rounded p-1 text-on-surface-variant transition-colors hover:text-primary"
                  onClick={() => navigate(-1)}
                  type="button"
                >
                  <span className="material-symbols-outlined">arrow_back</span>
                </button>
                <div className="h-4 w-px bg-outline-variant/30" />
                <div className="min-w-0 text-base">
          <div className="flex items-baseline gap-3 truncate">
                    <span className="text-on-surface-variant">Run Detail</span>
                    <span className="text-on-surface-variant/40">/</span>
                    <span className="truncate font-bold tracking-tight text-primary">
                      {runMatch?.params?.runId}
                    </span>
                  </div>
                </div>
              </>
            ) : (
              <div className="md:hidden">
                <h1 className="font-headline text-lg font-extrabold tracking-tight text-on-surface">
                  runr.
                </h1>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2 md:gap-3">
            {topRibbonItems.map((item) => (
              <TopRibbonAction item={item} key={item.label} />
            ))}
            {isRunDetail ? (
              <>
                <button
                  className="rounded p-2 text-on-surface-variant transition-colors hover:bg-surface-container-low hover:text-primary"
                  type="button"
                >
                  <span className="material-symbols-outlined text-xl">share</span>
                </button>
                <button
                  className="rounded p-2 text-on-surface-variant transition-colors hover:bg-surface-container-low hover:text-primary"
                  type="button"
                >
                  <span className="material-symbols-outlined text-xl">more_vert</span>
                </button>
              </>
            ) : null}
            <button
              className="rounded-full p-1 text-on-surface-variant transition-colors hover:bg-surface-container-low hover:text-primary"
              onClick={toggleTheme}
              title={isDark ? "Switch to light mode" : "Switch to dark mode"}
              type="button"
            >
              <span className="material-symbols-outlined">
                {isDark ? "light_mode" : "dark_mode"}
              </span>
            </button>
            <button
              className="rounded-full p-1 text-on-surface-variant transition-colors hover:bg-surface-container-low hover:text-primary"
              type="button"
            >
              <span className="material-symbols-outlined">notifications</span>
            </button>
            <button
              className="hidden text-sm text-on-surface-variant transition-colors hover:text-primary sm:block"
              onClick={disconnect}
              type="button"
            >
              Sign Out
            </button>
            <div className="hidden min-w-0 text-right xl:block">
              <p className="truncate text-sm font-semibold text-on-surface">{shellUser.name}</p>
              <p className="truncate text-xs text-on-surface-variant">{shellUser.subtitle}</p>
            </div>
            <img
              alt={shellUser.name}
              className="h-8 w-8 rounded-full border border-outline-variant/30 object-cover"
              src={shellUser.avatar}
            />
          </div>
        </header>

        <main className="w-full px-4 pb-12 pt-6 md:px-8">{children}</main>
      </div>
    </div>
  );
}
