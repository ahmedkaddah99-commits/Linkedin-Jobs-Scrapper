import { describe, expect, it, vi } from "vitest";
const { sendMessage } = vi.hoisted(() => ({ sendMessage: vi.fn() }));
vi.mock("wxt/browser", () => ({ browser: { runtime: { sendMessage } } }));
import { validWorkspaceResult, workspaceRequest } from "../../src/panel/workspace";

describe("workspace response boundary", () => {
  it("rejects incomplete libraries and unsupported document types", () => {
    expect(validWorkspaceResult("library", { documents: null, answers: [] })).toBe(false);
    expect(validWorkspaceResult("library", { documents: [{ id: "a", name: "file.exe", role: "cv" }], answers: [] })).toBe(false);
    expect(validWorkspaceResult("library", { documents: [{ id: "asset::a", name: "Resume.pdf", role: "cv" }], answers: [] })).toBe(true);
    expect(validWorkspaceResult("document", { id: "a", name: "Resume.pdf", base64: "https://elsewhere/file" })).toBe(false);
    expect(validWorkspaceResult("draft", { text: "" })).toBe(false);
  });
  it("propagates connection failures and rejects malformed success responses", async () => {
    sendMessage.mockResolvedValueOnce({ ok: false, error: "Connect Runr" });
    await expect(workspaceRequest("library")).rejects.toThrow("Connect Runr");
    sendMessage.mockResolvedValueOnce({ ok: true, result: { unexpected: true } });
    await expect(workspaceRequest("library")).rejects.toThrow("incomplete response");
  });
});
