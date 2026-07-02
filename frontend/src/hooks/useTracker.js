import { useCallback, useState } from "react";
import { useSession } from "../context/SessionContext";
import {
  TRACKER_INTEGRATION_REQUEST_TIMEOUT_MS,
  TRACKER_REQUEST_TIMEOUT_MS,
} from "../lib/trackerLoading";
import { useApiResource } from "./useApiResource";

const COLUMN_ORDER = ["not_applied", "applied", "interview_invited", "rejected", "offer", "withdrawn", "unknown"];

function groupByStatus(items) {
  const groups = Object.fromEntries(COLUMN_ORDER.map((key) => [key, []]));
  for (const item of items) {
    const trackerStatus = item.tracker_status === "email_confirmed" ? "applied" : item.tracker_status;
    const column = COLUMN_ORDER.includes(trackerStatus) ? trackerStatus : "unknown";
    groups[column].push(item);
  }
  return groups;
}

function detectionKey(detection) {
  return detection?.detection_id || detection?.source_email?.message_id || "";
}

export function useTracker() {
  const { request } = useSession();
  const [updating, setUpdating] = useState("");
  const [integrationBusy, setIntegrationBusy] = useState("");
  const [lastSyncResult, setLastSyncResult] = useState(null);

  const {
    data: tracker,
    loading: trackerLoading,
    error: trackerError,
    refresh: refreshTracker,
    setData: setTrackerData,
  } = useApiResource(() => request("/tracker", { timeoutMs: TRACKER_REQUEST_TIMEOUT_MS }), [request], {
    cacheKey: "tracker:items",
    staleMs: 15000,
    backgroundRefresh: true,
  });
  const {
    data: integration,
    loading: integrationLoading,
    error: integrationError,
    refresh: refreshIntegration,
    setData: setIntegrationData,
  } = useApiResource(() => request("/tracker/email-integration", { timeoutMs: TRACKER_INTEGRATION_REQUEST_TIMEOUT_MS }), [request], {
    cacheKey: "tracker:email-integration",
    staleMs: 300000,
    backgroundRefresh: true,
  });
  const refresh = useCallback(async (options) => {
    const [nextTracker, nextIntegration] = await Promise.all([
      refreshTracker(options),
      refreshIntegration(options),
    ]);
    return { tracker: nextTracker, integration: nextIntegration };
  }, [refreshIntegration, refreshTracker]);

  const items = tracker?.items || [];
  const columns = groupByStatus(items);
  const emailIntegration = integration || { providers: [], config: null };
  const loading = trackerLoading || (!tracker && integrationLoading);
  const error = trackerError || (!tracker ? integrationError : "");

  function removeDetectionsFromLastSyncResult(detections) {
    const resolvedIds = new Set((detections || []).map(detectionKey).filter(Boolean));
    if (!resolvedIds.size) {
      return;
    }
    setLastSyncResult((prev) => {
      if (!prev) {
        return prev;
      }
      return {
        ...prev,
        detections: (prev.detections || []).filter((detection) => !resolvedIds.has(detectionKey(detection))),
      };
    });
  }

  async function refreshEmailIntegration() {
    const integration = await request("/tracker/email-integration");
    setIntegrationData(integration);
    return integration;
  }

  async function updateCard(reviewId, fields) {
    setUpdating(reviewId);
    try {
      const result = await request(`/tracker/${reviewId}`, {
        method: "PUT",
        body: fields,
      });
      setTrackerData((prev) => {
        const currentTracker = prev || { items: [] };
        return {
          ...currentTracker,
          items: (currentTracker.items || []).map((item) =>
            item.review_id === reviewId ? { ...item, ...fields, ...result } : item,
          ),
        };
      });
      return result;
    } finally {
      setUpdating("");
    }
  }

  async function deleteCard(item) {
    const reviewId = String(item?.review_id || "").trim();
    if (!reviewId) {
      throw new Error("review_id is required");
    }
    setUpdating(reviewId);
    try {
      const result = await request(`/tracker/${reviewId}`, {
        method: "DELETE",
      });
      setTrackerData((prev) => {
        const currentTracker = prev || { items: [] };
        return {
          ...currentTracker,
          items: (currentTracker.items || []).filter((entry) => entry.review_id !== reviewId),
        };
      });
      return result;
    } finally {
      setUpdating("");
    }
  }

  async function bulkDeleteCards(itemsToDelete) {
    const reviewIds = Array.from(
      new Set(
        (itemsToDelete || [])
          .map((item) => String(item?.review_id || item || "").trim())
          .filter(Boolean),
      ),
    );
    if (!reviewIds.length) {
      throw new Error("Select at least one tracker job to delete.");
    }
    setUpdating("bulk-delete");
    try {
      const result = await request("/tracker/bulk", {
        method: "DELETE",
        body: { review_ids: reviewIds },
      });
      const deletedIds = new Set((result.deleted || []).map((entry) => String(entry.review_id || "").trim()));
      setTrackerData((prev) => {
        const currentTracker = prev || { items: [] };
        return {
          ...currentTracker,
          items: (currentTracker.items || []).filter((entry) => !deletedIds.has(String(entry.review_id || "").trim())),
        };
      });
      return result;
    } finally {
      setUpdating("");
    }
  }

  async function startGoogleEmailIntegration(fields) {
    setIntegrationBusy("authorize");
    try {
      const result = await request("/tracker/email-integration/google/start", {
        method: "POST",
        body: fields,
      });
      setIntegrationData(result.integration);
      return result;
    } finally {
      setIntegrationBusy("");
    }
  }

  async function updateEmailIntegrationSettings(fields) {
    setIntegrationBusy("save");
    try {
      const result = await request("/tracker/email-integration", {
        method: "PUT",
        body: fields,
      });
      setIntegrationData(result);
      return result;
    } finally {
      setIntegrationBusy("");
    }
  }

  async function syncEmailIntegration() {
    setIntegrationBusy("sync");
    try {
      const result = await request("/tracker/email-integration/sync", {
        method: "POST",
        body: { trigger: "manual" },
      });
      const tracker = await request("/tracker", { timeoutMs: TRACKER_REQUEST_TIMEOUT_MS });
      setLastSyncResult(result.result || null);
      setTrackerData(tracker);
      setIntegrationData(result.integration);
      return result;
    } finally {
      setIntegrationBusy("");
    }
  }

  async function approveEmailDetections(detections) {
    setIntegrationBusy("approve-detections");
    try {
      const result = await request("/tracker/email-integration/detections/approve", {
        method: "POST",
        body: { detections },
      });
      removeDetectionsFromLastSyncResult(detections);
      setTrackerData(result.tracker);
      setIntegrationData(result.integration);
      return result;
    } finally {
      setIntegrationBusy("");
    }
  }

  async function dismissEmailDetections(detections) {
    setIntegrationBusy("dismiss-detections");
    try {
      const result = await request("/tracker/email-integration/detections/dismiss", {
        method: "POST",
        body: { detections },
      });
      removeDetectionsFromLastSyncResult(detections);
      setIntegrationData(result.integration);
      return result;
    } finally {
      setIntegrationBusy("");
    }
  }

  async function deleteEmailIntegration() {
    setIntegrationBusy("delete");
    try {
      const result = await request("/tracker/email-integration", {
        method: "DELETE",
      });
      setLastSyncResult(null);
      setIntegrationData(result.integration);
      return result;
    } finally {
      setIntegrationBusy("");
    }
  }

  return {
    columns,
    items,
    loading,
    error,
    refresh,
    updating,
    updateCard,
    deleteCard,
    bulkDeleteCards,
    COLUMN_ORDER,
    emailIntegration,
    integrationBusy,
    lastSyncResult,
    refreshEmailIntegration,
    startGoogleEmailIntegration,
    updateEmailIntegrationSettings,
    syncEmailIntegration,
    approveEmailDetections,
    dismissEmailDetections,
    deleteEmailIntegration,
  };
}
