import { describe, expect, it } from "vitest";
import { parseDocumentGrant } from "../../src/documents/grant-validation";

const expected = {
  documentId: "asset::cv-1",
  documentVersion: 1,
  documentKind: "cv" as const,
  mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" as const,
  fileName: "Candidate CV.docx",
};

const valid = {
  grantToken: "aagrant_abcdefghijklmnopqrstuvwxyz123456",
  uploadFieldIntent: "lever.resume",
  file: {
    documentId: "asset::cv-1",
    documentVersion: 1,
    documentKind: "cv",
    fileName: "Candidate CV.docx",
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    size: 1024,
    sha256Hex: "a".repeat(64),
  },
};

describe("document grant validation", () => {
  it("accepts the backend top-level upload intent contract", () => {
    expect(parseDocumentGrant(valid, expected, "lever.resume")).toMatchObject({
      documentId: "asset::cv-1",
      uploadFieldIntent: "lever.resume",
      fileName: "Candidate CV.docx",
    });
  });

  it("fails closed on a wrong or missing upload intent", () => {
    expect(() => parseDocumentGrant({ ...valid, uploadFieldIntent: "lever.cover_letter" }, expected, "lever.resume"))
      .toThrow("invalid document grant metadata");
    const { uploadFieldIntent: _removed, ...missing } = valid;
    expect(() => parseDocumentGrant(missing, expected, "lever.resume"))
      .toThrow("invalid document grant metadata");
  });
});
