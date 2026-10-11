// Kept identical to the repository-confirmed extension protocol constants.
const ASSISTED_APPLY_PREPARATION_PROTOCOL = "runr.assisted_apply.preparation";
const ASSISTED_APPLY_PREPARATION_PROTOCOL_VERSION = 1;

export const ASSISTED_APPLY_PREPARATION_EXTENSION_ID =
  "najcdfohhfgbjpbokhmmekkahghfhegp";

const OPAQUE_ID = /^[A-Za-z0-9_-]{8,200}$/;

export function isAssistedApplyPreparationEnabled(env = import.meta.env || {}) {
  return String(env.VITE_ENABLE_ASSISTED_APPLY_PREPARATION || "").trim().toLowerCase() === "true";
}

function requireOpaque(value, label) {
  const normalized = String(value || "").trim();
  if (!OPAQUE_ID.test(normalized)) throw new Error(`${label} is invalid.`);
  return normalized;
}

function runtimeError(runtime) {
  return runtime?.lastError?.message || "Runr Assisted Apply did not respond.";
}

function commandEnvelope({ type, preparationId, packageId, ats, retryOf }) {
  const envelope = {
    protocol: ASSISTED_APPLY_PREPARATION_PROTOCOL,
    protocolVersion: ASSISTED_APPLY_PREPARATION_PROTOCOL_VERSION,
    type,
    source: "web",
    messageId: `web-${type}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    preparationId: requireOpaque(preparationId, "Preparation identity"),
    packageId: requireOpaque(packageId, "Package identity"),
    emittedAt: new Date().toISOString(),
  };
  if (type === "start") {
    return {
      ...envelope,
      capabilities: {
        adapters: [ats === "lever" ? "lever" : "greenhouse"],
        capabilities: ["fill", "document_attachment", "reconciliation"],
      },
    };
  }
  if (type === "review_activate") return { ...envelope, reviewId: envelope.preparationId };
  if (type === "retry") return { ...envelope, retryOf: requireOpaque(retryOf || preparationId, "Retry identity") };
  return type === "cancel" ? { ...envelope, reason: "user_requested" } : envelope;
}

export function sendAssistedApplyPreparationCommand({
  type,
  preparationId,
  packageId,
  ats,
  retryOf,
  runtime = globalThis.chrome?.runtime,
}) {
  if (!runtime || typeof runtime.sendMessage !== "function") {
    return Promise.reject(new Error("Install and connect the Runr browser extension before starting preparation."));
  }
  let message;
  try {
    message = commandEnvelope({ type, preparationId, packageId, ats, retryOf });
  } catch (error) {
    return Promise.reject(error);
  }
  return new Promise((resolve, reject) => {
    try {
      runtime.sendMessage(ASSISTED_APPLY_PREPARATION_EXTENSION_ID, message, (response) => {
        if (runtime.lastError) {
          reject(new Error(runtimeError(runtime)));
          return;
        }
        if (!response || response.ok !== true) {
          const error = new Error(response?.error || "Runr could not start Assisted Apply preparation.");
          error.status = response?.status || "";
          reject(error);
          return;
        }
        resolve(response);
      });
    } catch (error) {
      reject(error instanceof Error ? error : new Error("Runr could not contact the browser extension."));
    }
  });
}

export function normalizePreparationStatus(payload = {}) {
  const state = String(payload.state || "").trim();
  return {
    ...payload,
    state: ["created", "permission_required", "preparing", "needs_attention", "ready_for_review", "active", "cancelled", "expired"].includes(state)
      ? state : "needs_attention",
    total_count: Number.isInteger(payload.total_count) ? Math.max(0, payload.total_count) : 0,
    completed_count: Number.isInteger(payload.completed_count) ? Math.max(0, payload.completed_count) : 0,
  };
}

export function preparationUiModel(preparation, extensionStatus = "") {
  if (!preparation) return null;
  const normalized = normalizePreparationStatus(preparation);
  return {
    state: normalized.state,
    filled: normalized.completed_count,
    unresolved: Math.max(0, normalized.total_count - normalized.completed_count),
    permissionRequired: extensionStatus === "permission_required" || normalized.state === "permission_required",
    expired: normalized.error_category === "expired" || normalized.state === "expired",
    canReview: normalized.state === "ready_for_review",
    canRetry: ["permission_required", "needs_attention", "expired"].includes(normalized.state),
    canCancel: ["created", "permission_required", "preparing", "needs_attention", "ready_for_review"].includes(normalized.state),
  };
}
