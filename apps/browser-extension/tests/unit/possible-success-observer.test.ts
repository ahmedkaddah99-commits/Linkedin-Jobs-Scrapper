import { describe, expect, it, vi } from "vitest";
import { observePossibleSuccess } from "../../src/success/possible-success-observer";

describe("possible success observer", () => {
  it("reports bounded evidence only after a user-operated final control", async () => {
    document.body.innerHTML = '<form><button type="submit">Apply</button></form>';
    const onEvidence = vi.fn();
    const stop = observePossibleSuccess({
      document,
      adapter: "greenhouse",
      initialUrl: document.location.href,
      onEvidence,
      isUserInitiated: () => true,
    });
    document.querySelector("button")!.addEventListener("click", (event) => event.preventDefault());

    document.body.setAttribute("data-runr-application-success", "true");
    await Promise.resolve();
    expect(onEvidence).not.toHaveBeenCalled();

    document.querySelector("button")!.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    await Promise.resolve();
    expect(onEvidence).toHaveBeenCalledOnce();
    expect(onEvidence).toHaveBeenCalledWith("success_banner");
    stop();
  });

  it("ignores synthetic final-control activity and ambiguous page changes", async () => {
    document.body.innerHTML = '<form><button type="submit">Apply</button></form>';
    const onEvidence = vi.fn();
    const stop = observePossibleSuccess({
      document,
      adapter: "lever",
      initialUrl: document.location.href,
      onEvidence,
      isUserInitiated: () => false,
    });
    document.querySelector("button")!.addEventListener("click", (event) => event.preventDefault());
    document.querySelector("button")!.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    document.body.append(document.createElement("div"));
    await Promise.resolve();
    expect(onEvidence).not.toHaveBeenCalled();
    stop();
  });

  it("does not treat a pre-existing success marker as new evidence", async () => {
    document.body.innerHTML = '<form><button type="submit">Apply</button></form>';
    document.body.setAttribute("data-runr-application-success", "true");
    const onEvidence = vi.fn();
    const stop = observePossibleSuccess({
      document,
      adapter: "greenhouse",
      initialUrl: document.location.href,
      onEvidence,
      isUserInitiated: () => true,
    });
    const button = document.querySelector("button")!;
    button.addEventListener("click", (event) => event.preventDefault());
    button.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    await Promise.resolve();
    expect(onEvidence).not.toHaveBeenCalled();
    stop();
  });
});
