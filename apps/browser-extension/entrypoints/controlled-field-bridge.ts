import { installPageContextBridge } from "@runr/ats-core/page-bridge";
import { defineUnlistedScript } from "wxt/utils/define-unlisted-script";

declare global {
  interface Window { __runrControlledFieldBridgeInstalled?: boolean; }
}

export default defineUnlistedScript(() => {
  if (window.__runrControlledFieldBridgeInstalled) return;
  installPageContextBridge(window);
  window.__runrControlledFieldBridgeInstalled = true;
});
