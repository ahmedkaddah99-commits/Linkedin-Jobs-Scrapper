export const PAGE_BRIDGE_REQUEST_EVENT = "runr-assisted-apply:controlled-field-request";
export const PAGE_BRIDGE_RESPONSE_EVENT = "runr-assisted-apply:controlled-field-response";

export type PageBridgeControlKind = "text" | "textarea" | "select" | "checkbox" | "radio";

export interface PageBridgeSetRequest {
  schemaVersion: 1;
  operation: "set_control_value";
  operationId: string;
  elementId: string;
  controlKind: PageBridgeControlKind;
  value: string | boolean;
}

export interface PageBridgeSetResponse {
  schemaVersion: 1;
  operationId: string;
  status: "applied" | "not_found" | "rejected";
  acceptedValue?: string | boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function isPageBridgeSetRequest(value: unknown): value is PageBridgeSetRequest {
  if (!isRecord(value)) return false;
  const textKind = ["text", "textarea", "select"].includes(String(value.controlKind));
  const checkedKind = ["checkbox", "radio"].includes(String(value.controlKind));
  return Object.keys(value).every((key) =>
    ["schemaVersion", "operation", "operationId", "elementId", "controlKind", "value"].includes(key)) &&
    Object.keys(value).length === 6 && value.schemaVersion === 1 && value.operation === "set_control_value" &&
    typeof value.operationId === "string" && /^[a-zA-Z0-9-]{8,80}$/u.test(value.operationId) &&
    typeof value.elementId === "string" && /^[a-zA-Z][\w:.-]{0,127}$/u.test(value.elementId) &&
    ((textKind && typeof value.value === "string" && value.value.length <= 10_000) ||
      (checkedKind && typeof value.value === "boolean"));
}

export function isPageBridgeSetResponse(value: unknown): value is PageBridgeSetResponse {
  return isRecord(value) && Object.keys(value).every((key) =>
    ["schemaVersion", "operationId", "status", "acceptedValue"].includes(key)) &&
    value.schemaVersion === 1 &&
    typeof value.operationId === "string" &&
    ["applied", "not_found", "rejected"].includes(String(value.status)) &&
    (value.acceptedValue === undefined || typeof value.acceptedValue === "string" ||
      typeof value.acceptedValue === "boolean");
}

function bridgeReadback(control: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement) {
  return control instanceof HTMLInputElement && ["checkbox", "radio"].includes(control.type)
    ? control.checked
    : control.value;
}

function applyBoundedOperation(document: Document, request: PageBridgeSetRequest): PageBridgeSetResponse {
  const candidate = document.getElementById(request.elementId);
  if (!(candidate instanceof HTMLInputElement || candidate instanceof HTMLTextAreaElement ||
      candidate instanceof HTMLSelectElement)) {
    return { schemaVersion: 1, operationId: request.operationId, status: "not_found" };
  }
  if (candidate instanceof HTMLInputElement &&
      !["text", "email", "tel", "date", "checkbox", "radio"].includes(candidate.type)) {
    return { schemaVersion: 1, operationId: request.operationId, status: "rejected" };
  }
  if (candidate.disabled || candidate.closest('[hidden], [aria-hidden="true"]')) {
    return { schemaVersion: 1, operationId: request.operationId, status: "rejected" };
  }
  for (let current: Element | null = candidate; current; current = current.parentElement) {
    const style = document.defaultView?.getComputedStyle(current);
    if (style && (style.display === "none" || style.visibility === "hidden" || style.visibility === "collapse")) {
      return { schemaVersion: 1, operationId: request.operationId, status: "rejected" };
    }
  }
  const liveKind: PageBridgeControlKind = candidate instanceof HTMLTextAreaElement ? "textarea"
    : candidate instanceof HTMLSelectElement ? "select"
      : candidate.type === "checkbox" ? "checkbox"
        : candidate.type === "radio" ? "radio" : "text";
  if (liveKind !== request.controlKind) {
    return { schemaVersion: 1, operationId: request.operationId, status: "rejected" };
  }
  const prototype = candidate instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
    : candidate instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  const property = liveKind === "checkbox" || liveKind === "radio" ? "checked" : "value";
  const setter = Object.getOwnPropertyDescriptor(prototype, property)?.set;
  if (!setter) return { schemaVersion: 1, operationId: request.operationId, status: "rejected" };
  setter.call(candidate, request.value);
  candidate.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
  candidate.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
  return {
    schemaVersion: 1,
    operationId: request.operationId,
    status: "applied",
    acceptedValue: bridgeReadback(candidate),
  };
}

export function installPageContextBridge(window: Window): () => void {
  const listener = (event: Event) => {
    if (!(event instanceof CustomEvent) || typeof event.detail !== "string" || event.detail.length > 12_000) return;
    let parsed: unknown;
    try { parsed = JSON.parse(event.detail); } catch { return; }
    if (!isPageBridgeSetRequest(parsed)) return;
    const response = applyBoundedOperation(window.document, parsed);
    window.dispatchEvent(new CustomEvent(PAGE_BRIDGE_RESPONSE_EVENT, { detail: JSON.stringify(response) }));
  };
  window.addEventListener(PAGE_BRIDGE_REQUEST_EVENT, listener);
  return () => window.removeEventListener(PAGE_BRIDGE_REQUEST_EVENT, listener);
}

export async function requestPageContextSet(
  control: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement,
  value: string | boolean,
): Promise<PageBridgeSetResponse | null> {
  if (!control.id) return null;
  const controlKind: PageBridgeControlKind = control instanceof HTMLTextAreaElement ? "textarea"
    : control instanceof HTMLSelectElement ? "select"
      : control.type === "checkbox" ? "checkbox" : control.type === "radio" ? "radio" : "text";
  const operationId = globalThis.crypto?.randomUUID?.() ||
    `runr-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
  const request: PageBridgeSetRequest = {
    schemaVersion: 1, operation: "set_control_value", operationId,
    elementId: control.id, controlKind, value,
  };
  return new Promise((resolve) => {
    const timeout = setTimeout(() => { cleanup(); resolve(null); }, 250);
    const listener = (event: Event) => {
      if (!(event instanceof CustomEvent) || typeof event.detail !== "string") return;
      let parsed: unknown;
      try { parsed = JSON.parse(event.detail); } catch { return; }
      if (!isPageBridgeSetResponse(parsed) || parsed.operationId !== operationId) return;
      cleanup();
      resolve(parsed);
    };
    const cleanup = () => {
      clearTimeout(timeout);
      control.ownerDocument.defaultView?.removeEventListener(PAGE_BRIDGE_RESPONSE_EVENT, listener);
    };
    control.ownerDocument.defaultView?.addEventListener(PAGE_BRIDGE_RESPONSE_EVENT, listener);
    control.ownerDocument.defaultView?.dispatchEvent(
      new CustomEvent(PAGE_BRIDGE_REQUEST_EVENT, { detail: JSON.stringify(request) }),
    );
  });
}
