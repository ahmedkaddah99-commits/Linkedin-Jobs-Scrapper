import {
  inspectGreenhouseFixture,
  inspectLeverFixture,
  runLeverStandardFacts,
  runGreenhouseStandardFacts,
  runGreenhouseFixtureProof,
  uploadApplicationDocument,
  installSubmissionGuard,
} from "@runr/ats-core";
import { observeDynamicForm, type DynamicFormMonitor } from "@runr/ats-core/dynamic-form";
import {
  isContentRequest,
  isApplicationPackageContentRequest,
  isExactGreenhouseFixtureUrl,
  isExactLeverFixtureUrl,
  type ContentRequest,
  type PossibleSuccessEvidenceCategory,
} from "@runr/extension-messages";
import { browser } from "wxt/browser";
import { defineUnlistedScript } from "wxt/utils/define-unlisted-script";
import { observePossibleSuccess } from "../src/success/possible-success-observer";

const ADAPTER_VERSION = "1.0.0";

declare global {
  interface Window {
    __runrAssistedApplyFixtureBridgeInstalled?: boolean;
    __runrDynamicFormMonitor?: DynamicFormMonitor;
    __runrPossibleSuccessStop?: () => void;
    __runrDynamicChangeObserver?: MutationObserver;
    __runrDynamicChangeTimer?: number;
    __runrAnswerCaptureInstalled?: boolean;
    __runrAnswerCapturePackageId?: string;
    __runrAnswerCaptureKnownLabels?: Set<string>;
  }
}

function normalizedQuestionLabel(value: string): string {
  return value.replace(/[✱*]+/gu, " ").trim().toLowerCase().replace(/\s+/g, " ");
}

function userControlLabel(control: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement): string {
  const explicit = control.id
    ? Array.from(document.querySelectorAll<HTMLLabelElement>("label")).find((label) => label.htmlFor === control.id) || null
    : null;
  return String(explicit?.textContent || control.closest("label")?.textContent || control.getAttribute("aria-label") || "").trim();
}

function installExactAnswerCapture(packageId: string, knownLabels: string[]): void {
  window.__runrAnswerCapturePackageId = packageId;
  window.__runrAnswerCaptureKnownLabels = new Set(knownLabels.map(normalizedQuestionLabel));
  if (window.__runrAnswerCaptureInstalled) return;
  document.addEventListener("change", (event) => {
    const control = event.target;
    if (!(control instanceof HTMLInputElement || control instanceof HTMLTextAreaElement || control instanceof HTMLSelectElement)) return;
    if (["file", "hidden", "password", "submit", "button"].includes(control.type) || control.dataset.runrAssistedApplyFilled === "true") return;
    if (control instanceof HTMLInputElement && (control.type === "checkbox" || control.type === "radio") && !control.checked) return;
    const label = userControlLabel(control);
    const normalized = normalizedQuestionLabel(label);
    const value = control.type === "checkbox" ? "Yes" : String(control.value || "").trim();
    if (!normalized || !value || window.__runrAnswerCaptureKnownLabels?.has(normalized) ||
        /\b(?:visa|sponsorship|citizen|gender|race|ethnicity|disability|veteran|religion|declaration|certify|signature|terms|salary|compensation)\b/iu.test(normalized)) return;
    void browser.runtime.sendMessage({
      type: "ASSISTED_APPLY_SAVE_EXACT_ANSWER",
      packageId: window.__runrAnswerCapturePackageId,
      questionLabel: label,
      answerValue: value,
    });
  }, true);
  window.__runrAnswerCaptureInstalled = true;
}

function armPossibleSuccessObservation(
  request: Extract<ContentRequest, { package: unknown }>,
): void {
  const adapter = request.type === "CONTENT_RUN_LEVER_APPLICATION_PACKAGE" ? "lever" : "greenhouse";
  window.__runrPossibleSuccessStop?.();
  window.__runrPossibleSuccessStop = observePossibleSuccess({
    document,
    adapter,
    initialUrl: window.location.href,
    onEvidence: (evidenceCategory: PossibleSuccessEvidenceCategory) => {
      void browser.runtime.sendMessage({
        type: "ASSISTED_APPLY_POSSIBLE_SUCCESS",
        evidence: {
          packageId: request.package.packageId,
          packageVersion: request.package.version,
          adapter,
          adapterVersion: ADAPTER_VERSION,
          evidenceCategory,
          observedAt: new Date().toISOString(),
        },
      });
    },
  });
}

export default defineUnlistedScript(async () => {
  const submissionGuard = installSubmissionGuard(document);
  void submissionGuard;
  const testingFixturePage =
    import.meta.env.MODE === "testing" &&
    (isExactGreenhouseFixtureUrl(window.location.href) || isExactLeverFixtureUrl(window.location.href));
  window.__runrDynamicFormMonitor ??= observeDynamicForm(document);
  if (!window.__runrDynamicChangeObserver) {
    window.__runrDynamicChangeObserver = new MutationObserver((records) => {
      const meaningful = records.some((record) => record.type === "childList" &&
        [...record.addedNodes, ...record.removedNodes].some((node) => node instanceof Element &&
          (node.matches("form, fieldset, [data-step], [role=tabpanel], input, textarea, select") ||
            Boolean(node.querySelector?.("form, fieldset, [data-step], [role=tabpanel], input, textarea, select")))));
      if (!meaningful) return;
      if (window.__runrDynamicChangeTimer) window.clearTimeout(window.__runrDynamicChangeTimer);
      window.__runrDynamicChangeTimer = window.setTimeout(() => {
        void browser.runtime.sendMessage({ type: "ASSISTED_APPLY_DYNAMIC_FORM_CHANGED" });
      }, 120);
    });
    window.__runrDynamicChangeObserver.observe(document.documentElement, { childList: true, subtree: true });
  }
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
        armPossibleSuccessObservation(request);
        installExactAnswerCapture(
          request.package.packageId,
          [...request.package.answers, ...(request.package.standardAnswers || [])]
            .map((item) => item.label)
            .filter((label): label is string => typeof label === "string" && label.trim().length > 0),
        );
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
        const approvedAnswers = [...request.package.answers, ...(request.package.standardAnswers || [])]
          .filter((item, index, items) => items.findIndex((candidate) =>
            candidate.fieldIntent === item.fieldIntent && candidate.label === item.label) === index);
        return runner(
          document,
          window.location.href,
          request.package.packageId,
          request.package.version,
          {
            firstName: request.package.candidate?.firstName || firstName,
            lastName: request.package.candidate?.lastName || lastName,
            fullName: request.package.candidate?.fullName || answer("candidate.full_name"),
            email: request.package.candidate?.email || answer("candidate.email"),
            phone: request.package.candidate?.phone || answer("candidate.phone"),
          },
          approvedAnswers
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
          request.replaceFieldIntents || [],
        ).then(async ({ inspection, executions }) => {
          const dynamic = await window.__runrDynamicFormMonitor!.waitForQuiet();
          return {
            ...inspection,
            packageId: request.package.packageId,
            executions,
            formRevision: dynamic.revision,
            changeReasons: dynamic.reasons,
          };
        });
      }
      if (request.type === "CONTENT_UPLOAD_SELECTED_DOCUMENT") {
        const binary = atob(request.base64Bytes);
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
        const file = new File([bytes], request.fileName, { type: request.mimeType });
        bytes.fill(0);
        return uploadApplicationDocument(document, window.location.href, {
          file,
          documentId: request.documentId,
          documentVersion: request.documentVersion,
          documentKind: request.documentKind,
          uploadFieldIntent: request.uploadFieldIntent as import("@runr/ats-core").UploadFieldIntent,
        }).then((result) => ({
          documentId: request.documentId,
          documentVersion: request.documentVersion,
          documentKind: request.documentKind,
          fileName: result.fileName || request.fileName,
          status: result.status === "unsupported" ? "rejected" : result.status,
          reasons: result.reasons,
          telemetry: {
            schemaVersion: 1,
            adapter: request.ats,
            adapterVersion: "0.3.0",
            lifecycleStage: "upload",
            aggregateOutcome: result.status === "uploaded" ? "success"
              : (result.status === "mismatch" || result.status === "rejected") ? "failure"
                : "skipped",
            errorCategory: result.status === "uploaded" ? "none"
              : result.status === "preserved_existing" ? "existing_value"
                : result.status === "unsupported" ? "unsupported_role"
                  : result.reasons.some((reason) => /unavailable|no verified/iu.test(reason)) ? "control_unavailable"
                    : result.reasons.some((reason) => /disabled|hidden/iu.test(reason)) ? "control_blocked"
                      : result.reasons.some((reason) => /mime|does not accept/iu.test(reason)) ? "mime_rejected"
                        : result.status === "mismatch" ? "portal_rejected" : "unknown",
          },
        }));
      }
      if (import.meta.env.MODE === "testing" && request.type === "CONTENT_RUN_GREENHOUSE_FIXTURE_PROOF") {
        return runGreenhouseFixtureProof(document, window.location.href, request.proposedEmail);
      }
      return undefined;
    });
    window.__runrAssistedApplyFixtureBridgeInstalled = true;
  }

  // Local service-worker handshake. The sender tab is the authority for the
  // browser-local mapping; this message never crosses the web/backend boundary.
  void browser.runtime.sendMessage({ type: "ASSISTED_APPLY_CONTENT_READY" });

  const inspection = isExactLeverFixtureUrl(window.location.href)
    ? await inspectLeverFixture(document, window.location.href)
    : await inspectGreenhouseFixture(document, window.location.href);
  return {
    ...inspection,
    fixtureAvailable: testingFixturePage && inspection.fixtureAvailable,
  };
});
