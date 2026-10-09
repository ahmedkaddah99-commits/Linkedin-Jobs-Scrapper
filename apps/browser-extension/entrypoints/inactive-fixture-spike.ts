/**
 * AA-201 disposable test-only content runner.
 *
 * The coordinator lives in the testing service worker. This runner is injected
 * only into the sanitized fixture tab and reuses the production-safe ATS fill
 * and document-upload primitives; it is not a production content script.
 */
import {
  runGreenhouseStandardFacts,
  runLeverStandardFacts,
  uploadApplicationDocument,
  uploadFieldIntentFor,
  type ApplicationPackageAnswer,
} from "@runr/ats-core";
import { browser } from "wxt/browser";
import { defineUnlistedScript } from "wxt/utils/define-unlisted-script";

type InactiveSpikeCommand = {
  type: "AA201_RUN_INACTIVE_FIXTURE";
  ats: "greenhouse" | "lever";
  packageId: string;
  packageVersion: number;
  candidate: { firstName?: string; lastName?: string; fullName?: string; email?: string; phone?: string };
  answers: ApplicationPackageAnswer[];
  document: {
    documentId: string;
    documentVersion: number;
    documentKind: "cv" | "cover_letter" | "supporting_document";
    fileName: string;
    mimeType: string;
    base64Bytes: string;
  };
};

export default defineUnlistedScript(async () => {
  browser.runtime.onMessage.addListener((message: unknown) => {
    if (!message || typeof message !== "object" || (message as { type?: unknown }).type !== "AA201_RUN_INACTIVE_FIXTURE") {
      return undefined;
    }
    const command = message as InactiveSpikeCommand;
    return (async () => {
      const runner = command.ats === "greenhouse"
        ? runGreenhouseStandardFacts
        : runLeverStandardFacts;
      const execution = await runner(
        document,
        window.location.href,
        command.packageId,
        command.packageVersion,
        command.candidate,
        command.answers,
      );

      const binary = atob(command.document.base64Bytes);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
      const file = new File([bytes], command.document.fileName, { type: command.document.mimeType });
      bytes.fill(0);
      const upload = await uploadApplicationDocument(document, window.location.href, {
        file,
        documentId: command.document.documentId,
        documentVersion: command.document.documentVersion,
        documentKind: command.document.documentKind,
        uploadFieldIntent: uploadFieldIntentFor(command.ats, command.document.documentKind),
      });
      await browser.runtime.sendMessage({
        type: "AA201_INACTIVE_FIXTURE_COMPLETED",
        packageId: command.packageId,
        execution,
        upload,
      });
      return { execution, upload };
    })();
  });

  await browser.runtime.sendMessage({
    type: "AA201_INACTIVE_FIXTURE_READY",
    url: window.location.href,
  });
});
