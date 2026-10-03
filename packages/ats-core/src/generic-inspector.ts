import type { PageContext } from "./index";
import {
  classifyFieldIntent,
  normalizeFieldLabel,
  type ApplicationControlType,
  type DetectedApplicationField,
  type ManualOnlyReason,
} from "./field-intent";

/**
 * Provider-neutral form inspection.
 *
 * Walks the document and any reachable open shadow roots, and reports every
 * control a candidate would be expected to complete, together with the section
 * it belongs to and ??? for repeated work-experience and education blocks ??? which
 * instance it belongs to.
 *
 * Anything that cannot be inspected is reported in `unsupported` rather than
 * omitted. A silently dropped control reads as "handled" in the panel, which is
 * the failure mode this design exists to avoid.
 */

export const GENERIC_INSPECTOR_VERSION = "1.0.0";

export interface InspectedSection {
  id: string;
  heading: string;
  kind: "experience" | "education" | "other";
  repeatIndex?: number;
}

export interface UnsupportedControl {
  reason: ManualOnlyReason;
  detail: string;
}

export interface GenericInspection {
  fields: DetectedApplicationField[];
  sections: InspectedSection[];
  unsupported: UnsupportedControl[];
  inspectorVersion: string;
}

type AnyControl = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | HTMLElement;

const CONTROL_SELECTOR = "input, textarea, select, [role='combobox'], [role='listbox']";
const SKIPPED_INPUT_TYPES = new Set(["hidden", "submit", "button", "reset", "image"]);

/**
 * `CSS.escape` is not present in every document context Runr runs in, so
 * selector escaping falls back to a conservative manual escape rather than
 * throwing partway through an inspection.
 */
function escapeSelector(value: string): string {
  const globalCss = (globalThis as { CSS?: { escape?: (input: string) => string } }).CSS;
  if (typeof globalCss?.escape === "function") return globalCss.escape(value);
  return value.replace(/[^a-zA-Z0-9_-]/gu, (character) => `\\${character}`);
}

function isInput(node: Element): node is HTMLInputElement {
  return node.tagName === "INPUT";
}
function isTextarea(node: Element): node is HTMLTextAreaElement {
  return node.tagName === "TEXTAREA";
}
function isSelect(node: Element): node is HTMLSelectElement {
  return node.tagName === "SELECT";
}

function controlTypeOf(node: Element): ApplicationControlType {
  if (isTextarea(node)) return "textarea";
  if (isSelect(node)) return node.multiple ? "multiselect" : "select";
  if (isInput(node)) {
    const type = node.type.toLowerCase();
    const known: ApplicationControlType[] = [
      "text", "email", "tel", "url", "number", "radio", "checkbox", "date", "month", "file",
    ];
    return (known as string[]).includes(type) ? (type as ApplicationControlType) : "unknown";
  }
  const role = node.getAttribute("role");
  if (role === "combobox") {
    return node.getAttribute("aria-multiselectable") === "true" ? "multiselect" : "combobox";
  }
  if (role === "listbox") return "multiselect";
  return "custom";
}

function visible(node: Element): boolean {
  if (node.hasAttribute("hidden")) return false;
  if (node.closest('[hidden], [aria-hidden="true"]')) return false;
  const view = node.ownerDocument.defaultView;
  if (!view) return true;
  for (let current: Element | null = node; current; current = current.parentElement) {
    const style = view.getComputedStyle(current);
    if (style.display === "none" || style.visibility === "hidden") return false;
  }
  return true;
}

function labelFor(node: Element): string {
  const root = node.getRootNode();
  const scope: ParentNode = root instanceof ShadowRoot ? root : node.ownerDocument;
  const id = node.getAttribute("id");

  if (isInput(node) && node.type === "radio") {
    const legend = node.closest("fieldset")?.querySelector(":scope > legend")?.textContent;
    if (legend?.trim()) return legend.trim();
  }

  const labelledBy = node.getAttribute("aria-labelledby");
  if (labelledBy) {
    const text = labelledBy
      .split(/\s+/u)
      .map((token) => scope.querySelector(`#${escapeSelector(token)}`)?.textContent || "")
      .join(" ")
      .trim();
    if (text) return text;
  }

  const explicit = id
    ? Array.from(scope.querySelectorAll("label")).find((label) => (label as HTMLLabelElement).htmlFor === id)
    : undefined;

  return (
    explicit?.textContent ||
    node.closest("label")?.textContent ||
    node.getAttribute("aria-label") ||
    node.getAttribute("placeholder") ||
    node.getAttribute("name") ||
    ""
  ).replace(/\s+/gu, " ").trim();
}

function currentValueOf(node: Element): string {
  if (isInput(node)) {
    if (node.type === "checkbox" || node.type === "radio") return node.checked ? node.value || "on" : "";
    if (node.type === "file") return node.files?.[0]?.name ?? "";
    return node.value;
  }
  if (isTextarea(node) || isSelect(node)) return node.value;
  return (node.getAttribute("data-value") || node.textContent || "").trim();
}

function optionsOf(node: Element): Array<{ label: string; value: string }> | undefined {
  if (isSelect(node)) {
    return Array.from(node.options).map((option) => ({
      label: (option.textContent || option.label || "").trim(),
      value: option.value,
    }));
  }
  if (isInput(node) && node.type === "radio" && node.name) {
    const scope = node.getRootNode() instanceof ShadowRoot
      ? (node.getRootNode() as ShadowRoot)
      : node.ownerDocument;
    return Array.from(scope.querySelectorAll<HTMLInputElement>('input[type="radio"]'))
      .filter((candidate) => candidate.name === node.name)
      .map((candidate) => ({
        label: (candidate.labels?.[0]?.textContent || candidate.value).trim(),
        value: candidate.value,
      }));
  }
  const listbox = node.getAttribute("role") === "combobox"
    ? node.ownerDocument.getElementById(node.getAttribute("aria-controls") || "")
    : node.getAttribute("role") === "listbox" ? node : null;
  if (listbox) {
    const items = Array.from(listbox.querySelectorAll("[role='option']"));
    if (items.length) {
      return items.map((item) => ({
        label: (item.textContent || "").trim(),
        value: item.getAttribute("data-value") || (item.textContent || "").trim(),
      }));
    }
  }
  return undefined;
}

const HEADING_SELECTOR = "h1, h2, h3, h4, h5, h6, legend";

/**
 * The heading a candidate would read as governing this control: the last one
 * that appears before it in document order.
 *
 * Reading position rather than DOM containment is deliberate. Real portals nest
 * every section of a step inside one wrapper, so a containment-based search
 * returns whichever heading happens to come first in that wrapper ??? on a live
 * Avature form that made every work-experience control inherit the "Skills"
 * heading and lose its section entirely.
 */
function sectionHeadingFor(node: Element): string {
  const root = node.getRootNode();
  const scope: ParentNode = root instanceof ShadowRoot ? root : node.ownerDocument;
  const headings = Array.from(scope.querySelectorAll(HEADING_SELECTOR));

  let nearest = "";
  for (const heading of headings) {
    const position = heading.compareDocumentPosition(node);
    // Keep the last heading that precedes the control, or contains it.
    const precedes = (position & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
    const contains = (position & Node.DOCUMENT_POSITION_CONTAINED_BY) !== 0;
    if (!precedes && !contains) continue;
    const text = heading.textContent?.replace(/\s+/gu, " ").trim();
    if (text) nearest = text;
  }
  return nearest;
}

function sectionKindFor(heading: string): InspectedSection["kind"] {
  const normalized = normalizeFieldLabel(heading);
  if (/work experience|employment history|berufserfahrung|work history/u.test(normalized)) return "experience";
  if (/education|ausbildung|studium|academic/u.test(normalized)) return "education";
  return "other";
}

/**
 * The container that repeats. Portals mark these in different ways, so this
 * accepts explicit markers first and falls back to the nearest `fieldset`.
 */
function repeatContainerFor(node: Element): Element | null {
  return node.closest("[data-repeat], [data-repeat-index], fieldset");
}

function collectRoots(document: Document): Array<Document | ShadowRoot> {
  const roots: Array<Document | ShadowRoot> = [document];
  const queue: ParentNode[] = [document];
  while (queue.length) {
    const root = queue.shift()!;
    for (const element of Array.from(root.querySelectorAll("*"))) {
      const shadow = (element as HTMLElement).shadowRoot;
      if (shadow) {
        roots.push(shadow);
        queue.push(shadow);
      }
    }
  }
  return roots;
}

function stableId(intent: string, node: Element, index: number): string {
  const identity =
    node.getAttribute("id") ||
    node.getAttribute("name") ||
    node.getAttribute("data-automation-id") ||
    `${intent}-${index}`;
  return `field-${identity.toLowerCase().replace(/[^a-z0-9_-]+/gu, "-").replace(/^-|-$/gu, "") || index}`;
}

/**
 * Detects controls Runr cannot inspect, so they are reported rather than
 * silently treated as absent.
 */
function collectUnsupported(document: Document, pageUrl: string): UnsupportedControl[] {
  const unsupported: UnsupportedControl[] = [];

  let pageOrigin = "";
  try {
    pageOrigin = new URL(pageUrl).origin;
  } catch {
    pageOrigin = "";
  }

  for (const frame of Array.from(document.querySelectorAll("iframe"))) {
    // Compare declared origins first. A browser returns a null contentDocument
    // for a cross-origin frame, but a test DOM may not, and the frame's own src
    // is the honest signal either way.
    const src = frame.getAttribute("src") || "";
    let sameOrigin = true;
    if (src && !src.startsWith("about:") && !src.startsWith("javascript:")) {
      try {
        sameOrigin = new URL(src, pageUrl || undefined).origin === pageOrigin;
      } catch {
        sameOrigin = false;
      }
    }

    let reachable = sameOrigin;
    if (reachable) {
      try {
        reachable = Boolean(frame.contentDocument);
      } catch {
        reachable = false;
      }
    }
    if (!reachable) {
      unsupported.push({
        reason: "cross_origin_frame",
        detail: `A section of this application is in a frame Runr cannot read (${frame.getAttribute("title") || frame.getAttribute("name") || "untitled frame"}).`,
      });
    }
  }

  // A custom element with neither light-DOM children nor an open shadow root is
  // either empty or closed; either way its controls cannot be inspected.
  for (const element of Array.from(document.querySelectorAll("*"))) {
    if (!element.tagName.includes("-")) continue;
    if (element.children.length > 0 || (element as HTMLElement).shadowRoot) continue;
    if (element.hasAttribute("data-runr-assisted-apply")) continue;
    unsupported.push({
      reason: "closed_shadow_root",
      detail: `Runr cannot read inside <${element.tagName.toLowerCase()}>.`,
    });
  }

  return unsupported;
}

export function inspectApplicationForm(context: PageContext): GenericInspection {
  const { document } = context;
  const fields: DetectedApplicationField[] = [];
  const sections = new Map<string, InspectedSection>();

  // Repeat indices are assigned per section heading: containers under the same
  // heading that share labels are instances of one repeated block.
  const containersByHeading = new Map<string, Element[]>();
  const seenRadioGroups = new Set<string>();

  const controls: Element[] = [];
  for (const root of collectRoots(document)) {
    for (const node of Array.from(root.querySelectorAll(CONTROL_SELECTOR))) {
      controls.push(node);
    }
  }

  for (const node of controls) {
    if (isInput(node) && SKIPPED_INPUT_TYPES.has(node.type.toLowerCase())) continue;
    // Hidden template rows are not repeat instances. Portals commonly keep an
    // invisible "sample" row next to the real ones; counting it would shift
    // every real row's index by one and map it to the wrong profile entry.
    if (!visible(node)) continue;
    const heading = sectionHeadingFor(node);
    const container = repeatContainerFor(node);
    if (!container) continue;
    const list = containersByHeading.get(heading) ?? [];
    if (!list.includes(container)) list.push(container);
    containersByHeading.set(heading, list);
  }

  controls.forEach((node, index) => {
    if (isInput(node) && SKIPPED_INPUT_TYPES.has(node.type.toLowerCase())) return;
    if (!visible(node)) return;

    // One field per radio group, not one per radio button.
    if (isInput(node) && node.type === "radio" && node.name) {
      if (seenRadioGroups.has(node.name)) return;
      seenRadioGroups.add(node.name);
    }

    const controlType = controlTypeOf(node);
    const label = labelFor(node);
    const heading = sectionHeadingFor(node);
    const kind = sectionKindFor(heading);

    const container = repeatContainerFor(node);
    const siblings = containersByHeading.get(heading) ?? [];
    const repeatIndex = container && siblings.length > 1 && kind !== "other"
      ? siblings.indexOf(container)
      : undefined;

    const sectionId = heading ? `section-${normalizeFieldLabel(heading).replace(/[^a-z0-9]+/gu, "-").replace(/^-|-$/gu, "")}` : undefined;
    if (sectionId && !sections.has(sectionId)) {
      sections.set(sectionId, { id: sectionId, heading, kind });
    }

    const classification = classifyFieldIntent({
      label,
      controlType,
      section: kind === "other" ? undefined : kind,
      ariaLabel: node.getAttribute("aria-label") ?? undefined,
      placeholder: node.getAttribute("placeholder") ?? node.getAttribute("data-placeholder") ?? undefined,
      name: node.getAttribute("name") ?? undefined,
      autocomplete: node.getAttribute("autocomplete") ?? undefined,
      sectionHeading: heading,
    });

    fields.push({
      id: stableId(classification.intent, node, index),
      locator: {
        elementId: node.getAttribute("id") ?? undefined,
        name: node.getAttribute("name") ?? undefined,
        automationId: node.getAttribute("data-automation-id") ?? undefined,
      },
      intent: classification.intent,
      label: label || `Unlabelled ${controlType} control`,
      controlType,
      required: node.hasAttribute("required") || node.getAttribute("aria-required") === "true",
      currentValue: currentValueOf(node),
      options: optionsOf(node),
      sectionId,
      repeatIndex,
      sensitivity: classification.sensitivity,
      sourceEvidence: classification.sourceEvidence,
      confidence: classification.confidence,
      manualReason: classification.manualReason,
    });
  });

  return {
    fields,
    sections: Array.from(sections.values()),
    unsupported: collectUnsupported(document, context.url),
    inspectorVersion: GENERIC_INSPECTOR_VERSION,
  };
}

/**
 * Builds a resolver that maps planner field ids back to live controls.
 *
 * Uses the locator captured at inspection time rather than reconstructing a
 * selector from the normalised id, which is lossy for camelCase control ids.
 */
export function controlResolver(
  document: Document,
  inspection: GenericInspection,
): (fieldId: string) => Element | null {
  const byId = new Map(inspection.fields.map((field) => [field.id, field.locator]));
  return (fieldId: string): Element | null => {
    const locator = byId.get(fieldId);
    if (!locator) return null;
    if (locator.elementId) {
      const found = document.getElementById(locator.elementId);
      if (found) return found;
    }
    for (const [attribute, value] of [["name", locator.name], ["data-automation-id", locator.automationId]] as const) {
      if (!value) continue;
      const found = document.querySelector(`[${attribute}="${escapeSelector(value)}"]`);
      if (found) return found;
    }
    return null;
  };
}

/** Convenience accessor for the repeated blocks in an inspection. */
export function repeatedInstances(
  inspection: GenericInspection,
  kind: "experience" | "education",
): DetectedApplicationField[][] {
  const relevant = inspection.fields.filter(
    (field) => field.intent.startsWith(`${kind}.`) && field.repeatIndex !== undefined,
  );
  const byIndex = new Map<number, DetectedApplicationField[]>();
  for (const field of relevant) {
    const list = byIndex.get(field.repeatIndex!) ?? [];
    list.push(field);
    byIndex.set(field.repeatIndex!, list);
  }
  return Array.from(byIndex.entries())
    .sort((left, right) => left[0] - right[0])
    .map(([, group]) => group);
}
