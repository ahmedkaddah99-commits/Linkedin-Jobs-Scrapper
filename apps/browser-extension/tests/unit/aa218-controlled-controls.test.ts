import { beforeEach, describe, expect, it } from "vitest";
import {
  executeNativeValueAction,
  inspectControlValidation,
  readControlValue,
  verifyControlValue,
  writeControlValue,
} from "@runr/ats-core";

describe("AA-218 deterministic controlled executor", () => {
  beforeEach(() => { document.body.innerHTML = ""; });

  it("reads/writes/verifies React/Vue-like controlled native inputs and emits framework events", () => {
    document.body.innerHTML = `<input id="react" value="old"><textarea id="vue"></textarea>`;
    const events: string[] = [];
    for (const id of ["react", "vue"]) document.getElementById(id)!.addEventListener("input", () => events.push(`${id}:input`));
    expect(readControlValue(document, "react")).toBe("old");
    expect(writeControlValue(document, "react", "new")).toMatchObject({ valid: true, value: "new" });
    expect(executeNativeValueAction(document, { type: "fill_text", fieldId: "vue", value: "approved" })).toEqual({ status: "applied", actionType: "fill_text" });
    expect(verifyControlValue(document, "vue", "approved").valid).toBe(true);
    expect(events).toEqual(["react:input", "vue:input"]);
  });

  it("supports standard selects and accessible comboboxes", () => {
    document.body.innerHTML = `<select id="select"><option value="one">One</option><option value="two">Two</option></select><div id="combo" role="combobox" aria-expanded="false"></div>`;
    expect(executeNativeValueAction(document, { type: "select", fieldId: "select", value: "two" })).toMatchObject({ status: "applied" });
    expect(executeNativeValueAction(document, { type: "fill_text", fieldId: "combo", value: "Berlin" })).toMatchObject({ status: "applied" });
    expect(readControlValue(document, "select")).toBe("two");
    expect(readControlValue(document, "combo")).toBe("Berlin");
  });

  it("supports native dates, split month/year controls, and declared date pickers", () => {
    document.body.innerHTML = `<input id="date" type="date"><input id="month"><input id="year"><input id="picker" type="date">`;
    expect(executeNativeValueAction(document, { type: "set_date", fieldId: "date", value: "2026-08-01" })).toMatchObject({ status: "applied" });
    expect(executeNativeValueAction(document, { type: "set_date", fieldId: "month", monthFieldId: "month", yearFieldId: "year", datePickerSelector: "#picker", value: "2027-02" })).toMatchObject({ status: "applied" });
    expect(readControlValue(document, "month")).toBe("02");
    expect(readControlValue(document, "year")).toBe("2027");
    expect(executeNativeValueAction(document, { type: "set_date", fieldId: "date", datePickerSelector: "#missing", value: "2026-08-01" })).toMatchObject({ status: "unresolved" });
  });

  it("supports checkbox, radio, current-employment, and rich text controls", () => {
    document.body.innerHTML = `<input id="current" type="checkbox"><input id="remote" type="radio" name="location"><div id="rich" contenteditable="true"></div>`;
    expect(executeNativeValueAction(document, { type: "set_checkbox", fieldId: "current", checked: true })).toMatchObject({ status: "applied" });
    expect(executeNativeValueAction(document, { type: "set_radio", fieldId: "remote", checked: true })).toMatchObject({ status: "applied" });
    expect(executeNativeValueAction(document, { type: "fill_rich_text", fieldId: "rich", value: "Approved description" })).toMatchObject({ status: "applied" });
    expect(readControlValue(document, "current")).toBe(true);
    expect(readControlValue(document, "rich")).toBe("Approved description");
  });

  it("keeps validation and controlled readback failures unresolved", () => {
    document.body.innerHTML = `<input id="required" required><input id="controlled">`;
    document.getElementById("controlled")!.addEventListener("input", (event) => {
      (event.target as HTMLInputElement).value = "portal-rejected";
    });
    expect(inspectControlValidation(document, "required").valid).toBe(false);
    expect(executeNativeValueAction(document, { type: "fill_text", fieldId: "controlled", value: "approved" })).toMatchObject({ status: "unresolved" });
    expect(verifyControlValue(document, "controlled", "approved").valid).toBe(false);
  });

  it("treats closed-shadow and unsupported widgets as manual unresolved boundaries", () => {
    document.body.innerHTML = `<div id="closed" data-runr-shadow-root="closed"></div><div id="widget" role="treegrid"></div>`;
    expect(executeNativeValueAction(document, { type: "fill_text", fieldId: "missing", value: "x" })).toMatchObject({ status: "unresolved" });
    expect(executeNativeValueAction(document, { type: "fill_text", fieldId: "widget", value: "x" })).toMatchObject({ status: "unresolved" });
    expect(readControlValue(document, "closed")).toBe(null);
  });
});
