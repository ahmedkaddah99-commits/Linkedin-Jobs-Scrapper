export type SubmissionGuardEvent = "click" | "submit" | "requestSubmit" | "form.submit" | "enter" | "fetch" | "xhr" | "navigation";

export type SubmissionGuard = {
  events: SubmissionGuardEvent[];
  stop: () => void;
};

type NavigationControl = HTMLButtonElement | HTMLInputElement;

type IntermediateActivation = {
  control: NavigationControl;
  form: HTMLFormElement | null;
  validate: () => boolean;
  clickConsumed: boolean;
};

type SharedGuardState = {
  events: SubmissionGuardEvent[];
  installCount: number;
  trustedUserSubmitPending: boolean;
  activation: IntermediateActivation | null;
  pendingIntermediateSubmit: IntermediateActivation | null;
  teardown: (() => void) | null;
};

const GUARD_STATE = Symbol.for("runr.assisted-apply.submission-guard");

function sharedState(document: Document): SharedGuardState {
  const existing = Reflect.get(document, GUARD_STATE) as SharedGuardState | undefined;
  if (existing) return existing;
  const state: SharedGuardState = {
    events: [],
    installCount: 0,
    trustedUserSubmitPending: false,
    activation: null,
    pendingIntermediateSubmit: null,
    teardown: null,
  };
  Object.defineProperty(document, GUARD_STATE, { configurable: true, value: state });
  return state;
}

function isFormPostControl(control: NavigationControl): boolean {
  return control.tagName === "BUTTON"
    ? (control as HTMLButtonElement).type === "submit"
    : (control as HTMLInputElement).type === "submit";
}

/**
 * Authorizes one immediately revalidated intermediate control activation.
 * State lives on the document so the panel and application-form content-script
 * bundles share the same permit in the extension's isolated world.
 */
export function authorizeIntermediateActivation(
  document: Document,
  control: NavigationControl,
  validate: () => boolean,
): (() => void) | null {
  const state = sharedState(document);
  if (state.installCount === 0 || !control.isConnected) return null;
  let valid = false;
  try {
    valid = validate();
  } catch {
    valid = false;
  }
  if (!valid) return null;

  const activation: IntermediateActivation = { control, form: control.form, validate, clickConsumed: false };
  state.activation = activation;
  state.pendingIntermediateSubmit = null;
  return () => {
    if (state.activation === activation) state.activation = null;
    if (state.pendingIntermediateSubmit === activation) state.pendingIntermediateSubmit = null;
  };
}

export function installSubmissionGuard(document: Document): SubmissionGuard {
  const state = sharedState(document);
  const events = state.events;
  state.installCount += 1;
  if (!state.teardown) {
    const window = document.defaultView;
    const onClick = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      const control = target?.closest("button, input") as HTMLButtonElement | HTMLInputElement | null;
      if (control && (control.tagName === "BUTTON" || ["submit", "button", "image", "reset"].includes(control.type))) {
        events.push("click");
        if (event.isTrusted) {
          state.trustedUserSubmitPending = true;
          return;
        }
        const activation = state.activation;
        state.activation = null;
        if (activation && !activation.clickConsumed && control === activation.control) {
          let valid = false;
          try {
            valid = activation.validate();
          } catch {
            valid = false;
          }
          if (valid) {
            activation.clickConsumed = true;
            if (isFormPostControl(control) && activation.form && control.form === activation.form) {
              state.pendingIntermediateSubmit = activation;
            }
            return;
          }
        }
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    };
    const onSubmit = (event: Event) => {
      events.push("submit");
      const pending = state.pendingIntermediateSubmit;
      const submitter = (event as SubmitEvent).submitter;
      if (pending && pending.clickConsumed && pending.form &&
          event.target === pending.form && pending.control.isConnected &&
          pending.control.form === pending.form && submitter === pending.control) {
        state.pendingIntermediateSubmit = null;
        return;
      }
      if (event.isTrusted && state.trustedUserSubmitPending) {
        state.trustedUserSubmitPending = false;
        return;
      }
      state.trustedUserSubmitPending = false;
      event.preventDefault();
      event.stopImmediatePropagation();
    };
    const onKeydown = (event: KeyboardEvent) => {
      if (event.key === "Enter" && event.target instanceof HTMLInputElement) {
        events.push("enter");
        if (event.isTrusted) {
          state.trustedUserSubmitPending = true;
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
    state.teardown = () => {
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
    };
  }

  let stopped = false;
  return {
    events,
    stop: () => {
      if (stopped) return;
      stopped = true;
      state.installCount = Math.max(0, state.installCount - 1);
      if (state.installCount === 0) {
        state.activation = null;
        state.pendingIntermediateSubmit = null;
        state.trustedUserSubmitPending = false;
        state.teardown?.();
        state.teardown = null;
      }
    },
  };
}
