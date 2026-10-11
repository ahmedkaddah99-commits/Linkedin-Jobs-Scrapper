import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ProfileQuickCopy from "../../src/panel/ProfileQuickCopy";
import LocalDocumentPicker from "../../src/panel/LocalDocumentPicker";

let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  container = document.createElement("div"); document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => { await act(() => root.unmount()); container.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("application frontend tools", () => {
  it("copies the chosen answer and reports clipboard failures", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", Object.assign(Object.create(navigator), { clipboard: { writeText } }));
    await act(() => root.render(<ProfileQuickCopy answers details={[{ section: "Saved answer", label: "Notice period", value: "One month" }]} />));
    const button = container.querySelector<HTMLButtonElement>('button[aria-label="Copy Saved answer Notice period"]')!;
    await act(async () => { button.click(); });
    expect(writeText).toHaveBeenCalledWith("One month");
    expect(container.querySelector('[role="status"]')?.textContent).toBe("Notice period copied");
    writeText.mockRejectedValueOnce(new Error("Clipboard denied"));
    await act(async () => { button.click(); });
    expect(container.querySelector('[role="status"]')?.textContent).toContain("Select the text");
  });

  it("requires a file and an explicit replacement choice before attachment", async () => {
    const attach = vi.fn().mockResolvedValue("Resume attached.");
    await act(() => root.render(<LocalDocumentPicker role="cv" onAttach={attach} />));
    expect(container.querySelector("button")).toBeNull();
    const file = new File(["%PDF"], "resume.pdf", { type: "application/pdf" });
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    Object.defineProperty(input, "files", { configurable: true, value: [file] });
    await act(() => input.dispatchEvent(new Event("change", { bubbles: true })));
    const button = container.querySelector<HTMLButtonElement>("button")!;
    await act(async () => { button.click(); });
    expect(attach).toHaveBeenLastCalledWith("cv", file, false);
    const replace = container.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    await act(() => replace.click());
    await act(async () => { button.click(); });
    expect(attach).toHaveBeenLastCalledWith("cv", file, true);
    expect(container.querySelector('[role="status"]')?.textContent).toBe("Resume attached.");
  });
});
