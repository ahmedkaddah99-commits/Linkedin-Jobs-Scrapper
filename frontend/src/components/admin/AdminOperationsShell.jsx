import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useSession } from "../../context/SessionContext";
import { ADMIN_NAV_GROUPS, ADMIN_NAV_ITEMS, getAdminPageMeta } from "../../admin/adminRoutes";
import { AdminBadge, AdminState, useDialogFocus } from "./AdminPrimitives";
import "../../admin/adminOperations.css";

function navIsActive(pathname, item) {
  return item.end ? pathname === item.to : pathname === item.to || pathname.startsWith(`${item.to}/`);
}

function CommandPalette({ open, onClose }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const ref = useDialogFocus(open, onClose);
  const results = useMemo(() => {
    const value = query.trim().toLowerCase();
    return value ? ADMIN_NAV_ITEMS.filter((item) => item.label.toLowerCase().includes(value)) : ADMIN_NAV_ITEMS;
  }, [query]);

  useEffect(() => { if (!open) setQuery(""); }, [open]);
  if (!open) return null;
  return (
    <div className="admin-overlay admin-command-overlay">
      <button aria-label="Close command palette" className="admin-overlay__scrim" onClick={onClose} type="button" />
      <section aria-label="Admin command palette" aria-modal="true" className="admin-command" ref={ref} role="dialog">
        <label htmlFor="admin-command-search"><span className="material-symbols-outlined">search</span><input autoComplete="off" id="admin-command-search" onChange={(event) => setQuery(event.target.value)} placeholder="Go to an admin area…" value={query} /></label>
        <div className="admin-command__results">
          {results.length ? results.map((item) => <button key={item.to} onClick={() => { navigate(item.to); onClose(); }} type="button"><span className="material-symbols-outlined">{item.icon}</span><span>{item.label}</span><small>{item.to}</small></button>) : <AdminState description="Try a section name such as jobs, quality, or publication." title="No matching admin area" />}
        </div>
        <footer><span>↑↓ browse</span><span>Enter open</span><span>Esc close</span></footer>
      </section>
    </div>
  );
}

function OperationsInbox({ open, onClose }) {
  const ref = useDialogFocus(open, onClose);
  if (!open) return null;
  return (
    <div className="admin-popover admin-inbox" ref={ref} role="dialog" aria-label="Operations inbox">
      <header><div><strong>Operations inbox</strong><p>Review queues; no actions run automatically.</p></div><button aria-label="Close inbox" className="admin-icon-button" onClick={onClose} type="button"><span className="material-symbols-outlined">close</span></button></header>
      <Link onClick={onClose} to="/admin/acquisition/data-quality"><span className="material-symbols-outlined">fact_check</span><span><strong>Quality findings</strong><small>Inspect current report-only findings</small></span></Link>
      <Link onClick={onClose} to="/admin/acquisition/duplicates"><span className="material-symbols-outlined">content_copy</span><span><strong>Duplicate review</strong><small>Review clusters before any decision</small></span></Link>
      <Link onClick={onClose} to="/admin/acquisition/publication"><span className="material-symbols-outlined">publish</span><span><strong>Publication controls</strong><small>Preview current release state</small></span></Link>
    </div>
  );
}

export default function AdminOperationsShell({ children }) {
  const location = useLocation();
  const { error, refreshSession, status, user } = useSession();
  const [collapsed, setCollapsed] = useState(() => window.localStorage.getItem("runr.admin.sidebar.collapsed") === "1");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [inboxOpen, setInboxOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const closeMobile = useCallback(() => setMobileOpen(false), []);
  const mobileDialogRef = useDialogFocus(mobileOpen, closeMobile);
  const openCommand = useCallback(() => {
    setInboxOpen(false);
    setMobileOpen(false);
    setCommandOpen(true);
  }, []);
  const page = getAdminPageMeta(location.pathname);
  const isConnected = status === "connected";
  const environmentLabel = window.location.hostname === "app.userunr.com" ? "Production" : "Non-production";
  const identity = user?.display_name || user?.email || "Runr admin";

  useEffect(() => {
    window.localStorage.setItem("runr.admin.sidebar.collapsed", collapsed ? "1" : "0");
  }, [collapsed]);
  useEffect(() => { setMobileOpen(false); setInboxOpen(false); }, [location.pathname]);
  useEffect(() => {
    function handleShortcut(event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openCommand(); }
    }
    document.addEventListener("keydown", handleShortcut);
    return () => document.removeEventListener("keydown", handleShortcut);
  }, [openCommand]);

  const reconnect = useCallback(async () => {
    setRefreshing(true);
    try { await refreshSession(); } finally { setRefreshing(false); }
  }, [refreshSession]);

  return (
    <div className={`admin-operations ${collapsed ? "admin-operations--collapsed" : ""}`}>
      <a className="admin-skip-link" href="#admin-main">Skip to admin content</a>
      <aside className={`admin-sidebar ${mobileOpen ? "admin-sidebar--mobile-open" : ""}`} ref={mobileDialogRef}>
        <div className="admin-sidebar__brand"><Link aria-label="Runr admin overview" to="/admin"><span className="admin-brand-mark">R</span><span className="admin-sidebar__brand-copy"><strong>Runr</strong><small>Operations console</small></span></Link><button aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} className="admin-icon-button admin-sidebar__collapse" onClick={() => setCollapsed((value) => !value)} type="button"><span className="material-symbols-outlined">{collapsed ? "right_panel_open" : "left_panel_close"}</span></button><button aria-label="Close navigation" className="admin-icon-button admin-sidebar__mobile-close" onClick={() => setMobileOpen(false)} type="button"><span className="material-symbols-outlined">close</span></button></div>
        <nav aria-label="Admin operations navigation">
          {ADMIN_NAV_GROUPS.map((group) => <section key={group.label}><h2>{group.label}</h2>{group.items.map((item) => <NavLink aria-current={navIsActive(location.pathname, item) ? "page" : undefined} className={navIsActive(location.pathname, item) ? "admin-nav-link admin-nav-link--active" : "admin-nav-link"} end={item.end} key={item.to} title={collapsed ? item.label : undefined} to={item.to}><span className="material-symbols-outlined">{item.icon}</span><span>{item.label}</span></NavLink>)}</section>)}
        </nav>
        <div className="admin-sidebar__footer"><AdminBadge tone={isConnected ? "success" : "warning"}><span aria-hidden="true" className="admin-live-dot" />{isConnected ? `${environmentLabel} connected` : `${environmentLabel} connection requires attention`}</AdminBadge><p>External providers, AI, and paid calls remain policy-controlled.</p></div>
      </aside>
      {mobileOpen ? <button aria-label="Close navigation" className="admin-mobile-scrim" onClick={() => setMobileOpen(false)} type="button" /> : null}

      <div className="admin-workspace">
        <header className="admin-topbar">
          <button aria-label="Open navigation" className="admin-icon-button admin-menu-button" onClick={() => setMobileOpen(true)} type="button"><span className="material-symbols-outlined">menu</span></button>
          <div className="admin-breadcrumb"><span>{page.group}</span><span aria-hidden="true">/</span><strong>{page.title}</strong></div>
          <button className="admin-command-trigger" onClick={openCommand} type="button"><span className="material-symbols-outlined">search</span><span>Search admin</span><kbd>⌘K</kbd></button>
          <div className="admin-topbar__actions"><button aria-expanded={inboxOpen} aria-label="Open operations inbox" className="admin-icon-button" onClick={() => setInboxOpen((value) => !value)} type="button"><span className="material-symbols-outlined">notifications</span></button>{inboxOpen ? <OperationsInbox onClose={() => setInboxOpen(false)} open /> : null}<div className="admin-identity"><span>{String(identity).slice(0, 1).toUpperCase()}</span><div><strong>{identity}</strong><small>{user?.role || "admin"}</small></div></div></div>
        </header>
        {!isConnected ? <div className="admin-connection-banner" role="alert"><span className="material-symbols-outlined">cloud_off</span><div><strong>Admin data may be stale</strong><p>{error || "The authenticated API session is not currently connected."}</p></div><button disabled={refreshing} onClick={() => reconnect().catch(() => undefined)} type="button">{refreshing ? "Reconnecting…" : "Reconnect"}</button></div> : null}
        <main id="admin-main" tabIndex="-1"><div className="admin-content">{children}</div><footer className="admin-freshness"><span>Environment: {environmentLabel}</span><span>Session: {isConnected ? "connected" : status}</span><span>View: read and explicit-action controls</span></footer></main>
      </div>
      <CommandPalette onClose={() => setCommandOpen(false)} open={commandOpen} />
    </div>
  );
}
