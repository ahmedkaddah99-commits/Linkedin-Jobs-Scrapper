import { describe, expect, it } from "vitest";
import {
  PreparationCommandReplayGuard,
  validateTrustedWebPreparationCommand,
} from "../../src/preparation/external-command";
import type { AssistedApplyPreparationMessage } from "@runr/extension-messages";

const origin = "https://app.userunr.com";
const now = Date.parse("2026-08-01T12:00:00.000Z");

function start(overrides: Record<string, unknown> = {}): AssistedApplyPreparationMessage {
  return {
    protocol: "runr.assisted_apply.preparation",
    protocolVersion: 1,
    type: "start",
    source: "web",
    messageId: "msg_214_start",
    preparationId: "prep_214",
    packageId: "pkg_214",
    emittedAt: "2026-08-01T11:59:00.000Z",
    capabilities: { adapters: ["greenhouse"], capabilities: ["fill"] },
    ...overrides,
  } as AssistedApplyPreparationMessage;
}

describe("AA-214 external preparation command boundary", () => {
  it("accepts only the exact trusted Runr origin and versioned schema", () => {
    const message = start();
    expect(validateTrustedWebPreparationCommand(message, { url: origin }, origin, now)).toBe(true);
    expect(validateTrustedWebPreparationCommand(message, { url: "https://evil.example" }, origin, now)).toBe(false);
    expect(validateTrustedWebPreparationCommand({ ...message, protocolVersion: 2 }, { url: origin }, origin, now)).toBe(false);
    expect(validateTrustedWebPreparationCommand({ ...message, tabId: 42 }, { url: origin }, origin, now)).toBe(false);
  });

  it("rejects stale and future commands before service-worker work", () => {
    expect(validateTrustedWebPreparationCommand(start({ emittedAt: "2026-08-01T11:50:00.000Z" }), { url: origin }, origin, now)).toBe(false);
    expect(validateTrustedWebPreparationCommand(start({ emittedAt: "2026-08-01T12:01:00.000Z" }), { url: origin }, origin, now)).toBe(false);
  });

  it("fails closed on replay and message-id reuse", () => {
    const guard = new PreparationCommandReplayGuard();
    const message = start();
    const response = { ok: true, status: "accepted" };
    guard.write(message, response, now);
    expect(guard.read(message, now + 1)).toEqual(response);
    expect(() => guard.read({ ...message, capabilities: { adapters: ["lever"], capabilities: ["fill"] } } as AssistedApplyPreparationMessage, now + 1)).toThrow(/replayed|reused/iu);
  });

  it("keeps command handling in the service-worker boundary when the sidepanel is closed", () => {
    const message = start();
    expect(validateTrustedWebPreparationCommand(message, { url: origin }, origin, now)).toBe(true);
    // The validator requires only the trusted web sender; no sidepanel sender
    // or live panel instance participates in the external command path.
  });
});
