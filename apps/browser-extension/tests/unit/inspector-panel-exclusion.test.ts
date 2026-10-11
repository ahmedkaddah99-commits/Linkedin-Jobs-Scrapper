import { describe, expect, it } from "vitest";
import { inspectApplicationForm } from "@runr/ats-core/generic-inspector";
import { resolveUploadTarget } from "@runr/ats-core/generic-upload";

describe("employer form inspection with an open Runr panel", () => {
  it("ignores Runr's own inputs while still inspecting employer shadow roots", () => {
    document.body.innerHTML = '<label for="resume">Resume</label><input id="resume" type="file"><runr-assisted-apply-panel></runr-assisted-apply-panel><employer-contact></employer-contact>';
    const panel = document.querySelector("runr-assisted-apply-panel")!.attachShadow({ mode: "open" });
    panel.innerHTML = '<label for="runr-local-resume">Resume from your computer</label><input id="runr-local-resume" type="file"><label for="runr-search">Search profile</label><input id="runr-search">';
    const employer = document.querySelector("employer-contact")!.attachShadow({ mode: "open" });
    employer.innerHTML = '<label for="email">Email</label><input id="email" type="email">';
    const inspection = inspectApplicationForm({ document, url: "https://employer.example/apply" });
    expect(inspection.fields.map((field) => field.intent)).toEqual(["document.cv", "contact.email"]);
    expect(resolveUploadTarget(inspection, "cv")).toHaveProperty("field.intent", "document.cv");
    expect(inspection.fields.some((field) => field.label.includes("your computer") || field.label === "Search profile")).toBe(false);
    document.body.innerHTML = "";
  });
});
