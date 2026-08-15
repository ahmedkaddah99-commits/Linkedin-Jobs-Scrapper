import { useEffect, useRef } from "react";

export function AdminSection({ eyebrow = "Runr operations", title, description, actions, children }) {
  return (
    <section className="admin-section">
      {(title || description || actions) ? (
        <header className="admin-section__header">
          <div>
            <p className="admin-eyebrow">{eyebrow}</p>
            {title ? <h1>{title}</h1> : null}
            {description ? <p className="admin-section__description">{description}</p> : null}
          </div>
          {actions ? <div className="admin-section__actions">{actions}</div> : null}
        </header>
      ) : null}
      {children}
    </section>
  );
}

export function AdminState({ kind = "empty", title, description, action }) {
  const icons = { empty: "inbox", error: "cloud_off", forbidden: "lock", loading: "progress_activity", partial: "warning" };
  return (
    <div aria-live="polite" className={`admin-state admin-state--${kind}`} role={kind === "error" ? "alert" : "status"}>
      <span aria-hidden="true" className="material-symbols-outlined">{icons[kind] || icons.empty}</span>
      <div><strong>{title}</strong>{description ? <p>{description}</p> : null}</div>
      {action}
    </div>
  );
}

export function AdminPanel({ title, description, actions, children, className = "" }) {
  return (
    <section className={`admin-panel ${className}`.trim()}>
      {(title || description || actions) ? <header className="admin-panel__header"><div>{title ? <h2>{title}</h2> : null}{description ? <p>{description}</p> : null}</div>{actions}</header> : null}
      {children}
    </section>
  );
}

export function AdminMetric({ label, value = "Unknown", detail, tone = "neutral" }) {
  return <article className={`admin-metric admin-metric--${tone}`}><span>{label}</span><strong>{value ?? "Unknown"}</strong>{detail ? <small>{detail}</small> : null}</article>;
}

export function AdminBadge({ children, tone = "neutral" }) {
  return <span className={`admin-badge admin-badge--${tone}`}>{children}</span>;
}

export function useDialogFocus(open, onClose) {
  const ref = useRef(null);
  const returnFocusRef = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    returnFocusRef.current = document.activeElement;
    const node = ref.current;
    const focusable = () => [...(node?.querySelectorAll("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])") || [])].filter((element) => !element.disabled);
    window.requestAnimationFrame(() => focusable()[0]?.focus());
    function handleKeyDown(event) {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); onClose(); return; }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) { event.preventDefault(); return; }
      const first = items[0]; const last = items.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
    document.addEventListener("keydown", handleKeyDown, true);
    return () => { document.removeEventListener("keydown", handleKeyDown, true); returnFocusRef.current?.focus?.(); };
  }, [onClose, open]);
  return ref;
}

export function AdminInspector({ open, title, description, onClose, children }) {
  const ref = useDialogFocus(open, onClose);
  if (!open) return null;
  return <div className="admin-overlay"><button aria-label="Close inspection" className="admin-overlay__scrim" onClick={onClose} type="button" /><aside aria-describedby={description ? "admin-inspector-description" : undefined} aria-modal="true" className="admin-inspector" ref={ref} role="dialog"><header><div><p className="admin-eyebrow">Inspection</p><h2>{title}</h2>{description ? <p id="admin-inspector-description">{description}</p> : null}</div><button aria-label="Close inspection" className="admin-icon-button" onClick={onClose} type="button"><span className="material-symbols-outlined">close</span></button></header><div className="admin-inspector__body">{children}</div></aside></div>;
}

export function AdminConfirmDialog({ open, title, description, confirmLabel = "Confirm", tone = "danger", busy = false, onCancel, onConfirm, children }) {
  const ref = useDialogFocus(open, onCancel);
  if (!open) return null;
  return <div className="admin-overlay"><button aria-label="Cancel" className="admin-overlay__scrim" onClick={onCancel} type="button" /><section aria-modal="true" className="admin-dialog" ref={ref} role="alertdialog"><p className="admin-eyebrow">Explicit confirmation required</p><h2>{title}</h2>{description ? <p>{description}</p> : null}{children}<footer><button className="admin-button admin-button--secondary" disabled={busy} onClick={onCancel} type="button">Cancel</button><button className={`admin-button admin-button--${tone}`} disabled={busy} onClick={onConfirm} type="button">{busy ? "Working…" : confirmLabel}</button></footer></section></div>;
}
