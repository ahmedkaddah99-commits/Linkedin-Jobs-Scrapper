import {
  inspectGreenhouseFixture,
  inspectLeverFixture,
  runLeverStandardFacts,
  runGreenhouseStandardFacts,
  runGreenhouseFixtureProof,
  uploadGreenhousePdf,
} from "@runr/ats-core";
import {
  isContentRequest,
  isApplicationPackageContentRequest,
  isExactGreenhouseFixtureUrl,
  isExactLeverFixtureUrl,
  type ContentRequest,
} from "@runr/extension-messages";
import { browser } from "wxt/browser";
import { defineUnlistedScript } from "wxt/utils/define-unlisted-script";

declare global {
  interface Window {
    __runrAssistedApplyFixtureBridgeInstalled?: boolean;
  }
}

export default defineUnlistedScript(async () => {
  const testingFixturePage =
    import.meta.env.MODE === "testing" &&
    (isExactGreenhouseFixtureUrl(window.location.href) || isExactLeverFixtureUrl(window.location.href));
  if (!window.__runrAssistedApplyFixtureBridgeInstalled) {
    browser.runtime.onMessage.addListener((message: unknown) => {
      const validRequest = import.meta.env.MODE === "testing"
        ? isContentRequest(message)
        : isApplicationPackageContentRequest(message);
      if (!validRequest) return undefined;
      const request = message as ContentRequest;
      if (import.meta.env.MODE === "testing" &&
        request.type === "CONTENT_RUN_GREENHOUSE_FIXTURE_PROOF" &&
        !isExactGreenhouseFixtureUrl(window.location.href)
      ) {
        return {
          ats: null,
          fixtureAvailable: false,
          fieldCount: 0,
          manualReasons: [],
          execution: null,
        };
      }
      if (request.type === "CONTENT_RUN_GREENHOUSE_APPLICATION_PACKAGE" || request.type === "CONTENT_RUN_LEVER_APPLICATION_PACKAGE") {
        const answer = (intent: string) => request.package.answers.find(
          (item) => item.fieldIntent === intent &&
            (item.source === "profile_verified" || item.source === "scoped_preference") &&
            !item.requiresReview && item.confidence >= 0.95,
        )?.proposedValue;
        const firstName = answer("candidate.legal_first_name") ||
          answer("candidate.preferred_first_name") || answer("candidate.first_name");
        const lastName = answer("candidate.legal_last_name") ||
          answer("candidate.preferred_last_name") || answer("candidate.last_name");
        const runner = request.type === "CONTENT_RUN_LEVER_APPLICATION_PACKAGE"
          ? runLeverStandardFacts
          : runGreenhouseStandardFacts;
        return runner(
          document,
          window.location.href,
          request.package.packageId,
          request.package.version,
          {
            firstName,
            lastName,
            fullName: answer("candidate.full_name"),
            email: answer("candidate.email"),
            phone: answer("candidate.phone"),
          },
          request.package.answers
            .filter((item) =>
              item.source !== "ai_suggestion" && !item.requiresReview &&
              item.confidence >= 0.95 && item.sensitivity !== "legal" &&
              (item.sensitivity !== "demographic" || request.package.policy.permitDemographicAutofill) &&
              !(item.source === "scoped_preference" && item.sensitivity === "personal" &&
                !request.package.policy.permitSensitiveAutofill))
            .map((item) => ({
              fieldIntent: item.fieldIntent,
              label: item.label,
              proposedValue: item.proposedValue,
            })),
        ).then(({ inspection, executions }) => ({
          ...inspection,
          packageId: request.package.packageId,
          executions,
        }));
      }
      if (request.type === "CONTENT_UPLOAD_GREENHOUSE_CV") {
        const binary = atob(request.base64Bytes);
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
        const file = new File([bytes], request.fileName, { type: request.mimeType });
        bytes.fill(0);
        return uploadGreenhousePdf(document, window.location.href, {
          file,
          documentId: request.documentId,
          documentVersion: request.documentVersion,
        }).then((result) => ({
          documentId: request.documentId,
          documentVersion: request.documentVersion,
          fileName: result.fileName || request.fileName,
          status: result.status === "unsupported" ? "rejected" : result.status,
          reasons: result.reasons,
        }));
      }
      if (import.meta.env.MODE === "testing" && request.type === "CONTENT_RUN_GREENHOUSE_FIXTURE_PROOF") {
        return runGreenhouseFixtureProof(document, window.location.href, request.proposedEmail);
      }
      return undefined;
    });
    window.__runrAssistedApplyFixtureBridgeInstalled = true;
  }

  const inspection = isExactLeverFixtureUrl(window.location.href)
    ? await inspectLeverFixture(document, window.location.href)
    : await inspectGreenhouseFixture(document, window.location.href);
  return {
    ...inspection,
    fixtureAvailable: testingFixturePage && inspection.fixtureAvailable,
  };
});
