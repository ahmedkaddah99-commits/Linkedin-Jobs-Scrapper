import { useCallback, useState } from "react";
import { useSession } from "../context/SessionContext";
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

  const loader = useCallback(async () => {
    const [tracker, integration] = await Promise.all([
      request("/tracker"),
      request("/tracker/email-integration"),
    ]);
    if (!integration?.config?.connected) {
      return { tracker, integration };
    }
    try {
      const sync = await request("/tracker/email-integration/sync", {
        method: "POST",
        body: {},
      });
      const refreshedTracker = await request("/tracker");
      setLastSyncResult(sync.result || null);
      return {
        tracker: refreshedTracker,
        integration: sync.integration || integration,
      };
    } catch {
      const refreshedIntegration = await request("/tracker/email-integration").catch(() => integration);
      return { tracker, integration: refreshedIntegration };
    }
  }, [request]);

  const { data, loading, error, refresh, setData } = useApiResource(loader, [loader]);

  const items = data?.tracker?.items || [];
  const columns = groupByStatus(items);
  const emailIntegration = data?.integration || { providers: [], config: null };

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
    setData((prev) => ({ ...(prev || {}), integration }));
    return integration;
  }

  async function updateCard(reviewId, fields) {
    setUpdating(reviewId);
    try {
      const result = await request(`/tracker/${reviewId}`, {
        method: "PUT",
        body: fields,
      });
      setData((prev) => {
        const tracker = prev?.tracker || { items: [] };
        return {
          ...(prev || {}),
          tracker: {
            ...tracker,
            items: (tracker.items || []).map((item) =>
              item.review_id === reviewId ? { ...item, ...fields, ...result } : item,
            ),
          },
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
      setData((prev) => {
        const tracker = prev?.tracker || { items: [] };
        return {
          ...(prev || {}),
          tracker: {
            ...tracker,
            items: (tracker.items || []).filter((entry) => entry.review_id !== reviewId),
          },
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
      setData((prev) => ({ ...(prev || {}), integration: result.integration }));
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
      setData((prev) => ({ ...(prev || {}), integration: result }));
      return result;
    } finally {
      setIntegrationBusy("");
    }
  }

  async function syncEmailIntegration(fields = {}) {
    setIntegrationBusy("sync");
    try {
      const result = await request("/tracker/email-integration/sync", {
        method: "POST",
        body: fields,
      });
      const tracker = await request("/tracker");
      setLastSyncResult(result.result || null);
      setData((prev) => ({
        ...(prev || {}),
        tracker,
        integration: result.integration,
      }));
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
      setData((prev) => ({
        ...(prev || {}),
        tracker: result.tracker,
        integration: result.integration,
      }));
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
      setData((prev) => ({
        ...(prev || {}),
        integration: result.integration,
      }));
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
      setData((prev) => ({
        ...(prev || {}),
        integration: result.integration,
      }));
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
