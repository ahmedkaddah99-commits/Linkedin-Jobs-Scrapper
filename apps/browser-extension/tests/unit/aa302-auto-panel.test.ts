import { describe, expect, it } from "vitest";
import type { ApplicationPageDetection, ApplicationPageKind } from "@runr/ats-core";
import { shouldMountPanel } from "../../src/panel/mount-decision";
import { assistantPanelMatchPatterns, isExcludedPanelUrl } from "../../src/panel/script-registration";
import { formatPostedAt, providerLabel } from "../../src/panel/AssistantPanel";

function detectionOf(kind: ApplicationPageKind, fillableFieldCount = 12): ApplicationPageDetection {
  return {
    kind,
    provider: "avature",
    confidence: 0.9,
    fillableFieldCount,
    hasDocumentUpload: kind === "application_form",
    hasRepeatedSections: kind === "application_form",
    reasons: [],
    algorithmVersion: "1.0.0",
  };
}

describe("AA-302 automatic panel display rule", () => {
  it("raises the panel only on an application form", () => {
    expect(shouldMountPanel(detectionOf("application_form")).mount).toBe(true);
  });

  it("stays closed on a job posting, a sign-in step, and an unrelated page", () => {
    // These are the three cases the reference captures show the panel absent for.
    expect(shouldMountPanel(detectionOf("job_detail", 2)).mount).toBe(false);
    expect(shouldMountPanel(detectionOf("application_gateway", 1)).mount).toBe(false);
    expect(shouldMountPanel(detectionOf("unsupported", 0)).mount).toBe(false);
  });

  it("explains why it stayed closed", () => {
    expect(shouldMountPanel(detectionOf("job_detail", 2)).reason).toMatch(/job posting/iu);
    expect(shouldMountPanel(detectionOf("application_gateway", 1)).reason).toMatch(/sign-in/iu);
  });

  it("stays closed on a form that has not rendered its controls yet", () => {
    expect(shouldMountPanel(detectionOf("application_form", 0)).mount).toBe(false);
  });

  it("honors the user turning automatic display off", () => {
    const decision = shouldMountPanel(detectionOf("application_form"), { autoOpenOnApplicationPage: false });
    expect(decision.mount).toBe(false);
    expect(decision.reason).toMatch(/turned off/iu);
  });
});

describe("AA-302 content-script registration targets", () => {
  it("collapses to the broad grant so the script is registered once", () => {
    // Host access is granted at install, so this is the normal case. Keeping
    // narrower patterns alongside it would run the script twice per page.
    expect(assistantPanelMatchPatterns(["https://*/*", "https://boards.greenhouse.io/*"]))
      .toEqual(["https://*/*"]);
    expect(assistantPanelMatchPatterns(["<all_urls>"])).toEqual(["https://*/*"]);
  });

  it("still filters Runr's own origins when no broad grant is present", () => {
    expect(assistantPanelMatchPatterns([
      "https://runr-api.onrender.com/*",
      "https://www.linkedin.com/*",
      "https://app.userunr.com/*",
    ])).toEqual([]);
  });

  it("deduplicates and ignores non-web origins", () => {
    expect(assistantPanelMatchPatterns([
      "https://jobs.siemens.com/*",
      "https://jobs.siemens.com/*",
      "file:///*",
      "chrome://settings/*",
    ])).toEqual(["https://jobs.siemens.com/*"]);
  });

  it("keeps the panel off Runr's own surfaces under a broad grant", () => {
    // A broad match pattern cannot express an exclusion, so the page checks.
    expect(isExcludedPanelUrl("https://app.userunr.com/dashboard")).toBe(true);
    expect(isExcludedPanelUrl("https://www.linkedin.com/feed/")).toBe(true);
    expect(isExcludedPanelUrl("https://runr-api.onrender.com/health")).toBe(true);
    expect(isExcludedPanelUrl("https://jobs.siemens.com/en_US/externaljobs/Register")).toBe(false);
  });
});

describe("AA-302 panel presentation helpers", () => {
  it("formats a posting date and omits one it cannot parse", () => {
    expect(formatPostedAt("2026-08-14")).toBe(new Date("2026-08-14").toLocaleDateString());
    expect(formatPostedAt("14-Aug-2026")).toBe(new Date("14-Aug-2026").toLocaleDateString());
    expect(formatPostedAt("sometime last week")).toBeNull();
    expect(formatPostedAt(undefined)).toBeNull();
  });

  it("names providers in prose and falls back without inventing one", () => {
    expect(providerLabel("avature")).toBe("Avature");
    expect(providerLabel("taleo")).toBe("Oracle Recruiting");
    expect(providerLabel("unknown")).toBe("this employer's portal");
  });
});
