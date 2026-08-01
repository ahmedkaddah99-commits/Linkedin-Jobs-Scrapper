import { requestPageContextSet } from "./page-bridge";
import { executeNativeValueAction, inspectControlValidation, planFillAction, readControlValue, type NativeValueAction } from "./declarative-actions";

export * from "./telemetry";
export * from "./declarative-actions";
export * from "./submission-guard";
export * from "./reconciliation";

export type AtsType = "greenhouse" | "lever";
export type UploadFieldIntent =
  | "greenhouse.resume"
  | "greenhouse.cover_letter"
  | "greenhouse.supporting_document"
  | "lever.resume"
  | "lever.cover_letter"
  | "lever.supporting_document";

export type ApplicationDocumentKind = "cv" | "cover_letter" | "supporting_document";

export function uploadFieldIntentFor(
  ats: AtsType,
  kind: ApplicationDocumentKind,
): UploadFieldIntent {
  return `${ats}.${kind === "cv" ? "resume" : kind}` as UploadFieldIntent;
}

export interface PageContext {
  url: string;
  document: Document;
}

export interface DetectionResult {
  detected: boolean;
  ats: AtsType | null;
  confidence: number;
  reasons: string[];
}

export type DetectedFieldType =
  | "text"
  | "email"
  | "tel"
  | "textarea"
  | "select"
  | "radio"
  | "checkbox"
  | "date"
  | "file"
  | "unknown";

export type ManualReason =
  | "final_submission"
  | "captcha"
  | "signature"
  | "legal_declaration"
  | "legal_terms"
  | "assessment"
  | "cross_origin_frame"
  | "closed_shadow_root"
  | "unsupported_custom_control"
  | "unsupported_control";

export interface DetectedField {
  id: string;
  stepId: string;
  label: string;
  normalizedLabel: string;
  type: DetectedFieldType;
  required: boolean;
  disabled: boolean;
  hidden: boolean;
  options?: Array<{ label: string; value: string }>;
  existingValue?: unknown;
  classification: "fillable" | "manual";
  uploadFieldIntent?: UploadFieldIntent;
  manualReason?: ManualReason;
  locator: {
    adapterStrategy: string;
    stableAttributes: Record<string, string>;
  };
}

export interface InspectedApplicationForm {
  ats: AtsType;
  fields: DetectedField[];
}

export interface ApplicationPackageCandidate {
  firstName?: string;
  lastName?: string;
  fullName?: string;
  email?: string;
  phone?: string;
}

export interface ApplicationPackageAnswer {
  fieldIntent: string;
  label: string;
  proposedValue: string;
}

export interface ApplicationPackage {
  id: string;
  version: number;
  candidate: ApplicationPackageCandidate;
  answers?: ApplicationPackageAnswer[];
}

export interface FieldMatch {
  detectedFieldId: string;
  fieldLabel: string;
  fieldIntent: string;
  proposedValue?: unknown;
  confidence: number;
  source: "profile_verified" | "unknown";
  sensitivity: "standard" | "personal" | "legal" | "demographic";
  action: "fill" | "leave_empty" | "manual_only";
  reasons: string[];
}

export interface ApprovedFieldMatch extends FieldMatch {
  action: "fill";
  proposedValue: string;
}

export type FieldExecutionStatus =
  | "filled"
  | "already_filled"
  | "preserved_existing"
  | "skipped_hidden"
  | "skipped_disabled"
  | "rejected"
  | "mismatch";

export interface FieldExecutionResult {
  detectedFieldId: string;
  fieldLabel: string;
  fieldIntent?: string;
  status: FieldExecutionStatus;
  existingValue?: string;
  acceptedValue?: string;
  validationMessage?: string;
  reasons: string[];
}

export interface DocumentUploadRequest {
  detectedFieldId: string;
  file: File;
  documentId: string;
  documentVersion: number;
  documentKind: "cv" | "cover_letter" | "supporting_document";
  uploadFieldIntent: UploadFieldIntent;
}

export interface DocumentUploadResult {
  status: "uploaded" | "rejected" | "mismatch" | "preserved_existing" | "unsupported";
  fileName?: string;
  reasons: string[];
}

export interface FormValidationResult {
  valid: boolean;
  invalidFieldIds: string[];
}

export interface SubmissionEvidence {
  kind: string;
  confidence: number;
}

export interface AtsAdapter {
  readonly id: AtsType;
  readonly version: string;

  detect(context: PageContext): Promise<DetectionResult>;
  inspect(context: PageContext): Promise<InspectedApplicationForm>;
  match(
    form: InspectedApplicationForm,
    applicationPackage: ApplicationPackage,
  ): Promise<FieldMatch[]>;
  plan(match: ApprovedFieldMatch): NativeValueAction | null;
  fill(match: ApprovedFieldMatch): Promise<FieldExecutionResult>;
  authorizeReplacement(detectedFieldId: string): void;
  upload(request: DocumentUploadRequest): Promise<DocumentUploadResult>;
  validate(form: InspectedApplicationForm): Promise<FormValidationResult>;
  detectPossibleSubmissionSuccess(
    context: PageContext,
  ): Promise<SubmissionEvidence | null>;
}

export const ATS_ADAPTER_CAPABILITIES = [
  "detect",
  "inspect",
  "match",
  "plan",
  "fill",
  "authorizeReplacement",
  "upload",
  "validate",
  "detectPossibleSubmissionSuccess",
] as const satisfies ReadonlyArray<keyof AtsAdapter>;

type ForbiddenSubmissionCapability = Extract<
  keyof AtsAdapter,
  `${string}${"submit" | "Submit"}${string}`
>;

// Adding a forbidden method to AtsAdapter turns this assignment into a type error.
export const ADAPTER_SUBMISSION_CAPABILITY_FORBIDDEN: ForbiddenSubmissionCapability extends never
  ? true
  : false = true;

function safeUrl(value: string): URL | null {
  try {
    return new URL(value);
  } catch {
    return null;
  }
}

export function detectAtsFromUrl(value: string): DetectionResult {
  const parsed = safeUrl(value);
  if (!parsed || parsed.protocol !== "https:") {
    return {
      detected: false,
      ats: null,
      confidence: 0,
      reasons: ["URL is not a supported HTTPS application portal."],
    };
  }

  const hostname = parsed.hostname.toLowerCase();
  if (hostname === "boards.greenhouse.io") {
    return {
      detected: true,
      ats: "greenhouse",
      confidence: 1,
      reasons: ["The page host is a Greenhouse-owned domain."],
    };
  }

  if (hostname.endsWith(".lever.co")) {
    return {
      detected: true,
      ats: "lever",
      confidence: 1,
      reasons: ["The page host is a supported Lever jobs domain."],
    };
  }

  return {
    detected: false,
    ats: null,
    confidence: 0,
    reasons: ["The page host is outside the supported application portals."],
  };
}

function normalizeLabel(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

function isInput(control: Element | null | undefined): control is HTMLInputElement {
  return control?.tagName.toLowerCase() === "input";
}

function isTextarea(control: Element | null | undefined): control is HTMLTextAreaElement {
  return control?.tagName.toLowerCase() === "textarea";
}

function isSelect(control: Element | null | undefined): control is HTMLSelectElement {
  return control?.tagName.toLowerCase() === "select";
}

function isButton(control: Element | null | undefined): control is HTMLButtonElement {
  return control?.tagName.toLowerCase() === "button";
}

function isShadowRoot(root: Node): root is ShadowRoot {
  return root.nodeType === Node.DOCUMENT_FRAGMENT_NODE && "host" in root;
}

function queryRoot(control: Element): Document | ShadowRoot {
  const root = control.getRootNode();
  return isShadowRoot(root) ? root : control.ownerDocument;
}

function controlLabel(control: Element, root: Document | ShadowRoot): string {
  if (isInput(control) && control.type === "radio") {
    const legend = control.closest("fieldset")?.querySelector(":scope > legend")?.textContent?.trim();
    if (legend) return legend;
  }
  const id = control.getAttribute("id");
  const explicit = id
    ? Array.from(root.querySelectorAll("label")).find((label) => label.htmlFor === id) ?? null
    : null;
  const wrapping = control.closest("label");
  return (
    explicit?.textContent ||
    wrapping?.textContent ||
    control.getAttribute("aria-label") ||
    control.getAttribute("placeholder") ||
    control.getAttribute("name") ||
    "Unlabelled control"
  ).trim();
}

function fieldType(control: Element): DetectedFieldType {
  if (isTextarea(control)) return "textarea";
  if (isSelect(control)) return "select";
  if (!isInput(control)) return "unknown";
  const type = control.type.toLowerCase();
  if (["text", "email", "tel", "radio", "checkbox", "date", "file"].includes(type)) {
    return type as DetectedFieldType;
  }
  return "unknown";
}

function declaredUploadFieldIntent(ats: AtsType, control: Element): UploadFieldIntent | undefined {
  if (!isInput(control) || control.type !== "file") return undefined;
  const id = control.id.toLowerCase();
  const name = (control.getAttribute("name") || "").toLowerCase();
  const prefix = ats === "greenhouse" ? "" : "lever-";
  if (id === `${prefix}resume` || name === "resume") return `${ats}.resume` as UploadFieldIntent;
  if (id === `${prefix}cover-letter` || name === "cover_letter") return `${ats}.cover_letter` as UploadFieldIntent;
  if (id === `${prefix}supporting-document` || name === "supporting_document") return `${ats}.supporting_document` as UploadFieldIntent;
  return undefined;
}

function manualReason(control: Element, normalized: string): ManualReason | undefined {
  if (
    (isButton(control) && control.type === "submit") ||
    (isInput(control) && control.type === "submit")
  ) {
    return "final_submission";
  }

  const identity = [
    normalized,
    control.getAttribute("id") || "",
    control.getAttribute("name") || "",
    control.getAttribute("class") || "",
  ]
    .join(" ")
    .toLowerCase();

  if (/captcha|recaptcha|hcaptcha/.test(identity)) return "captcha";
  if (/signature|sign here/.test(identity)) return "signature";
  if (/assessment|skills test|coding test/.test(identity)) return "assessment";
  if (/terms and conditions|accept terms|legal terms/.test(identity)) return "legal_terms";
  if (/declaration|declare|certify|accuracy/.test(identity)) return "legal_declaration";
  return undefined;
}

function isHidden(control: Element): boolean {
  if (isInput(control) && control.type === "hidden") return true;
  if (control.closest('[hidden], [aria-hidden="true"]')) return true;

  const view = control.ownerDocument.defaultView;
  for (let current: Element | null = control; current;) {
    const style = view?.getComputedStyle(current);
    if (
      style?.display === "none" ||
      style?.visibility === "hidden" ||
      style?.visibility === "collapse"
    ) {
      return true;
    }
    const parentElement: Element | null = current.parentElement;
    const root = current.getRootNode();
    current = parentElement || (isShadowRoot(root) ? root.host : null);
  }
  return false;
}

function stableAttributes(control: Element): Record<string, string> {
  const allowed = ["id", "name", "type", "value", "autocomplete", "aria-label"];
  return Object.fromEntries(
    allowed
      .map((name) => [name, control.getAttribute(name) || ""] as const)
      .filter(([, value]) => value.length > 0),
  );
}

function stableFieldId(ats: AtsType, control: Element, normalizedLabel: string, index: number): string {
  const attributes = stableAttributes(control);
  const identity = attributes.id || attributes.name || attributes.autocomplete || normalizedLabel;
  const normalized = identity.toLowerCase().replace(/[^a-z0-9_-]+/gu, "-").replace(/^-|-$/gu, "");
  return `${ats}-field-${normalized || index + 1}`;
}

function existingValue(control: Element): unknown {
  if (isInput(control)) {
    if (control.type === "checkbox" || control.type === "radio") return control.checked;
    return control.value;
  }
  if (isTextarea(control) || isSelect(control)) {
    return control.value;
  }
  return undefined;
}

interface FilledFieldLedgerEntry {
  element: Element;
  acceptedValue: string;
  userModified: boolean;
}

const filledFieldLedgers = new WeakMap<Document, Map<string, FilledFieldLedgerEntry>>();
const ledgerObservedControls = new WeakSet<Element>();

function fillLedger(document: Document): Map<string, FilledFieldLedgerEntry> {
  let ledger = filledFieldLedgers.get(document);
  if (!ledger) {
    ledger = new Map();
    filledFieldLedgers.set(document, ledger);
  }
  return ledger;
}

function inputOption(control: HTMLInputElement): { label: string; value: string } {
  return {
    label: control.labels?.[0]?.textContent?.trim() || control.value,
    value: control.value,
  };
}

function controlOptions(control: Element): Array<{ label: string; value: string }> | undefined {
  if (isSelect(control)) {
    return Array.from(control.options).map((option) => ({
      label: option.textContent?.trim() || option.label,
      value: option.value,
    }));
  }
  if (!isInput(control) || !["radio", "checkbox"].includes(control.type)) {
    return undefined;
  }
  if (control.type === "checkbox" || !control.name) return [inputOption(control)];
  return Array.from(queryRoot(control).querySelectorAll<HTMLInputElement>('input[type="radio"]'))
    .filter((candidate) => candidate.name === control.name)
    .map(inputOption);
}

function setNativeTextValue(control: HTMLInputElement | HTMLTextAreaElement, value: string): void {
  const view = control.ownerDocument.defaultView;
  const prototype = isInput(control) ? view?.HTMLInputElement.prototype : view?.HTMLTextAreaElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
  if (!setter) throw new Error("The control does not expose a native value setter.");
  setter.call(control, value);
}

function setNativeSelectValue(control: HTMLSelectElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(control.ownerDocument.defaultView?.HTMLSelectElement.prototype ?? HTMLSelectElement.prototype, "value")?.set;
  if (!setter) throw new Error("The select does not expose a native value setter.");
  setter.call(control, value);
}

function setNativeChecked(control: HTMLInputElement, value: boolean): void {
  const setter = Object.getOwnPropertyDescriptor(control.ownerDocument.defaultView?.HTMLInputElement.prototype ?? HTMLInputElement.prototype, "checked")?.set;
  if (!setter) throw new Error("The control does not expose a native checked setter.");
  setter.call(control, value);
}

function booleanValue(value: string): boolean | null {
  const normalized = normalizeLabel(value);
  if (["true", "yes", "1", "checked"].includes(normalized)) return true;
  if (["false", "no", "0", "unchecked"].includes(normalized)) return false;
  return null;
}

function answerValueForField(field: DetectedField, answer: ApplicationPackageAnswer): string | null {
  if (!answer.label || normalizeLabel(answer.label) !== field.normalizedLabel) return null;
  const proposed = answer.proposedValue;
  if (field.type === "select") {
    const option = field.options?.find((item) =>
      item.value === proposed || normalizeLabel(item.label) === normalizeLabel(proposed));
    return option?.value ?? null;
  }
  if (field.type === "radio") {
    const ownValue = field.locator.stableAttributes.value || "on";
    const ownOption = field.options?.find((item) => item.value === ownValue);
    return ownValue === proposed || normalizeLabel(ownOption?.label || "") === normalizeLabel(proposed)
      ? ownValue
      : null;
  }
  if (field.type === "checkbox") return booleanValue(proposed) == null ? null : proposed;
  if (field.type === "date" && !/^\d{4}-\d{2}-\d{2}$/.test(proposed)) return null;
  return ["text", "email", "tel", "textarea", "date"].includes(field.type) ? proposed : null;
}

function isEmailCompatibleField(field: DetectedField): boolean {
  if (field.type === "email") return true;
  if (field.type !== "text") return false;
  return (
    /(^|\b)e-?mail(\b|$)/.test(field.normalizedLabel) ||
    field.locator.stableAttributes.autocomplete === "email"
  );
}

type StandardCandidateIntent =
  | "candidate.first_name"
  | "candidate.last_name"
  | "candidate.full_name"
  | "candidate.email"
  | "candidate.phone";

function standardCandidateMatch(
  field: DetectedField,
  candidate: ApplicationPackageCandidate,
): { intent: StandardCandidateIntent; value: string } | null {
  const autocomplete = field.locator.stableAttributes.autocomplete?.toLowerCase();
  const label = field.normalizedLabel;
  const textLike = field.type === "text";
  if (isEmailCompatibleField(field) && candidate.email) {
    return { intent: "candidate.email", value: candidate.email };
  }
  if ((field.type === "tel" || (textLike && /(^|\b)(phone|telephone|mobile)(\b|$)/.test(label)) || autocomplete === "tel") && candidate.phone) {
    return { intent: "candidate.phone", value: candidate.phone };
  }
  if ((textLike && /(^|\b)(first|given) name(\b|$)/.test(label) || autocomplete === "given-name") && candidate.firstName) {
    return { intent: "candidate.first_name", value: candidate.firstName };
  }
  if ((textLike && /(^|\b)(last|family|sur)\s*name(\b|$)/.test(label) || autocomplete === "family-name") && candidate.lastName) {
    return { intent: "candidate.last_name", value: candidate.lastName };
  }
  if ((textLike && /^(full )?name$/.test(label) || autocomplete === "name") && candidate.fullName) {
    return { intent: "candidate.full_name", value: candidate.fullName };
  }
  return null;
}

interface InspectableControl {
  control: Element;
  stepId: string;
  strategy: string;
}

interface ManualBoundary {
  label: string;
  stepId: string;
  reason: Extract<ManualReason, "cross_origin_frame" | "closed_shadow_root" | "unsupported_custom_control">;
  stableAttributes: Record<string, string>;
}

function inspectionTargets(document: Document): {
  controls: InspectableControl[];
  boundaries: ManualBoundary[];
} {
  const controls: InspectableControl[] = [];
  const boundaries: ManualBoundary[] = [];
  const visitedRoots = new Set<Node>();
  const visitedControls = new Set<Element>();

  const walk = (root: Document | ShadowRoot, stepId: string, strategy: string): void => {
    if (visitedRoots.has(root)) return;
    visitedRoots.add(root);

    for (const control of root.querySelectorAll("input, textarea, select, button")) {
      if (!visitedControls.has(control)) {
        visitedControls.add(control);
        controls.push({ control, stepId, strategy });
      }
    }

    for (const candidate of root.querySelectorAll<HTMLElement>("*")) {
      if (candidate.shadowRoot) {
        walk(candidate.shadowRoot, `${stepId}/open-shadow`, `${strategy}-open-shadow`);
      } else if (candidate.dataset.runrShadowRoot === "closed") {
        boundaries.push({
          label: candidate.getAttribute("aria-label") || "Closed shadow-root application section",
          stepId: `${stepId}/closed-shadow`,
          reason: "closed_shadow_root",
          stableAttributes: stableAttributes(candidate),
        });
      }
    }

    for (const frame of root.querySelectorAll<HTMLIFrameElement>("iframe")) {
      const label = frame.title || frame.getAttribute("aria-label") || frame.name || "Embedded application section";
      try {
        const childDocument = frame.contentDocument;
        if (childDocument?.documentElement) {
          walk(childDocument, `${stepId}/same-origin-frame`, `${strategy}-same-origin-frame`);
        } else {
          boundaries.push({
            label,
            stepId: `${stepId}/cross-origin-frame`,
            reason: "cross_origin_frame",
            stableAttributes: stableAttributes(frame),
          });
        }
      } catch {
        boundaries.push({
          label,
          stepId: `${stepId}/cross-origin-frame`,
          reason: "cross_origin_frame",
          stableAttributes: stableAttributes(frame),
        });
      }
    }

    for (const custom of root.querySelectorAll<HTMLElement>(
      '[role="textbox"], [role="combobox"], [role="checkbox"], [role="radio"]',
    )) {
      if (visitedControls.has(custom) || custom.shadowRoot) continue;
      boundaries.push({
        label: custom.getAttribute("aria-label") || custom.textContent?.trim() || "Custom application control",
        stepId,
        reason: "unsupported_custom_control",
        stableAttributes: stableAttributes(custom),
      });
    }
  };

  walk(document, "primary", "semantic-control");
  return { controls, boundaries };
}

function manualActionReason(reason: ManualReason): string {
  if (reason === "cross_origin_frame") {
    return "Complete this cross-origin frame manually; Runr does not request access to its origin.";
  }
  if (reason === "closed_shadow_root") {
    return "Complete controls inside this closed shadow root manually because the page does not expose them.";
  }
  if (reason === "unsupported_custom_control") {
    return "Review this custom control manually; semantic classification does not authorize generic filling.";
  }
  return `The control is manual-only: ${reason}.`;
}

class StandardFactsAdapter implements AtsAdapter {
  readonly version = "0.3.0";
  protected readonly controls = new Map<
    string,
    { element: Element; field: DetectedField }
  >();
  private readonly approvedMatches = new Map<string, ApprovedFieldMatch>();
  private readonly replacementAuthorizations = new Set<string>();

  constructor(readonly id: AtsType) {}

  async detect(context: PageContext): Promise<DetectionResult> {
    const urlDetection = detectAtsFromUrl(context.url);
    if (urlDetection.ats === this.id) return urlDetection;
    if (context.document.documentElement.dataset.runrAssistedApplyFixture === this.id) {
      return {
        detected: true,
        ats: this.id,
        confidence: 1,
        reasons: [`The document is an explicit local ${this.id} test fixture.`],
      };
    }
    return urlDetection;
  }

  async inspect(context: PageContext): Promise<InspectedApplicationForm> {
    this.controls.clear();
    this.approvedMatches.clear();
    const targets = inspectionTargets(context.document);
    const fields = targets.controls.map(({ control, stepId, strategy }, index): DetectedField => {
      const label = controlLabel(control, queryRoot(control));
      const normalizedLabel = normalizeLabel(label);
      const id = stableFieldId(this.id, control, normalizedLabel, index);
      const reason = manualReason(control, normalizedLabel);
      const type = fieldType(control);
      const classification = reason || type === "unknown" ? "manual" : "fillable";
      const field: DetectedField = {
        id,
        stepId,
        label,
        normalizedLabel,
        type,
        required: control.hasAttribute("required"),
        disabled:
          (isInput(control) || isTextarea(control) || isSelect(control) || isButton(control)) &&
          control.disabled,
        hidden: isHidden(control),
        options: controlOptions(control),
        existingValue: existingValue(control),
        classification,
        uploadFieldIntent: declaredUploadFieldIntent(this.id, control),
        manualReason: reason || (type === "unknown" ? "unsupported_control" : undefined),
        locator: {
          adapterStrategy: `${this.id}-${strategy}`,
          stableAttributes: stableAttributes(control),
        },
      };
      this.controls.set(id, { element: control, field });
      return field;
    });
    for (const [index, boundary] of targets.boundaries.entries()) {
      fields.push({
        id: `${this.id}-manual-boundary-${index + 1}`,
        stepId: boundary.stepId,
        label: boundary.label,
        normalizedLabel: normalizeLabel(boundary.label),
        type: "unknown",
        required: false,
        disabled: false,
        hidden: false,
        classification: "manual",
        manualReason: boundary.reason,
        locator: {
          adapterStrategy: `${this.id}-manual-boundary`,
          stableAttributes: boundary.stableAttributes,
        },
      });
    }
    return { ats: this.id, fields };
  }

  authorizeReplacement(detectedFieldId: string): void {
    this.replacementAuthorizations.add(detectedFieldId);
  }

  plan(match: ApprovedFieldMatch): NativeValueAction | null {
    const registered = this.controls.get(match.detectedFieldId);
    const approved = this.approvedMatches.get(match.detectedFieldId);
    if (!registered || !approved || approved.fieldIntent !== match.fieldIntent || approved.proposedValue !== match.proposedValue) return null;
    return planFillAction(registered.field, match.proposedValue);
  }

  async match(
    form: InspectedApplicationForm,
    applicationPackage: ApplicationPackage,
  ): Promise<FieldMatch[]> {
    this.approvedMatches.clear();
    return form.fields.map((field): FieldMatch => {
      const standardMatch = standardCandidateMatch(field, applicationPackage.candidate);
      if (
        standardMatch &&
        field.classification === "fillable" &&
        !field.disabled &&
        !field.hidden
      ) {
        const match: ApprovedFieldMatch = {
          detectedFieldId: field.id,
          fieldLabel: field.label,
          fieldIntent: standardMatch.intent,
          proposedValue: standardMatch.value,
          confidence: 1,
          source: "profile_verified",
          sensitivity: "personal",
          action: "fill",
          reasons: ["A verified standard candidate fact matched a semantic control."],
        };
        this.approvedMatches.set(field.id, match);
        return match;
      }
      const packageAnswer = applicationPackage.answers?.find(
        (answer) => answerValueForField(field, answer) !== null,
      );
      const packageValue = packageAnswer ? answerValueForField(field, packageAnswer) : null;
      if (
        packageAnswer && packageValue !== null &&
        field.classification === "fillable" && !field.disabled && !field.hidden
      ) {
        const match: ApprovedFieldMatch = {
          detectedFieldId: field.id,
          fieldLabel: field.label,
          fieldIntent: packageAnswer.fieldIntent,
          proposedValue: packageValue,
          confidence: 1,
          source: "profile_verified",
          sensitivity: "standard",
          action: "fill",
          reasons: ["A verified package answer matched a native control and its options."],
        };
        this.approvedMatches.set(field.id, match);
        return match;
      }
      return {
        detectedFieldId: field.id,
        fieldLabel: field.label,
        fieldIntent: "unknown",
        confidence: 0,
        source: "unknown",
        sensitivity: "standard",
        action: field.classification === "manual" ? "manual_only" : "leave_empty",
        reasons: [
          field.manualReason
            ? manualActionReason(field.manualReason)
            : "No verified fixture value matched this control.",
        ],
      };
    });
  }

  async fill(match: ApprovedFieldMatch): Promise<FieldExecutionResult> {
    const registered = this.controls.get(match.detectedFieldId);
    if (!registered) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "rejected",
        reasons: ["The inspected control is no longer registered."],
      };
    }

    const { element: control, field } = registered;
    const approved = this.approvedMatches.get(match.detectedFieldId);
    if (!approved || approved.fieldIntent !== match.fieldIntent || approved.proposedValue !== match.proposedValue) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "rejected",
        reasons: ["The field match was not approved by the current inspection and package match pass."],
      };
    }
    if (field.classification !== "fillable" || field.manualReason) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "rejected",
        reasons: [
          `The inspected control is manual-only: ${field.manualReason || "unsupported_control"}.`,
        ],
      };
    }
    if (!control.isConnected) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "rejected",
        reasons: ["The inspected control was replaced or removed before execution."],
      };
    }

    const liveType = fieldType(control);
    const liveNormalizedLabel = normalizeLabel(controlLabel(control, queryRoot(control)));
    const liveManualReason = manualReason(control, liveNormalizedLabel);
    if (
      liveType !== field.type ||
      liveNormalizedLabel !== field.normalizedLabel ||
      liveManualReason
    ) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "rejected",
        reasons: [
          liveManualReason
            ? `The live control became manual-only: ${liveManualReason}.`
            : "Only an unchanged, semantically verified standard-fact control can execute.",
        ],
      };
    }
    if (!(isInput(control) || isTextarea(control) || isSelect(control))) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "rejected",
        reasons: ["The matched control is not a supported native input."],
      };
    }
    if (isHidden(control)) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "skipped_hidden",
        reasons: ["Hidden controls are never filled."],
      };
    }
    if (control.disabled) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "skipped_disabled",
        reasons: ["Disabled controls are never filled."],
      };
    }
    const currentValue = isInput(control) && ["checkbox", "radio"].includes(control.type)
      ? String(control.checked)
      : control.value;
    const desiredValue = isInput(control) && control.type === "checkbox"
      ? String(booleanValue(match.proposedValue))
      : isInput(control) && control.type === "radio"
        ? "true"
        : match.proposedValue;
    const replacementAuthorized = this.replacementAuthorizations.delete(match.detectedFieldId);
    const ledger = fillLedger(control.ownerDocument);
    const priorFill = ledger.get(match.detectedFieldId);
    if (priorFill && !replacementAuthorized) {
      const alreadyFilled = currentValue === desiredValue;
      if (alreadyFilled || priorFill.userModified || priorFill.element === control) {
        return {
          detectedFieldId: match.detectedFieldId,
          fieldLabel: match.fieldLabel,
          status: alreadyFilled ? "already_filled" : "preserved_existing",
          existingValue: field.existingValue == null ? "" : String(field.existingValue),
          acceptedValue: currentValue,
          reasons: [alreadyFilled
            ? "The verified Runr value is already present; no events were repeated."
            : "The field changed after Runr filled it, so the current user or portal value was preserved."],
        };
      }
    }
    if (control.dataset.runrAssistedApplyFilled === "true" && !replacementAuthorized) {
      const alreadyFilled = currentValue === desiredValue;
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: alreadyFilled ? "already_filled" : "preserved_existing",
        existingValue: field.existingValue == null ? "" : String(field.existingValue),
        acceptedValue: currentValue,
        reasons: [
          alreadyFilled
            ? "The verified Runr value is already present; no events were repeated."
            : "The field changed after Runr filled it, so the current user or portal value was preserved.",
        ],
      };
    }
    const radioSelection = isInput(control) && control.type === "radio" && control.name
      ? Array.from(queryRoot(control).querySelectorAll<HTMLInputElement>('input[type="radio"]')).find(
          (item) => item.name === control.name && item.checked,
        )
      : null;
    const hasExistingValue = isInput(control) && control.type === "checkbox"
      ? control.checked && desiredValue !== "true"
      : isInput(control) && control.type === "radio"
        ? Boolean(radioSelection && radioSelection !== control)
        : Boolean(control.value);
    if (hasExistingValue && !replacementAuthorized) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "preserved_existing",
        existingValue: String(field.existingValue ?? currentValue),
        acceptedValue: radioSelection?.value ?? currentValue,
        reasons: ["An existing page, browser, ATS, or user value was preserved."],
      };
    }

    if (currentValue === desiredValue) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "already_filled",
        existingValue: String(field.existingValue ?? currentValue),
        acceptedValue: currentValue,
        reasons: ["The verified answer is already present; no events were emitted."],
      };
    }

    const plannedAction = this.plan(match);
    if (!plannedAction) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "rejected",
        reasons: ["The adapter could not express this control as a declarative action."],
      };
    }
    const actionResult = executeNativeValueAction(
      control.ownerDocument,
      plannedAction,
      () => control,
    );
    if (actionResult.status !== "applied") {
      const validation = inspectControlValidation(control.ownerDocument, match.detectedFieldId, () => control);
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "rejected",
        acceptedValue: readControlValue(control.ownerDocument, match.detectedFieldId, () => control) == null
          ? undefined : String(readControlValue(control.ownerDocument, match.detectedFieldId, () => control)),
        validationMessage: validation.messages[0],
        reasons: [actionResult.reason, ...validation.messages],
      };
    }
    control.blur();

    await new Promise((resolve) => setTimeout(resolve, 0));
    let acceptedValue = isInput(control) && ["checkbox", "radio"].includes(control.type)
      ? String(control.checked) : control.value;
    if (acceptedValue !== desiredValue) {
      const bridgeValue = isInput(control) && ["checkbox", "radio"].includes(control.type)
        ? desiredValue === "true" : match.proposedValue;
      const bridgeResult = await requestPageContextSet(control, bridgeValue);
      if (bridgeResult?.status === "applied") await new Promise((resolve) => setTimeout(resolve, 0));
      acceptedValue = isInput(control) && ["checkbox", "radio"].includes(control.type)
        ? String(control.checked) : control.value;
    }

    if (acceptedValue !== desiredValue) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "mismatch",
        existingValue: field.existingValue == null ? "" : String(field.existingValue),
        acceptedValue,
        reasons: ["The live value did not match the proposed value after readback."],
      };
    }
    if (!control.checkValidity()) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "rejected",
        existingValue: field.existingValue == null ? "" : String(field.existingValue),
        acceptedValue,
        validationMessage: control.validationMessage,
        reasons: ["The live control rejected the value during local validation."],
      };
    }
    control.dataset.runrAssistedApplyFilled = "true";
    ledger.set(match.detectedFieldId, { element: control, acceptedValue, userModified: false });
    if (!ledgerObservedControls.has(control)) {
      const observeUserChange = () => {
        const entry = fillLedger(control.ownerDocument).get(match.detectedFieldId);
        if (!entry || entry.element !== control) return;
        const liveValue = isInput(control) && ["checkbox", "radio"].includes(control.type)
          ? String(control.checked) : control.value;
        if (liveValue !== entry.acceptedValue) entry.userModified = true;
      };
      control.addEventListener("input", observeUserChange);
      control.addEventListener("change", observeUserChange);
      ledgerObservedControls.add(control);
    }
    return {
      detectedFieldId: match.detectedFieldId,
      fieldLabel: match.fieldLabel,
      fieldIntent: match.fieldIntent,
      status: "filled",
      existingValue: field.existingValue == null ? "" : String(field.existingValue),
      acceptedValue,
      reasons: ["The live control accepted the verified value on readback."],
    };
  }

  canReceiveDocument(fieldId: string): boolean {
    const control = this.controls.get(fieldId)?.element;
    return isInput(control) && control.type === "file" &&
      (!control.files?.length ||
        (control.multiple && control.dataset.runrAssistedApplyUploaded === "true"));
  }

  async upload(request: DocumentUploadRequest): Promise<DocumentUploadResult> {
    const registered = this.controls.get(request.detectedFieldId);
    const roleLabel = request.documentKind.replaceAll("_", " ");
    if (!registered || !(registered.element instanceof HTMLInputElement) || registered.element.type !== "file") {
      return { status: "rejected", reasons: [`The inspected ${roleLabel} upload control is unavailable.`] };
    }
    const input = registered.element;
    if (input.disabled || isHidden(input)) {
      return { status: "rejected", reasons: [`The ${roleLabel} upload control is disabled or hidden.`] };
    }
    const existingFiles = Array.from(input.files || []);
    const runrOwnedMultiple = input.multiple && input.dataset.runrAssistedApplyUploaded === "true";
    if (existingFiles.length && !runrOwnedMultiple) {
      return {
        status: "preserved_existing",
        fileName: existingFiles[0]?.name,
        reasons: ["An existing portal or user-selected document was preserved."],
      };
    }
    const suffix = request.file.type === "application/pdf" ? ".pdf"
      : request.file.type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ? ".docx" : "";
    if (!suffix || !request.file.name.toLowerCase().endsWith(suffix)) {
      return { status: "rejected", reasons: ["The selected document MIME type and filename are unsupported."] };
    }
    const accepted = input.accept.toLowerCase().split(",").map((item) => item.trim()).filter(Boolean);
    if (accepted.length && !accepted.includes(request.file.type) && !accepted.includes(suffix)) {
      return { status: "rejected", reasons: [`The portal control does not accept ${suffix.slice(1).toUpperCase()} documents.`] };
    }
    const transfer = new DataTransfer();
    for (const file of existingFiles) transfer.items.add(file);
    transfer.items.add(request.file);
    input.focus();
    input.files = transfer.files;
    input.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    input.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    input.blur();
    await new Promise((resolve) => setTimeout(resolve, 50));
    const acceptedFile = Array.from(input.files || []).find((file) => file.name === request.file.name);
    if (!acceptedFile || acceptedFile.type !== request.file.type) {
      return { status: "mismatch", fileName: acceptedFile?.name, reasons: ["The portal did not retain the selected document."] };
    }
    if (!input.checkValidity()) {
      return { status: "rejected", fileName: acceptedFile.name, reasons: ["The portal rejected the selected document during local validation."] };
    }
    input.dataset.runrAssistedApplyUploaded = "true";
    return {
      status: "uploaded",
      fileName: acceptedFile.name,
      reasons: [`The portal retained ${roleLabel} version ${request.documentVersion}.`],
    };
  }

  async validate(form: InspectedApplicationForm): Promise<FormValidationResult> {
    const invalidFieldIds = form.fields
      .filter((field) => {
        const control = this.controls.get(field.id)?.element;
        if (!control) return false;
        return (
          isInput(control) || isTextarea(control) || isSelect(control)
        )
          ? !control.checkValidity()
          : false;
      })
      .map((field) => field.id);
    return { valid: invalidFieldIds.length === 0, invalidFieldIds };
  }

  async detectPossibleSubmissionSuccess(
    _context: PageContext,
  ): Promise<SubmissionEvidence | null> {
    return null;
  }
}

export class GreenhouseAdapter extends StandardFactsAdapter {
  constructor() { super("greenhouse"); }
}

export class LeverAdapter extends StandardFactsAdapter {
  constructor() { super("lever"); }
}

function documentRolePattern(kind: DocumentUploadRequest["documentKind"]): RegExp {
  if (kind === "cv") return /(^|\b)(cv|resume|résumé)(\b|$)/iu;
  if (kind === "cover_letter") return /(^|\b)cover\s+letter(\b|$)/iu;
  return /(^|\b)(supporting|additional|attachment|certificate|portfolio|work\s+sample)(\b|$)/iu;
}

export async function uploadApplicationDocument(
  document: Document,
  url: string,
  request: Omit<DocumentUploadRequest, "detectedFieldId">,
): Promise<DocumentUploadResult> {
  const fixtureAts = document.documentElement.dataset.runrAssistedApplyFixture;
  const detectedAts = detectAtsFromUrl(url).ats;
  const ats = detectedAts || (fixtureAts === "greenhouse" || fixtureAts === "lever" ? fixtureAts : null);
  const adapter = ats === "greenhouse" ? new GreenhouseAdapter() : ats === "lever" ? new LeverAdapter() : null;
  if (!adapter) return { status: "rejected", reasons: ["The current page is not a supported application portal."] };
  const detection = await adapter.detect({ document, url });
  if (detection.ats !== adapter.id) {
    return { status: "rejected", reasons: ["The current page does not match its supported application adapter."] };
  }
  const form = await adapter.inspect({ document, url });
  const declaredFields = form.fields.filter((field) =>
    field.type === "file" && field.uploadFieldIntent === request.uploadFieldIntent);
  if (declaredFields.length !== 1) {
    return { status: "rejected", reasons: [declaredFields.length > 1
      ? "The declared upload intent matched multiple controls."
      : "The declared upload intent did not match exactly one upload control."] };
  }
  const roleField = declaredFields[0]!;
  if (!adapter.canReceiveDocument(roleField.id)) {
    return { status: "rejected", reasons: ["The declared upload control is unavailable or already occupied."] };
  }
  return adapter.upload({ ...request, detectedFieldId: roleField.id });
}

export async function uploadGreenhousePdf(
  document: Document,
  url: string,
  request: Omit<DocumentUploadRequest, "detectedFieldId" | "documentKind">,
): Promise<DocumentUploadResult> {
  return uploadApplicationDocument(document, url, {
    ...request,
    documentKind: "cv",
    uploadFieldIntent: "greenhouse.resume",
  });
}

export interface FixtureInspectionResult {
  ats: AtsType | null;
  fixtureAvailable: boolean;
  fieldCount: number;
  manualReasons: ManualReason[];
}

export interface FixtureProofResult extends FixtureInspectionResult {
  execution: FieldExecutionResult | null;
}

export async function inspectGreenhouseFixture(
  document: Document,
  url: string,
): Promise<FixtureInspectionResult> {
  const adapter = new GreenhouseAdapter();
  const detection = await adapter.detect({ document, url });
  if (detection.ats !== "greenhouse") {
    return { ats: detection.ats, fixtureAvailable: false, fieldCount: 0, manualReasons: [] };
  }
  const form = await adapter.inspect({ document, url });
  return {
    ats: "greenhouse",
    fixtureAvailable:
      document.documentElement.dataset.runrAssistedApplyFixture === "greenhouse",
    fieldCount: form.fields.length,
    manualReasons: Array.from(
      new Set(
        form.fields
          .map((field) => field.manualReason)
          .filter((reason): reason is ManualReason => Boolean(reason)),
      ),
    ),
  };
}

export async function runGreenhouseFixtureProof(
  document: Document,
  url: string,
  proposedEmail: string,
): Promise<FixtureProofResult> {
  const adapter = new GreenhouseAdapter();
  const detection = await adapter.detect({ document, url });
  const fixtureAvailable =
    document.documentElement.dataset.runrAssistedApplyFixture === "greenhouse";
  if (detection.ats !== "greenhouse" || !fixtureAvailable) {
    return {
      ats: detection.ats,
      fixtureAvailable: false,
      fieldCount: 0,
      manualReasons: [],
      execution: null,
    };
  }

  const form = await adapter.inspect({ document, url });
  const matches = await adapter.match(form, {
    id: "aa-01-local-fixture",
    version: 1,
    candidate: { email: proposedEmail },
  });
  const approved = matches.find(
    (match): match is ApprovedFieldMatch => match.action === "fill",
  );
  const execution = approved ? await adapter.fill(approved) : null;
  return {
    ats: "greenhouse",
    fixtureAvailable: true,
    fieldCount: form.fields.length,
    manualReasons: Array.from(
      new Set(
        form.fields
          .map((field) => field.manualReason)
          .filter((reason): reason is ManualReason => Boolean(reason)),
      ),
    ),
    execution,
  };
}

export async function runGreenhouseStandardFacts(
  document: Document,
  url: string,
  packageId: string,
  version: number,
  candidate: ApplicationPackageCandidate,
  answers: ApplicationPackageAnswer[] = [],
  replaceFieldIntents: string[] = [],
): Promise<{ inspection: FixtureInspectionResult; executions: FieldExecutionResult[] }> {
  const adapter = new GreenhouseAdapter();
  const detection = await adapter.detect({ document, url });
  if (detection.ats !== "greenhouse") {
    return {
      inspection: { ats: detection.ats, fixtureAvailable: false, fieldCount: 0, manualReasons: [] },
      executions: [],
    };
  }
  let form = await adapter.inspect({ document, url });
  const executions = new Map<string, FieldExecutionResult>();
  for (let pass = 0; pass < 3; pass += 1) {
    const signature = form.fields.map((field) => field.id).join("|");
    const matches = await adapter.match(form, { id: packageId, version, candidate, answers });
    for (const match of matches) {
      if (match.action !== "fill") continue;
      if (replaceFieldIntents.includes(match.fieldIntent)) adapter.authorizeReplacement(match.detectedFieldId);
      const result = await adapter.fill(match as ApprovedFieldMatch);
      if (!executions.has(match.detectedFieldId)) {
        executions.set(match.detectedFieldId, { ...result, fieldIntent: match.fieldIntent });
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 0));
    const nextForm = await adapter.inspect({ document, url });
    form = nextForm;
    if (nextForm.fields.map((field) => field.id).join("|") === signature) break;
  }
  return {
    inspection: {
      ats: "greenhouse",
      fixtureAvailable: document.documentElement.dataset.runrAssistedApplyFixture === "greenhouse",
      fieldCount: form.fields.length,
      manualReasons: Array.from(new Set(form.fields.flatMap((field) => field.manualReason ? [field.manualReason] : []))),
    },
    executions: [...executions.values()],
  };
}

export async function inspectLeverFixture(
  document: Document,
  url: string,
): Promise<FixtureInspectionResult> {
  const adapter = new LeverAdapter();
  const detection = await adapter.detect({ document, url });
  if (detection.ats !== "lever") {
    return { ats: detection.ats, fixtureAvailable: false, fieldCount: 0, manualReasons: [] };
  }
  const form = await adapter.inspect({ document, url });
  return {
    ats: "lever",
    fixtureAvailable: document.documentElement.dataset.runrAssistedApplyFixture === "lever",
    fieldCount: form.fields.length,
    manualReasons: Array.from(new Set(form.fields.map((field) => field.manualReason).filter((reason): reason is ManualReason => Boolean(reason)))),
  };
}

export async function runLeverFixtureProof(
  document: Document,
  url: string,
  candidate: ApplicationPackageCandidate,
): Promise<{ inspection: FixtureInspectionResult; executions: FieldExecutionResult[] }> {
  const adapter = new LeverAdapter();
  const inspection = await inspectLeverFixture(document, url);
  if (!inspection.fixtureAvailable) return { inspection, executions: [] };
  const form = await adapter.inspect({ document, url });
  const matches = await adapter.match(form, { id: "aa-05-local-fixture", version: 1, candidate });
  const executions: FieldExecutionResult[] = [];
  for (const match of matches) {
    if (match.action === "fill" && typeof match.proposedValue === "string") {
      executions.push(await adapter.fill(match as ApprovedFieldMatch));
    }
  }
  return { inspection, executions };
}

export async function runLeverStandardFacts(
  document: Document,
  url: string,
  packageId: string,
  version: number,
  candidate: ApplicationPackageCandidate,
  answers: ApplicationPackageAnswer[] = [],
  replaceFieldIntents: string[] = [],
): Promise<{ inspection: FixtureInspectionResult; executions: FieldExecutionResult[] }> {
  const adapter = new LeverAdapter();
  const detection = await adapter.detect({ document, url });
  if (detection.ats !== "lever") {
    return { inspection: { ats: detection.ats, fixtureAvailable: false, fieldCount: 0, manualReasons: [] }, executions: [] };
  }
  let form = await adapter.inspect({ document, url });
  const executions = new Map<string, FieldExecutionResult>();
  for (let pass = 0; pass < 3; pass += 1) {
    const signature = form.fields.map((field) => field.id).join("|");
    const matches = await adapter.match(form, { id: packageId, version, candidate, answers });
    for (const match of matches) {
      if (match.action !== "fill" || typeof match.proposedValue !== "string") continue;
      if (replaceFieldIntents.includes(match.fieldIntent)) adapter.authorizeReplacement(match.detectedFieldId);
      const result = await adapter.fill(match as ApprovedFieldMatch);
      if (!executions.has(match.detectedFieldId)) {
        executions.set(match.detectedFieldId, { ...result, fieldIntent: match.fieldIntent });
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 0));
    const nextForm = await adapter.inspect({ document, url });
    form = nextForm;
    if (nextForm.fields.map((field) => field.id).join("|") === signature) break;
  }
  return {
    inspection: {
      ats: "lever",
      fixtureAvailable: document.documentElement.dataset.runrAssistedApplyFixture === "lever",
      fieldCount: form.fields.length,
      manualReasons: Array.from(new Set(form.fields.flatMap((field) => field.manualReason ? [field.manualReason] : []))),
    },
    executions: [...executions.values()],
  };
}
