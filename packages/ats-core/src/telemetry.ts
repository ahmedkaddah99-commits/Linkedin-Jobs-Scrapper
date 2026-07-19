/**
 * AA-15: Bounded adapter-health telemetry reporter.
 *
 * Records **only** aggregate lifecycle outcomes — never answers, PII, document
 * content, URLs, tokens, credentials, filenames, or raw DOM/page markup.
 *
 * Each adapter method calls `report()` at the end of its lifecycle stage with
 * the aggregate outcome. The reporter batches events and sends them through a
 * configurable transport. Remote configuration controls **only** batching and
 * sampling — never adapter algorithms, protections, or code execution.
 */

import type {
  AdapterHealthTelemetry,
  AggregateOutcome,
  ErrorCategory,
  LifecycleStage,
  RemoteTelemetryConfig,
} from "@runr/extension-messages";

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface TelemetryTransport {
  send(event: AdapterHealthTelemetry): void;
}

export interface TelemetryReporter {
  report(
    adapterId: "greenhouse" | "lever",
    adapterVersion: string,
    lifecycleStage: LifecycleStage,
    outcome: AggregateOutcome,
    error: ErrorCategory,
  ): void;

  /** Update remote config at runtime — only sampling/batch fields are accepted. */
  applyRemoteConfig(config: RemoteTelemetryConfig): void;

  flush(): void;
}

// ---------------------------------------------------------------------------
// Default reporter
// ---------------------------------------------------------------------------

export function createTelemetryReporter(transport: TelemetryTransport): TelemetryReporter {
  let config: RemoteTelemetryConfig = {
    schemaVersion: 1,
    batchIntervalSeconds: 30,
    sampleRate: 1,
    maxQueueSize: 100,
  };

  let queue: AdapterHealthTelemetry[] = [];
  let timer: ReturnType<typeof setTimeout> | null = null;

  const scheduleFlush = () => {
    if (timer !== null) return;
    timer = setTimeout(() => {
      timer = null;
      if (queue.length === 0) return;
      const batch = queue;
      queue = [];
      // Apply sampling
      for (const event of batch) {
        if (Math.random() < config.sampleRate) {
          transport.send(event);
        }
      }
    }, config.batchIntervalSeconds * 1000);
  };

  const reporter: TelemetryReporter = {
    report(
      adapterId: "greenhouse" | "lever",
      adapterVersion: string,
      lifecycleStage: LifecycleStage,
      outcome: AggregateOutcome,
      error: ErrorCategory,
    ): void {
      const event: AdapterHealthTelemetry = {
        schemaVersion: 1,
        adapter: adapterId,
        adapterVersion,
        lifecycleStage,
        aggregateOutcome: outcome,
        errorCategory: error,
      };

      queue.push(event);

      // Enforce max queue size
      if (queue.length >= config.maxQueueSize) {
        const batch = queue;
        queue = [];
        for (const ev of batch) {
          if (Math.random() < config.sampleRate) {
            transport.send(ev);
          }
        }
        return;
      }

      scheduleFlush();
    },

    applyRemoteConfig(newConfig: RemoteTelemetryConfig): void {
      // Only data-only fields are applied. No algorithm, protection, or
      // execution-affecting keys exist on RemoteTelemetryConfig.
      config = { ...newConfig };

      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
      if (queue.length > 0) {
        scheduleFlush();
      }
    },

    flush(): void {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
      if (queue.length === 0) return;
      const batch = queue;
      queue = [];
      for (const ev of batch) {
        if (Math.random() < config.sampleRate) {
          transport.send(ev);
        }
      }
    },
  };

  return reporter;
}

// ---------------------------------------------------------------------------
// Outcome mapping helpers
// ---------------------------------------------------------------------------

/**
 * Map a FieldExecutionStatus to an aggregate outcome.
 * "filled" / "already_filled" → success
 * "rejected" / "mismatch"    → failure
 * "preserved_existing" / "skipped_hidden" / "skipped_disabled" → skipped
 */
export function executionStatusToOutcome(
  status: string,
): AggregateOutcome {
  if (status === "filled" || status === "already_filled") return "success";
  if (status === "rejected" || status === "mismatch") return "failure";
  if (
    status === "preserved_existing" ||
    status === "skipped_hidden" ||
    status === "skipped_disabled"
  ) {
    return "skipped";
  }
  return "failure";
}

/**
 * Map a FieldExecutionStatus to a bounded error category.
 */
export function executionStatusToErrorCategory(
  status: string,
): ErrorCategory {
  if (status === "filled" || status === "already_filled") return "none";
  if (status === "rejected") return "fill_rejected";
  if (status === "mismatch") return "fill_mismatched";
  if (status === "skipped_hidden" || status === "skipped_disabled") return "control_blocked";
  if (status === "preserved_existing") return "existing_value";
  return "unknown";
}

/**
 * Map a DocumentUploadResult status to an aggregate outcome.
 */
export function uploadStatusToOutcome(status: string): AggregateOutcome {
  if (status === "uploaded") return "success";
  if (status === "rejected" || status === "mismatch") return "failure";
  if (status === "preserved_existing" || status === "unsupported") return "skipped";
  return "failure";
}

/**
 * Map a DocumentUploadResult status to a bounded error category.
 */
export function uploadStatusToErrorCategory(status: string): ErrorCategory {
  if (status === "uploaded") return "none";
  if (status === "rejected") return "portal_rejected";
  if (status === "mismatch") return "fill_mismatched";
  if (status === "preserved_existing") return "existing_value";
  if (status === "unsupported") return "unsupported_role";
  return "unknown";
}

