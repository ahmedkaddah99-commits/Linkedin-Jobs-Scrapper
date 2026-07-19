export interface RuntimeMessageSender {
  id?: string;
  url?: string;
}

export function isExactSidePanelSender(
  sender: RuntimeMessageSender,
  runtimeId: string,
  sidePanelUrl: string,
): boolean {
  return sender.id === runtimeId && sender.url === sidePanelUrl;
}

/** Only the configured Runr web origin may request a package-tab binding. */
export function isExactRunrWebSender(
  sender: RuntimeMessageSender,
  expectedOrigin: string,
): boolean {
  if (!sender.url) return false;
  try {
    return new URL(sender.url).origin === expectedOrigin;
  } catch {
    return false;
  }
}
