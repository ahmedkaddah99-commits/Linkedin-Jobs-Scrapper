import { useCallback, useState } from "react";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "./useApiResource";

const COLUMN_ORDER = ["applied", "email_confirmed", "interview_invited", "rejected"];

function groupByStatus(items) {
  const groups = Object.fromEntries(COLUMN_ORDER.map((key) => [key, []]));
  for (const item of items) {
    const column = COLUMN_ORDER.includes(item.tracker_status) ? item.tracker_status : "applied";
    groups[column].push(item);
  }
  return groups;
}

export function useTracker() {
  const { request } = useSession();
  const [updating, setUpdating] = useState("");
  const [integrationBusy, setIntegrationBusy] = useState("");
  const [lastSyncResult, setLastSyncResult] = useState(null);

  const loader = useCallback(
    () =>
      Promise.all([request("/tracker"), request("/tracker/email-integration")]).then(
        ([tracker, integration]) => ({ tracker, integration }),
      ),
    [request],
  );

  const { data, loading, error, refresh, setData } = useApiResource(loader, [loader]);

  const items = data?.tracker?.items || [];
  const columns = groupByStatus(items);
  const emailIntegration = data?.integration || { providers: [], config: null };

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

  async function syncEmailIntegration() {
    setIntegrationBusy("sync");
    try {
      const result = await request("/tracker/email-integration/sync", {
        method: "POST",
        body: {},
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
    COLUMN_ORDER,
    emailIntegration,
    integrationBusy,
    lastSyncResult,
    refreshEmailIntegration,
    startGoogleEmailIntegration,
    updateEmailIntegrationSettings,
    syncEmailIntegration,
    deleteEmailIntegration,
  };
}
