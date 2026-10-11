import { defineUnlistedScript } from "wxt/utils/define-unlisted-script";
import { extractLinkedInConnections, type LinkedInConnectionsSnapshot } from "../src/linkedin/connections";

export default defineUnlistedScript(async (): Promise<LinkedInConnectionsSnapshot> => {
  const delay = (milliseconds: number) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));
  let previousHeight = 0;
  for (let index = 0; index < 40; index += 1) {
    window.scrollTo(0, document.body.scrollHeight);
    document.querySelectorAll("main, [role='main'], ul").forEach((element) => {
      if (element.scrollHeight > element.clientHeight + 200) element.scrollTop = element.scrollHeight;
    });
    await delay(250);
    const nextHeight = Math.max(
      document.body.scrollHeight,
      ...[...document.querySelectorAll("main, [role='main'], ul")].map((element) => element.scrollHeight),
    );
    if (nextHeight === previousHeight && index > 3) break;
    previousHeight = nextHeight;
  }
  window.scrollTo(0, 0);
  return extractLinkedInConnections(document, window.location.href);
});
