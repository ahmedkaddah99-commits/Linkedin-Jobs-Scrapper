/**
 * AA-15: Privacy-safe adapter health telemetry — schema, privacy, and operator report tests.
 *
 * Acceptance gate:
 * - Privacy schema tests pass (no answers, sensitive values, bytes, URLs, tokens,
 *   credentials, filenames, or raw markup in event payloads)
 * - Event payloads are bounded (only adapter/version, lifecycle stage, aggregate
 *   outcome, and bounded error category)
 * - Operator reports separate Greenhouse and Lever lifecycle regressions
 * - No executable behavior can come from remote telemetry configuration
 */

import { describe, expect, it } from "vitest";
import {
  isAdapterHealthTelemetry,
  isRemoteTelemetryConfig,
  type AdapterHealthTelemetry,
  type LifecycleStage,
  type AggregateOutcome,
  type ErrorCategory,
  type RemoteTelemetryConfig,
} from "@runr/extension-messages";
import {
  createTelemetryReporter,
  executionStatusToOutcome,
  executionStatusToErrorCategory,
  uploadStatusToOutcome,
  uploadStatusToErrorCategory,
  type TelemetryTransport,
} from "@runr/ats-core";

// ---------------------------------------------------------------------------
// Schema and privacy gate
// ---------------------------------------------------------------------------

const ALL_LIFECYCLE_STAGES: LifecycleStage[] = [
  "detect", "inspect", "match", "fill", "validate", "upload",
];

const ALL_AGGREGATE_OUTCOMES: AggregateOutcome[] = [
  "success", "failure", "partial", "skipped",
];

const ALL_ERROR_CATEGORIES: ErrorCategory[] = [
  "none", "detection_failed", "inspection_failed", "matching_failed",
  "fill_rejected", "fill_mismatched", "validation_failed",
  "control_unavailable", "control_blocked", "mime_rejected",
  "portal_rejected", "existing_value", "unsupported_role", "unknown",
];

describe("AA-15: privacy schema — adapter health telemetry payloads", () => {
  it.each(ALL_LIFECYCLE_STAGES)(
    "accepts only the six bounded keys for lifecycleStage=%s",
    (stage) => {
      for (const outcome of ALL_AGGREGATE_OUTCOMES) {
        for (const error of ALL_ERROR_CATEGORIES) {
          const event = {
            schemaVersion: 1,
            adapter: "greenhouse" as const,
            adapterVersion: "0.3.0",
            lifecycleStage: stage,
            aggregateOutcome: outcome,
            errorCategory: error,
          };
          expect(isAdapterHealthTelemetry(event)).toBe(true);
        }
      }
    },
  );

  it("rejects every forbidden key in telemetry payloads", () => {
    const base = {
      schemaVersion: 1,
      adapter: "greenhouse",
      adapterVersion: "0.3.0",
      lifecycleStage: "fill",
      aggregateOutcome: "success",
      errorCategory: "none",
    } as const;

    const forbiddenKeys = [
      "answer", "answers", "sensitiveValue", "sensitive_values",
      "bytes", "documentBytes", "fileBytes",
      "url", "documentUrl", "redirectUrl",
      "token", "sessionToken", "authToken",
      "credential", "credentials", "password",
      "fileName", "filenames", "originalFileName",
      "rawMarkup", "rawHtml", "pageContent", "domMarkup",
      "selector", "cssSelector", "locator",
    ];

    for (const key of forbiddenKeys) {
      expect(isAdapterHealthTelemetry({ ...base, [key]: "secret" })).toBe(false);
    }
  });

  it("rejects objects with extra unknown keys", () => {
    const valid = {
      schemaVersion: 1,
      adapter: "greenhouse",
      adapterVersion: "0.3.0",
      lifecycleStage: "detect",
      aggregateOutcome: "success",
      errorCategory: "none",
    };
    expect(isAdapterHealthTelemetry(valid)).toBe(true);
    expect(isAdapterHealthTelemetry({ ...valid, extraField: "value" })).toBe(false);
    expect(isAdapterHealthTelemetry({ ...valid, nested: { x: 1 } })).toBe(false);
  });

  it("rejects invalid enum values", () => {
    const base = {
      schemaVersion: 1,
      adapter: "greenhouse" as const,
      adapterVersion: "0.3.0",
    };
    expect(isAdapterHealthTelemetry(
      { ...base, lifecycleStage: "submit" as LifecycleStage,
        aggregateOutcome: "success" as AggregateOutcome,
        errorCategory: "none" as ErrorCategory },
    )).toBe(false);
    expect(isAdapterHealthTelemetry(
      { ...base, lifecycleStage: "detect",
        aggregateOutcome: "complete" as AggregateOutcome,
        errorCategory: "none" as ErrorCategory },
    )).toBe(false);
    expect(isAdapterHealthTelemetry(
      { ...base, lifecycleStage: "detect",
        aggregateOutcome: "success",
        errorCategory: "critical" as ErrorCategory },
    )).toBe(false);
    expect(isAdapterHealthTelemetry(
      { ...base, lifecycleStage: "detect",
        aggregateOutcome: "success",
        errorCategory: "none",
        adapter: "workday" },
    )).toBe(false);
  });

  it("requires a valid semver adapter version", () => {
    const base = {
      schemaVersion: 1,
      adapter: "greenhouse" as const,
      lifecycleStage: "validate" as const,
      aggregateOutcome: "success" as const,
      errorCategory: "none" as const,
    };
    expect(isAdapterHealthTelemetry({ ...base, adapterVersion: "0.3.0" })).toBe(true);
    expect(isAdapterHealthTelemetry({ ...base, adapterVersion: "1.0.0" })).toBe(true);
    expect(isAdapterHealthTelemetry({ ...base, adapterVersion: "invalid" })).toBe(false);
    expect(isAdapterHealthTelemetry({ ...base, adapterVersion: "" })).toBe(false);
    expect(isAdapterHealthTelemetry({ ...base, adapterVersion: "v1.0.0" })).toBe(false);
  });
});


// ---------------------------------------------------------------------------
// Greenhouse vs Lever operator reporting
// ---------------------------------------------------------------------------

describe("AA-15: operator reporting separates Greenhouse and Lever", () => {
  it("maps execution status to bounded aggregate outcomes", () => {
    expect(executionStatusToOutcome("filled")).toBe("success");
    expect(executionStatusToOutcome("already_filled")).toBe("success");
    expect(executionStatusToOutcome("rejected")).toBe("failure");
    expect(executionStatusToOutcome("mismatch")).toBe("failure");
    expect(executionStatusToOutcome("preserved_existing")).toBe("skipped");
    expect(executionStatusToOutcome("skipped_hidden")).toBe("skipped");
    expect(executionStatusToOutcome("skipped_disabled")).toBe("skipped");
  });

  it("maps execution status to bounded error categories", () => {
    expect(executionStatusToErrorCategory("filled")).toBe("none");
    expect(executionStatusToErrorCategory("already_filled")).toBe("none");
    expect(executionStatusToErrorCategory("rejected")).toBe("fill_rejected");
    expect(executionStatusToErrorCategory("mismatch")).toBe("fill_mismatched");
    expect(executionStatusToErrorCategory("skipped_hidden")).toBe("control_blocked");
    expect(executionStatusToErrorCategory("skipped_disabled")).toBe("control_blocked");
    expect(executionStatusToErrorCategory("preserved_existing")).toBe("existing_value");
  });

  it("maps upload status to bounded aggregate outcomes", () => {
    expect(uploadStatusToOutcome("uploaded")).toBe("success");
    expect(uploadStatusToOutcome("rejected")).toBe("failure");
    expect(uploadStatusToOutcome("mismatch")).toBe("failure");
    expect(uploadStatusToOutcome("preserved_existing")).toBe("skipped");
    expect(uploadStatusToOutcome("unsupported")).toBe("skipped");
  });

  it("maps upload status to bounded error categories", () => {
    expect(uploadStatusToErrorCategory("uploaded")).toBe("none");
    expect(uploadStatusToErrorCategory("rejected")).toBe("portal_rejected");
    expect(uploadStatusToErrorCategory("mismatch")).toBe("fill_mismatched");
    expect(uploadStatusToErrorCategory("preserved_existing")).toBe("existing_value");
    expect(uploadStatusToErrorCategory("unsupported")).toBe("unsupported_role");
  });
});

// ---------------------------------------------------------------------------
// Telemetry reporter
// ---------------------------------------------------------------------------

describe("AA-15: telemetry reporter", () => {
  it("reports bounded events through the transport", () => {
    const sent: AdapterHealthTelemetry[] = [];
    const transport: TelemetryTransport = { send: (e) => sent.push(e) };
    const reporter = createTelemetryReporter(transport);

    reporter.report("greenhouse", "0.3.0", "detect", "success", "none");
    reporter.report("lever", "0.3.0", "fill", "failure", "fill_rejected");
    reporter.flush();

    expect(sent).toHaveLength(2);
    expect(sent[0]).toEqual({
      schemaVersion: 1,
      adapter: "greenhouse",
      adapterVersion: "0.3.0",
      lifecycleStage: "detect",
      aggregateOutcome: "success",
      errorCategory: "none",
    });
    expect(sent[1]).toEqual({
      schemaVersion: 1,
      adapter: "lever",
      adapterVersion: "0.3.0",
      lifecycleStage: "fill",
      aggregateOutcome: "failure",
      errorCategory: "fill_rejected",
    });
  });

  it("applies remote config for batching and sampling only", () => {
    const sent: AdapterHealthTelemetry[] = [];
    const transport: TelemetryTransport = { send: (e) => sent.push(e) };
    const reporter = createTelemetryReporter(transport);

    const config: RemoteTelemetryConfig = {
      schemaVersion: 1,
      batchIntervalSeconds: 5,
      sampleRate: 1,
      maxQueueSize: 10,
    };
    reporter.applyRemoteConfig(config);
    reporter.report("greenhouse", "0.3.0", "inspect", "success", "none");
    reporter.flush();

    expect(sent).toHaveLength(1);
  });

  it("enforces max queue size by flushing immediately", () => {
    const sent: AdapterHealthTelemetry[] = [];
    const transport: TelemetryTransport = { send: (e) => sent.push(e) };
    const reporter = createTelemetryReporter(transport);

    reporter.applyRemoteConfig({
      schemaVersion: 1,
      batchIntervalSeconds: 300,
      sampleRate: 1,
      maxQueueSize: 1,
    });

    reporter.report("greenhouse", "0.3.0", "match", "success", "none");
    reporter.report("lever", "0.3.0", "match", "failure", "matching_failed");

    expect(sent).toHaveLength(2);
  });
});


// ---------------------------------------------------------------------------
// Remote configuration — data-only proof
// ---------------------------------------------------------------------------

describe("AA-15: remote config is strictly data-only", () => {
  it("accepts only the bounded data-only config schema", () => {
    const valid: RemoteTelemetryConfig = {
      schemaVersion: 1,
      batchIntervalSeconds: 30,
      sampleRate: 1,
      maxQueueSize: 100,
    };
    expect(isRemoteTelemetryConfig(valid)).toBe(true);
  });

  it("rejects config with algorithm, execution, or protection keys", () => {
    const base = {
      schemaVersion: 1,
      batchIntervalSeconds: 30,
      sampleRate: 1,
      maxQueueSize: 100,
    };
    expect(isRemoteTelemetryConfig(base)).toBe(true);

    const dangerousKeys = [
      "algorithm", "fn", "function", "script", "code", "eval",
      "adapter", "protection", "submit", "command", "exec",
      "enabledPortals", "disableSubmitProtection", "overrideClassification",
    ];
    for (const key of dangerousKeys) {
      expect(isRemoteTelemetryConfig({ ...base, [key]: "danger" })).toBe(false);
    }
  });

  it("rejects out-of-range values", () => {
    expect(isRemoteTelemetryConfig({
      schemaVersion: 1, batchIntervalSeconds: 4, sampleRate: 0.5, maxQueueSize: 100,
    })).toBe(false);
    expect(isRemoteTelemetryConfig({
      schemaVersion: 1, batchIntervalSeconds: 301, sampleRate: 0.5, maxQueueSize: 100,
    })).toBe(false);
    expect(isRemoteTelemetryConfig({
      schemaVersion: 1, batchIntervalSeconds: 30, sampleRate: -0.1, maxQueueSize: 100,
    })).toBe(false);
    expect(isRemoteTelemetryConfig({
      schemaVersion: 1, batchIntervalSeconds: 30, sampleRate: 1.1, maxQueueSize: 100,
    })).toBe(false);
    expect(isRemoteTelemetryConfig({
      schemaVersion: 1, batchIntervalSeconds: 30, sampleRate: 0.5, maxQueueSize: 0,
    })).toBe(false);
    expect(isRemoteTelemetryConfig({
      schemaVersion: 1, batchIntervalSeconds: 30, sampleRate: 0.5, maxQueueSize: 1001,
    })).toBe(false);
  });

  it("rejects non-integer batch and queue values", () => {
    expect(isRemoteTelemetryConfig({
      schemaVersion: 1, batchIntervalSeconds: 30.5, sampleRate: 0.5, maxQueueSize: 100,
    })).toBe(false);
    expect(isRemoteTelemetryConfig({
      schemaVersion: 1, batchIntervalSeconds: 30, sampleRate: 0.5, maxQueueSize: 100.5,
    })).toBe(false);
  });
});
