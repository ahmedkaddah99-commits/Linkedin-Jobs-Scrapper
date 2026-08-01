import { beforeEach, describe, expect, it } from "vitest";
import {
  LeverAdapter,
  planLeverApplication,
  type ApplicationPackage,
} from "@runr/ats-core";

function packageFor(answers: ApplicationPackage["answers"] = []): ApplicationPackage {
  return {
    id: "aa220-lever-package",
    version: 1,
    candidate: { fullName: "Ada Lovelace", email: "ada@example.com" },
    answers,
  };
}

describe("AA-220 Lever adapter contract", () => {
  beforeEach(() => {
    document.documentElement.dataset.runrAssistedApplyFixture = "lever";
    document.body.innerHTML = `
      <form>
        <label for="name">Full name</label>
        <input id="name" name="name" autocomplete="name" required>
        <label for="sensitive">Work authorization</label>
        <input id="sensitive" name="work_authorization">
        <button id="final-submit" type="submit">Submit application</button>
      </form>`;
  });

  it("detects, inspects, and plans only declarative non-terminal actions", async () => {
    const plan = await planLeverApplication(
      document,
      "https://jobs.lever.co/example/1",
      packageFor(),
    );

    expect(plan.actions).toEqual([
      expect.objectContaining({ type: "fill_text", value: "Ada Lovelace" }),
    ]);
    expect(plan.actions.some((action) => action.type === "propose_intermediate_navigation")).toBe(false);
    expect(plan.actions.some((action) => action.type === "upload_document")).toBe(false);
    expect(plan.actions.some((action) => /submit|terminal/iu.test(action.type))).toBe(false);
    expect(plan.manualReasons).toContain("final_submission");
    expect(plan.stopsAtReview).toBe(true);
    expect(plan.unresolved.some((item) => /repeatable experience\/education/iu.test(item))).toBe(true);
    expect(document.querySelector<HTMLInputElement>("#name")!.value).toBe("");
  });

  it("preserves nonempty values and leaves sensitive answers unresolved", async () => {
    document.querySelector<HTMLInputElement>("#name")!.value = "Existing Name";
    const plan = await planLeverApplication(
      document,
      "https://jobs.lever.co/example/1",
      packageFor([
        { fieldIntent: "application.work_authorization", label: "Work authorization", proposedValue: "Yes" },
      ]),
    );

    expect(plan.actions).toEqual([]);
    expect(plan.unresolved).toEqual(expect.arrayContaining([
      expect.stringContaining("Full name"),
      expect.stringContaining("Work authorization"),
    ]));
    expect(document.querySelector<HTMLInputElement>("#name")!.value).toBe("Existing Name");
  });

  it("fails closed outside a confirmed Lever page", async () => {
    delete document.documentElement.dataset.runrAssistedApplyFixture;
    const adapter = new LeverAdapter();
    const detection = await adapter.detect({ document, url: "https://boards.greenhouse.io/example/jobs/1" });
    expect(detection.ats).toBe("greenhouse");
    const plan = await planLeverApplication(document, "https://boards.greenhouse.io/example/jobs/1", packageFor());
    expect(plan.actions).toEqual([]);
    expect(plan.stopsAtReview).toBe(true);
  });
});
