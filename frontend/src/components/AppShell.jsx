import { useEffect, useState } from "react";
import { matchPath, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useTheme } from "../context/ThemeContext";

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
  {
    label: "Admin",
    icon: "admin_panel_settings",
    to: "/admin",
    matchers: [{ path: "/admin", end: false }],
  },
];

const footerLinks = [
  { label: "Support", icon: "contact_support" },
  { label: "Documentation", icon: "menu_book" },
];

function isNavItemActive(pathname, item) {
  return (item.matchers || []).some((matcher) => Boolean(matchPath(matcher, pathname)));
}

function SidebarLink({ item, onNavigate }) {
  const location = useLocation();
  const isActive = isNavItemActive(location.pathname, item);

  return (
    <NavLink
      aria-current={isActive ? "page" : undefined}
      className={() =>
        [
          "ml-4 flex items-center gap-3 py-3 pl-6 text-sm font-bold tracking-tight transition-all duration-300",
          isActive
            ? "translate-x-1 rounded-l-full bg-white text-primary shadow-sm"
            : "text-on-surface-variant hover:text-primary active:translate-x-1",
        ].join(" ")
      }
      onClick={onNavigate}
      to={item.to}
    >
      {() => (
        <>
          <span
            className="material-symbols-outlined text-lg"
            style={isActive ? { fontVariationSettings: "'FILL' 1" } : undefined}
          >
            {item.icon}
          </span>
          <span>{item.label}</span>
        </>
      )}
    </NavLink>
  );
}

function SidebarContents({ onClose, onDisconnect, onStartRun, shellUser, showSignOut = false }) {
  function handleStartRun() {
    onStartRun();
    onClose?.();
  }

  function handleDisconnect() {
    onDisconnect();
    onClose?.();
  }

  return (
    <>
      <div className="px-6">
        <div className="mb-6 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded bg-teal-600 text-white">
              <span className="material-symbols-outlined text-[20px]">work</span>
            </div>
            <div>
              <h1 className="font-headline text-3xl font-extrabold tracking-tighter text-on-surface">
                runr.
              </h1>
              <p className="text-xs font-medium text-on-surface-variant">High Performance Ops</p>
            </div>
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
          className="mb-8 flex w-full items-center justify-center gap-2 rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:opacity-90 active:scale-[0.98]"
          onClick={handleStartRun}
          type="button"
        >
          <span className="material-symbols-outlined text-[18px]">add</span>
          Start New Run
        </button>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto">
        {navItems.map((item) => (
          <SidebarLink key={item.label} item={item} onNavigate={onClose} />
        ))}
      </nav>

      <div className="mt-auto px-6">
        {footerLinks.map((item) => (
          <button
            key={item.label}
            className="flex items-center gap-3 py-2 text-sm font-bold tracking-tight text-on-surface-variant transition-all hover:text-primary"
            type="button"
          >
            <span className="material-symbols-outlined text-lg">{item.icon}</span>
            {item.label}
          </button>
        ))}
        {showSignOut ? (
          <button
            className="mt-3 flex items-center gap-3 py-2 text-sm font-bold tracking-tight text-on-surface-variant transition-all hover:text-primary"
            onClick={handleDisconnect}
            type="button"
          >
            <span className="material-symbols-outlined text-lg">logout</span>
            Sign Out
          </button>
        ) : null}
        <div className="mt-4 flex items-center gap-3 py-2">
          <img
            alt={shellUser.name}
            className="h-8 w-8 rounded-full border border-outline-variant/30 object-cover"
            src={shellUser.avatar}
          />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-on-surface">{shellUser.name}</p>
            <p className="truncate text-xs text-on-surface-variant">{shellUser.subtitle}</p>
          </div>
        </div>
      </div>
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

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname, location.search]);

  const shellUser = {
    name: user?.display_name || user?.email || "Disconnected",
    subtitle: user?.email || (status === "connected" ? "" : "Backend not connected"),
    avatar:
      "https://lh3.googleusercontent.com/aida-public/AB6AXuDeh_GwQ1tyaiUiDvT71g8HFsHEJ5gVS679pFkoWXtNfLFzoFMzeRd4HMomF0XAuq8mfaec3nzeharFzxat1NNtR0s1NGQ8OmsZwjVfuKfX6PFUGr0duTgyC5ItHvMrLbUKmVICPFeD-iyiVRX9E4uWBHxGmGTQWtgvLOpUORp77hhc30XrStvTwhM64ft7fw0EhK8zMcSjQubBgd6isZ-HmuKrN7-OkTq3cDe4ub5eT-F6nWziFtgteycj_e7n3xQafjsJUdJbHiU",
  };

  return (
    <div className="min-h-screen bg-background text-on-surface">
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
          "fixed inset-y-0 left-0 z-50 flex w-72 flex-col bg-surface-container-low py-6 shadow-soft transition-transform duration-300 md:hidden",
          mobileNavOpen ? "translate-x-0" : "-translate-x-full",
        ].join(" ")}
      >
        <SidebarContents
          onClose={() => setMobileNavOpen(false)}
          onDisconnect={disconnect}
          onStartRun={() => navigate("/workspaces")}
          shellUser={shellUser}
          showSignOut
        />
      </aside>

      <aside className="fixed left-0 top-0 hidden h-screen w-64 flex-col bg-surface-container-low py-8 md:flex">
        <SidebarContents
          onDisconnect={disconnect}
          onStartRun={() => navigate("/workspaces")}
          shellUser={shellUser}
        />
      </aside>

      <div className="min-h-screen md:ml-64">
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

          <div className="flex items-center gap-3">
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
            ) : (
              <>
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
                  className="rounded-full p-1 text-on-surface-variant transition-colors hover:bg-surface-container-low hover:text-primary"
                  type="button"
                >
                  <span className="material-symbols-outlined">help</span>
                </button>
                <button
                  className="hidden text-sm text-on-surface-variant transition-colors hover:text-primary sm:block"
                  onClick={disconnect}
                  type="button"
                >
                  Sign Out
                </button>
                <img
                  alt={shellUser.name}
                  className="h-8 w-8 rounded-full border border-outline-variant/30 object-cover"
                  src={shellUser.avatar}
                />
              </>
            )}
          </div>
        </header>

        <main className="mx-auto max-w-7xl px-4 pb-12 pt-6 md:px-8">{children}</main>
      </div>
    </div>
  );
}
