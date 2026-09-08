export type SubmissionGuardEvent = "click" | "submit" | "requestSubmit" | "form.submit" | "enter" | "fetch" | "xhr" | "navigation";

export type SubmissionGuard = {
  events: SubmissionGuardEvent[];
  stop: () => void;
};

export function installSubmissionGuard(document: Document): SubmissionGuard {
  const events: SubmissionGuardEvent[] = [];
  let trustedUserSubmitPending = false;
  const window = document.defaultView;
  const onClick = (event: MouseEvent) => {
    const target = event.target instanceof Element ? event.target : null;
    const terminal = target?.closest("button, input") as HTMLButtonElement | HTMLInputElement | null;
    if (terminal && (terminal.tagName === "BUTTON" || ["submit", "button", "image", "reset"].includes(terminal.type))) {
      events.push("click");
      if (event.isTrusted) {
        trustedUserSubmitPending = true;
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  };
  const onSubmit = (event: Event) => {
    events.push("submit");
    if (event.isTrusted && trustedUserSubmitPending) {
      trustedUserSubmitPending = false;
      return;
    }
    trustedUserSubmitPending = false;
    event.preventDefault();
    event.stopImmediatePropagation();
  };
  const onKeydown = (event: KeyboardEvent) => {
    if (event.key === "Enter" && event.target instanceof HTMLInputElement) {
      events.push("enter");
      if (event.isTrusted) {
        trustedUserSubmitPending = true;
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  };
  document.addEventListener("click", onClick, true);
  document.addEventListener("submit", onSubmit, true);
  document.addEventListener("keydown", onKeydown, true);
  const onNavigation = () => events.push("navigation");
  window?.addEventListener("beforeunload", onNavigation, true);
  window?.addEventListener("hashchange", onNavigation, true);
  window?.addEventListener("popstate", onNavigation, true);

  const formPrototype = window?.HTMLFormElement?.prototype;
  const originalRequestSubmit = formPrototype?.requestSubmit;
  const originalSubmit = formPrototype?.submit;
  if (formPrototype) {
    formPrototype.requestSubmit = function () { events.push("requestSubmit"); };
    formPrototype.submit = function () { events.push("form.submit"); };
  }
  const originalFetch = window?.fetch;
  if (window && originalFetch) {
    window.fetch = ((...args: Parameters<typeof fetch>) => {
      events.push("fetch");
      return originalFetch.apply(window, args);
    }) as typeof fetch;
  }
  const xhrPrototype = window?.XMLHttpRequest?.prototype;
  const originalXhrOpen = xhrPrototype?.open;
  const originalXhrSend = xhrPrototype?.send;
  if (xhrPrototype && originalXhrOpen && originalXhrSend) {
    const open = originalXhrOpen as (...args: unknown[]) => void;
    const send = originalXhrSend as (...args: unknown[]) => void;
    xhrPrototype.open = function (this: XMLHttpRequest, ...args: unknown[]) { events.push("xhr"); return open.apply(this, args); } as typeof xhrPrototype.open;
    xhrPrototype.send = function (this: XMLHttpRequest, ...args: unknown[]) { events.push("xhr"); return send.apply(this, args); } as typeof xhrPrototype.send;
  }
  return {
    events,
    stop: () => {
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("submit", onSubmit, true);
      document.removeEventListener("keydown", onKeydown, true);
      window?.removeEventListener("beforeunload", onNavigation, true);
      window?.removeEventListener("hashchange", onNavigation, true);
      window?.removeEventListener("popstate", onNavigation, true);
      if (formPrototype) {
        if (originalRequestSubmit) formPrototype.requestSubmit = originalRequestSubmit;
        if (originalSubmit) formPrototype.submit = originalSubmit;
      }
      if (window && originalFetch) window.fetch = originalFetch;
      if (xhrPrototype && originalXhrOpen && originalXhrSend) {
        xhrPrototype.open = originalXhrOpen;
        xhrPrototype.send = originalXhrSend;
      }
    },
  };
}
