import assert from "node:assert/strict";
import test from "node:test";
import { candidateDocuments, defaultSelectedDocumentIds } from "./assistedApplyDocuments.js";

const pdf = (overrides = {}) => ({
  document_id: "asset::cv-1",
  asset_kind: "workspace_cv",
  display_name: "CV.pdf",
  content_type: "application/pdf",
  metadata: { purposes: ["include_in_applications"] },
  ...overrides,
});

test("only application-approved supported assets are candidates", () => {
  const documents = candidateDocuments([
    pdf(),
    pdf({ document_id: "asset::private", metadata: { purposes: ["private_never_attach"] } }),
    pdf({ document_id: "asset::identity", asset_kind: "identity_work_authorization" }),
    pdf({ document_id: "artifact::generated", asset_kind: "generated_cv" }),
    pdf({ document_id: "asset::docx", display_name: "CV.docx", content_type: "" }),
  ]);
  assert.deepEqual(documents.map((item) => item.document_id), ["asset::cv-1", "asset::docx"]);
});

test("admits a ready legacy workspace CV whose DOCX was stored as octet-stream", () => {
  const documents = candidateDocuments([
    pdf({ document_id: "asset::legacy-pdf", metadata: {}, status: "ready" }),
    pdf({
      document_id: "asset::legacy-octet-docx",
      display_name: "Legacy CV.docx",
      content_type: "application/octet-stream",
      metadata: {},
      status: "ready",
    }),
    pdf({ document_id: "asset::legacy-processing", metadata: {}, status: "processing" }),
  ]);
  assert.deepEqual(documents.map((item) => item.document_id), ["asset::legacy-pdf", "asset::legacy-octet-docx"]);
  assert.deepEqual(defaultSelectedDocumentIds(documents), ["asset::legacy-pdf"]);
});

test("one eligible document is selected by default", () => {
  assert.deepEqual(defaultSelectedDocumentIds([pdf()]), ["asset::cv-1"]);
});

test("multiple documents default to the workspace CV only", () => {
  assert.deepEqual(
    defaultSelectedDocumentIds([pdf(), pdf({ document_id: "asset::cover", asset_kind: "cover_letter", display_name: "Cover.pdf" })]),
    ["asset::cv-1"],
  );
});
