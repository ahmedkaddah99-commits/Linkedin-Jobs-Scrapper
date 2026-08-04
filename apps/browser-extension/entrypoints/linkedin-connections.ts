import { defineUnlistedScript } from "wxt/utils/define-unlisted-script";
import { extractLinkedInConnections, type LinkedInConnectionsSnapshot } from "../src/linkedin/connections";

export default defineUnlistedScript(async (): Promise<LinkedInConnectionsSnapshot> => {
  const delay = (milliseconds: number) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));
  let previousHeight = 0;
  for (let index = 0; index < 40; index += 1) {
    window.scrollTo(0, document.body.scrollHeight);
    await delay(250);
    const nextHeight = document.body.scrollHeight;
    if (nextHeight === previousHeight && index > 3) break;
    previousHeight = nextHeight;
  }
window.scrollTo(0, 0);
return extractLinkedInConnections(document, window.location.href);
});
