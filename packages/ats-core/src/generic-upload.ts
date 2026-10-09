import type { DetectedApplicationField } from "./field-intent";
import { controlResolver, type GenericInspection } from "./generic-inspector";

/**
 * Provider-neutral document attachment.
 *
 * The upload target is chosen by the field intent the inspector already
 * derived from the control's own label, not by a provider-specific control id.
 * That is what lets the same code attach a CV on Greenhouse, Lever, and an
 * Avature portal nobody wrote an adapter for.
 *
 * Two rules are absolute: a document is never attached to a control whose role
 * is ambiguous, and the attachment is verified by reading the control back.
 */

export type DocumentRole = "cv" | "cover_letter" | "supporting_document";

const ROLE_INTENTS: Record<DocumentRole, string> = {
  cv: "document.cv",
  cover_letter: "document.cover_letter",
  supporting_document: "document.supporting",
};

export interface DocumentAttachment {
  role: DocumentRole;
  fileName: string;
  mimeType: string;
  bytes: Uint8Array;
}

export type UploadStatus = "uploaded" | "rejected" | "ambiguous" | "unsupported" | "preserved_existing";

export interface UploadOutcome {
  role: DocumentRole;
  status: UploadStatus;
  fileName?: string;
  reasons: string[];
}

/**
 * Chooses the single control for a role.
 *
 * Returns null when there is no candidate, and reports ambiguity separately
 * when there is more than one ??? a form with three "Additional document" slots
 * must not receive the same file three times, nor a guess at which is meant.
 */
export function resolveUploadTarget(
  inspection: GenericInspection,
  role: DocumentRole,
): { field: DetectedApplicationField } | { ambiguous: true; count: number } | null {
  const intent = ROLE_INTENTS[role];
  const matches = inspection.fields.filter(
    (field) => field.intent === intent && field.controlType === "file",
  );
  if (matches.length === 0) return null;
  if (matches.length === 1) return { field: matches[0]! };
  return { ambiguous: true, count: matches.length };
}

function acceptsFile(control: HTMLInputElement, attachment: DocumentAttachment): boolean {
  const accept = (control.getAttribute("accept") || "").trim();
  if (!accept) return true;
  const extension = `.${attachment.fileName.split(".").pop()?.toLowerCase() ?? ""}`;
  return accept
    .split(",")
    .map((token) => token.trim().toLowerCase())
    .some((token) => {
      if (!token) return false;
      if (token === attachment.mimeType.toLowerCase()) return true;
      if (token.endsWith("/*")) return attachment.mimeType.toLowerCase().startsWith(token.slice(0, -1));
      return token === extension;
    });
}

/**
 * Attaches one document and verifies the control kept it.
 *
 * `preserveExisting` defaults to true: a file the candidate already attached is
 * never replaced silently.
 */
export function attachDocument(
  document: Document,
  inspection: GenericInspection,
  attachment: DocumentAttachment,
  options: { preserveExisting?: boolean; resolve?: (fieldId: string) => Element | null } = {},
): UploadOutcome {
  const preserveExisting = options.preserveExisting !== false;
  const resolve = options.resolve ?? controlResolver(document, inspection);

  const target = resolveUploadTarget(inspection, attachment.role);
  if (!target) {
    return { role: attachment.role, status: "unsupported", reasons: ["This application has no control for that document."] };
  }
  if ("ambiguous" in target) {
    return {
      role: attachment.role,
      status: "ambiguous",
      reasons: [`This application offers ${target.count} controls for that document, so Runr will not choose between them.`],
    };
  }

  const control = resolve(target.field.id);
  if (!(control instanceof HTMLInputElement) || control.type !== "file") {
    return { role: attachment.role, status: "rejected", reasons: ["The upload control was not available."] };
  }
  if (control.disabled) {
    return { role: attachment.role, status: "rejected", reasons: ["The upload control is disabled."] };
  }
  if (preserveExisting && control.files && control.files.length > 0) {
    return {
      role: attachment.role,
      status: "preserved_existing",
      fileName: control.files[0]?.name,
      reasons: ["A file you attached is already here."],
    };
  }
  if (!acceptsFile(control, attachment)) {
    return {
      role: attachment.role,
      status: "rejected",
      reasons: [`This control does not accept ${attachment.fileName.split(".").pop()?.toUpperCase() ?? "that"} files.`],
    };
  }

  const view = document.defaultView;
  if (!view || typeof view.DataTransfer !== "function") {
    return { role: attachment.role, status: "unsupported", reasons: ["This browser cannot attach files programmatically."] };
  }

  try {
    const file = new view.File([attachment.bytes as unknown as BlobPart], attachment.fileName, { type: attachment.mimeType });
    const transfer = new view.DataTransfer();
    transfer.items.add(file);
    control.files = transfer.files;
  } catch (error) {
    return {
      role: attachment.role,
      status: "rejected",
      reasons: [error instanceof Error ? error.message : "The file could not be attached."],
    };
  }

  control.dispatchEvent(new (view.Event ?? Event)("input", { bubbles: true }));
  control.dispatchEvent(new (view.Event ?? Event)("change", { bubbles: true }));

  // Verified by reading the control back, not by assuming the assignment stuck.
  const attached = control.files?.[0];
  if (!attached || attached.name !== attachment.fileName) {
    return { role: attachment.role, status: "rejected", reasons: ["The page did not keep the attached file."] };
  }
  return { role: attachment.role, status: "uploaded", fileName: attached.name, reasons: [] };
}
