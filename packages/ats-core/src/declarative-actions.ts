/** AA-216: adapter plans are data; only this module may execute DOM mutations. */

export type DeclarativeAction =
  | { type: "fill_text" | "fill_rich_text"; fieldId: string; value: string }
  | { type: "select_combobox_option"; fieldId: string; value: string; optionSelector: string; acceptedStateSelector?: string }
  | { type: "select_enhanced_options"; fieldId: string; values: string[] }
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
  /**
   * Provider identifier. Widened from the original Greenhouse/Lever union so
   * provider-neutral planning can target any portal; the two named adapters
   * remain valid values and their behavior is unchanged.
   */
  adapter: string;
  actions: DeclarativeAction[];
};

export type NativeValueAction = Extract<DeclarativeAction, {
  type: "fill_text" | "fill_rich_text" | "select_combobox_option" | "select" | "set_date" | "set_checkbox" | "set_radio"
}>;

export type ActionExecution =
  | { status: "applied"; actionType: DeclarativeAction["type"] }
  | { status: "needs_attention"; actionType: DeclarativeAction["type"]; reason: string }
  | { status: "unresolved"; actionType: DeclarativeAction["type"]; reason: string }
  | { status: "rejected"; actionType: string; reason: string };

const actionTypes = new Set([
  "fill_text", "fill_rich_text", "select_combobox_option", "select_enhanced_options", "select", "set_date",
  "set_checkbox", "set_radio", "add_repeatable_section", "upload_document", "propose_intermediate_navigation",
]);

function record(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function isDeclarativeAction(value: unknown): value is DeclarativeAction {
  if (!record(value) || !actionTypes.has(String(value.type)) || Object.keys(value).some((key) =>
    !["type", "fieldId", "value", "checked", "sectionId", "values", "documentId", "documentVersion",
      "stepId", "selector", "expectedTransition", "controlKind", "monthFieldId", "yearFieldId", "datePickerSelector",
      "optionSelector", "acceptedStateSelector"].includes(key))) return false;
  if (typeof value.type !== "string") return false;
  if (["fill_text", "fill_rich_text", "select", "set_date"].includes(value.type)) {
    if (typeof value.fieldId !== "string" || typeof value.value !== "string") return false;
    if (value.type !== "set_date") return true;
    return (value.monthFieldId === undefined && value.yearFieldId === undefined ||
      typeof value.monthFieldId === "string" && typeof value.yearFieldId === "string") &&
      (value.datePickerSelector === undefined || typeof value.datePickerSelector === "string");
  }
  if (value.type === "select_combobox_option") {
    return typeof value.fieldId === "string" && typeof value.value === "string" &&
      typeof value.optionSelector === "string" && value.optionSelector.length > 0 &&
      (value.acceptedStateSelector === undefined || typeof value.acceptedStateSelector === "string");
  }
  if (value.type === "select_enhanced_options") {
    return typeof value.fieldId === "string" && Array.isArray(value.values) &&
      value.values.length > 0 && value.values.every((item) => typeof item === "string" && item.length > 0);
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
  // The adapter is validated by shape rather than against a fixed list so new
  // providers do not require editing this module. It must still be a plain
  // lowercase identifier, so a plan cannot smuggle arbitrary text through.
  return record(value) && value.schemaVersion === 1 &&
    typeof value.adapter === "string" && /^[a-z][a-z0-9_]{1,31}$/u.test(value.adapter) &&
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
  if (action.type === "select_combobox_option") {
    return { status: "unresolved", actionType: action.type, reason: "Combobox options require the asynchronous centralized executor." };
  }
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

export async function executeComboboxOptionAction(
  document: Document,
  action: Extract<NativeValueAction, { type: "select_combobox_option" }>,
  resolve: (fieldId: string) => Element | null = (fieldId) => document.getElementById(fieldId),
): Promise<ActionExecution> {
  const control = resolveControl(document, action.fieldId, resolve);
  if (!(control instanceof HTMLInputElement) || ["submit", "button", "file"].includes(control.type)) {
    return { status: "unresolved", actionType: action.type, reason: "The declared combobox input is unavailable." };
  }
  control.focus();
  setProperty(control, "value", action.value);
  emitFrameworkEvents(control);
  const choose = (): HTMLElement | null => {
    const options = Array.from(document.querySelectorAll<HTMLElement>(action.optionSelector))
      .filter((item) => item.getAttribute("aria-disabled") !== "true" && !item.hasAttribute("disabled"));
    const exact = options.filter((item) => {
      const label = String(item.getAttribute("data-value") || item.textContent || "").trim().toLowerCase();
      return label === action.value.trim().toLowerCase();
    });
    return exact.length === 1 ? exact[0]! : options.length === 1 ? options[0]! : null;
  };
  let option = choose();
  if (!option) {
    option = await new Promise<HTMLElement | null>((resolveOption) => {
      const observer = new MutationObserver(() => {
        const candidate = choose();
        if (!candidate) return;
        observer.disconnect();
        clearTimeout(timeout);
        resolveOption(candidate);
      });
      observer.observe(document.documentElement, { childList: true, subtree: true });
      const timeout = setTimeout(() => { observer.disconnect(); resolveOption(null); }, 2_000);
    });
  }
  if (!option) {
    control.blur();
    return { status: "unresolved", actionType: action.type, reason: "The combobox did not expose one deterministic matching option." };
  }
  option.click();
  await Promise.resolve();
  const accepted = action.acceptedStateSelector
    ? document.querySelector<HTMLInputElement>(action.acceptedStateSelector)
    : null;
  const visibleValue = control.value.trim();
  if (!visibleValue || (accepted && !accepted.value.trim())) {
    return { status: "unresolved", actionType: action.type, reason: "The combobox did not retain a verified selected state." };
  }
  return { status: "applied", actionType: action.type };
}

export type EnhancedSelectionExecution = ActionExecution & {
  /** Values confirmed selected by reading the control back. */
  applied?: string[];
  /** Values the control did not offer or did not retain. */
  rejected?: string[];
};

function normalizedText(value: string): string {
  return value.replace(/\s+/gu, " ").trim().toLowerCase();
}

/** Finds the listbox a combobox drives, whether declared or adjacent. */
function relatedListbox(document: Document, control: Element): Element | null {
  const controls = control.getAttribute("aria-controls") || control.getAttribute("aria-owns");
  if (controls) {
    const declared = document.getElementById(controls);
    if (declared) return declared;
  }
  const sibling = control.parentElement?.querySelector("[role='listbox']");
  if (sibling && sibling !== control) return sibling;
  return control.getAttribute("role") === "listbox" ? control : null;
}

function optionElements(root: ParentNode): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>("[role='option']"))
    .filter((option) => option.getAttribute("aria-disabled") !== "true" && !option.hasAttribute("disabled"));
}

/**
 * An option can be identified by its visible text or by its declared value, and
 * widgets disagree about which carries the human label. Both are compared, so a
 * list rendering "Germany" behind `data-value="DE"` still matches "Germany".
 */
function optionIdentifiers(option: Element): string[] {
  return [normalizedText(option.textContent || ""), normalizedText(option.getAttribute("data-value") || "")]
    .filter((value) => value.length > 0);
}

function optionText(option: Element): string {
  return optionIdentifiers(option)[0] ?? "";
}

function optionMatches(option: Element, wanted: string): boolean {
  return optionIdentifiers(option).includes(wanted);
}

/** True when the control visibly reflects the value after selection. */
function selectionRetained(control: Element, listbox: Element | null, value: string): boolean {
  const wanted = normalizedText(value);
  if (listbox) {
    const chosen = optionElements(listbox).some(
      (option) => option.getAttribute("aria-selected") === "true" && optionMatches(option, wanted),
    );
    if (chosen) return true;
  }
  const container = control.parentElement ?? control;
  const chipText = normalizedText(container.textContent || "");
  if (chipText.includes(wanted)) return true;
  const inner = control.querySelector("input") ?? (control instanceof HTMLInputElement ? control : null);
  return Boolean(inner && normalizedText(inner.value).includes(wanted));
}

/**
 * Operates enhanced list controls: native multi-selects, ARIA comboboxes, and
 * searchable selects that filter as you type.
 *
 * Every value is verified by reading the control back after selection. A value
 * the control never offered, or accepted and then dropped, is reported rejected
 * rather than counted as applied ??? the panel routes those to review.
 */
export async function executeEnhancedSelection(
  document: Document,
  action: Extract<DeclarativeAction, { type: "select_enhanced_options" }>,
  resolve: (fieldId: string) => Element | null = (fieldId) => document.getElementById(fieldId),
): Promise<EnhancedSelectionExecution> {
  const control = resolveControl(document, action.fieldId, resolve);
  if (!control) {
    return { status: "unresolved", actionType: action.type, reason: "The enhanced control is unavailable." };
  }
  if (control.tagName === "BUTTON" || (control instanceof HTMLInputElement && ["submit", "button", "image", "reset"].includes(control.type))) {
    return { status: "rejected", actionType: action.type, reason: "Terminal or button controls are never executable." };
  }

  const applied: string[] = [];
  const rejected: string[] = [];

  // Native selects need no interaction choreography.
  if (control instanceof HTMLSelectElement) {
    (control as HTMLElement).focus();
    for (const value of action.values) {
      const wanted = normalizedText(value);
      const option = Array.from(control.options).find(
        (item) => item.value === value || normalizedText(item.label || item.textContent || "") === wanted,
      );
      if (!option) {
        rejected.push(value);
        continue;
      }
      if (control.multiple) option.selected = true;
      else setProperty(control, "value", option.value);
      applied.push(value);
    }
    emitFrameworkEvents(control);
    (control as HTMLElement).blur();
    const confirmed = applied.filter((value) => {
      const wanted = normalizedText(value);
      return Array.from(control.selectedOptions).some(
        (item) => item.value === value || normalizedText(item.label || item.textContent || "") === wanted,
      );
    });
    const dropped = applied.filter((value) => !confirmed.includes(value));
    rejected.push(...dropped);
    return confirmed.length === action.values.length
      ? { status: "applied", actionType: action.type, applied: confirmed, rejected }
      : confirmed.length > 0
        ? { status: "needs_attention", actionType: action.type, reason: "Some values were not accepted by the control.", applied: confirmed, rejected }
        : { status: "unresolved", actionType: action.type, reason: "The control did not accept any of the values.", applied: [], rejected };
  }

  const listbox = relatedListbox(document, control);
  const inner = control.querySelector<HTMLInputElement>("input");

  for (const value of action.values) {
    (control as HTMLElement).focus();
    // Activation is never synthesized: focus plus typed input is what opens
    // most searchable widgets, and any widget that only opens on a real
    // pointer event is reported unresolved rather than clicked. Option choice
    // is the one classified non-terminal interaction (AA-216).

    if (inner) {
      setProperty(inner, "value", value);
      emitFrameworkEvents(inner);
    }

    const searchRoot = relatedListbox(document, control) ?? listbox ?? document;
    const wanted = normalizedText(value);
    const pick = (): HTMLElement | null => {
      const options = optionElements(searchRoot);
      const exact = options.filter((option) => optionMatches(option, wanted));
      if (exact.length === 1) return exact[0]!;
      const starts = options.filter((option) => optionText(option).startsWith(wanted));
      return starts.length === 1 ? starts[0]! : null;
    };

    let option = pick();
    if (!option) {
      // Options frequently arrive asynchronously after typing.
      option = await new Promise<HTMLElement | null>((resolveOption) => {
        const observer = new MutationObserver(() => {
          const candidate = pick();
          if (!candidate) return;
          observer.disconnect();
          clearTimeout(timer);
          resolveOption(candidate);
        });
        observer.observe(document.documentElement, { childList: true, subtree: true });
        const timer = setTimeout(() => { observer.disconnect(); resolveOption(null); }, 1_500);
      });
    }

    if (!option) {
      rejected.push(value);
      continue;
    }
    option.click();
    await Promise.resolve();

    if (selectionRetained(control, relatedListbox(document, control) ?? listbox, value)) applied.push(value);
    else rejected.push(value);
  }

  (control as HTMLElement).blur();

  if (applied.length === action.values.length) {
    return { status: "applied", actionType: action.type, applied, rejected };
  }
  if (applied.length > 0) {
    return { status: "needs_attention", actionType: action.type, reason: "Some values were not accepted by the control.", applied, rejected };
  }
  return { status: "unresolved", actionType: action.type, reason: "The control did not expose matching options.", applied, rejected };
}

/** Wording used by "add another row" affordances in repeated sections. */
const ADD_ROW_PATTERNS: ReadonlyArray<RegExp> = [
  /\badd\s+another\b/iu,
  /\badd\s+(?:more|new|another\s+)?(?:experience|education|position|role|school|qualification)\b/iu,
  /\badd\b/iu,
  /\bweitere[ns]?\s+hinzuf/iu,
];

/** Wording that must never be mistaken for an add-row control. */
const NOT_ADD_ROW: ReadonlyArray<RegExp> = [
  /\bsubmit\b/iu, /\bremove\b/iu, /\bdelete\b/iu, /\bcontinue\b/iu, /\bnext\b/iu, /\bsave\b/iu, /\bapply\b/iu,
];

export type AddRowExecution = ActionExecution & {
  /** Number of repeat containers present after the attempt. */
  rowCount?: number;
};

/**
 * Classifies the add-row control of a repeated section without activating it.
 *
 * The control is found by reading button text inside the section; terminal and
 * destructive wording is excluded outright, and ambiguous sections are refused
 * rather than guessed. Runr never dispatches a click on a page control, so a
 * single identified candidate is reported `needs_attention` for a trusted user
 * activation instead of being operated by code.
 */
export function executeAddRepeatedRow(
  document: Document,
  sectionRoot: Element,
  repeatSelector = "[data-repeat], [data-repeat-index], fieldset",
): AddRowExecution {
  const countRows = () => sectionRoot.querySelectorAll(repeatSelector).length;
  const before = countRows();

  const candidates = Array.from(sectionRoot.querySelectorAll<HTMLElement>("button, a[role='button'], [data-repeat-add]"))
    .filter((element) => !(element as HTMLButtonElement).disabled)
    .filter((element) => {
      const label = (element.getAttribute("aria-label") || element.textContent || "").replace(/\s+/gu, " ").trim();
      if (!label) return Boolean(element.getAttribute("data-repeat-add"));
      if (NOT_ADD_ROW.some((pattern) => pattern.test(label))) return false;
      return ADD_ROW_PATTERNS.some((pattern) => pattern.test(label));
    });

  if (candidates.length === 0) {
    return { status: "unresolved", actionType: "add_repeatable_section", reason: "This section has no add-row control.", rowCount: before };
  }
  if (candidates.length > 1) {
    return { status: "unresolved", actionType: "add_repeatable_section", reason: "More than one add-row control was found.", rowCount: before };
  }

  const candidate = candidates[0]!;
  const label = (candidate.getAttribute("aria-label") || candidate.textContent || "").replace(/\s+/gu, " ").trim();
  return {
    status: "needs_attention",
    actionType: "add_repeatable_section",
    reason: `Add-row control identified ("${label}"); row creation waits for a trusted user activation.`,
    rowCount: before,
  };
}

/**
 * Confirms a row was actually created after a trusted user activates the
 * add-row control. Reading the page back is what separates "the row exists"
 * from "an activation was sent": a count that did not grow is reported
 * unresolved rather than assumed to have worked.
 */
export function verifyRepeatedRowGrowth(
  before: number,
  sectionRoot: Element,
  repeatSelector = "[data-repeat], [data-repeat-index], fieldset",
): AddRowExecution {
  const after = sectionRoot.querySelectorAll(repeatSelector).length;
  if (after <= before) {
    return { status: "unresolved", actionType: "add_repeatable_section", reason: "The page did not add a row.", rowCount: after };
  }
  return { status: "applied", actionType: "add_repeatable_section", rowCount: after };
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
  if (action.type === "add_repeatable_section" || action.type === "upload_document" ||
      action.type === "select_enhanced_options") {
    // These need the asynchronous executors; the synchronous entry point cannot
    // await them, so it reports rather than half-applying.
    return { status: "needs_attention", actionType: action.type, reason: "This action requires the adapter-specific controlled executor." };
  }
  return executeNativeValueAction(document, action);
}
