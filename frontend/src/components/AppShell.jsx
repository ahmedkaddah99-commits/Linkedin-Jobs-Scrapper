import { useEffect, useId, useRef, useState } from "react";
import { Show, SignInButton, SignUpButton, UserButton, useUser } from "@clerk/react";
import { matchPath, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useTheme } from "../context/ThemeContext";
import { isAdminUser } from "../lib/auth";
import { currentEntryAssetPath, fetchLatestEntryAssetPath } from "../lib/deployVersion";
import { personalizedJobsExperienceEnabled } from "../lib/personalizedJobs";
import { requestRouteNavigation, resolveRouteParent } from "../lib/routeParents";

const DESKTOP_SIDEBAR_STORAGE_KEY = "runr.sidebarCollapsed";

export const careerAssetSections = [
  {
    label: "Asset Library",
    description: "Upload and manage source files.",
    icon: "folder_open",
    to: "/documents",
  },
  {
    label: "Career Evidence",
    description: "Extract, review, and map your experience.",
    icon: "fact_check",
    to: "/career-evidence",
  },
  {
    label: "CV Studio",
    description: "Edit and export your latest CV draft.",
    icon: "description",
    to: "/cv-studio",
  },
];

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
    matchers: [
      { path: "/workspaces", end: false },
      { path: "/job-workspaces/:runId/:jobId", end: true },
    ],
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
    label: "Tracker",
    icon: "table_rows",
    to: "/tracker",
    matchers: [{ path: "/tracker", end: false }],
  },
  {
    label: "Career Assets",
    icon: "inventory_2",
    to: "/career-evidence",
    matchers: [
      { path: "/documents", end: false },
      { path: "/artifacts", end: false },
      { path: "/career-evidence", end: false },
      { path: "/career-memory", end: false },
      { path: "/cv-studio", end: false },
    ],
  },
  {
    label: "Referrals",
    icon: "group_add",
    to: "/referrals",
    matchers: [{ path: "/referrals", end: false }],
  },
  {
    label: "Account",
    icon: "account_circle",
    to: "/settings",
    matchers: [
      { path: "/settings", end: false },
    ],
  },
  {
    label: "Pricing",
    icon: "diamond",
    to: "/pricing",
    matchers: [{ path: "/pricing", end: false }],
  },
];

const personalizedNavItems = personalizedJobsExperienceEnabled
  ? [
    navItems[0],
    {
      label: "Jobs",
      icon: "work_outline",
      to: "/jobs",
      matchers: [{ path: "/jobs", end: false }, { path: "/onboarding", end: false }],
    },
    ...navItems.slice(1),
  ]
  : navItems;

const secondaryTopRibbonItems = [
  {
    label: "Pricing",
    icon: "diamond",
    to: "/pricing",
    matchers: [{ path: "/pricing", end: false }],
  },
  { label: "Support", icon: "contact_support" },
  { label: "Documentation", icon: "menu_book" },
  {
    adminOnly: true,
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
  const navigate = useNavigate();
  const isActive = isNavItemActive(location.pathname, item);
  const parentRoute = isActive ? resolveRouteParent(location) : "";

  function handleClick(event) {
    if (!isActive) {
      onNavigate?.();
      return;
    }
    event.preventDefault();
    if (!parentRoute || !requestRouteNavigation(parentRoute)) {
      return;
    }
    navigate(parentRoute);
    onNavigate?.();
  }

  return (
    <NavLink
      aria-current={isActive ? "page" : undefined}
      aria-label={collapsed ? item.label : undefined}
      className={["shell-nav-link", isActive ? "is-active" : "", collapsed ? "is-collapsed" : ""].join(" ")}
      onClick={handleClick}
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

function CareerAssetsNavigation() {
  return (
    <nav
      aria-label="Career Assets sections"
      className="mx-auto mb-2 grid w-full max-w-5xl gap-2 rounded-2xl bg-surface-container-low p-2 sm:grid-cols-3"
    >
      {careerAssetSections.map((section) => (
        <NavLink
          className={({ isActive }) => [
            "flex items-start gap-3 rounded-xl px-4 py-3 transition-colors",
            isActive
              ? "bg-surface-container-lowest text-on-surface shadow-soft"
              : "text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface",
          ].join(" ")}
          key={section.to}
          to={section.to}
        >
          {({ isActive }) => (
            <>
              <span
                className="material-symbols-outlined mt-0.5 text-[20px] text-primary"
                style={isActive ? { fontVariationSettings: "'FILL' 1" } : undefined}
              >
                {section.icon}
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold">{section.label}</span>
                <span className="mt-0.5 block text-xs leading-5 text-on-surface-variant">
                  {section.description}
                </span>
              </span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

function getTopRibbonActionClassName(isActive) {
  return [
    "top-ribbon__action inline-flex items-center gap-2 rounded-full border px-3 py-2 text-sm font-medium transition-colors",
    isActive
      ? "border-primary/30 bg-primary/10 text-primary"
      : "border-outline-variant/20 bg-surface-container-low text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface",
  ].join(" ");
}

function SecondaryTopRibbonMenuItem({ item }) {
  const location = useLocation();
  const isActive = item.to ? isNavItemActive(location.pathname, item) : false;
  const className = [
    "flex w-full items-center gap-3 rounded-2xl px-3 py-2 text-left text-sm font-medium transition-colors",
    isActive
      ? "bg-primary/10 text-primary"
      : "text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface",
  ].join(" ");

  const content = (
    <>
      <span
        className="material-symbols-outlined text-[20px]"
        style={isActive ? { fontVariationSettings: "'FILL' 1" } : undefined}
      >
        {item.icon}
      </span>
      <span>{item.label}</span>
    </>
  );

  if (item.to) {
    return (
      <NavLink
        aria-current={isActive ? "page" : undefined}
        className={className}
        title={item.label}
        to={item.to}
      >
        {content}
      </NavLink>
    );
  }

  return (
    <button className={className} title={item.label} type="button">
      {content}
    </button>
  );
}

function TopRibbonDisclosure({ items }) {
  const location = useLocation();
  const menuId = useId();
  const buttonRef = useRef(null);
  const containerRef = useRef(null);
  const menuRef = useRef(null);
  const [isOpen, setIsOpen] = useState(false);
  const hasActiveItem = items.some((item) => item.to && isNavItemActive(location.pathname, item));

  useEffect(() => {
    setIsOpen(false);
  }, [location.pathname, location.search]);

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    function handlePointerDown(event) {
      if (containerRef.current?.contains(event.target)) {
        return;
      }
      setIsOpen(false);
    }

    function handleKeyDown(event) {
      if (event.key !== "Escape") {
        return;
      }
      event.preventDefault();
      setIsOpen(false);
      buttonRef.current?.focus();
    }

    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  function moveFocusToFirstItem() {
    requestAnimationFrame(() => {
      menuRef.current?.querySelector("a, button")?.focus();
    });
  }

  function handleButtonClick() {
    setIsOpen((currentValue) => !currentValue);
  }

  function handleButtonKeyDown(event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
      }
      moveFocusToFirstItem();
    }
  }

  function handleBlurCapture(event) {
    if (!isOpen) {
      return;
    }

    const nextFocusedElement = event.relatedTarget;
    if (!nextFocusedElement || containerRef.current?.contains(nextFocusedElement)) {
      return;
    }

    setIsOpen(false);
  }

  return (
    <div className="relative" onBlurCapture={handleBlurCapture} ref={containerRef}>
      <button
        aria-label="More"
        aria-controls={menuId}
        aria-expanded={isOpen ? "true" : "false"}
        aria-haspopup="true"
        className={getTopRibbonActionClassName(isOpen || hasActiveItem)}
        onClick={handleButtonClick}
        onKeyDown={handleButtonKeyDown}
        ref={buttonRef}
        title="More"
        type="button"
      >
        <span
          className="material-symbols-outlined text-[20px]"
          style={isOpen || hasActiveItem ? { fontVariationSettings: "'FILL' 1" } : undefined}
        >
          more_horiz
        </span>
      </button>

      {isOpen ? (
        <div
          aria-label="More actions"
          className="top-ribbon__menu absolute right-0 top-[calc(100%+0.5rem)] z-50 flex min-w-[14rem] flex-col gap-1 rounded-[1.5rem] border border-outline-variant/20 bg-background/95 p-2 shadow-soft backdrop-blur-[20px]"
          id={menuId}
          ref={menuRef}
        >
          {items.map((item) => (
            <SecondaryTopRibbonMenuItem item={item} key={item.label} />
          ))}
        </div>
      ) : null}
    </div>
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
        {personalizedNavItems.map((item) => (
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

export default function AppShell({ children, muteSidebar = false }) {
  const navigate = useNavigate();
  const location = useLocation();
  const runMatch = matchPath({ path: "/runs/:runId", end: true }, location.pathname);
  const isRunDetail = Boolean(runMatch);
  const routeParent = resolveRouteParent(location);
  const isCareerAssetsRoute = navItems
    .find((item) => item.label === "Career Assets")
    ?.matchers.some((matcher) => Boolean(matchPath(matcher, location.pathname)));
  const { status, user } = useSession();
  const { user: clerkUser } = useUser();
  const { isDark, toggleTheme } = useTheme();
  const isAdmin = isAdminUser(user);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [desktopSidebarCollapsed, setDesktopSidebarCollapsed] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.localStorage.getItem(DESKTOP_SIDEBAR_STORAGE_KEY) === "true";
  });
  const [deployUpdateAvailable, setDeployUpdateAvailable] = useState(false);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname, location.search]);

  useEffect(() => {
    window.localStorage.setItem(
      DESKTOP_SIDEBAR_STORAGE_KEY,
      desktopSidebarCollapsed ? "true" : "false",
    );
  }, [desktopSidebarCollapsed]);

  useEffect(() => {
    if (typeof window === "undefined" || typeof document === "undefined") {
      return undefined;
    }
    const loadedEntryAsset = currentEntryAssetPath(document);
    const fetchImpl = window.fetch?.bind(window);
    if (!loadedEntryAsset || !fetchImpl) {
      return undefined;
    }

    let cancelled = false;
    async function checkForNewDeploy() {
      if (document.visibilityState === "hidden") {
        return;
      }
      try {
        const latestEntryAsset = await fetchLatestEntryAssetPath({
          baseUrl: window.location.href,
          fetchImpl,
        });
        if (!cancelled && latestEntryAsset && latestEntryAsset !== loadedEntryAsset) {
          setDeployUpdateAvailable(true);
        }
      } catch {
        // Update checks are best-effort; a failed check should not affect normal app use.
      }
    }

    function handleVisibilityChange() {
      if (document.visibilityState === "visible") {
        checkForNewDeploy();
      }
    }

    window.addEventListener("focus", checkForNewDeploy);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    const intervalId = window.setInterval(checkForNewDeploy, 120000);
    checkForNewDeploy();

    return () => {
      cancelled = true;
      window.removeEventListener("focus", checkForNewDeploy);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.clearInterval(intervalId);
    };
  }, []);

  const normalizedPlanId = String(
    user?.plan_id || clerkUser?.publicMetadata?.plan_id || "none",
  ).trim().toLowerCase() || "none";
  const planBadgeLabel = normalizedPlanId === "free"
    ? "Free"
    : normalizedPlanId === "scale"
    ? "Scale"
    : normalizedPlanId === "momentum"
      ? "Momentum"
      : normalizedPlanId === "launch"
        ? "Launch"
        : "Choose plan";
  const shellUser = {
    name: user?.display_name || user?.email || "",
    subtitle: user?.email || "",
  };
  const topRibbonItems = secondaryTopRibbonItems.filter((item) => !item.adminOnly || isAdmin);

  return (
    <div
      className={[
        "app-shell min-h-screen bg-background text-on-surface",
        muteSidebar ? "app-shell--sidebar-muted" : "",
      ].join(" ")}
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
        <header
          className="top-ribbon top-ribbon--teal sticky top-0 z-30 flex h-16 items-center justify-between overflow-visible border-b border-outline-variant/10 bg-background/95 px-4 py-4 backdrop-blur-[20px] transition-all duration-200 md:px-8"
        >
          <div className="flex min-w-0 items-center gap-3">
            <button
              aria-label="Open navigation"
              className="rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container-low hover:text-primary disabled:pointer-events-none disabled:opacity-40 md:hidden"
              disabled={muteSidebar}
              onClick={() => setMobileNavOpen(true)}
              type="button"
            >
              <span className="material-symbols-outlined">menu</span>
            </button>
            {isRunDetail ? (
              <>
                <button
                  aria-label="Back to runs"
                  className="rounded p-1 text-on-surface-variant transition-colors hover:text-primary"
                  onClick={() => {
                    if (routeParent && requestRouteNavigation(routeParent)) {
                      navigate(routeParent);
                    }
                  }}
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
            <TopRibbonDisclosure items={topRibbonItems} />
            {isRunDetail ? (
              <>
                <button
                  className="rounded p-2 text-on-surface-variant transition-colors hover:bg-surface-container-low hover:text-primary"
                  type="button"
                >
                  <span className="material-symbols-outlined text-xl">share</span>
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
            <Show when="signed-out">
              <div className="hidden items-center gap-2 sm:flex">
                <SignInButton fallbackRedirectUrl="/" mode="modal">
                  <button
                    className="rounded-full border border-outline-variant/20 bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                    type="button"
                  >
                    Sign In
                  </button>
                </SignInButton>
                <SignUpButton fallbackRedirectUrl="/" mode="modal">
                  <button
                    className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90"
                    type="button"
                  >
                    Create Account
                  </button>
                </SignUpButton>
              </div>
            </Show>
            <Show when="signed-in">
              <>
                {status === "connected" ? (
                  <button
                    aria-label={`${planBadgeLabel} plan - view pricing`}
                    className="top-ribbon__action inline-flex items-center gap-2 rounded-full border border-outline-variant/20 bg-surface-container-low p-2 text-xs font-bold uppercase tracking-[0.18em] text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface sm:px-3 sm:py-1.5"
                    onClick={() => navigate("/pricing")}
                    title={`${planBadgeLabel} plan - view pricing`}
                    type="button"
                  >
                    <span className="material-symbols-outlined text-[16px]">diamond</span>
                    <span className="hidden sm:inline">{planBadgeLabel}</span>
                  </button>
                ) : null}
                <div className="hidden min-w-0 text-right xl:block">
                  <p className="truncate text-sm font-semibold text-on-surface">{shellUser.name}</p>
                  <p className="truncate text-xs text-on-surface-variant">{shellUser.subtitle}</p>
                </div>
                <div className="shrink-0">
                  <UserButton />
                </div>
              </>
            </Show>
          </div>
        </header>

        {deployUpdateAvailable ? (
          <div
            className="mx-4 mt-4 flex flex-col gap-3 rounded-2xl border border-primary/20 bg-primary/10 px-4 py-3 text-sm text-on-surface shadow-soft md:mx-8 md:flex-row md:items-center md:justify-between"
            role="status"
          >
            <div>
              <div className="font-semibold text-on-surface">A newer Runr version is available.</div>
            </div>
            <button
              className="inline-flex items-center justify-center gap-2 rounded-full bg-primary px-4 py-2 text-xs font-semibold text-white transition-opacity hover:opacity-90"
              onClick={() => window.location.reload()}
              type="button"
            >
              <span className="material-symbols-outlined text-[16px]">refresh</span>
              Refresh now
            </button>
          </div>
        ) : null}

        <main className="w-full px-4 pb-12 pt-6 md:px-8">
          {isCareerAssetsRoute ? <CareerAssetsNavigation /> : null}
          {children}
        </main>
      </div>
    </div>
  );
}
