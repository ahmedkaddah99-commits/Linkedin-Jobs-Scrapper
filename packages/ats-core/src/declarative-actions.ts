/** AA-216: adapter plans are data; only this module may execute DOM mutations. */

export type DeclarativeAction =
  | { type: "fill_text" | "fill_rich_text"; fieldId: string; value: string }
  | { type: "select"; fieldId: string; value: string }
  | { type: "set_date"; fieldId: string; value: string; monthFieldId?: string; yearFieldId?: string; datePickerSelector?: string }
  | { type: "set_checkbox" | "set_radio"; fieldId: string; checked: boolean }
  | { type: "add_repeatable_section"; sectionId: string; values: Record<string, string> }
  | { type: "upload_document"; fieldId: string; documentId: string; documentVersion: number }
  | {
      type: "propose_intermediate_navigation";
      stepId: string;
      selector: string;
      expectedTransition: { fromStepId: string; toStepId: string; url?: string };
      controlKind: "submit" | "button" | "link";
    };

export type DeclarativePlan = {
  schemaVersion: 1;
  adapter: "greenhouse" | "lever";
  actions: DeclarativeAction[];
};

export type NativeValueAction = Extract<DeclarativeAction, {
  type: "fill_text" | "fill_rich_text" | "select" | "set_date" | "set_checkbox" | "set_radio"
}>;

export type ActionExecution =
  | { status: "applied"; actionType: DeclarativeAction["type"] }
  | { status: "needs_attention"; actionType: DeclarativeAction["type"]; reason: string }
  | { status: "unresolved"; actionType: DeclarativeAction["type"]; reason: string }
  | { status: "rejected"; actionType: string; reason: string };

const actionTypes = new Set([
  "fill_text", "fill_rich_text", "select", "set_date", "set_checkbox", "set_radio",
  "add_repeatable_section", "upload_document", "propose_intermediate_navigation",
]);

function record(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function isDeclarativeAction(value: unknown): value is DeclarativeAction {
  if (!record(value) || !actionTypes.has(String(value.type)) || Object.keys(value).some((key) =>
    !["type", "fieldId", "value", "checked", "sectionId", "values", "documentId", "documentVersion",
      "stepId", "selector", "expectedTransition", "controlKind", "monthFieldId", "yearFieldId", "datePickerSelector"].includes(key))) return false;
  if (typeof value.type !== "string") return false;
  if (["fill_text", "fill_rich_text", "select", "set_date"].includes(value.type)) {
    if (typeof value.fieldId !== "string" || typeof value.value !== "string") return false;
    if (value.type !== "set_date") return true;
    return (value.monthFieldId === undefined && value.yearFieldId === undefined ||
      typeof value.monthFieldId === "string" && typeof value.yearFieldId === "string") &&
      (value.datePickerSelector === undefined || typeof value.datePickerSelector === "string");
  }
  if (["set_checkbox", "set_radio"].includes(value.type)) {
    return typeof value.fieldId === "string" && typeof value.checked === "boolean";
  }
  if (value.type === "add_repeatable_section") {
    return typeof value.sectionId === "string" && record(value.values) &&
      Object.values(value.values).every((item) => typeof item === "string");
  }
  if (value.type === "upload_document") {
    return typeof value.fieldId === "string" && typeof value.documentId === "string" &&
      Number.isInteger(value.documentVersion) && Number(value.documentVersion) > 0;
  }
  return typeof value.stepId === "string" && typeof value.selector === "string" &&
    record(value.expectedTransition) && typeof value.expectedTransition.fromStepId === "string" &&
    typeof value.expectedTransition.toStepId === "string" &&
    ["submit", "button", "link"].includes(String(value.controlKind));
}

export function isDeclarativePlan(value: unknown): value is DeclarativePlan {
  return record(value) && value.schemaVersion === 1 && (value.adapter === "greenhouse" || value.adapter === "lever") &&
    Array.isArray(value.actions) && value.actions.every(isDeclarativeAction);
}

export function planFillAction(
  field: { id: string; type: string },
  value: string,
): NativeValueAction | null {
  if (["text", "email", "tel", "textarea"].includes(field.type)) return { type: "fill_text", fieldId: field.id, value };
  if (field.type === "select") return { type: "select", fieldId: field.id, value };
  if (field.type === "date") return { type: "set_date", fieldId: field.id, value };
  if (field.type === "checkbox") return { type: "set_checkbox", fieldId: field.id, checked: value === "true" };
  if (field.type === "radio") return { type: "set_radio", fieldId: field.id, checked: true };
  return null;
}

export type NavigationEvidence = {
  currentStepId: string;
  selector: string;
  expectedTransition: { fromStepId: string; toStepId: string; url?: string };
};

export function authorizeIntermediateNavigation(
  action: Extract<DeclarativeAction, { type: "propose_intermediate_navigation" }>,
  evidence: NavigationEvidence,
  root: ParentNode,
): { allowed: true } | { allowed: false; reason: string } {
  if (action.controlKind === "button" || action.controlKind === "link") {
    return { allowed: false, reason: "Button and link navigation require explicit manual review." };
  }
  if (action.controlKind !== "submit" || action.stepId !== evidence.currentStepId ||
      action.selector !== evidence.selector || action.expectedTransition.fromStepId !== evidence.expectedTransition.fromStepId ||
      action.expectedTransition.toStepId !== evidence.expectedTransition.toStepId ||
      !root.querySelector(action.selector)) {
    return { allowed: false, reason: "Intermediate navigation evidence is ambiguous or stale." };
  }
  return { allowed: true };
}

export type ControlValue = string | boolean | null;

export type ControlValidation = {
  supported: boolean;
  valid: boolean;
  value: ControlValue;
  messages: string[];
};

function controlKind(control: Element): "input" | "textarea" | "select" | "combobox" | "rich_text" | null {
  const tag = control.tagName.toLowerCase();
  if (tag === "input") return "input";
  if (tag === "textarea") return "textarea";
  if (tag === "select") return "select";
  if (control.getAttribute("role") === "combobox") return "combobox";
  if (control.getAttribute("contenteditable") === "true" ||
      (control as HTMLElement).isContentEditable) return "rich_text";
  return null;
}

function resolveControl(document: Document, fieldId: string, resolve: (id: string) => Element | null): Element | null {
  const control = resolve(fieldId);
  if (control) return control;
  // A closed shadow root intentionally cannot be queried and remains unresolved.
  const escaped = globalThis.CSS?.escape?.(fieldId) ?? fieldId.replace(/(["\\])/gu, "\\$1");
  try { return document.querySelector(`[data-runr-field-id="${escaped}"]`); } catch { return null; }
}

export function readControlValue(
  document: Document,
  fieldId: string,
  resolve: (id: string) => Element | null = (id) => document.getElementById(id),
): ControlValue {
  const control = resolveControl(document, fieldId, resolve);
  if (!control || !controlKind(control)) return null;
  const kind = controlKind(control);
  if (kind === "input" && ["checkbox", "radio"].includes((control as HTMLInputElement).type)) return (control as HTMLInputElement).checked;
  if (kind === "input" || kind === "textarea" || kind === "select") return String((control as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement).value);
  if (kind === "combobox") return "value" in control ? String((control as HTMLElement & { value?: unknown }).value ?? "") : control.textContent?.trim() || "";
  return control.textContent || "";
}

export function inspectControlValidation(
  document: Document,
  fieldId: string,
  resolve: (id: string) => Element | null = (id) => document.getElementById(id),
): ControlValidation {
  const control = resolveControl(document, fieldId, resolve);
  if (!control || !controlKind(control)) return { supported: false, valid: false, value: null, messages: ["Unsupported or inaccessible control."] };
  const messages: string[] = [];
  if (control.getAttribute("aria-invalid") === "true") messages.push("The control is marked invalid.");
  const candidate = control as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
  if (typeof candidate.checkValidity === "function" && !candidate.checkValidity()) {
    if (candidate.validationMessage) messages.push(candidate.validationMessage);
    else messages.push("The control failed browser validation.");
  }
  const error = control.parentElement?.querySelector('[role="alert"], .error, .field-error');
  if (error?.textContent?.trim()) messages.push(error.textContent.trim());
  return { supported: true, valid: messages.length === 0, value: readControlValue(document, fieldId, resolve), messages };
}

export function verifyControlValue(
  document: Document,
  fieldId: string,
  expected: ControlValue,
  resolve: (id: string) => Element | null = (id) => document.getElementById(id),
): ControlValidation {
  const validation = inspectControlValidation(document, fieldId, resolve);
  if (validation.supported && validation.value !== expected) {
    return { ...validation, valid: false, messages: [...validation.messages, "Readback did not match the approved value."] };
  }
  return validation;
}

function setProperty(control: Element, property: "value" | "checked", value: string | boolean): void {
  const prototype = Object.getPrototypeOf(control);
  const setter = Object.getOwnPropertyDescriptor(prototype, property)?.set;
  if (setter) setter.call(control, value);
  else (control as unknown as Record<string, string | boolean>)[property] = value;
}

function emitFrameworkEvents(control: Element): void {
  const EventConstructor = control.ownerDocument.defaultView?.Event ?? Event;
  control.dispatchEvent(new EventConstructor("input", { bubbles: true, composed: true }));
  control.dispatchEvent(new EventConstructor("change", { bubbles: true, composed: true }));
}

export function writeControlValue(
  document: Document,
  fieldId: string,
  value: string | boolean,
  resolve: (id: string) => Element | null = (id) => document.getElementById(id),
): ControlValidation {
  const control = resolveControl(document, fieldId, resolve);
  const kind = control && controlKind(control);
  if (!control || !kind) return { supported: false, valid: false, value: null, messages: ["Unsupported or inaccessible control."] };
  if (kind === "input" && ["submit", "button", "image", "reset", "file"].includes((control as HTMLInputElement).type)) {
    return { supported: false, valid: false, value: null, messages: ["Terminal, upload, or button controls are not native value targets."] };
  }
  (control as HTMLElement).focus();
  if (kind === "input" && ["checkbox", "radio"].includes((control as HTMLInputElement).type)) setProperty(control, "checked", Boolean(value));
  else if (kind === "input" || kind === "textarea" || kind === "select") setProperty(control, "value", String(value));
  else if (kind === "combobox" && "value" in control) setProperty(control, "value", String(value));
  else if (kind === "combobox" || kind === "rich_text") control.textContent = String(value);
  else return { supported: false, valid: false, value: null, messages: ["The control kind is not supported."] };
  emitFrameworkEvents(control);
  (control as HTMLElement).blur();
  return inspectControlValidation(document, fieldId, resolve);
}

export function executeNativeValueAction(
  document: Document,
  action: NativeValueAction,
  resolve: (fieldId: string) => Element | null = (fieldId) => document.getElementById(fieldId),
): ActionExecution {
  const control = resolveControl(document, action.fieldId, resolve);
  if (!control) return { status: "unresolved", actionType: action.type, reason: "Target control is unsupported, closed, or unavailable." };
  if (control.tagName.toLowerCase() === "button" || (control.tagName.toLowerCase() === "input" && ["submit", "button", "image", "reset"].includes((control as HTMLInputElement).type))) {
    return { status: "rejected", actionType: action.type, reason: "Terminal or button controls are never executable." };
  }
  if (!controlKind(control)) return { status: "unresolved", actionType: action.type, reason: "Target control is unsupported, closed, or unavailable." };
  if (action.type === "set_date" && action.datePickerSelector && !document.querySelector(action.datePickerSelector)) {
    return { status: "unresolved", actionType: action.type, reason: "The adapter-declared date picker was not present." };
  }
  if (action.type === "set_date" && action.monthFieldId && action.yearFieldId) {
    const match = /^(\d{4})-(\d{2})/.exec(action.value);
    if (!match) return { status: "unresolved", actionType: action.type, reason: "The date value is not an ISO month/date." };
    const month = writeControlValue(document, action.monthFieldId, match[2]!, resolve);
    const year = writeControlValue(document, action.yearFieldId, match[1]!, resolve);
    if (!month.valid || !year.valid || month.value !== match[2] || year.value !== match[1]) {
      return { status: "unresolved", actionType: action.type, reason: "Split month/year date readback or validation failed." };
    }
    return { status: "applied", actionType: action.type };
  }
  let expected: string | boolean;
  if ("value" in action) {
    expected = action.value;
  } else {
    expected = action.checked;
  }
  const written = writeControlValue(document, action.fieldId, expected, resolve);
  if (!written.supported || !written.valid || written.value !== expected) {
    return { status: "unresolved", actionType: action.type, reason: written.messages.join(" ") || "Deterministic readback or validation failed." };
  }
  return { status: "applied", actionType: action.type };
}

export function executeDeclarativeAction(
  document: Document,
  action: unknown,
  navigationEvidence?: NavigationEvidence,
): ActionExecution {
  if (!isDeclarativeAction(action)) return { status: "rejected", actionType: "unknown", reason: "Unknown or malformed action." };
  if (action.type === "propose_intermediate_navigation") {
    if (!navigationEvidence) return { status: "needs_attention", actionType: action.type, reason: "Navigation requires controller evidence." };
    const authorization = authorizeIntermediateNavigation(action, navigationEvidence, document);
    return authorization.allowed
      ? { status: "needs_attention", actionType: action.type, reason: "Post-transition verification is required before navigation." }
      : { status: "needs_attention", actionType: action.type, reason: authorization.reason };
  }
  if (action.type === "add_repeatable_section" || action.type === "upload_document") {
    return { status: "needs_attention", actionType: action.type, reason: "This action requires the adapter-specific controlled executor." };
  }
  return executeNativeValueAction(document, action);
}
