import { useCallback, useState } from "react";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "./useApiResource";

const COLUMN_ORDER = ["applied", "email_confirmed", "interview_invited", "rejected"];

function groupByStatus(items) {
  const groups = Object.fromEntries(COLUMN_ORDER.map((k) => [k, []]));
  for (const item of items) {
    const col = COLUMN_ORDER.includes(item.tracker_status)
      ? item.tracker_status
      : "applied";
    groups[col].push(item);
  }
  return groups;
}

export function useTracker() {
  const { request } = useSession();
  const [updating, setUpdating] = useState("");

  const loader = useCallback(() => request("/tracker"), [request]);
  const { data, loading, error, refresh, setData } = useApiResource(loader, [loader]);

  const items = data?.items || [];
  const columns = groupByStatus(items);

  async function updateCard(reviewId, fields) {
    setUpdating(reviewId);
    try {
      const result = await request(`/tracker/${reviewId}`, {
        method: "PUT",
        body: fields,
      });
      // Optimistically update local state so the UI moves the card instantly
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          items: prev.items.map((item) =>
            item.review_id === reviewId ? { ...item, ...fields, ...result } : item,
          ),
        };
      });
      return result;
    } finally {
      setUpdating("");
    }
  }

  return { columns, items, loading, error, refresh, updating, updateCard, COLUMN_ORDER };
}
