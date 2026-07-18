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
  email?: string;
}

export interface ApplicationPackage {
  id: string;
  version: number;
  candidate: ApplicationPackageCandidate;
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
  acceptedValue?: string;
  validationMessage?: string;
  reasons: string[];
}

export interface DocumentUploadRequest {
  detectedFieldId: string;
  fileName: string;
}

export interface DocumentUploadResult {
  status: "unsupported";
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
  const allowed = ["id", "name", "type", "autocomplete", "aria-label"];
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

function setNativeTextValue(control: HTMLInputElement | HTMLTextAreaElement, value: string): void {
  const prototype =
    control instanceof HTMLInputElement ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
  if (!setter) throw new Error("The control does not expose a native value setter.");
  setter.call(control, value);
}

function isEmailCompatibleField(field: DetectedField): boolean {
  if (field.type === "email") return true;
  if (field.type !== "text") return false;
  return (
    /(^|\b)e-?mail(\b|$)/.test(field.normalizedLabel) ||
    field.locator.stableAttributes.autocomplete === "email"
  );
}

export class GreenhouseAdapter implements AtsAdapter {
  readonly id = "greenhouse" as const;
  readonly version = "0.1.0";
  private readonly controls = new Map<
    string,
    { element: Element; field: DetectedField }
  >();

  async detect(context: PageContext): Promise<DetectionResult> {
    const urlDetection = detectAtsFromUrl(context.url);
    if (urlDetection.ats === "greenhouse") return urlDetection;
    if (context.document.documentElement.dataset.runrAssistedApplyFixture === "greenhouse") {
      return {
        detected: true,
        ats: "greenhouse",
        confidence: 1,
        reasons: ["The document is an explicit local Greenhouse test fixture."],
      };
    }
    return urlDetection;
  }

  async inspect(context: PageContext): Promise<InspectedApplicationForm> {
    this.controls.clear();
    const controls = Array.from(
      context.document.querySelectorAll("input, textarea, select, button"),
    );
    const fields = controls.map((control, index): DetectedField => {
      const id = `greenhouse-field-${index + 1}`;
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
        options:
          control instanceof HTMLSelectElement
            ? Array.from(control.options).map((option) => ({
                label: option.textContent?.trim() || option.label,
                value: option.value,
              }))
            : undefined,
        existingValue: existingValue(control),
        classification,
        manualReason: reason || (type === "unknown" ? "unsupported_control" : undefined),
        locator: {
          adapterStrategy: "greenhouse-semantic-control",
          stableAttributes: stableAttributes(control),
        },
      };
      this.controls.set(id, { element: control, field });
      return field;
    });
    return { ats: "greenhouse", fields };
  }

  async match(
    form: InspectedApplicationForm,
    applicationPackage: ApplicationPackage,
  ): Promise<FieldMatch[]> {
    return form.fields.map((field): FieldMatch => {
      if (
        isEmailCompatibleField(field) &&
        field.classification === "fillable" &&
        !field.disabled &&
        !field.hidden &&
        applicationPackage.candidate.email
      ) {
        return {
          detectedFieldId: field.id,
          fieldLabel: field.label,
          fieldIntent: "candidate.email",
          proposedValue: applicationPackage.candidate.email,
          confidence: 1,
          source: "profile_verified",
          sensitivity: "personal",
          action: "fill",
          reasons: ["Verified candidate email matched a semantic email control."],
        };
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
    const liveEmailCompatible =
      liveType === "email" ||
      (liveType === "text" &&
        (/(^|\b)e-?mail(\b|$)/.test(liveNormalizedLabel) ||
          control.getAttribute("autocomplete") === "email"));
    if (
      match.fieldIntent !== "candidate.email" ||
      !isEmailCompatibleField(field) ||
      liveType !== field.type ||
      !liveEmailCompatible ||
      liveManualReason
    ) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "rejected",
        reasons: [
          liveManualReason
            ? `The live control became manual-only: ${liveManualReason}.`
            : "AA-01 executes only the unchanged, semantically verified text/email control.",
        ],
      };
    }
    if (!(control instanceof HTMLInputElement || control instanceof HTMLTextAreaElement)) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "rejected",
        reasons: ["The matched control is not a supported text input."],
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
    if (control.dataset.runrAssistedApplyFilled === "true") {
      const alreadyFilled = control.value === match.proposedValue;
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: alreadyFilled ? "already_filled" : "preserved_existing",
        acceptedValue: control.value,
        reasons: [
          alreadyFilled
            ? "The verified Runr value is already present; no events were repeated."
            : "The field changed after Runr filled it, so the current user or portal value was preserved.",
        ],
      };
    }
    if (control.value) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "preserved_existing",
        acceptedValue: control.value,
        reasons: ["An existing page, browser, ATS, or user value was preserved."],
      };
    }

    control.focus();
    setNativeTextValue(control, match.proposedValue);
    control.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    control.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    control.blur();

    const acceptedValue = control.value;
    if (acceptedValue !== match.proposedValue) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "mismatch",
        acceptedValue,
        reasons: ["The live value did not match the proposed value after readback."],
      };
    }
    if (!control.checkValidity()) {
      return {
        detectedFieldId: match.detectedFieldId,
        fieldLabel: match.fieldLabel,
        status: "rejected",
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
