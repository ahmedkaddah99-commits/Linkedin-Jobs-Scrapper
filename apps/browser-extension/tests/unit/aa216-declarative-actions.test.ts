import { beforeEach, describe, expect, it } from "vitest";
import {
  authorizeIntermediateNavigation,
  executeDeclarativeAction,
  executeNativeValueAction,
  isDeclarativeAction,
  isDeclarativePlan,
  planFillAction,
} from "@runr/ats-core";
import { installSubmissionGuard } from "@runr/ats-core";

describe("AA-216 declarative action boundary", () => {
  beforeEach(() => { document.body.innerHTML = ""; });

  it("plans and centrally executes text, select, date, checkbox, and radio actions", () => {
    document.body.innerHTML = `<input id="text"><select id="select"><option value="x">X</option></select><input id="date" type="date"><input id="check" type="checkbox"><input id="radio" type="radio">`;
    const cases = [
      ["text", "fill_text", "hello"], ["select", "select", "x"], ["date", "set_date", "2026-08-01"],
    ] as const;
    for (const [fieldId, type, value] of cases) {
      const action = planFillAction({ id: fieldId, type: fieldId === "date" ? "date" : fieldId === "select" ? "select" : "text" }, value);
      expect(action?.type).toBe(type);
      expect(executeNativeValueAction(document, action!, () => document.getElementById(fieldId))).toMatchObject({ status: "applied" });
    }
    expect(executeDeclarativeAction(document, { type: "set_checkbox", fieldId: "check", checked: true })).toMatchObject({ status: "applied" });
    expect(executeDeclarativeAction(document, { type: "set_radio", fieldId: "radio", checked: true })).toMatchObject({ status: "applied" });
  });

  it("supports rich text planning and rejects unknown/final actions", () => {
    document.body.innerHTML = `<div id="rich" contenteditable="true"></div><button id="final">Apply</button>`;
    expect(isDeclarativeAction({ type: "fill_rich_text", fieldId: "rich", value: "approved" })).toBe(true);
    expect(executeDeclarativeAction(document, { type: "fill_rich_text", fieldId: "rich", value: "approved" })).toMatchObject({ status: "applied" });
    expect(isDeclarativeAction({ type: "submit_final", fieldId: "final" })).toBe(false);
    expect(executeDeclarativeAction(document, { type: "submit_final", fieldId: "final" })).toMatchObject({ status: "rejected" });
    expect(executeDeclarativeAction(document, { type: "fill_text", fieldId: "final", value: "no" })).toMatchObject({ status: "rejected" });
  });

  it("accepts only independently checked intermediate submit evidence", () => {
    document.body.innerHTML = `<button id="next" type="submit">Next</button>`;
    const action = { type: "propose_intermediate_navigation", stepId: "one", selector: "#next", expectedTransition: { fromStepId: "one", toStepId: "two" }, controlKind: "submit" } as const;
    expect(authorizeIntermediateNavigation(action, { currentStepId: "one", selector: "#next", expectedTransition: action.expectedTransition }, document)).toEqual({ allowed: true });
    expect(executeDeclarativeAction(document, action)).toMatchObject({ status: "needs_attention" });
    expect(authorizeIntermediateNavigation(action, { currentStepId: "one", selector: "#next", expectedTransition: { ...action.expectedTransition, toStepId: "wrong" } }, document)).toMatchObject({ allowed: false });
    expect(authorizeIntermediateNavigation({ ...action, controlKind: "button" }, { currentStepId: "one", selector: "#next", expectedTransition: action.expectedTransition }, document)).toMatchObject({ allowed: false });
  });

  it("rejects malformed plans and repeatable/upload actions until controlled handlers exist", () => {
    expect(isDeclarativePlan({ schemaVersion: 1, adapter: "greenhouse", actions: [{ type: "future" }] })).toBe(false);
    expect(executeDeclarativeAction(document, { type: "add_repeatable_section", sectionId: "experience", values: { title: "x" } })).toMatchObject({ status: "needs_attention" });
    expect(executeDeclarativeAction(document, { type: "upload_document", fieldId: "cv", documentId: "doc", documentVersion: 1 })).toMatchObject({ status: "needs_attention" });
  });

  it("blocks and instruments submit, Enter, terminal clicks, requestSubmit, form.submit, fetch, and XHR", async () => {
    document.body.innerHTML = `<form><input id="email"><button type="submit">Submit</button></form>`;
    const guard = installSubmissionGuard(document);
    document.querySelector("button")!.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    document.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    document.querySelector("#email")!.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    const form = document.querySelector("form")!;
    form.requestSubmit();
    form.submit();
    await fetch("data:text/plain,aa216");
    const xhr = new XMLHttpRequest();
    xhr.open("GET", "data:text/plain,aa216");
    expect(guard.events).toEqual(expect.arrayContaining(["click", "submit", "enter", "requestSubmit", "form.submit", "fetch", "xhr"]));
    guard.stop();
  });

});
