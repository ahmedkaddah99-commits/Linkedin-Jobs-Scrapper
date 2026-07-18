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
