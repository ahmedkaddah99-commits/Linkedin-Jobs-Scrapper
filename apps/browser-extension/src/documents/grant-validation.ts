import type { ApplicationPackageDocumentMeta } from "@runr/extension-messages";

export interface VerifiedDocumentGrant {
  grantToken: string;
  documentId: string;
  documentVersion: number;
  documentKind: ApplicationPackageDocumentMeta["documentKind"];
  uploadFieldIntent: string;
  fileName: string;
  mimeType: ApplicationPackageDocumentMeta["mimeType"];
  size: number;
  sha256Hex: string;
}

export function parseDocumentGrant(
  value: unknown,
  expected: ApplicationPackageDocumentMeta,
  expectedUploadFieldIntent: string,
): VerifiedDocumentGrant {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Runr returned an invalid document grant.");
  }
  const record = value as Record<string, unknown>;
  const file = record.file;
  if (!file || typeof file !== "object" || Array.isArray(file)) {
    throw new Error("Runr returned invalid document metadata.");
  }
  const metadata = file as Record<string, unknown>;
  const uploadFieldIntent = typeof record.uploadFieldIntent === "string"
    ? record.uploadFieldIntent
    : metadata.uploadFieldIntent;
  if (typeof record.grantToken !== "string" || record.grantToken.length < 20 ||
      metadata.documentId !== expected.documentId ||
      !Number.isInteger(metadata.documentVersion) || Number(metadata.documentVersion) < 1 ||
      metadata.documentVersion !== expected.documentVersion ||
      metadata.documentKind !== expected.documentKind ||
      uploadFieldIntent !== expectedUploadFieldIntent ||
      metadata.fileName !== expected.fileName ||
      metadata.mimeType !== expected.mimeType ||
      !((metadata.mimeType === "application/pdf" && expected.fileName.toLowerCase().endsWith(".pdf")) ||
        (metadata.mimeType === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" &&
          expected.fileName.toLowerCase().endsWith(".docx"))) ||
      !Number.isInteger(metadata.size) || Number(metadata.size) < 1 || Number(metadata.size) > 10 * 1024 * 1024 ||
      typeof metadata.sha256Hex !== "string" || !/^[0-9a-f]{64}$/u.test(metadata.sha256Hex)) {
    throw new Error("Runr returned invalid document grant metadata.");
  }
  return {
    grantToken: record.grantToken,
    documentId: metadata.documentId as string,
    documentVersion: metadata.documentVersion as number,
    documentKind: expected.documentKind,
    uploadFieldIntent: uploadFieldIntent as string,
    fileName: metadata.fileName as string,
    mimeType: expected.mimeType,
    size: metadata.size as number,
    sha256Hex: metadata.sha256Hex,
  };
}
