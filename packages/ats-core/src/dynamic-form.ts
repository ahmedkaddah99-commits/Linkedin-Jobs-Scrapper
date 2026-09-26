export type DynamicFormChangeReason =
  | "controls_changed"
  | "step_changed"
  | "upload_changed"
  | "validation_changed";

export interface DynamicFormSnapshot {
  revision: number;
  reasons: DynamicFormChangeReason[];
  observerActive: boolean;
}

export interface DynamicFormMonitor {
  snapshot(): DynamicFormSnapshot;
  waitForQuiet(): Promise<DynamicFormSnapshot>;
  disconnect(): void;
}

export function observeDynamicForm(document: Document): DynamicFormMonitor {
  let revision = 0;
  let active = true;
  let pending = false;
  let windowStartedAt = Date.now();
  let flushesInWindow = 0;
  const reasons = new Set<DynamicFormChangeReason>();
  const waiters = new Set<(snapshot: DynamicFormSnapshot) => void>();

  const snapshot = (): DynamicFormSnapshot => ({ revision, reasons: [...reasons], observerActive: active });
  const schedule = (reason: DynamicFormChangeReason) => {
    if (!active) return;
    reasons.add(reason);
    if (pending) return;
    pending = true;
    setTimeout(() => {
      pending = false;
      if (!active) return;
      const now = Date.now();
      if (now - windowStartedAt > 10_000) { windowStartedAt = now; flushesInWindow = 0; }
      flushesInWindow += 1;
      if (flushesInWindow > 100) { active = false; observer.disconnect(); }
      revision += 1;
      const current = snapshot();
      for (const resolve of waiters) resolve(current);
      waiters.clear();
    }, 40);
  };
  const observer = new MutationObserver((records) => {
    for (const record of records.slice(0, 1_000)) {
      if (record.type === "childList") {
        const target = record.target instanceof Element ? record.target : null;
        const added = Array.from(record.addedNodes).filter((node): node is Element => node instanceof Element);
        if (target?.closest("[data-runr-upload-status]") ||
            added.some((node) => node.matches("[data-runr-upload-status]") || node.querySelector("[data-runr-upload-status]"))) {
          schedule("upload_changed");
        } else {
          schedule("controls_changed");
        }
        if (added.some((node) => node.matches("form, [data-step], [role=tabpanel]") ||
            node.querySelector("form, [data-step], [role=tabpanel]"))) schedule("step_changed");
      }
      else if (record.attributeName === "data-runr-upload-status") schedule("upload_changed");
      else if (["hidden", "disabled", "required", "aria-invalid", "class", "style"].includes(record.attributeName || "")) {
        schedule("validation_changed");
      }
    }
  });
  observer.observe(document.documentElement, {
    subtree: true, childList: true, attributes: true,
    attributeFilter: ["hidden", "disabled", "required", "aria-invalid", "class", "style", "data-runr-upload-status"],
  });
  const validationListener = () => schedule("validation_changed");
  const uploadListener = (event: Event) => {
    if (event.target instanceof HTMLInputElement && event.target.type === "file") schedule("upload_changed");
  };
  const stepListener = () => schedule("step_changed");
  document.addEventListener("invalid", validationListener, true);
  document.addEventListener("change", uploadListener, true);
  document.defaultView?.addEventListener("hashchange", stepListener);
  document.defaultView?.addEventListener("popstate", stepListener);

  return {
    snapshot,
    waitForQuiet: () => pending
      ? new Promise((resolve) => waiters.add(resolve))
      : Promise.resolve(snapshot()),
    disconnect: () => {
      active = false;
      observer.disconnect();
      document.removeEventListener("invalid", validationListener, true);
      document.removeEventListener("change", uploadListener, true);
      document.defaultView?.removeEventListener("hashchange", stepListener);
      document.defaultView?.removeEventListener("popstate", stepListener);
      const current = snapshot();
      for (const resolve of waiters) resolve(current);
      waiters.clear();
    },
  };
}
