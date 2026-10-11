import { afterEach, describe, expect, it, vi } from "vitest";
import { act, createElement, useState } from "react";
import { createRoot } from "react-dom/client";
import { runGreenhouseStandardFacts } from "@runr/ats-core";
import { observeDynamicForm } from "@runr/ats-core/dynamic-form";
import {
  installPageContextBridge,
  isPageBridgeSetRequest,
  PAGE_BRIDGE_REQUEST_EVENT,
  requestPageContextSet,
} from "@runr/ats-core/page-bridge";

function packageAnswers() {
  return [
    { fieldIntent: "application.country", label: "Country", proposedValue: "Germany" },
    { fieldIntent: "application.conditional", label: "Conditional answer", proposedValue: "Ready" },
  ];
}

afterEach(() => vi.useRealTimers());

describe("AA-08 bounded page-context bridge", () => {
  it("accepts only bounded native field updates and cannot express submission", async () => {
    document.body.innerHTML = '<form><label for="controlled">Controlled</label><input id="controlled"><button type="submit">Submit</button></form>';
    let submissions = 0;
    document.querySelector("form")!.addEventListener("submit", (event) => { event.preventDefault(); submissions += 1; });
    const uninstall = installPageContextBridge(window);
    const input = document.querySelector<HTMLInputElement>("#controlled")!;

    expect(await requestPageContextSet(input, "framework value")).toMatchObject({
      status: "applied", acceptedValue: "framework value",
    });
    expect(input.value).toBe("framework value");
    expect(isPageBridgeSetRequest({
      schemaVersion: 1, operation: "submit", operationId: "forged-1234",
      elementId: "controlled", controlKind: "text", value: "x",
    })).toBe(false);
    expect(isPageBridgeSetRequest({
      schemaVersion: 1, operation: "set_control_value", operationId: "forged-1234",
      elementId: "controlled", controlKind: "text", value: "x", selector: "form button",
    })).toBe(false);
    window.dispatchEvent(new CustomEvent(PAGE_BRIDGE_REQUEST_EVENT, {
      detail: JSON.stringify({ schemaVersion: 1, operation: "submit", operationId: "forged-1234" }),
    }));
    expect(submissions).toBe(0);
    uninstall();
  });

  it("updates React controlled state and retains rendered readback", async () => {
    document.body.innerHTML = '<div id="root"></div>';
    function ControlledField() {
      const [value, setValue] = useState("");
      return createElement("input", {
        id: "react-controlled", value, "data-framework-state": value,
        onInput: (event) => setValue((event.currentTarget as HTMLInputElement).value),
      });
    }
    const root = createRoot(document.querySelector("#root")!);
    await act(async () => root.render(createElement(ControlledField)));
    const uninstall = installPageContextBridge(window);
    const input = document.querySelector<HTMLInputElement>("#react-controlled")!;
    await act(async () => { await requestPageContextSet(input, "React state"); });
    expect(input.value).toBe("React state");
    expect(input.dataset.frameworkState).toBe("React state");
    uninstall();
    await act(async () => root.unmount());
  });
});

describe("AA-08 dynamic and repeatable execution", () => {
  it("coalesces conditional, validation, upload, and navigation changes", async () => {
    vi.useFakeTimers();
    document.body.innerHTML = '<form><input id="first"></form>';
    const monitor = observeDynamicForm(document);
    document.querySelector("form")!.append(document.createElement("input"));
    document.querySelector("#first")!.setAttribute("aria-invalid", "true");
    const uploadStatus = document.createElement("p");
    uploadStatus.dataset.runrUploadStatus = "true";
    document.querySelector("form")!.append(uploadStatus);
    uploadStatus.textContent = "Uploaded";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    await vi.advanceTimersByTimeAsync(50);
    expect(monitor.snapshot()).toMatchObject({ revision: 1, observerActive: true });
    expect(monitor.snapshot().reasons).toEqual(expect.arrayContaining([
      "controls_changed", "validation_changed", "upload_changed", "step_changed",
    ]));
    monitor.disconnect();
  });

  it("reinspects and fills a conditional question, then stays idempotent", async () => {
    document.documentElement.dataset.runrAssistedApplyFixture = "greenhouse";
    document.body.innerHTML = `<form>
      <label for="country">Country</label><select id="country"><option value="">Choose</option><option value="DE">Germany</option></select>
      <button type="submit">Submit</button></form>`;
    const form = document.querySelector("form")!;
    document.querySelector("#country")!.addEventListener("change", () => {
      if (document.querySelector("#conditional")) return;
      form.insertAdjacentHTML("beforeend", '<label for="conditional">Conditional answer</label><input id="conditional">');
    });
    let submissions = 0;
    form.addEventListener("submit", (event) => { event.preventDefault(); submissions += 1; });

    const first = await runGreenhouseStandardFacts(document, location.href, "aa08", 1, {}, packageAnswers());
    const second = await runGreenhouseStandardFacts(document, location.href, "aa08", 1, {}, packageAnswers());
    expect(first.executions.map((item) => [item.fieldIntent, item.status])).toEqual([
      ["application.country", "filled"], ["application.conditional", "filled"],
    ]);
    expect(second.executions.every((item) => item.status === "already_filled")).toBe(true);
    expect(document.querySelector<HTMLInputElement>("#conditional")!.value).toBe("Ready");
    expect(submissions).toBe(0);
  });

  it("preserves a changed value until one explicit replacement authorization", async () => {
    document.documentElement.dataset.runrAssistedApplyFixture = "greenhouse";
    document.body.innerHTML = '<form><label for="country">Country</label><select id="country"><option value="">Choose</option><option value="DE">Germany</option><option value="GB">United Kingdom</option></select></form>';
    const country = document.querySelector<HTMLSelectElement>("#country")!;
    country.value = "GB";
    const preserved = await runGreenhouseStandardFacts(document, location.href, "aa08", 1, {}, packageAnswers());
    expect(preserved.executions[0]).toMatchObject({ status: "preserved_existing", fieldIntent: "application.country" });
    expect(country.value).toBe("GB");

    const replaced = await runGreenhouseStandardFacts(
      document, location.href, "aa08", 1, {}, packageAnswers(), ["application.country"],
    );
    expect(replaced.executions[0]).toMatchObject({ status: "filled", acceptedValue: "DE" });
    expect(country.value).toBe("DE");
    const repeated = await runGreenhouseStandardFacts(document, location.href, "aa08", 1, {}, packageAnswers());
    expect(repeated.executions[0]?.status).toBe("already_filled");

    country.value = "";
    country.dispatchEvent(new Event("input", { bubbles: true }));
    const replacement = country.cloneNode(true) as HTMLSelectElement;
    replacement.value = "";
    country.replaceWith(replacement);
    const afterRerender = await runGreenhouseStandardFacts(document, location.href, "aa08", 1, {}, packageAnswers());
    expect(afterRerender.executions[0]?.status).toBe("preserved_existing");
    expect(replacement.value).toBe("");
  });
});
