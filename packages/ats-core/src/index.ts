export type AtsType = "greenhouse" | "lever";

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
  fill(match: ApprovedFieldMatch): Promise<FieldExecutionResult>;
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
  "fill",
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
  if (hostname.endsWith(".greenhouse.io")) {
    return {
      detected: true,
      ats: "greenhouse",
      confidence: 1,
      reasons: ["The page host is a Greenhouse-owned domain."],
    };
  }

  if (hostname === "jobs.lever.co" || hostname === "jobs.eu.lever.co") {
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

function controlLabel(control: Element, document: Document): string {
  if (control instanceof HTMLInputElement && control.type === "radio") {
    const legend = control.closest("fieldset")?.querySelector(":scope > legend")?.textContent?.trim();
    if (legend) return legend;
  }
  const id = control.getAttribute("id");
  const explicit = id
    ? Array.from(document.querySelectorAll("label")).find((label) => label.htmlFor === id) ?? null
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
  if (control instanceof HTMLTextAreaElement) return "textarea";
  if (control instanceof HTMLSelectElement) return "select";
  if (!(control instanceof HTMLInputElement)) return "unknown";
  const type = control.type.toLowerCase();
  if (["text", "email", "tel", "radio", "checkbox", "date", "file"].includes(type)) {
    return type as DetectedFieldType;
  }
  return "unknown";
}

function manualReason(control: Element, normalized: string): ManualReason | undefined {
  if (
    (control instanceof HTMLButtonElement && control.type === "submit") ||
    (control instanceof HTMLInputElement && control.type === "submit")
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
  if (control instanceof HTMLInputElement && control.type === "hidden") return true;
  if (control.closest('[hidden], [aria-hidden="true"]')) return true;

  const view = control.ownerDocument.defaultView;
  for (let current: Element | null = control; current; current = current.parentElement) {
    const style = view?.getComputedStyle(current);
    if (
      style?.display === "none" ||
      style?.visibility === "hidden" ||
      style?.visibility === "collapse"
    ) {
      return true;
    }
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

function existingValue(control: Element): unknown {
  if (control instanceof HTMLInputElement) {
    if (control.type === "checkbox" || control.type === "radio") return control.checked;
    return control.value;
  }
  if (control instanceof HTMLTextAreaElement || control instanceof HTMLSelectElement) {
    return control.value;
  }
  return undefined;
}

function inputOption(control: HTMLInputElement): { label: string; value: string } {
  return {
    label: control.labels?.[0]?.textContent?.trim() || control.value,
    value: control.value,
  };
}

function controlOptions(control: Element): Array<{ label: string; value: string }> | undefined {
  if (control instanceof HTMLSelectElement) {
    return Array.from(control.options).map((option) => ({
      label: option.textContent?.trim() || option.label,
      value: option.value,
    }));
  }
  if (!(control instanceof HTMLInputElement) || !["radio", "checkbox"].includes(control.type)) {
    return undefined;
  }
  if (control.type === "checkbox" || !control.name) return [inputOption(control)];
  return Array.from(control.ownerDocument.querySelectorAll<HTMLInputElement>('input[type="radio"]'))
    .filter((candidate) => candidate.name === control.name)
    .map(inputOption);
}

function setNativeTextValue(control: HTMLInputElement | HTMLTextAreaElement, value: string): void {
  const prototype =
    control instanceof HTMLInputElement ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
  if (!setter) throw new Error("The control does not expose a native value setter.");
  setter.call(control, value);
}

function setNativeSelectValue(control: HTMLSelectElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")?.set;
  if (!setter) throw new Error("The select does not expose a native value setter.");
  setter.call(control, value);
}

function setNativeChecked(control: HTMLInputElement, value: boolean): void {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "checked")?.set;
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

class StandardFactsAdapter implements AtsAdapter {
  readonly version = "0.2.0";
  protected readonly controls = new Map<
    string,
    { element: Element; field: DetectedField }
  >();
  private readonly approvedMatches = new Map<string, ApprovedFieldMatch>();

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
    const controls = Array.from(
      context.document.querySelectorAll("input, textarea, select, button"),
    );
    const fields = controls.map((control, index): DetectedField => {
      const id = `${this.id}-field-${index + 1}`;
      const label = controlLabel(control, context.document);
      const normalizedLabel = normalizeLabel(label);
      const reason = manualReason(control, normalizedLabel);
      const type = fieldType(control);
      const classification = reason || type === "unknown" ? "manual" : "fillable";
      const field: DetectedField = {
        id,
        stepId: "primary",
        label,
        normalizedLabel,
        type,
        required: control.hasAttribute("required"),
        disabled:
          (control instanceof HTMLInputElement ||
            control instanceof HTMLTextAreaElement ||
            control instanceof HTMLSelectElement ||
            control instanceof HTMLButtonElement) &&
          control.disabled,
        hidden: isHidden(control),
        options: controlOptions(control),
        existingValue: existingValue(control),
        classification,
        manualReason: reason || (type === "unknown" ? "unsupported_control" : undefined),
        locator: {
          adapterStrategy: `${this.id}-semantic-control`,
          stableAttributes: stableAttributes(control),
        },
      };
      this.controls.set(id, { element: control, field });
      return field;
    });
    return { ats: this.id, fields };
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
            ? `The control is manual-only: ${field.manualReason}.`
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
    const liveNormalizedLabel = normalizeLabel(controlLabel(control, control.ownerDocument));
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
    if (!(control instanceof HTMLInputElement || control instanceof HTMLTextAreaElement || control instanceof HTMLSelectElement)) {
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
    const currentValue = control instanceof HTMLInputElement && ["checkbox", "radio"].includes(control.type)
      ? String(control.checked)
      : control.value;
    const desiredValue = control instanceof HTMLInputElement && control.type === "checkbox"
      ? String(booleanValue(match.proposedValue))
      : control instanceof HTMLInputElement && control.type === "radio"
        ? "true"
        : match.proposedValue;
    if (control.dataset.runrAssistedApplyFilled === "true") {
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
    const radioSelection = control instanceof HTMLInputElement && control.type === "radio" && control.name
      ? Array.from(control.ownerDocument.querySelectorAll<HTMLInputElement>('input[type="radio"]')).find(
          (item) => item.name === control.name && item.checked,
        )
      : null;
    const hasExistingValue = control instanceof HTMLInputElement && control.type === "checkbox"
      ? control.checked && desiredValue !== "true"
      : control instanceof HTMLInputElement && control.type === "radio"
        ? Boolean(radioSelection && radioSelection !== control)
        : Boolean(control.value);
    if (hasExistingValue) {
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

    control.focus();
    if (control instanceof HTMLSelectElement) setNativeSelectValue(control, match.proposedValue);
    else if (control instanceof HTMLInputElement && control.type === "checkbox") {
      setNativeChecked(control, booleanValue(match.proposedValue) === true);
    } else if (control instanceof HTMLInputElement && control.type === "radio") {
      setNativeChecked(control, true);
    } else setNativeTextValue(control, match.proposedValue);
    control.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    control.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    control.blur();

    const acceptedValue = control instanceof HTMLInputElement && ["checkbox", "radio"].includes(control.type)
      ? String(control.checked)
      : control.value;
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
    return {
      detectedFieldId: match.detectedFieldId,
      fieldLabel: match.fieldLabel,
      status: "filled",
      existingValue: field.existingValue == null ? "" : String(field.existingValue),
      acceptedValue,
      reasons: ["The live control accepted the verified value on readback."],
    };
  }

  async upload(_request: DocumentUploadRequest): Promise<DocumentUploadResult> {
    return { status: "unsupported", reasons: ["Document upload is not part of AA-01."] };
  }

  async validate(form: InspectedApplicationForm): Promise<FormValidationResult> {
    const invalidFieldIds = form.fields
      .filter((field) => {
        const control = this.controls.get(field.id)?.element;
        return (
          control instanceof HTMLInputElement ||
          control instanceof HTMLTextAreaElement ||
          control instanceof HTMLSelectElement
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

  override async upload(request: DocumentUploadRequest): Promise<DocumentUploadResult> {
    const registered = this.controls.get(request.detectedFieldId);
    if (!registered || !(registered.element instanceof HTMLInputElement) || registered.element.type !== "file") {
      return { status: "rejected", reasons: ["The inspected CV upload control is unavailable."] };
    }
    const input = registered.element;
    if (input.disabled || isHidden(input)) {
      return { status: "rejected", reasons: ["The CV upload control is disabled or hidden."] };
    }
    if (input.files?.length) {
      return {
        status: "preserved_existing",
        fileName: input.files[0]?.name,
        reasons: ["An existing portal or user-selected document was preserved."],
      };
    }
    if (request.file.type !== "application/pdf" || !request.file.name.toLowerCase().endsWith(".pdf")) {
      return { status: "rejected", reasons: ["AA-11 accepts a selected PDF CV only."] };
    }
    const accepted = input.accept.toLowerCase();
    if (accepted && !accepted.includes("application/pdf") && !accepted.includes(".pdf")) {
      return { status: "rejected", reasons: ["The portal control does not accept PDF documents."] };
    }
    const transfer = new DataTransfer();
    transfer.items.add(request.file);
    input.focus();
    input.files = transfer.files;
    input.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    input.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    input.blur();
    await new Promise((resolve) => setTimeout(resolve, 50));
    const acceptedFile = input.files?.[0];
    if (!acceptedFile || acceptedFile.name !== request.file.name || acceptedFile.type !== request.file.type) {
      return { status: "mismatch", fileName: acceptedFile?.name, reasons: ["The portal did not retain the selected PDF CV."] };
    }
    return {
      status: "uploaded",
      fileName: acceptedFile.name,
      reasons: [`The portal retained document version ${request.documentVersion} in its CV control.`],
    };
  }
}

export class LeverAdapter extends StandardFactsAdapter {
  constructor() { super("lever"); }
}

export async function uploadGreenhousePdf(
  document: Document,
  url: string,
  request: Omit<DocumentUploadRequest, "detectedFieldId">,
): Promise<DocumentUploadResult> {
  const adapter = new GreenhouseAdapter();
  const detection = await adapter.detect({ document, url });
  if (detection.ats !== "greenhouse") {
    return { status: "rejected", reasons: ["The current page is not a supported Greenhouse application."] };
  }
  const form = await adapter.inspect({ document, url });
  const cvField = form.fields.find((field) =>
    field.type === "file" && /(^|\b)(cv|resume|résumé)(\b|$)/iu.test(field.normalizedLabel),
  );
  if (!cvField) {
    return { status: "rejected", reasons: ["No verified Greenhouse CV upload control was found."] };
  }
  return adapter.upload({ ...request, detectedFieldId: cvField.id });
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
): Promise<{ inspection: FixtureInspectionResult; executions: FieldExecutionResult[] }> {
  const adapter = new GreenhouseAdapter();
  const detection = await adapter.detect({ document, url });
  if (detection.ats !== "greenhouse") {
    return {
      inspection: { ats: detection.ats, fixtureAvailable: false, fieldCount: 0, manualReasons: [] },
      executions: [],
    };
  }
  const form = await adapter.inspect({ document, url });
  const matches = await adapter.match(form, { id: packageId, version, candidate, answers });
  const executions: FieldExecutionResult[] = [];
  for (const match of matches) {
    if (match.action === "fill") executions.push(await adapter.fill(match as ApprovedFieldMatch));
  }
  return {
    inspection: {
      ats: "greenhouse",
      fixtureAvailable: document.documentElement.dataset.runrAssistedApplyFixture === "greenhouse",
      fieldCount: form.fields.length,
      manualReasons: Array.from(new Set(form.fields.flatMap((field) => field.manualReason ? [field.manualReason] : []))),
    },
    executions,
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
): Promise<{ inspection: FixtureInspectionResult; executions: FieldExecutionResult[] }> {
  const adapter = new LeverAdapter();
  const detection = await adapter.detect({ document, url });
  if (detection.ats !== "lever") {
    return { inspection: { ats: detection.ats, fixtureAvailable: false, fieldCount: 0, manualReasons: [] }, executions: [] };
  }
  const form = await adapter.inspect({ document, url });
  const matches = await adapter.match(form, { id: packageId, version, candidate, answers });
  const executions: FieldExecutionResult[] = [];
  for (const match of matches) {
    if (match.action === "fill" && typeof match.proposedValue === "string") executions.push(await adapter.fill(match as ApprovedFieldMatch));
  }
  return {
    inspection: {
      ats: "lever",
      fixtureAvailable: document.documentElement.dataset.runrAssistedApplyFixture === "lever",
      fieldCount: form.fields.length,
      manualReasons: Array.from(new Set(form.fields.flatMap((field) => field.manualReason ? [field.manualReason] : []))),
    },
    executions,
  };
}
