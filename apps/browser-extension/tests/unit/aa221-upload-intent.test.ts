import { beforeEach, describe, expect, it } from "vitest";
import {
  GreenhouseAdapter,
  LeverAdapter,
  uploadApplicationDocument,
  uploadFieldIntentFor,
} from "@runr/ats-core";

describe("AA-221 adapter-declared upload intents", () => {
  beforeEach(() => {
    document.documentElement.dataset.runrAssistedApplyFixture = "greenhouse";
    document.body.innerHTML = "";
  });

  it("declares exact CV, cover-letter, and supporting intents without using document bytes", async () => {
    document.body.innerHTML = `
      <label for="resume">CV / Resume</label><input id="resume" name="resume" type="file">
      <label for="cover-letter">Cover letter</label><input id="cover-letter" name="cover_letter" type="file">
      <label for="supporting-document">Supporting document</label><input id="supporting-document" name="supporting_document" type="file">
    `;
    const form = await new GreenhouseAdapter().inspect({ document, url: "https://boards.greenhouse.io/example/jobs/1" });
    expect(form.fields.filter((field) => field.uploadFieldIntent).map((field) => field.uploadFieldIntent)).toEqual([
      "greenhouse.resume", "greenhouse.cover_letter", "greenhouse.supporting_document",
    ]);
    expect(uploadFieldIntentFor("lever", "cv")).toBe("lever.resume");
  });

  it("does not guess an upload target when the declared intent is absent or duplicated", async () => {
    document.body.innerHTML = `
      <input id="resume" name="resume" type="file">
      <input id="resume-copy" name="resume" type="file">
    `;
    const result = await uploadApplicationDocument(document, "https://boards.greenhouse.io/example/jobs/1", {
      documentId: "cv-1",
      documentVersion: 1,
      documentKind: "cv",
      file: new File(["pdf"], "Candidate.pdf", { type: "application/pdf" }),
      uploadFieldIntent: "greenhouse.resume",
    });
    expect(result.status).toBe("rejected");
    expect(result.reasons[0]).toContain("multiple");
  });

  it("keeps Lever declarations separate from Greenhouse declarations", async () => {
    document.documentElement.dataset.runrAssistedApplyFixture = "lever";
    document.body.innerHTML = `<input id="lever-resume" name="resume" type="file">`;
    const form = await new LeverAdapter().inspect({ document, url: "https://jobs.lever.co/example/1" });
    expect(form.fields.find((field) => field.type === "file")?.uploadFieldIntent).toBe("lever.resume");
  });
});
