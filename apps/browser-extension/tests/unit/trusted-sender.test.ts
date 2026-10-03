import { describe, expect, it } from "vitest";
import { isExactSidePanelSender } from "../../src/auth/trusted-sender";

const EXTENSION_ID = "abcdefghijklmnopabcdefghijklmnop";
const SIDE_PANEL = `chrome-extension://${EXTENSION_ID}/sidepanel.html`;

describe("privileged panel sender boundary", () => {
  it("accepts only the exact side panel page for this extension", () => {
    expect(
      isExactSidePanelSender(
        { id: EXTENSION_ID, url: SIDE_PANEL },
        EXTENSION_ID,
        SIDE_PANEL,
      ),
    ).toBe(true);
    expect(
      isExactSidePanelSender(
        { id: EXTENSION_ID, url: "https://boards.greenhouse.io/acme/jobs/1" },
        EXTENSION_ID,
        SIDE_PANEL,
      ),
    ).toBe(false);
    expect(
      isExactSidePanelSender(
        { id: EXTENSION_ID, url: `chrome-extension://${EXTENSION_ID}/application-form.js` },
        EXTENSION_ID,
        SIDE_PANEL,
      ),
    ).toBe(false);
    expect(
      isExactSidePanelSender(
        { id: "other-extension", url: SIDE_PANEL },
        EXTENSION_ID,
        SIDE_PANEL,
      ),
    ).toBe(false);
    expect(
      isExactSidePanelSender(
        { id: EXTENSION_ID, url: `${SIDE_PANEL}#forged` },
        EXTENSION_ID,
        SIDE_PANEL,
      ),
    ).toBe(false);
  });
});
