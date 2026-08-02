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

test("multiple approved documents default to the CV and attachments", () => {
  assert.deepEqual(
    defaultSelectedDocumentIds([pdf(), pdf({ document_id: "asset::cover", asset_kind: "cover_letter", display_name: "Cover.pdf" })]),
    ["asset::cv-1", "asset::cover"],
  );
});

test("prefers the exact role tailored PDF and includes role application attachments", () => {
  const role = { run_id: "run-1", job_id: "job-1" };
  const documents = [
    pdf(),
    pdf({ document_id: "artifact::run-1::cv-docx", run_id: "run-1", job_id: "job-1", asset_kind: "generated_cv", display_name: "Tailored CV.docx", content_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" }),
    pdf({ document_id: "artifact::run-1::cv-pdf", run_id: "run-1", job_id: "job-1", asset_kind: "generated_cv", display_name: "Tailored CV.pdf" }),
    pdf({ document_id: "artifact::run-1::letter", run_id: "run-1", job_id: "job-1", asset_kind: "motivation_letter", display_name: "Motivation letter.pdf" }),
    pdf({ document_id: "artifact::run-2::foreign", run_id: "run-2", job_id: "job-1", asset_kind: "generated_cv" }),
  ];
  const candidates = candidateDocuments(documents, role);
  assert.deepEqual(candidates.map((item) => item.document_id), [
    "asset::cv-1", "artifact::run-1::cv-docx", "artifact::run-1::cv-pdf", "artifact::run-1::letter",
  ]);
  assert.deepEqual(defaultSelectedDocumentIds(candidates, role), [
    "artifact::run-1::cv-pdf", "artifact::run-1::letter",
  ]);
});
