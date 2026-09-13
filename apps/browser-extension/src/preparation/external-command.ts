import {
  ASSISTED_APPLY_PREPARATION_MAX_AGE_MS,
  isAssistedApplyPreparationMessage,
  type AssistedApplyPreparationMessage,
} from "@runr/extension-messages";
import { isExactRunrWebSender, type RuntimeMessageSender } from "../auth/trusted-sender";

export type WebPreparationCommand = Extract<AssistedApplyPreparationMessage, { source: "web" }>;

export function isWebPreparationCommand(value: unknown): value is WebPreparationCommand {
  return isAssistedApplyPreparationMessage(value) && value.source === "web" &&
    (value.type === "start" || value.type === "review_activate" || value.type === "cancel" || value.type === "retry");
}

export function isFreshPreparationCommand(
  message: AssistedApplyPreparationMessage,
  now = Date.now(),
  maxAgeMs = ASSISTED_APPLY_PREPARATION_MAX_AGE_MS,
): boolean {
  const age = now - Date.parse(message.emittedAt);
  return Number.isFinite(age) && age <= maxAgeMs && age >= -30_000;
}

export function validateTrustedWebPreparationCommand(
  value: unknown,
  sender: RuntimeMessageSender,
  expectedOrigin: string,
  now = Date.now(),
): value is WebPreparationCommand {
  return isExactRunrWebSender(sender, expectedOrigin) && isWebPreparationCommand(value) &&
    isFreshPreparationCommand(value, now);
}

export function preparationCommandFingerprint(message: AssistedApplyPreparationMessage): string {
  return JSON.stringify(message);
}

export class PreparationCommandReplayGuard {
  private readonly commands = new Map<string, { fingerprint: string; expiresAt: number; response: unknown }>();

  read(message: AssistedApplyPreparationMessage, now = Date.now()): unknown | undefined {
    const existing = this.commands.get(message.messageId);
    if (!existing) return undefined;
    if (existing.expiresAt <= now || existing.fingerprint !== preparationCommandFingerprint(message)) {
      throw new Error("The preparation command was replayed or reused with different content.");
    }
    return existing.response;
  }

  write(message: AssistedApplyPreparationMessage, response: unknown, now = Date.now(), maxAgeMs = ASSISTED_APPLY_PREPARATION_MAX_AGE_MS): void {
    this.commands.set(message.messageId, {
      fingerprint: preparationCommandFingerprint(message),
      expiresAt: now + maxAgeMs,
      response,
    });
  }
}
